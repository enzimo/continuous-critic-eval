"""Regressions for the first architecture audit, using real HTTP and SQLite."""

from pathlib import Path

import pytest
from conftest import finding, finish_inv, invocation, started

from critic_observer.client import Reporter
from critic_observer.metrics import compare_experiment
from critic_observer.models import Batch, Experiment, Usage
from critic_observer.store import Conflict, Store
from critic_observer.trials import TrialResult, event, fingerprint, run_trial, skill_material

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def trial_case(live_server, tmp_path):
    app, _, settings = live_server
    target = tmp_path / "design"
    target.mkdir()
    (target / "design.md").write_text("One service owns persistent state.\n")
    critics = [c["id"] for c in app.state.store.critics()][:2]

    def create(team=None):
        return app.state.store.create_experiment(
            Experiment(
                name="Architecture failure regressions",
                hypothesis="Collection preserves results and measured failures",
                review_type="architecture",
                skill_revision=skill_material(ROOT, "architecture")[0],
                primary_metric="valid_issues",
                variants=[
                    {"id": "a", "name": "A", "critic_ids": team or critics[:1]},
                    {"id": "b", "name": "B", "critic_ids": critics[1:]},
                ],
                cases=[
                    {
                        "id": "design",
                        "title": "Frozen architecture",
                        "target": "collector",
                        "target_revision": fingerprint(target),
                        "instructions": "Review design.md",
                    }
                ],
            )
        )

    reporter = Reporter(settings.public_url, settings.ingest_token, tmp_path / "outbox")

    def run(exp):
        return run_trial(
            reporter,
            exp["id"],
            "a",
            "design",
            1,
            "codex",
            target,
            ROOT,
            trace_root=tmp_path / "traces",
        )

    return app.state.store, target, critics, reporter, create, run


def large_findings():
    text = "雪" * 16_000
    return [
        {
            "title": f"Finding {i}",
            "severity": "should_fix",
            "confidence": "verified",
            "category": "operations",
            "location": text,
            "trigger": text,
            "impact": text,
            "evidence": text,
        }
        for i in range(12)
    ]


def test_large_utf8_trial_delivers_all_events_and_following_review(trial_case, monkeypatch):
    store, _, critics, reporter, create, run = trial_case
    result = TrialResult(
        status="completed",
        inspected_paths=["design.md"],
        limitations=[],
        findings=large_findings(),
    )
    monkeypatch.setattr("critic_observer.trials.execute_critic", lambda *args: (result, None, None))
    trial = run(create())
    detail = store.run(trial["run_id"])
    assert trial["status"] == "completed" and trial["pending_batches"] == 0
    assert detail["run"]["status"] == "completed"
    assert detail["run"]["review_type"] == "architecture"
    assert detail["invocations"][0]["status"] == "completed"
    assert len(detail["findings"]) == 12
    assert {f["title"] for f in detail["findings"]} == {f"Finding {i}" for i in range(12)}
    reporter.send({"events": [event("following", started(critics))]})
    assert store.run("following")["run"]["status"] == "running"
    assert not list(reporter.directory.glob("*.json"))


def test_oversized_atomic_batch_is_rejected_without_outbox_writes(trial_case):
    _, _, critics, reporter, _, _ = trial_case
    observations = [
        event("atomic", {**finding(f"f{i}", "i"), **claim})
        for i, claim in enumerate(large_findings())
    ]
    batch = Batch.model_validate({"events": observations})
    assert len(batch.model_dump_json().encode("utf-8")) > 2_000_000
    with pytest.raises(ValueError, match="byte"):
        reporter.enqueue(batch)
    assert not list(reporter.directory.glob("*.json"))
    assert not list(reporter.directory.glob("*.tmp"))
    # A rejected batch cannot poison the next valid delivery.
    reporter.send({"events": [event("after-rejection", started(critics))]})


@pytest.mark.parametrize("failure", ["changed_target", "invalid_finding"])
def test_post_execution_failure_retains_acquired_measurements(trial_case, monkeypatch, failure):
    store, target, _, _, create, run = trial_case
    exp = create()
    usage = Usage(source="runtime", input_tokens=101, output_tokens=202)

    def execute(*args):
        claims = []
        if failure == "changed_target":
            (target / "design.md").write_text("Changed during review\n")
        else:
            claims = [large_findings()[0], {**large_findings()[1], "evidence": "x" * 16_001}]
        return (
            TrialResult(
                status="completed",
                inspected_paths=["design.md"],
                limitations=[],
                findings=claims,
            ),
            usage,
            "model-probe",
        )

    monkeypatch.setattr("critic_observer.trials.execute_critic", execute)
    result = run(exp)
    detail = store.run(result["run_id"])
    assert result["status"] == "failed" and result["pending_batches"] == 0
    assert detail["run"]["status"] == "failed"
    inv = detail["invocations"][0]
    assert inv["status"] == "failed"
    assert inv["usage"] == usage.model_dump(mode="json")
    assert inv["resolved_model"] == "model-probe"
    assert not detail["findings"]
    assert compare_experiment(exp, store.snapshot())["matched_trials"] == 0


def test_failed_critic_does_not_inherit_previous_critics_usage(trial_case, monkeypatch):
    store, _, critics, _, create, run = trial_case
    calls = 0

    def execute(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Execution failed before returning measurements")
        return (
            TrialResult(
                status="completed",
                inspected_paths=["design.md"],
                limitations=[],
                findings=[],
            ),
            Usage(source="runtime", input_tokens=99, output_tokens=3),
            "first-model",
        )

    monkeypatch.setattr("critic_observer.trials.execute_critic", execute)
    result = run(create(critics))
    invocations = store.run(result["run_id"])["invocations"]
    first = next(i for i in invocations if i["critic_id"] == critics[0])
    second = next(i for i in invocations if i["critic_id"] == critics[1])
    assert first["usage"]["input_tokens"] == 99
    assert second["status"] == "failed"
    assert second["usage"] is None and second["resolved_model"] is None


def test_interrupt_after_execution_preserves_acquired_usage(trial_case, monkeypatch):
    store, _, _, _, create, run = trial_case
    exp = create()
    usage = Usage(source="runtime", input_tokens=13, output_tokens=7)
    monkeypatch.setattr(
        "critic_observer.trials.execute_critic",
        lambda *args: (
            TrialResult(
                status="completed", inspected_paths=["design.md"], limitations=[], findings=[]
            ),
            usage,
            "interrupted-model",
        ),
    )
    fingerprints = 0

    def interrupted(path):
        nonlocal fingerprints
        fingerprints += 1
        if fingerprints == 2:
            raise KeyboardInterrupt
        return fingerprint(path)

    monkeypatch.setattr("critic_observer.trials.fingerprint", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run(exp)
    run_id = store.snapshot()["runs"][0]["id"]
    detail = store.run(run_id)
    assert detail["run"]["status"] == "cancelled"
    inv = detail["invocations"][0]
    assert inv["status"] == "cancelled"
    assert inv["usage"] == usage.model_dump(mode="json")
    assert inv["resolved_model"] == "interrupted-model"


def test_fractional_timestamp_lifecycle_and_replay_over_http(live_server):
    app, client, settings = live_server
    critic = app.state.store.critics()[0]["id"]
    # Equivalent offsets normalize to UTC, but the recorded strings retain
    # their original precision. Replay must retain exactly the same documents.
    payloads = [
        (started([critic]), "2026-11-01T13:00:00+01:00"),
        (invocation(critic, "i"), "2026-11-01T12:00:00.100000Z"),
        (finding("f", "i"), "2026-11-01T12:00:00.200000Z"),
        (finish_inv("i"), "2026-11-01T12:00:00.300000Z"),
        (
            {"type": "run_finished", "status": "completed", "reason": "done"},
            "2026-11-01T12:00:00.400000Z",
        ),
    ]
    batch = {"events": [{**event("fractional", p), "occurred_at": at} for p, at in payloads]}
    writer = {"Authorization": f"Bearer {settings.ingest_token}"}
    response = client.post("/api/events", headers=writer, json=batch)
    assert response.status_code == 200, response.text
    reopened = Store(settings.database)
    before = reopened.run("fractional")
    replay = client.post("/api/events", headers=writer, json=batch)
    assert replay.status_code == 200
    assert len(replay.json()["duplicates"]) == 5
    assert reopened.run("fractional") == before
    assert before["run"]["started_at"] == "2026-11-01T12:00:00Z"


@pytest.mark.parametrize("kind", ["invocation_started", "finding_recorded", "invocation_finished"])
def test_whole_second_start_orders_fractional_events_and_rejects_earlier(store, critics, kind):
    def send(payload, at):
        return store.ingest(
            Batch.model_validate(
                {
                    "events": [
                        {**event("order", payload), "occurred_at": at},
                    ]
                }
            )
        )

    send(started(critics), "2026-11-01T12:00:00Z")
    if kind == "invocation_started":
        payload = invocation(critics[0], "i")
    else:
        send(invocation(critics[0], "i"), "2026-11-01T12:00:01Z")
        payload = finding("f", "i") if kind == "finding_recorded" else finish_inv("i")
    with pytest.raises(Conflict, match="predate"):
        send(
            payload,
            "2026-11-01T11:59:59.900000Z"
            if kind == "invocation_started"
            else "2026-11-01T12:00:00.900000Z",
        )
    accepted = send(
        payload,
        "2026-11-01T12:00:00.100000Z"
        if kind == "invocation_started"
        else "2026-11-01T12:00:01.100000Z",
    )
    assert len(accepted["accepted"]) == 1
