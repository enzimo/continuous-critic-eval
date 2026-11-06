"""Reviewer-accepted contributions, critic groups, calibration, and the assessment queue."""

import asyncio
import json

from conftest import finding, finish_inv, invocation, judge, started, submit
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from critic_observer.metrics import METRIC_VERSION, assessment_queue, calculate
from critic_observer.models import Critic


def verdict(inv, finding_id, kind, version=1):
    return dict(
        type="verdict_recorded",
        invocation_id=inv,
        finding_id=finding_id,
        finding_version=version,
        verdict=kind,
        rationale=f"{kind} after checking the claim",
        evidence="contradicting trace" if kind == "DISAGREE_EVIDENCE" else "",
    )


def decide(finding_id, state, version=1):
    return dict(
        type="decision_recorded",
        finding_id=finding_id,
        finding_version=version,
        state=state,
        rationale=f"Reviewer {state} the claim",
    )


def recorded_review(store, critics):
    """Two critics and a lead, one critique round, no operator judgments."""
    a, b, lead = critics
    submit(
        store,
        "r",
        started(critics),
        invocation(a, "a"),
        invocation(b, "b"),
        invocation(lead, "lead"),
        finding("shared-a", "a"),
        finding("shared-b", "b", issue="shared-a"),
        {**finding("only-a", "a"), "severity": "blocking"},
        finding("only-b", "b"),
        finding("lead-claim", "lead"),
        finish_inv("a"),
        finish_inv("b"),
        finish_inv("lead"),
        invocation(b, "b1", 1),
        invocation(a, "a1", 1),
        invocation(lead, "lead1", 1),
        verdict("b1", "only-a", "DISAGREE_EVIDENCE"),
        verdict("b1", "lead-claim", "DISAGREE_CONCERN"),
        verdict("b1", "shared-a", "AGREE"),
        verdict("a1", "only-b", "DISAGREE_CONCERN"),
        finding("lead-claim", "lead1", version=2),
        decide("only-a", "withdrawn"),
        decide("shared-a", "supported"),
        decide("shared-b", "supported"),
        decide("only-b", "supported"),
        decide("lead-claim", "supported", version=2),
        finish_inv("b1"),
        finish_inv("a1"),
        finish_inv("lead1"),
        {"type": "run_finished", "status": "completed", "reason": "Review done"},
    )


def test_reviewer_accepted_contributions_appear_without_operator_judgments(store, critics):
    a, b, lead = critics
    recorded_review(store, critics)
    result = calculate(store.snapshot(), store.critics())
    assert result["metric_version"] == METRIC_VERSION == "1.3"
    assert result["overview"]["reviewer_decisions"] == {
        "supported": 3,
        "withdrawn": 1,
        "unresolved": 0,
        "undecided": 0,
    }
    stats = {c["critic_id"]: c for c in result["critics"]}
    assert stats[a]["distinct_issues"] == 2
    assert stats[a]["issues_per_review"] == 2.0
    assert stats[a]["reviewer_supported_issues"] == 1
    assert stats[a]["reviewer_withdrawn_issues"] == 1
    assert stats[a]["reviewer_keep_rate"] == 0.5
    # The shared issue was found by both critics, so it is unique to neither.
    assert stats[a]["unique_supported_discoveries"] == 0
    assert stats[a]["supported_severity"] == {"should_fix": 1}
    # Critic a's challenge was rejected: the reviewer kept the claim.
    assert stats[a]["challenge_responses"]["kept"] == 1
    assert stats[a]["challenges_changed_review"] == 0
    assert stats[b]["reviewer_supported_issues"] == 2
    assert stats[b]["unique_supported_discoveries"] == 1
    assert stats[b]["challenge_responses"] == {
        "withdrawn": 1,
        "revised": 1,
        "kept": 0,
        "pending": 0,
    }
    assert stats[b]["challenges_changed_review"] == 2
    # Original discovery credit stays with the lead's first claim after revision.
    assert stats[lead]["reviewer_supported_issues"] == 1
    assert stats[lead]["unique_supported_discoveries"] == 1
    # Agreement and reviewer decisions never become independent validity.
    for critic in stats.values():
        assert critic["valid_issues"] == 0
        assert critic["unique_valid_discoveries"] == 0
        assert critic["judgment_coverage"] == 0
    rounds = {r["round"]: r for r in result["rounds"]}
    assert rounds[0]["new_issues"] == 4
    assert rounds[0]["reviewer_supported_new_issues"] == 3
    assert (rounds[1]["challenges"], rounds[1]["challenges_changed_review"]) == (3, 2)
    assert result["run_summaries"]["r"] == {
        "issues": 4,
        "reviewer_supported": 3,
        "reviewer_withdrawn": 1,
        "judged": 0,
        "valid": 0,
        "critics": 3,
    }
    assert result["reviewer_calibration"]["agreement_rate"] is None


def test_independent_judgments_calibrate_without_changing_provisional_measures(store, critics):
    a = critics[0]
    recorded_review(store, critics)
    before = calculate(store.snapshot(), store.critics())
    submit(
        store,
        "r",
        judge("shared-a"),
        judge("only-a", "invalid"),
        judge("only-b", "invalid"),
        judge("lead-claim", "unknown"),
        actor="operator",
    )
    after = calculate(store.snapshot(), store.critics())
    calibration = after["reviewer_calibration"]
    assert calibration["by_decision"]["supported"] == {"valid": 1, "invalid": 1, "unjudged": 1}
    assert calibration["by_decision"]["withdrawn"] == {"valid": 0, "invalid": 1, "unjudged": 0}
    assert (calibration["matched"], calibration["compared"]) == (2, 3)
    assert calibration["agreement_rate"] == 2 / 3
    stats = {c["critic_id"]: c for c in after["critics"]}
    old = {c["critic_id"]: c for c in before["critics"]}
    assert stats[a]["reviewer_supported_issues"] == old[a]["reviewer_supported_issues"] == 1
    assert (stats[a]["valid_issues"], stats[a]["invalid_issues"]) == (1, 1)


def test_assessment_queue_lists_unjudged_issues_most_severe_first(store, critics):
    recorded_review(store, critics)
    queue = assessment_queue(store.snapshot())
    assert queue["total"] == 4
    first = queue["items"][0]
    assert (first["issue_id"], first["severity"], first["reviewer_state"]) == (
        "only-a",
        "blocking",
        "withdrawn",
    )
    assert first["title"] == "Defect only-a"
    assert first["disagree"] == 1
    shared = next(i for i in queue["items"] if i["issue_id"] == "shared-a")
    assert (shared["claims"], len(shared["critic_ids"]), shared["agree"]) == (2, 2, 1)
    assert assessment_queue(store.snapshot(), limit=1)["items"] == [first]
    submit(
        store,
        "r",
        judge("shared-a"),
        judge("only-a", "invalid"),
        judge("only-b"),
        judge("lead-claim", "unknown"),
        actor="operator",
    )
    remaining = assessment_queue(store.snapshot())
    assert [(i["issue_id"], i["judgment"]) for i in remaining["items"]] == [
        ("lead-claim", "unknown")
    ]
    submit(
        store,
        "unusable",
        started(critics),
        invocation(critics[0], "x"),
        finding("unusable-claim", "x"),
        finish_inv("x"),
        {"type": "run_finished", "status": "completed", "reason": "Inspection failed"},
    )
    assert assessment_queue(store.snapshot())["total"] == 2
    submit(store, "unusable", {"type": "run_invalidated", "reason": "No access"}, actor="operator")
    assert assessment_queue(store.snapshot())["total"] == 1
    # The invalidated review stays listed, but its claims no longer count.
    assert calculate(store.snapshot(), store.critics())["run_summaries"]["unusable"]["issues"] == 0


def test_groups_count_each_issue_once_across_prompt_versions(store):
    def register(role, prompt, model):
        critic = Critic(name=f"{role} {prompt}", role=role, prompt=prompt, model=model)
        return store.register_critic(critic)["id"]

    first = register("Bug hunter", "Find failures", "model-a")
    reworded = register(" bug  Hunter", "Find failures, revised", "model-a")
    other_model = register("Bug hunter", "Find failures", "model-b")
    lead = register("Lead", "Combine findings", "model-a")

    def inv(critic, key, model):
        return {**invocation(critic, key), "model": model}

    submit(
        store,
        "g1",
        started([first, reworded, lead]),
        inv(first, "p1", "model-a"),
        inv(reworded, "p2", "model-a"),
        inv(lead, "pl", "model-a"),
        finding("same-1", "p1", issue="same"),
        finding("same-2", "p2", issue="same"),
        finding("first-only", "p1"),
        finding("lead-only", "pl"),
        *[decide(key, "supported") for key in ("same-1", "same-2", "first-only", "lead-only")],
        finish_inv("p1"),
        finish_inv("p2"),
        finish_inv("pl"),
    )
    submit(
        store,
        "g2",
        started([other_model]),
        inv(other_model, "p3", "model-b"),
        finding("other-only", "p3"),
        decide("other-only", "supported"),
    )
    result = calculate(store.snapshot(), store.critics())
    by_role = {g["group_key"]: g for g in result["groups"]["role"]}
    hunters = by_role["bug hunter"]
    assert hunters["label"] == "Bug hunter"
    assert hunters["critic_ids"] == sorted([first, reworded, other_model])
    # Union, not sum: the definitions report 2 + 1 + 1 claimed issues.
    assert hunters["distinct_issues"] == 3
    assert hunters["run_count"] == 2
    # Two group-unique discoveries in g1. Solo g2 provides no comparison.
    assert hunters["unique_supported_discoveries"] == 2
    per_definition = {c["critic_id"]: c for c in result["critics"]}
    assert per_definition[first]["unique_supported_discoveries"] == 1
    assert by_role["lead"]["distinct_issues"] == 1
    by_model = {g["label"]: g for g in result["groups"]["role_model"]}
    assert set(by_model) == {"Bug hunter · model-a", "Bug hunter · model-b", "Lead · model-a"}
    assert by_model["Bug hunter · model-a"]["distinct_issues"] == 2
    assert by_model["Bug hunter · model-b"]["distinct_issues"] == 1


def test_mcp_lists_compact_critic_summaries_and_full_definitions(live_server):
    app, client, settings = live_server
    store = app.state.store
    long_prompt = "Inspect boundaries. " * 40
    used = store.register_critic(
        Critic(name="Bug hunter v1", role="Bug hunter", prompt=long_prompt)
    )
    submit(store, "used", started([used["id"]]), invocation(used["id"], "i"))

    async def verify():
        import httpx

        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {settings.ingest_token}"}
        ) as http:
            async with streamable_http_client(settings.public_url + "/mcp", http_client=http) as s:
                async with ClientSession(s[0], s[1]) as session:
                    await session.initialize()
                    listed = await session.call_tool("list_critics", {"role": " bug HUNTER "})
                    assert not listed.isError
                    summaries = listed.structuredContent["result"]
                    assert summaries[0]["id"] == used["id"]
                    assert all(c["role"].casefold() == "bug hunter" for c in summaries)
                    assert any(
                        c["name"] == "Bug hunter" and c["review_count"] == 0 for c in summaries
                    )
                    summary = summaries[0]
                    assert "prompt" not in summary
                    assert summary["review_count"] == 1
                    assert summary["prompt_chars"] == len(long_prompt)
                    assert len(summary["prompt_preview"]) <= 201
                    by_specialty = await session.call_tool(
                        "list_critics", {"specialty": "Bug hunting"}
                    )
                    assert not by_specialty.isError
                    assert by_specialty.structuredContent["result"][0]["id"] == used["id"]
                    everything = await session.call_tool("list_critics", {})
                    ranked = everything.structuredContent["result"]
                    assert ranked[0]["id"] == used["id"] and len(ranked) > 1
                    full = await session.call_tool("get_critic", {"critic_id": used["id"]})
                    assert not full.isError
                    detail = full.structuredContent or json.loads(full.content[0].text)
                    assert detail["prompt"] == long_prompt

    asyncio.run(verify())
    operator = {"Authorization": f"Bearer {settings.admin_token}"}
    dashboard = client.get("/api/dashboard", headers=operator).json()
    assert dashboard["metrics"]["metric_version"] == "1.3"
    assert dashboard["assessment"] == {"total": 0, "limit": 200, "items": []}
    writer = {"Authorization": f"Bearer {settings.ingest_token}"}
    assert client.get("/api/dashboard", headers=writer).status_code == 403


def test_failed_discovery_is_not_completed_by_empty_retry(store, critics):
    a, b, _ = critics
    submit(
        store,
        "retry",
        started([a, b]),
        invocation(a, "failed"),
        finding("f", "failed"),
        decide("f", "supported"),
        {
            "type": "invocation_finished",
            "invocation_id": "failed",
            "status": "failed",
            "error": "Inspection interrupted",
        },
        invocation(a, "retry"),
        finish_inv("retry"),
        invocation(b, "other"),
        finish_inv("other"),
    )
    submit(store, "retry", judge("f"), actor="operator")
    result = calculate(store.snapshot(), store.critics())
    # Both the definition and its groups must retain authorship without independence.
    rows = [next(c for c in result["critics"] if c["critic_id"] == a)]
    rows += [g for groups in result["groups"].values() for g in groups if g["critic_ids"] == [a]]
    for row in rows:
        assert row["raw_findings"] == row["distinct_issues"] == 1
        assert row["reviewer_supported_issues"] == row["valid_issues"] == 1
        assert row["comparison_reviews"] == 1
        assert row["exclusive_issues"] == 1
        assert row["unique_discoveries"] == 0
        assert row["unique_supported_discoveries"] == 0
        assert row["unique_valid_discoveries"] == 0
        assert row["independent_valid_discoveries"] == 0
        assert row["unique_issue_refs"][0]["independent_comparison"] is False
    assert store.snapshot()["findings"][0]["origin_invocation_id"] == "failed"
    # A new, genuinely completed claim of the issue can earn discovery credit.
    submit(
        store,
        "retry",
        invocation(a, "new-discovery"),
        finding("new-f", "new-discovery", issue="f"),
        finish_inv("new-discovery"),
    )
    row = next(
        c for c in calculate(store.snapshot(), store.critics())["critics"] if c["critic_id"] == a
    )
    assert row["raw_findings"] == 2
    assert row["distinct_issues"] == row["unique_valid_discoveries"] == 1


def test_assessment_queue_uses_latest_versions_after_merge_and_revision(store, critics):
    a, b, lead = critics
    submit(
        store,
        "versions",
        started(critics),
        invocation(a, "author"),
        finding("f", "author"),
        finish_inv("author"),
        invocation(b, "coauthor"),
        finding("duplicate", "coauthor"),
        finish_inv("coauthor"),
        {
            "type": "issues_merged",
            "source_issue_id": "duplicate",
            "target_issue_id": "f",
            "reason": "Same defect",
        },
        invocation(lead, "votes", 1),
        verdict("votes", "f", "AGREE"),
        verdict("votes", "duplicate", "DISAGREE_CONCERN"),
        finish_inv("votes"),
        invocation(a, "revision", 2),
        finding("f", "revision", version=2),
        finish_inv("revision"),
    )
    item = assessment_queue(store.snapshot())["items"][0]
    assert (item["claims"], item["agree"], item["disagree"]) == (2, 0, 1)
    submit(
        store,
        "versions",
        invocation(lead, "current-votes", 3),
        verdict("current-votes", "f", "AGREE", version=2),
        finish_inv("current-votes"),
    )
    item = assessment_queue(store.snapshot())["items"][0]
    assert (item["agree"], item["disagree"]) == (1, 1)
    assert len(store.snapshot()["verdicts"]) == 3
