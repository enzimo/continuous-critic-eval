"""Transactional storage. Accepted events and projections commit together."""

import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .models import OPERATOR_EVENTS, Batch, Critic, Experiment, now
from .specialties import specialty_of

log = logging.getLogger(__name__)


class Conflict(ValueError):
    """A reference, version, or lifecycle precondition has not been satisfied."""


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def identity(prefix, value):
    return prefix + hashlib.sha256(encoded(value).encode()).hexdigest()


SCHEMA = """
BEGIN IMMEDIATE;
CREATE TABLE critics(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, document TEXT NOT NULL);
CREATE TABLE experiments(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, document TEXT NOT NULL);
CREATE TABLE runs(
 id TEXT PRIMARY KEY, status TEXT NOT NULL, started_at TEXT NOT NULL,
 finished_at TEXT, document TEXT NOT NULL, evaluation TEXT
);
CREATE TABLE events(
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL,
 run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, occurred_at TEXT NOT NULL, received_at TEXT NOT NULL,
 actor TEXT NOT NULL, document TEXT NOT NULL
);
CREATE INDEX event_run ON events(run_id, sequence);
CREATE TABLE invocations(
 run_id TEXT REFERENCES runs(id) ON DELETE CASCADE, id TEXT,
 critic_id TEXT NOT NULL REFERENCES critics(id), status TEXT NOT NULL,
 started_at TEXT NOT NULL, finished_at TEXT, document TEXT NOT NULL, usage TEXT,
 PRIMARY KEY(run_id,id)
);
CREATE TABLE findings(
 run_id TEXT REFERENCES runs(id) ON DELETE CASCADE, id TEXT, version INTEGER,
 issue_id TEXT NOT NULL, invocation_id TEXT NOT NULL, document TEXT NOT NULL,
 PRIMARY KEY(run_id,id,version),
 FOREIGN KEY(run_id,invocation_id) REFERENCES invocations(run_id,id)
);
CREATE INDEX issue_run ON findings(run_id,issue_id);
CREATE TABLE verdicts(
 event_id TEXT PRIMARY KEY, run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
 invocation_id TEXT NOT NULL, finding_id TEXT NOT NULL, finding_version INTEGER NOT NULL,
 document TEXT NOT NULL,
 UNIQUE(run_id,invocation_id,finding_id,finding_version),
 FOREIGN KEY(run_id,invocation_id) REFERENCES invocations(run_id,id),
 FOREIGN KEY(run_id,finding_id,finding_version) REFERENCES findings(run_id,id,version)
);
CREATE TABLE decisions(
 run_id TEXT REFERENCES runs(id) ON DELETE CASCADE, finding_id TEXT,
 finding_version INTEGER, revision INTEGER NOT NULL, document TEXT NOT NULL,
 PRIMARY KEY(run_id,finding_id,finding_version),
 FOREIGN KEY(run_id,finding_id,finding_version) REFERENCES findings(run_id,id,version)
);
CREATE TABLE judgments(
 run_id TEXT REFERENCES runs(id) ON DELETE CASCADE, issue_id TEXT,
 revision INTEGER NOT NULL, document TEXT NOT NULL, PRIMARY KEY(run_id,issue_id)
);
CREATE TABLE challenge_judgments(
 verdict_event_id TEXT PRIMARY KEY REFERENCES verdicts(event_id) ON DELETE CASCADE,
 run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL, document TEXT NOT NULL
);
CREATE TABLE outcomes(
 run_id TEXT REFERENCES runs(id) ON DELETE CASCADE, issue_id TEXT,
 revision INTEGER NOT NULL, document TEXT NOT NULL, PRIMARY KEY(run_id,issue_id)
);
PRAGMA user_version=1;
COMMIT;
"""


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                db.executescript(SCHEMA)
            elif version != 1:
                raise RuntimeError(f"Unsupported database version {version}; expected 1")
            db.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def register_critic(self, critic: Critic):
        document = critic.model_dump(mode="json")
        # An omitted specialty must retain the original immutable identity.
        if document["specialty"] is None:
            del document["specialty"]
        key = identity("c_", document)
        with self.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO critics VALUES(?,?,?)", (key, now(), encoded(document))
            )
        return self.critic(key)

    def critic(self, key):
        with self.connect() as db:
            row = db.execute("SELECT * FROM critics WHERE id=?", (key,)).fetchone()
            if row is None:
                raise Conflict(f"Unknown critic {key}; register its definition first")
            return {"id": row["id"], "created_at": row["created_at"], **json.loads(row["document"])}

    def critics(self):
        with self.connect() as db:
            return [
                dict(id=r["id"], created_at=r["created_at"], **json.loads(r["document"]))
                for r in db.execute("SELECT * FROM critics ORDER BY created_at,id")
            ]

    def critic_summaries(self, role="", specialty=""):
        """Short definitions for agents choosing one to reuse; full prompts stay separate.

        Full prompts of every definition can exceed an agent's tool-result limit.
        Most-used definitions come first so agents reuse established roles.
        """
        wanted = " ".join(role.split()).casefold()
        with self.connect() as db:
            usage = {
                r["critic_id"]: r["reviews"]
                for r in db.execute(
                    "SELECT critic_id, COUNT(DISTINCT run_id) AS reviews "
                    "FROM invocations GROUP BY critic_id"
                )
            }
        summaries = []
        for critic in self.critics():
            if wanted and " ".join(critic["role"].split()).casefold() != wanted:
                continue
            if (
                specialty
                and specialty_of(critic).casefold() != " ".join(specialty.split()).casefold()
            ):
                continue
            prompt = critic["prompt"]
            summaries.append(
                {
                    **{k: critic[k] for k in ("id", "name", "role", "provider", "model")},
                    "settings": critic["settings"],
                    "specialty": specialty_of(critic),
                    "created_at": critic["created_at"],
                    "review_count": usage.get(critic["id"], 0),
                    "prompt_chars": len(prompt),
                    "prompt_preview": prompt if len(prompt) <= 200 else prompt[:200] + "…",
                }
            )
        return sorted(summaries, key=lambda c: (-c["review_count"], c["role"].casefold()))

    def create_experiment(self, experiment: Experiment):
        document = experiment.model_dump(mode="json")
        # Code was implicit in the original contract. Keep those immutable IDs.
        if document["review_type"] == "code":
            del document["review_type"]
        key = identity("e_", document)
        with self.transaction() as db:
            for variant in experiment.variants:
                for critic in variant.critic_ids:
                    self.require(db, "critics", "id=?", (critic,), f"Unknown critic {critic}")
            db.execute(
                "INSERT OR IGNORE INTO experiments VALUES(?,?,?)", (key, now(), encoded(document))
            )
        return self.experiment(key)

    def experiments(self, review_type=""):
        with self.connect() as db:
            return [
                dict(
                    id=r["id"],
                    created_at=r["created_at"],
                    review_type="code",
                )
                | json.loads(r["document"])
                for r in db.execute("SELECT * FROM experiments ORDER BY created_at DESC")
                if not review_type
                or json.loads(r["document"]).get("review_type", "code") == review_type
            ]

    def experiment(self, key):
        with self.connect() as db:
            row = self.require(db, "experiments", "id=?", (key,), f"Unknown experiment {key}")
            return dict(id=key, created_at=row["created_at"], review_type="code") | json.loads(
                row["document"]
            )

    def brief(self, key, variant_id, case_id):
        experiment = self.experiment(key)
        variant = next((v for v in experiment["variants"] if v["id"] == variant_id), None)
        case = next((c for c in experiment["cases"] if c["id"] == case_id), None)
        if variant is None or case is None:
            raise Conflict("Variant or case is not part of this experiment")
        return {
            "experiment_id": key,
            "skill_revision": experiment["skill_revision"],
            "review_type": experiment["review_type"],
            "dataset": "benchmark",
            "input_mode": experiment.get("input_mode", "filesystem"),
            "variant": variant,
            "case": {k: v for k, v in case.items() if k != "known_issues"},
            "critics": [self.critic(c) for c in variant["critic_ids"]],
        }

    @staticmethod
    def require(db, table, condition, args, message):
        # table and condition are fixed source-code fragments, never request input.
        row = db.execute(f"SELECT * FROM {table} WHERE {condition}", args).fetchone()
        if row is None:
            raise Conflict(message)
        return row

    def ingest(self, batch: Batch, actor="ingest"):
        if actor != "operator" and any(e.data.type in OPERATOR_EVENTS for e in batch.events):
            raise PermissionError("Only the operator can record independent judgments or outcomes")
        accepted, duplicates = [], []
        try:
            with self.transaction() as db:
                for event in batch.events:
                    document = event.model_dump(mode="json")
                    body = encoded(document)
                    prior = db.execute(
                        "SELECT document FROM events WHERE event_id=?", (event.event_id,)
                    ).fetchone()
                    if prior:
                        if prior["document"] != body:
                            raise Conflict(
                                f"Event ID {event.event_id} already has different content"
                            )
                        duplicates.append(event.event_id)
                        continue
                    self.apply(db, document)
                    db.execute(
                        "INSERT INTO events(event_id,run_id,kind,occurred_at,"
                        "received_at,actor,document) "
                        "VALUES(?,?,?,?,?,?,?)",
                        (
                            event.event_id,
                            event.run_id,
                            event.data.type,
                            document["occurred_at"],
                            now(),
                            actor,
                            body,
                        ),
                    )
                    accepted.append(event.event_id)
        except sqlite3.IntegrityError as exc:
            raise Conflict(
                "Duplicate entity or assessment; replay the original event ID, "
                "or use the next revision"
            ) from exc
        log.info(
            "batch_committed accepted=%s duplicates=%s actor=%s",
            len(accepted),
            len(duplicates),
            actor,
        )
        return {"accepted": accepted, "duplicates": duplicates, "received_at": now()}

    def apply(self, db, event):
        p, run_id, at = event["data"], event["run_id"], event["occurred_at"]
        # Keep serialized events intact for replay; variable precision is not
        # chronologically ordered by string comparison.
        event_time = datetime.fromisoformat(at)
        kind = p["type"]
        if kind == "run_started":
            for key in p["expected_critic_ids"]:
                self.require(db, "critics", "id=?", (key,), f"Unknown critic {key}")
            if p["experiment_id"]:
                row = self.require(
                    db,
                    "experiments",
                    "id=?",
                    (p["experiment_id"],),
                    "Create the experiment before registering a trial",
                )
                exp = json.loads(row["document"])
                variant = next((v for v in exp["variants"] if v["id"] == p["variant_id"]), None)
                case = next((c for c in exp["cases"] if c["id"] == p["case_id"]), None)
                if (
                    variant is None
                    or case is None
                    or case["target_revision"] != p["target_revision"]
                    or set(variant["critic_ids"]) != set(p["expected_critic_ids"])
                    or exp["skill_revision"] != p["skill_revision"]
                    or exp.get("review_type", "code") != p["review_type"]
                ):
                    raise Conflict(
                        "Trial must match its frozen review type, case revision "
                        "and critic membership"
                    )
                for existing in db.execute("SELECT document FROM runs"):
                    old = json.loads(existing["document"])
                    keys = ("experiment_id", "variant_id", "case_id", "trial")
                    if all(old[k] == p[k] for k in keys):
                        raise Conflict("This experiment variant/case/trial already has a run")
                if p["dataset"] != "benchmark":
                    raise Conflict("Experiment trials must use the benchmark dataset")
            db.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,NULL)", (run_id, "running", at, None, encoded(p))
            )
            return
        run = self.require(
            db,
            "runs",
            "id=?",
            (run_id,),
            f"Run {run_id} is missing; deliver run_started first and retry",
        )
        if event_time < datetime.fromisoformat(run["started_at"]):
            raise Conflict("An event cannot predate its run")
        if kind not in OPERATOR_EVENTS and kind != "issues_merged" and run["status"] != "running":
            raise Conflict("The review is finished; start a new run for new review activity")
        if kind == "invocation_started":
            run_config = json.loads(run["document"])
            if run_config["experiment_id"]:
                if p["critic_id"] not in run_config["expected_critic_ids"]:
                    raise Conflict("Experiment invocations must belong to the frozen variant")
                prior_pass = db.execute(
                    "SELECT 1 FROM invocations WHERE run_id=? AND critic_id=? "
                    "AND json_extract(document,'$.phase')=? AND json_extract(document,'$.round')=?",
                    (run_id, p["critic_id"], p["phase"], p["round"]),
                ).fetchone()
                if prior_pass:
                    raise Conflict(
                        "One invocation per critic/phase/round is allowed in a trial; "
                        "use another trial number to repeat"
                    )
            critic = self.require(
                db, "critics", "id=?", (p["critic_id"],), "Register the critic first"
            )
            config = json.loads(critic["document"])
            for key in ("provider", "model"):
                if config[key] is not None and p[key] != config[key]:
                    raise Conflict(f"Invocation {key} must match its immutable critic definition")
            db.execute(
                "INSERT INTO invocations VALUES(?,?,?,?,?,?,?,NULL)",
                (run_id, p["invocation_id"], p["critic_id"], "running", at, None, encoded(p)),
            )
        elif kind == "invocation_finished":
            inv = self.invocation(db, run_id, p["invocation_id"])
            if inv["status"] != "running" or event_time < datetime.fromisoformat(inv["started_at"]):
                raise Conflict("Invocation is already finished, or its finish predates its start")
            db.execute(
                "UPDATE invocations SET status=?,finished_at=?,usage=?,document=? "
                "WHERE run_id=? AND id=?",
                (
                    p["status"],
                    at,
                    encoded(p["usage"]) if p["usage"] is not None else None,
                    encoded(
                        {
                            **json.loads(inv["document"]),
                            "error": p["error"],
                            "resolved_model": p["resolved_model"],
                        }
                    ),
                    run_id,
                    p["invocation_id"],
                ),
            )
        elif kind == "finding_recorded":
            inv = self.invocation(db, run_id, p["invocation_id"])
            if inv["status"] != "running":
                raise Conflict("Record findings before finishing their invocation")
            previous = db.execute(
                "SELECT * FROM findings WHERE run_id=? AND id=? ORDER BY version DESC LIMIT 1",
                (run_id, p["finding_id"]),
            ).fetchone()
            if p["version"] != (previous["version"] + 1 if previous else 1):
                raise Conflict("Finding versions must be contiguous, starting at 1")
            if previous and previous["issue_id"] != p["issue_id"]:
                raise Conflict("A revised finding must preserve its issue identity")
            if event_time < datetime.fromisoformat(inv["started_at"]):
                raise Conflict("A finding cannot predate its reporting invocation")
            db.execute(
                "INSERT INTO findings VALUES(?,?,?,?,?,?)",
                (
                    run_id,
                    p["finding_id"],
                    p["version"],
                    p["issue_id"],
                    p["invocation_id"],
                    encoded(p),
                ),
            )
        elif kind == "verdict_recorded":
            inv = self.invocation(db, run_id, p["invocation_id"])
            claim = self.finding(db, run_id, p["finding_id"], p["finding_version"])
            if inv["status"] != "running" or inv["id"] == claim["invocation_id"]:
                raise Conflict("An active, different invocation must assess the finding")
            if json.loads(inv["document"])["phase"] != "critique":
                raise Conflict("Verdicts must come from a critique invocation")
            db.execute(
                "INSERT INTO verdicts VALUES(?,?,?,?,?,?)",
                (
                    event["event_id"],
                    run_id,
                    p["invocation_id"],
                    p["finding_id"],
                    p["finding_version"],
                    encoded(p),
                ),
            )
        elif kind == "decision_recorded":
            self.finding(db, run_id, p["finding_id"], p["finding_version"])
            self.revise(
                db,
                "decisions",
                "run_id=? AND finding_id=? AND finding_version=?",
                (run_id, p["finding_id"], p["finding_version"]),
                p,
            )
            db.execute(
                "INSERT OR REPLACE INTO decisions VALUES(?,?,?,?,?)",
                (run_id, p["finding_id"], p["finding_version"], p["revision"], encoded(p)),
            )
        elif kind == "issues_merged":
            source, target = p["source_issue_id"], p["target_issue_id"]
            self.issue(db, run_id, source)
            self.issue(db, run_id, target)
            if source == target:
                raise Conflict("An issue cannot be merged into itself")
            if db.execute(
                "SELECT 1 FROM judgments WHERE run_id=? AND issue_id IN (?,?)",
                (run_id, source, target),
            ).fetchone():
                raise Conflict("Merge duplicates before adjudicating either issue")
            if db.execute(
                "SELECT 1 FROM outcomes WHERE run_id=? AND issue_id IN (?,?)",
                (run_id, source, target),
            ).fetchone():
                raise Conflict("Merge duplicates before recording outcomes")
            db.execute(
                "UPDATE findings SET issue_id=? WHERE run_id=? AND issue_id=?",
                (target, run_id, source),
            )
        elif kind == "run_finished":
            if p["status"] == "completed":
                active = db.execute(
                    "SELECT 1 FROM invocations WHERE run_id=? AND status='running'", (run_id,)
                ).fetchone()
                if active:
                    raise Conflict("Finish all active invocations before completing the run")
            db.execute(
                "UPDATE runs SET status=?,finished_at=? WHERE id=?", (p["status"], at, run_id)
            )
        elif kind == "issue_judged":
            self.issue(db, run_id, p["issue_id"])
            self.revise(db, "judgments", "run_id=? AND issue_id=?", (run_id, p["issue_id"]), p)
            self.validate_known_issue(db, run, run_id, p)
            if p["validity"] == "valid" and p["severity"] is None:
                raise Conflict("A valid finding needs an independently assessed severity")
            db.execute(
                "INSERT OR REPLACE INTO judgments VALUES(?,?,?,?)",
                (run_id, p["issue_id"], p["revision"], encoded(p)),
            )
        elif kind == "challenge_judged":
            verdict = self.require(
                db,
                "verdicts",
                "event_id=? AND run_id=?",
                (p["verdict_event_id"], run_id),
                "Unknown verdict in this run",
            )
            if json.loads(verdict["document"])["verdict"] == "AGREE":
                raise Conflict("Challenge judgments apply to disagreement verdicts")
            self.revise(
                db, "challenge_judgments", "verdict_event_id=?", (p["verdict_event_id"],), p
            )
            db.execute(
                "INSERT OR REPLACE INTO challenge_judgments VALUES(?,?,?,?)",
                (p["verdict_event_id"], run_id, p["revision"], encoded(p)),
            )
        elif kind == "outcome_recorded":
            self.issue(db, run_id, p["issue_id"])
            self.revise(db, "outcomes", "run_id=? AND issue_id=?", (run_id, p["issue_id"]), p)
            db.execute(
                "INSERT OR REPLACE INTO outcomes VALUES(?,?,?,?)",
                (run_id, p["issue_id"], p["revision"], encoded(p)),
            )
        elif kind == "run_invalidated":
            if run["status"] == "running":
                raise Conflict("Close the active run before invalidating its result")
            db.execute("UPDATE runs SET status='invalidated',evaluation=NULL WHERE id=?", (run_id,))
        elif kind == "run_evaluated":
            if run["status"] != "completed":
                raise Conflict("Only a completed run can be marked fully evaluated")
            issues = {
                r[0]
                for r in db.execute(
                    "SELECT DISTINCT issue_id FROM findings WHERE run_id=?", (run_id,)
                )
            }
            judged = {
                r[0]
                for r in db.execute(
                    "SELECT issue_id FROM judgments WHERE run_id=? "
                    "AND json_extract(document,'$.validity') IN ('valid','invalid')",
                    (run_id,),
                )
            }
            if issues != judged:
                raise Conflict("Adjudicate every distinct issue before marking evaluation complete")
            db.execute("UPDATE runs SET evaluation=? WHERE id=?", (encoded(p), run_id))
        if kind in {"finding_recorded", "issue_judged", "issues_merged"}:
            db.execute("UPDATE runs SET evaluation=NULL WHERE id=?", (run_id,))

    def validate_known_issue(self, db, run, run_id, p):
        if not p["known_issue_id"]:
            return
        config = json.loads(run["document"])
        if not config["experiment_id"] or p["validity"] != "valid":
            raise Conflict("Known-defect matches need a valid issue in an experiment trial")
        exp = json.loads(
            self.require(
                db, "experiments", "id=?", (config["experiment_id"],), "Missing experiment"
            )["document"]
        )
        case = next(c for c in exp["cases"] if c["id"] == config["case_id"])
        if p["known_issue_id"] not in {i["id"] for i in case["known_issues"]}:
            raise Conflict("Unknown known_issue_id for this frozen case")
        for row in db.execute("SELECT issue_id,document FROM judgments WHERE run_id=?", (run_id,)):
            if (
                row["issue_id"] != p["issue_id"]
                and json.loads(row["document"])["known_issue_id"] == p["known_issue_id"]
            ):
                raise Conflict("This known defect is already matched; merge duplicate claims first")

    def invocation(self, db, run_id, key):
        return self.require(
            db,
            "invocations",
            "run_id=? AND id=?",
            (run_id, key),
            f"Invocation {key} is missing; deliver invocation_started first",
        )

    def finding(self, db, run_id, key, version):
        return self.require(
            db,
            "findings",
            "run_id=? AND id=? AND version=?",
            (run_id, key, version),
            "Finding/version is missing; deliver finding_recorded first",
        )

    def issue(self, db, run_id, key):
        return self.require(
            db,
            "findings",
            "run_id=? AND issue_id=?",
            (run_id, key),
            f"Unknown issue {key}; it may have been merged into another issue",
        )

    @staticmethod
    def revise(db, table, condition, args, payload):
        prior = db.execute(f"SELECT revision FROM {table} WHERE {condition}", args).fetchone()
        expected = prior[0] + 1 if prior else 1
        if payload["revision"] != expected:
            raise Conflict(f"Expected revision {expected}; reload the current record and retry")

    def snapshot(self, filters=None, *, run_id=None, include_evidence=False):
        filters = filters or {}
        with self.connect() as db:
            db.execute("BEGIN")
            runs = []
            run_query = "SELECT * FROM runs"
            parameters = ()
            if run_id is not None:
                run_query += " WHERE id=?"
                parameters = (run_id,)
            for r in db.execute(run_query + " ORDER BY started_at DESC,id", parameters):
                doc = json.loads(r["document"])
                if any(
                    value and doc.get(key) != value
                    for key, value in filters.items()
                    if key not in {"since", "until"}
                ):
                    continue
                if filters.get("since") and r["started_at"][:10] < filters["since"]:
                    continue
                if filters.get("until") and r["started_at"][:10] > filters["until"]:
                    continue
                runs.append(
                    dict(
                        id=r["id"],
                        status=r["status"],
                        started_at=r["started_at"],
                        finished_at=r["finished_at"],
                        evaluation=json.loads(r["evaluation"]) if r["evaluation"] else None,
                        **doc,
                    )
                )
            selected = {r["id"] for r in runs}
            db.execute("CREATE TEMP TABLE selected_runs(id TEXT PRIMARY KEY)")
            db.executemany("INSERT INTO selected_runs VALUES(?)", ((key,) for key in selected))
            result = {"runs": runs}
            for table in (
                "invocations",
                "findings",
                "verdicts",
                "decisions",
                "judgments",
                "challenge_judgments",
                "outcomes",
            ):
                values = []
                # Compact cohort records drop long evidence text. Finding titles stay
                # (at most 240 characters) so the assessment queue can name each issue.
                document = (
                    "t.document"
                    if include_evidence
                    else (
                        "json_remove(t.document,'$.evidence','$.rationale','$.location','$.impact',"
                        "'$.trigger','$.scope','$.error')"
                    )
                )
                query = (
                    f"SELECT t.*, {document} AS compact_document FROM {table} AS t "
                    "JOIN selected_runs AS s ON t.run_id=s.id"
                )
                for row in db.execute(query):
                    value = {**dict(row), **json.loads(row["compact_document"])}
                    del value["document"]
                    del value["compact_document"]
                    if table == "findings":
                        value["issue_id"] = row["issue_id"]
                    if table == "invocations":
                        value["usage"] = json.loads(row["usage"]) if row["usage"] else None
                    values.append(value)
                result[table] = values
            origins = {}
            for finding in sorted(result["findings"], key=lambda f: f["version"]):
                origins.setdefault((finding["run_id"], finding["id"]), finding["invocation_id"])
            for finding in result["findings"]:
                finding["origin_invocation_id"] = origins[(finding["run_id"], finding["id"])]
            return result

    def run(self, key):
        snapshot = self.snapshot(run_id=key, include_evidence=True)
        runs = [r for r in snapshot["runs"] if r["id"] == key]
        if not runs:
            raise Conflict(f"Unknown run {key}")
        with self.connect() as db:
            events = [
                {
                    **json.loads(r["document"]),
                    "received_at": r["received_at"],
                    "actor": r["actor"],
                    "sequence": r["sequence"],
                }
                for r in db.execute("SELECT * FROM events WHERE run_id=? ORDER BY sequence", (key,))
            ]
        return {
            "run": runs[0],
            **{
                k: [v for v in values if v["run_id"] == key]
                for k, values in snapshot.items()
                if k != "runs"
            },
            "events": events,
        }

    def delete_run(self, key):
        with self.transaction() as db:
            self.require(db, "runs", "id=?", (key,), "Unknown run")
            # Cascading tables retain their cross-reference integrity within the transaction.
            db.execute("DELETE FROM runs WHERE id=?", (key,))
        log.warning("run_deleted run_id=%s", key)

    def backup(self, destination):
        destination = Path(destination)
        if destination.exists():
            raise Conflict("Backup destination already exists")
        with self.connect() as source, sqlite3.connect(destination) as target:
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup failed its SQLite integrity check")
        return destination

    def export_bundle(self, key):
        detail = self.run(key)
        return {
            "schema_version": 1,
            "exported_at": now(),
            "critics": self.critics(),
            "experiments": self.experiments(),
            "run": detail,
            "export_id": str(uuid4()),
        }
