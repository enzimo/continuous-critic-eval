import socket
import threading
import time
from uuid import uuid4

import httpx
import pytest
import uvicorn

from critic_observer.app import create_app
from critic_observer.config import Settings
from critic_observer.models import Batch, Critic
from critic_observer.store import Store
from critic_observer.trials import event


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "observer.sqlite3")


@pytest.fixture
def critics(store):
    return [
        store.register_critic(Critic(name=name, role=name, prompt=f"Inspect {name}"))["id"]
        for name in ("Intent", "Counterexample", "Lead")
    ]


def started(critic_ids, **overrides):
    return (
        dict(
            type="run_started",
            project="sample",
            title="Review sample",
            review_type="code",
            target="fixture",
            target_revision="sha256:fixed",
            skill_revision="test-v1",
            client="test",
            expected_critic_ids=critic_ids,
        )
        | overrides
    )


def invocation(critic_id, key, round_no=0):
    return dict(
        type="invocation_started",
        invocation_id=key,
        critic_id=critic_id,
        phase="independent" if round_no == 0 else "critique",
        round=round_no,
        context="independent" if round_no == 0 else "shared",
        scope="fixture",
    )


def finding(key, inv, issue=None, **overrides):
    return dict(
        type="finding_recorded",
        finding_id=key,
        invocation_id=inv,
        issue_id=issue or key,
        title=f"Defect {key}",
        severity="should_fix",
        confidence="likely",
        category="correctness",
        location="queue.py:5",
        trigger="wrong owner completes",
        impact="unrelated work is lost",
        evidence="queue.jobs is modified without checking owner",
        **overrides,
    )


def submit(store, run_id, *payloads, actor="ingest"):
    batch = Batch.model_validate({"events": [event(run_id, p) for p in payloads]})
    store.ingest(batch, actor=actor)
    return batch


def finish_inv(key):
    return {"type": "invocation_finished", "invocation_id": key, "status": "completed"}


def judge(issue, validity="valid", **overrides):
    return dict(
        type="issue_judged",
        issue_id=issue,
        validity=validity,
        method="reproduction",
        severity="should_fix" if validity == "valid" else None,
        assessor="Test operator",
        rationale="Executed a concrete scenario",
        evidence="Reproduction demonstrated the result",
        **overrides,
    )


@pytest.fixture
def live_server(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    settings = Settings(
        tmp_path / "live.sqlite3", "a" * 48, "i" * 48, public_url=f"http://127.0.0.1:{port}"
    )
    app = create_app(settings)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # Registering the catalog commits SQLite transactions on startup; HDDs need
    # more than two seconds even when the service is healthy.
    for _ in range(1500):
        if server.started:
            break
        if not thread.is_alive():
            raise RuntimeError("Test server failed to start")
        time.sleep(0.02)
    else:
        raise RuntimeError("Test server did not become ready")
    with httpx.Client(base_url=settings.public_url, timeout=10) as client:
        yield app, client, settings
    server.should_exit = True
    thread.join(timeout=10)
    assert not thread.is_alive()


def new_run_id():
    return str(uuid4())
