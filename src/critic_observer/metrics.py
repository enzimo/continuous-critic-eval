"""Deterministic measurements. Agreement, correctness, and outcomes stay separate.

Reviewer-accepted measures come from the review team's own decisions and are
provisional. Validated measures come only from the operator's independent
judgments. Both are reported side by side and never substituted for each other.
"""

from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations
from math import ceil
from statistics import mean, median

from .specialties import specialty_of

METRIC_VERSION = "1.3"
SEVERITIES = ("blocking", "should_fix", "consider")
# Ordered by priority: an issue is "supported" if any reporting claim was kept.
REVIEWER_STATES = ("supported", "withdrawn", "unresolved", "undecided")
# What the reviewer did with a challenged claim version.
CHALLENGE_RESPONSES = ("withdrawn", "revised", "kept", "pending")
CHANGED_REVIEW = {"withdrawn", "revised"}
GROUPINGS = ("specialty", "specialty_model", "role", "role_model")
QUEUE_LIMIT = 200


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def seconds(start, finish):
    if not finish:
        return None
    return (datetime.fromisoformat(finish) - datetime.fromisoformat(start)).total_seconds()


def most_severe(values):
    return min(values, key=SEVERITIES.index) if values else None


def normalized(value):
    """Group labels ignore case and repeated whitespace, not wording."""
    return " ".join(str(value).split())


def rollup_usage(invocations):
    by_basis = defaultdict(float)
    token_count, input_tokens, output_tokens, measured_cost = 0, 0, 0, 0
    for inv in invocations:
        usage = inv.get("usage") or {}
        if usage.get("cost_usd") is not None:
            measured_cost += 1
            by_basis[usage["cost_basis"]] += usage["cost_usd"]
        if usage.get("input_tokens") is not None and usage.get("output_tokens") is not None:
            token_count += 1
            input_tokens += usage["input_tokens"]
            output_tokens += usage["output_tokens"]
    complete = bool(invocations) and measured_cost == len(invocations) and len(by_basis) == 1
    return {
        "invocations": len(invocations),
        "cost_measured": measured_cost,
        "cost_coverage": ratio(measured_cost, len(invocations)),
        "cost_by_basis": dict(by_basis),
        "complete_cost_usd": sum(by_basis.values()) if complete else None,
        "complete_cost_basis": next(iter(by_basis)) if complete else None,
        "tokens_measured": token_count,
        "input_tokens": input_tokens if token_count else None,
        "output_tokens": output_tokens if token_count else None,
    }


def index_snapshot(snapshot):
    invocations = {(i["run_id"], i["id"]): i for i in snapshot["invocations"]}
    latest = {}
    for finding in snapshot["findings"]:
        key = (finding["run_id"], finding["id"])
        if key not in latest or latest[key]["version"] < finding["version"]:
            latest[key] = finding
    issues = defaultdict(list)
    for finding in latest.values():
        issues[(finding["run_id"], finding["issue_id"])].append(finding)
    judgments = {(j["run_id"], j["issue_id"]): j for j in snapshot["judgments"]}
    return invocations, latest, issues, judgments


def without_invalidated(snapshot):
    """Invalidated runs keep their invocations (usage, failures) but no claims."""
    invalidated = {r["id"] for r in snapshot["runs"] if r["status"] == "invalidated"}
    filtered = {
        key: [row for row in values if row["run_id"] not in invalidated]
        if key not in {"runs", "invocations"}
        else values
        for key, values in snapshot.items()
    }
    return invalidated, filtered


def decision_index(snapshot):
    return {
        (d["run_id"], d["finding_id"], d["finding_version"]): d["state"]
        for d in snapshot["decisions"]
    }


def reviewer_state(claims, decisions):
    """The review team's decision on the latest version of these claims."""
    states = {decisions.get((f["run_id"], f["id"], f["version"])) for f in claims}
    return next((s for s in REVIEWER_STATES[:3] if s in states), "undecided")


def validity_of(judgments, issue):
    return judgments.get(issue, {}).get("validity")


def calculate(snapshot, critics):
    invalidated, snapshot = without_invalidated(snapshot)
    invs, latest, issues, judgments = index_snapshot(snapshot)
    outcomes = {(o["run_id"], o["issue_id"]): o for o in snapshot["outcomes"]}
    decisions = decision_index(snapshot)

    def outcome_counts(issue_keys):
        return dict(Counter(outcomes[key]["state"] for key in issue_keys if key in outcomes))

    configs = {c["id"]: c for c in critics}
    original_claims = {}
    for finding in sorted(snapshot["findings"], key=lambda f: f["version"]):
        original_claims.setdefault((finding["run_id"], finding["id"]), finding)

    def origin(finding):
        original = original_claims[(finding["run_id"], finding["id"])]
        return invs[(original["run_id"], original["invocation_id"])]

    discoveries = defaultdict(set)
    reporting = defaultdict(set)
    comparison_participants = defaultdict(set)
    for inv in invs.values():
        if (
            inv["phase"] == "independent"
            and inv["context"] == "independent"
            and inv["status"] == "completed"
            and inv["run_id"] not in invalidated
        ):
            comparison_participants[inv["run_id"]].add(inv["critic_id"])
    for key, findings in issues.items():
        for finding in findings:
            inv = origin(finding)
            reporting[key].add(inv["critic_id"])
            # Completion belongs to the original pass, never a same-critic retry.
            if (
                inv["phase"] == "independent"
                and inv["context"] == "independent"
                and inv["status"] == "completed"
            ):
                discoveries[key].add(inv["critic_id"])
    issue_reviewer = {key: reviewer_state(claims, decisions) for key, claims in issues.items()}

    def challenge_response(verdict):
        """A challenge changed the review when its claim version was withdrawn or revised."""
        current = latest.get((verdict["run_id"], verdict["finding_id"]))
        if current and current["version"] > verdict["finding_version"]:
            return "revised"
        state = decisions.get(
            (verdict["run_id"], verdict["finding_id"], verdict["finding_version"])
        )
        return {"withdrawn": "withdrawn", "supported": "kept"}.get(state, "pending")

    verdict_by_id = {v["event_id"]: v for v in snapshot["verdicts"]}

    def contribution(members):
        """Measurements for one critic definition or a group of definitions.

        Groups use set unions: an issue raised by two members counts once, and a
        unique discovery means no critic outside the group found it independently.
        """
        own = [i for i in invs.values() if i["critic_id"] in members]
        usable_runs = {i["run_id"] for i in own} - invalidated

        def mine(finding):
            return origin(finding)["critic_id"] in members

        def unique(issue):
            return (
                bool(discoveries[issue] & members & comparison_participants[issue[0]])
                and reporting[issue] <= members
                and bool(comparison_participants[issue[0]] - members)
                and bool(comparison_participants[issue[0]] & members)
            )

        compared_runs = {
            i["run_id"]
            for i in invs.values()
            if i["critic_id"] not in members and i["status"] == "completed"
        }
        completed_own_runs = {i["run_id"] for i in own if i["status"] == "completed"}
        reported_comparisons = usable_runs & completed_own_runs & compared_runs
        exclusive = {
            issue
            for issue in issues
            if reporting[issue] and reporting[issue] <= members and issue[0] in reported_comparisons
        }

        claimed = {issue for issue, findings in issues.items() if any(mine(f) for f in findings)}
        own_claims = {issue: [f for f in issues[issue] if mine(f)] for issue in claimed}
        valid = {issue for issue in claimed if validity_of(judgments, issue) == "valid"}
        invalid = {issue for issue in claimed if validity_of(judgments, issue) == "invalid"}
        reviewer = {issue: reviewer_state(own_claims[issue], decisions) for issue in claimed}
        supported = {issue for issue, state in reviewer.items() if state == "supported"}
        votes = [
            v
            for v in snapshot["verdicts"]
            if invs[(v["run_id"], v["invocation_id"])]["critic_id"] in members
        ]
        challenged = [v for v in votes if v["verdict"] != "AGREE"]
        responses = Counter(challenge_response(v) for v in challenged)
        judged_challenges = [
            j
            for j in snapshot["challenge_judgments"]
            if j["verdict_event_id"] in {v["event_id"] for v in challenged}
        ]
        upheld = sum(j["result"] == "upheld" for j in judged_challenges)
        decided = sum(j["result"] != "unknown" for j in judged_challenges)
        confidence = {}
        for label in ("verified", "likely", "possible"):
            group = {
                issue
                for issue in claimed
                if any(
                    original_claims[(f["run_id"], f["id"])]["confidence"] == label
                    for f in own_claims[issue]
                )
            }
            yes = sum(validity_of(judgments, i) == "valid" for i in group)
            no = sum(validity_of(judgments, i) == "invalid" for i in group)
            confidence[label] = {
                "proposed": len(group),
                "valid": yes,
                "invalid": no,
                "validity_rate": ratio(yes, yes + no),
            }
        usage = rollup_usage(own)
        durations = [
            duration
            for i in own
            if (duration := seconds(i["started_at"], i["finished_at"])) is not None
        ]
        kept = len(supported)
        dropped = sum(state == "withdrawn" for state in reviewer.values())
        return {
            "run_count": len({i["run_id"] for i in own}),
            "run_ids": sorted({i["run_id"] for i in own}),
            "invocations": len(own),
            "responsibilities": sorted(
                {
                    {
                        "lead": "Coordinator",
                        "independent": "Independent reviewer",
                        "critique": "Challenger",
                    }[i["phase"]]
                    for i in own
                }
            ),
            "failed_invocations": sum(i["status"] == "failed" for i in own),
            "completed_invocations": sum(i["status"] == "completed" for i in own),
            "raw_findings": sum(mine(f) for f in latest.values()),
            "distinct_issues": len(claimed),
            "issues_per_review": ratio(len(claimed), len(usable_runs)),
            # Provisional: the review team's own decisions, not independent truth.
            "reviewer_supported_issues": kept,
            "reviewer_withdrawn_issues": dropped,
            "reviewer_decisions": {
                s: sum(v == s for v in reviewer.values()) for s in REVIEWER_STATES
            },
            "reviewer_keep_rate": ratio(kept, kept + dropped),
            "unique_supported_discoveries": sum(unique(i) for i in supported),
            "exclusive_issues": len(claimed & exclusive),
            "exclusive_supported_issues": len(supported & exclusive),
            "exclusive_valid_issues": len(valid & exclusive),
            "report_comparison_reviews": len(reported_comparisons),
            "exclusive_kept_per_review": ratio(
                len(supported & exclusive), len(reported_comparisons)
            ),
            "unique_discoveries": sum(unique(i) for i in claimed),
            "comparison_reviews": sum(
                bool(ids & members) and bool(ids - members)
                for ids in comparison_participants.values()
            ),
            "unique_issue_refs": [
                {
                    "run_id": i[0],
                    "issue_id": i[1],
                    "title": issues[i][0]["title"],
                    "reviewer_state": issue_reviewer[i],
                    "validity": judgments.get(i, {}).get("validity", "unknown"),
                    "independent_comparison": unique(i),
                }
                for i in sorted(claimed & exclusive)
            ],
            "supported_severity": dict(
                Counter(most_severe([f["severity"] for f in own_claims[i]]) for i in supported)
            ),
            "challenge_responses": {r: responses[r] for r in CHALLENGE_RESPONSES},
            "challenges_changed_review": sum(responses[r] for r in CHANGED_REVIEW),
            "median_pass_seconds": median(durations) if durations else None,
            # Independently validated: operator judgments only.
            "valid_issues": len(valid),
            "invalid_issues": len(invalid),
            "unjudged_issues": len(claimed - valid - invalid),
            "validity_rate": ratio(len(valid), len(valid) + len(invalid)),
            "judgment_coverage": ratio(len(valid) + len(invalid), len(claimed)),
            "unique_valid_discoveries": sum(unique(i) for i in valid),
            "independent_valid_discoveries": sum(bool(discoveries[i] & members) for i in valid),
            "severity": dict(Counter(judgments[i]["severity"] for i in valid)),
            "outcomes": outcome_counts(valid),
            "outcome_coverage": ratio(sum(i in outcomes for i in valid), len(valid)),
            "categories": dict(Counter(f["category"] for f in latest.values() if mine(f))),
            "verdicts": dict(Counter(v["verdict"] for v in votes)),
            "challenges": len(challenged),
            "upheld_challenges": upheld,
            "decided_challenges": decided,
            "challenge_success": ratio(upheld, decided),
            "challenge_effects": dict(
                Counter(j["effect"] for j in judged_challenges if j["result"] == "upheld")
            ),
            "confidence": confidence,
            "usage": usage,
            "cost_per_valid_issue": ratio(usage["complete_cost_usd"], len(valid))
            if usage["complete_cost_usd"] is not None
            else None,
        }

    # Oldest first, so a tie between role spellings uses the earliest definition's.
    active = sorted(
        {i["critic_id"] for i in invs.values()} & set(configs),
        key=lambda key: (configs[key]["created_at"], key),
    )
    per_critic = [
        {
            "critic_id": key,
            "name": configs[key]["name"],
            "role": configs[key]["role"],
            "specialty": specialty_of(configs[key]),
            "provider": configs[key]["provider"],
            "model": configs[key]["model"],
            **contribution({key}),
        }
        for key in active
    ]

    def grouped(kind):
        """Group reusable specialties or legacy roles, optionally split by model."""
        members, roles, models = defaultdict(set), defaultdict(Counter), {}
        for key in active:
            if kind.startswith("specialty") and not any(
                i["critic_id"] == key and i["phase"] != "lead" for i in invs.values()
            ):
                continue
            role = (
                specialty_of(configs[key])
                if kind.startswith("specialty")
                else normalized(configs[key]["role"])
            )
            model = normalized(configs[key]["model"] or "")
            split_model = kind.endswith("_model")
            group = f"{role.casefold()}|{model.casefold()}" if split_model else role.casefold()
            members[group].add(key)
            roles[group][role] += 1
            models.setdefault(group, Counter())[model] += 1
        rows = []
        for group, keys in members.items():
            role = roles[group].most_common(1)[0][0]
            model = models[group].most_common(1)[0][0] or None if kind.endswith("_model") else None
            rows.append(
                {
                    "group_key": group,
                    "label": role
                    if not kind.endswith("_model")
                    else f"{role} · {model or 'model not recorded'}",
                    "role": role,
                    "model": model,
                    "critic_ids": sorted(keys),
                    **contribution(keys),
                }
            )
        return sorted(rows, key=lambda row: row["label"].casefold())

    # Compare shared finding versions in the same round. Count an underlying issue
    # once per pair/run, using the earliest comparable assessment, never silence.
    by_claim = defaultdict(list)
    finding_lookup = {(f["run_id"], f["id"], f["version"]): f for f in snapshot["findings"]}
    for verdict in snapshot["verdicts"]:
        inv = invs[(verdict["run_id"], verdict["invocation_id"])]
        by_claim[
            (
                verdict["run_id"],
                verdict["finding_id"],
                verdict["finding_version"],
                inv["round"],
                inv["context"],
            )
        ].append((inv["critic_id"], verdict))
    pair_cases = {}
    for claim, votes in sorted(by_claim.items(), key=lambda item: (item[0][3], item[0][2])):
        issue = finding_lookup[claim[:3]]["issue_id"]
        for left, right in combinations(votes, 2):
            if left[0] == right[0]:
                continue
            a, b = sorted((left[0], right[0]))
            case_key = (a, b, claim[0], issue)
            if case_key not in pair_cases:
                pair_cases[case_key] = (
                    (left[1]["verdict"] == "AGREE") != (right[1]["verdict"] == "AGREE"),
                    left[1]["verdict"],
                    right[1]["verdict"],
                )
    pairs = defaultdict(
        lambda: {"compared": 0, "conflicts": 0, "evidence_objections": 0, "concern_objections": 0}
    )
    for (a, b, _, _), (conflict, left, right) in pair_cases.items():
        p = pairs[(a, b)]
        p["compared"] += 1
        p["conflicts"] += conflict
        p["evidence_objections"] += "DISAGREE_EVIDENCE" in (left, right)
        p["concern_objections"] += "DISAGREE_CONCERN" in (left, right)
    independent_runs = defaultdict(set)
    for inv in invs.values():
        if (
            inv["phase"] == "independent"
            and inv["context"] == "independent"
            and inv["status"] == "completed"
            and inv["run_id"] not in invalidated
        ):
            independent_runs[inv["critic_id"]].add(inv["run_id"])
    # Discovery overlap exists without a debate. No verdicts means unknown
    # disagreement, not absence of a useful independence comparison.
    for a, b in combinations(sorted(independent_runs), 2):
        if independent_runs[a] & independent_runs[b]:
            _ = pairs[(a, b)]
    pair_results = []
    for (a, b), values in pairs.items():
        common_runs = independent_runs[a] & independent_runs[b]
        first = {i for i, found in discoveries.items() if a in found and i[0] in common_runs}
        second = {i for i, found in discoveries.items() if b in found and i[0] in common_runs}
        pair_results.append(
            {
                "left": a,
                "right": b,
                "left_name": configs[a]["name"],
                "right_name": configs[b]["name"],
                **values,
                "disagreement_rate": ratio(values["conflicts"], values["compared"]),
                "discovery_overlap": ratio(len(first & second), len(first | second)),
                "shared_discoveries": len(first & second),
                "combined_discoveries": len(first | second),
                "common_independent_runs": len(common_runs),
                "run_ids": sorted(
                    common_runs | {case[2] for case in pair_cases if case[:2] == (a, b)}
                ),
            }
        )
    round_results = []
    first_round = {}
    for issue, claims in issues.items():
        first_round[issue] = min(origin(f)["round"] for f in claims)
    for round_no in sorted({i["round"] for i in invs.values()}):
        own = [i for i in invs.values() if i["round"] == round_no]
        introduced = {issue for issue, number in first_round.items() if number == round_no}
        round_challenges = [
            v
            for v in snapshot["verdicts"]
            if v["verdict"] != "AGREE"
            and invs[(v["run_id"], v["invocation_id"])]["round"] == round_no
        ]
        round_results.append(
            {
                "round": round_no,
                "invocations": len(own),
                "new_issues": len(introduced),
                "reviewer_supported_new_issues": sum(
                    issue_reviewer[i] == "supported" for i in introduced
                ),
                "valid_new_issues": sum(validity_of(judgments, i) == "valid" for i in introduced),
                "challenges": len(round_challenges),
                "challenges_changed_review": sum(
                    challenge_response(v) in CHANGED_REVIEW for v in round_challenges
                ),
                "upheld_challenges": sum(
                    j["result"] == "upheld"
                    and invs[(j["run_id"], verdict_by_id[j["verdict_event_id"]]["invocation_id"])][
                        "round"
                    ]
                    == round_no
                    for j in snapshot["challenge_judgments"]
                ),
                "usage": rollup_usage(own),
            }
        )
    validity = Counter(validity_of(judgments, i) or "unknown" for i in issues)
    # How often the review team's keep/withdraw decision matched the operator's
    # later independent judgment. This calibrates the provisional measures.
    calibration = {state: {"valid": 0, "invalid": 0, "unjudged": 0} for state in REVIEWER_STATES}
    for issue, state in issue_reviewer.items():
        outcome = validity_of(judgments, issue)
        calibration[state][outcome if outcome in {"valid", "invalid"} else "unjudged"] += 1
    matched = calibration["supported"]["valid"] + calibration["withdrawn"]["invalid"]
    compared = sum(
        calibration[s][v] for s in ("supported", "withdrawn") for v in ("valid", "invalid")
    )
    elapsed = sorted(
        v for r in snapshot["runs"] if (v := seconds(r["started_at"], r["finished_at"])) is not None
    )
    missing = []
    for run in snapshot["runs"]:
        completed = {
            i["critic_id"]
            for i in invs.values()
            if i["run_id"] == run["id"] and i["status"] == "completed"
        }
        absent = set(run["expected_critic_ids"]) - completed
        if absent:
            missing.append({"run_id": run["id"], "critic_ids": sorted(absent)})
    run_summaries = {}
    for run in snapshot["runs"]:
        own_issues = [key for key in issues if key[0] == run["id"]]
        run_summaries[run["id"]] = {
            "issues": len(own_issues),
            "reviewer_supported": sum(issue_reviewer[i] == "supported" for i in own_issues),
            "reviewer_withdrawn": sum(issue_reviewer[i] == "withdrawn" for i in own_issues),
            "judged": sum(validity_of(judgments, i) in {"valid", "invalid"} for i in own_issues),
            "valid": sum(validity_of(judgments, i) == "valid" for i in own_issues),
            "critics": len({i["critic_id"] for i in invs.values() if i["run_id"] == run["id"]}),
        }
    return {
        "metric_version": METRIC_VERSION,
        "overview": {
            "runs": len(snapshot["runs"]),
            "raw_findings": len(latest),
            "distinct_issues": len(issues),
            "reviewer_decisions": {
                s: sum(v == s for v in issue_reviewer.values()) for s in REVIEWER_STATES
            },
            "valid_issues": validity["valid"],
            "invalid_issues": validity["invalid"],
            "unjudged_issues": validity["unknown"],
            "outcomes": outcome_counts(i for i in issues if validity_of(judgments, i) == "valid"),
            "validity_rate": ratio(validity["valid"], validity["valid"] + validity["invalid"]),
            "judgment_coverage": ratio(validity["valid"] + validity["invalid"], len(issues)),
            "status": dict(Counter(r["status"] for r in snapshot["runs"])),
            "median_seconds": median(elapsed) if elapsed else None,
            "p95_seconds": elapsed[ceil(len(elapsed) * 0.95) - 1] if elapsed else None,
            "usage": rollup_usage(list(invs.values())),
        },
        "reviewer_calibration": {
            "by_decision": calibration,
            "matched": matched,
            "compared": compared,
            "agreement_rate": ratio(matched, compared),
        },
        "critics": per_critic,
        "groups": {kind: grouped(kind) for kind in GROUPINGS},
        "pairs": sorted(pair_results, key=lambda p: p["conflicts"], reverse=True),
        "rounds": round_results,
        "run_summaries": run_summaries,
        "data_health": {
            "invalidated_runs": len(invalidated),
            "missing_expected_critics": missing,
            "active_invocations": sum(i["status"] == "running" for i in invs.values()),
            "failed_invocations": sum(i["status"] == "failed" for i in invs.values()),
            "fully_evaluated_runs": sum(r["evaluation"] is not None for r in snapshot["runs"]),
            "unknown_model_invocations": sum(
                not (i.get("resolved_model") or i["model"]) for i in invs.values()
            ),
            "registered_runs_only": True,
        },
    }


def assessment_queue(snapshot, limit=QUEUE_LIMIT):
    """Issues in the cohort that still need an independent valid/invalid judgment.

    Most severe claims first, then the newest review. Each item carries enough
    context to open the judgment form; full evidence loads with the review.
    """
    _, snapshot = without_invalidated(snapshot)
    invs, _, issues, judgments = index_snapshot(snapshot)
    decisions = decision_index(snapshot)
    runs = {r["id"]: r for r in snapshot["runs"]}
    verdicts = defaultdict(Counter)
    for v in snapshot["verdicts"]:
        verdicts[(v["run_id"], v["finding_id"], v["finding_version"])][
            "agree" if v["verdict"] == "AGREE" else "disagree"
        ] += 1
    pending = []
    for (run_id, issue_id), claims in issues.items():
        judgment = validity_of(judgments, (run_id, issue_id))
        if judgment in {"valid", "invalid"}:
            continue
        severity = most_severe([f["severity"] for f in claims])
        lead = min(claims, key=lambda f: (SEVERITIES.index(f["severity"]), f["id"]))
        votes = sum((verdicts[(run_id, f["id"], f["version"])] for f in claims), Counter())
        run = runs[run_id]
        pending.append(
            {
                "run_id": run_id,
                "run_title": run["title"],
                "project": run["project"],
                "started_at": run["started_at"],
                "issue_id": issue_id,
                "title": lead.get("title"),
                "severity": severity,
                "category": lead["category"],
                "claims": len(claims),
                "critic_ids": sorted(
                    {invs[(run_id, f["origin_invocation_id"])]["critic_id"] for f in claims}
                ),
                "reviewer_state": reviewer_state(claims, decisions),
                "agree": votes["agree"],
                "disagree": votes["disagree"],
                "judgment": judgment,
            }
        )
    pending.sort(key=lambda item: item["issue_id"])
    pending.sort(key=lambda item: item["started_at"], reverse=True)
    pending.sort(key=lambda item: SEVERITIES.index(item["severity"]))
    return {"total": len(pending), "limit": limit, "items": pending[:limit]}


def compare_experiment(experiment, snapshot):
    invs, _, issues, judgments = index_snapshot(snapshot)
    rows = [r for r in snapshot["runs"] if r["experiment_id"] == experiment["id"]]
    variants = experiment["variants"]
    by_trial = defaultdict(dict)
    for run in rows:
        by_trial[(run["case_id"], run["trial"])][run["variant_id"]] = run
    matched = []
    for key, values in by_trial.items():
        if not all(v["id"] in values for v in variants):
            continue
        if all(
            values[v["id"]]["status"] == "completed"
            and values[v["id"]]["evaluation"]
            and not (
                set(values[v["id"]]["expected_critic_ids"])
                - {
                    i["critic_id"]
                    for i in invs.values()
                    if i["run_id"] == values[v["id"]]["id"] and i["status"] == "completed"
                }
            )
            for v in variants
        ):
            matched.append((key, values))
    cases = {c["id"]: c for c in experiment["cases"]}
    results = []
    paired = []
    for variant in variants:
        trials = []
        for (case_id, trial), values in matched:
            run = values[variant["id"]]
            own_issues = {i for i in issues if i[0] == run["id"]}
            own_judgments = [judgments[i] for i in own_issues]
            detected = {
                j["known_issue_id"]
                for j in own_judgments
                if j["validity"] == "valid" and j["known_issue_id"]
            }
            usage = rollup_usage([i for i in invs.values() if i["run_id"] == run["id"]])
            trials.append(
                {
                    "run_id": run["id"],
                    "case_id": case_id,
                    "trial": trial,
                    "valid_issues": sum(j["validity"] == "valid" for j in own_judgments),
                    "false_alarms": sum(j["validity"] == "invalid" for j in own_judgments),
                    "known_detected": len(detected),
                    "known_total": len(cases[case_id]["known_issues"]),
                    "cost_usd": usage["complete_cost_usd"],
                    "cost_basis": usage["complete_cost_basis"],
                }
            )
        known_total = sum(t["known_total"] for t in trials)
        known_detected = sum(t["known_detected"] for t in trials)
        complete_cost = bool(trials) and all(t["cost_usd"] is not None for t in trials)
        results.append(
            {
                "variant_id": variant["id"],
                "name": variant["name"],
                "registered": sum(r["variant_id"] == variant["id"] for r in rows),
                "failed": sum(
                    r["variant_id"] == variant["id"] and r["status"] == "failed" for r in rows
                ),
                "matched_trials": len(trials),
                "known_detected": known_detected,
                "known_total": known_total,
                "known_defect_recall": ratio(known_detected, known_total),
                "mean_valid_issues": mean(t["valid_issues"] for t in trials) if trials else None,
                "mean_false_alarms": mean(t["false_alarms"] for t in trials) if trials else None,
                "mean_cost_usd": mean(t["cost_usd"] for t in trials) if complete_cost else None,
                "cost_bases": sorted({t["cost_basis"] for t in trials if t["cost_basis"]}),
                "trials": trials,
            }
        )
    if results:
        baseline = results[0]
        for result in results[1:]:
            primary = experiment["primary_metric"]
            field = {
                "valid_issues": "mean_valid_issues",
                "false_alarms": "mean_false_alarms",
                "cost_usd": "mean_cost_usd",
                "known_defect_recall": "known_defect_recall",
            }[primary]
            a, b = baseline[field], result[field]
            compatible = primary != "cost_usd" or (
                len(baseline["cost_bases"]) == 1 and baseline["cost_bases"] == result["cost_bases"]
            )
            paired.append(
                {
                    "baseline": baseline["variant_id"],
                    "variant": result["variant_id"],
                    "metric": primary,
                    "difference": b - a if a is not None and b is not None and compatible else None,
                }
            )
    return {
        "experiment": experiment,
        "runs": rows,
        "matched_trials": len(matched),
        "unmatched_or_unevaluated_trials": len(by_trial) - len(matched),
        "variants": results,
        "comparisons": paired,
        "interpretation": "Matched, fully adjudicated case/trials only. "
        "Differences are descriptive; "
        "repeat trials and use held-out cases before changing the default team.",
    }
