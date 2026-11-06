"""Check the pilot's independent reference against executed code, not model agreement."""

import importlib.util
from pathlib import Path

from critic_observer.trials import fingerprint


def probe_cases():
    root = Path(__file__).resolve().parents[1] / "data/benchmarks"
    results = {}
    for name in ("queue-a", "queue-b"):
        spec = importlib.util.spec_from_file_location("pilot_queue", root / name / "queue.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        q = module.JobQueue()
        q.enqueue("x", {})
        q.claim("x", "alice")
        q.enqueue("x", {})
        resets_claim = q.jobs["x"]["owner"] != "alice"
        q = module.JobQueue()
        q.enqueue("x", {})
        q.claim("x", "alice")
        q.complete("x", "bob")
        wrong_owner = q.jobs["x"]["state"] == "completed"
        q = module.JobQueue()
        q.enqueue("x", {})
        q.snapshot().clear()
        snapshot_changes_queue = "x" not in q.jobs
        q = module.JobQueue()
        q.enqueue("x", {})
        owner = ["alice"]
        q.claim("x", owner)
        owner[0] = "bob"
        q.complete("x", ["bob"])
        results[name] = {
            "target_revision": fingerprint(root / name),
            "duplicate_resets_claim": resets_claim,
            "wrong_owner_completes": wrong_owner,
            "snapshot_changes_queue": snapshot_changes_queue,
            "mutable_owner_completes": q.jobs["x"]["state"] == "completed",
        }
    return results


def test_reference_defects_and_unresolved_control_assumption():
    cases = probe_cases()
    keys = ("duplicate_resets_claim", "wrong_owner_completes", "snapshot_changes_queue")
    assert all(cases["queue-a"][key] for key in keys)
    assert not any(cases["queue-b"][key] for key in keys)
    # This behavior is reproducible; its correctness depends on a supported-owner
    # contract that the pilot README does not define. It must not be auto-graded.
    assert cases["queue-b"]["mutable_owner_completes"]
