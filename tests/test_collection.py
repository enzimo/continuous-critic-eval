import asyncio
import json

import pytest
from conftest import finding, finish_inv, invocation, judge, started, submit
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from critic_observer.cli import restore_database
from critic_observer.client import DeliveryError, Reporter
from critic_observer.metrics import calculate
from critic_observer.models import Batch, Critic
from critic_observer.store import Conflict, Store
from critic_observer.trials import event


def test_atomic_replay_conflict_and_restart(store, critics):
    run_id = "atomic"
    first = Batch.model_validate({"events": [event(run_id, started(critics))]})
    assert len(store.ingest(first)["accepted"]) == 1
    assert len(store.ingest(first)["duplicates"]) == 1
    changed = first.model_copy(deep=True)
    changed.events[0].data.title = "Different review"
    with pytest.raises(Conflict, match="different content"):
        store.ingest(changed)
    with pytest.raises(Conflict, match="missing"):
        submit(store, run_id, invocation(critics[0], "new"), finding("f", "not-started"))
    assert store.run(run_id)["invocations"] == []
    submit(
        store,
        run_id,
        invocation(critics[0], "new"),
        finding("f", "new"),
        finish_inv("new"),
        {"type": "run_finished", "status": "completed", "reason": "all passes finished"},
    )
    reopened = Store(store.path)
    assert reopened.run(run_id)["run"]["status"] == "completed"
    assert len(reopened.run(run_id)["events"]) == 5


def test_version_dependencies_and_lifecycle(store, critics):
    with pytest.raises(Conflict, match="run_started"):
        submit(store, "r", invocation(critics[0], "a"))
    submit(store, "r", started(critics), invocation(critics[0], "a"), finding("f", "a"))
    with pytest.raises(Conflict, match="contiguous"):
        submit(store, "r", finding("f", "a", version=3))
    with pytest.raises(Conflict, match="active"):
        submit(store, "r", {"type": "run_finished", "status": "completed", "reason": "premature"})
    submit(store, "r", invocation(critics[1], "b", 1))
    verdict = dict(
        type="verdict_recorded",
        invocation_id="b",
        finding_id="f",
        finding_version=2,
        verdict="DISAGREE_CONCERN",
        rationale="Need proof",
    )
    with pytest.raises(Conflict, match="Finding/version"):
        submit(store, "r", verdict)
    submit(store, "r", finding("f", "a", version=2), verdict)
    with pytest.raises(Conflict, match="same defect|Unknown issue|merged|Unknown"):
        submit(
            store,
            "r",
            {
                "type": "issues_merged",
                "source_issue_id": "f",
                "target_issue_id": "missing",
                "reason": "same defect",
            },
        )
    submit(store, "r", finish_inv("a"))
    with pytest.raises(Conflict, match="before finishing"):
        submit(store, "r", finding("late", "a"))


def test_revision_keeps_original_discovery_credit(store, critics):
    submit(
        store,
        "revised",
        started(critics),
        invocation(critics[0], "origin"),
        finding("f", "origin"),
        finish_inv("origin"),
        invocation(critics[1], "comparison"),
        finish_inv("comparison"),
        invocation(critics[1], "editor", 1),
        finding("f", "editor", version=2),
    )
    submit(store, "revised", judge("f"), actor="operator")
    metrics = calculate(store.snapshot(), store.critics())
    by_critic = {c["critic_id"]: c for c in metrics["critics"]}
    assert by_critic[critics[0]]["unique_valid_discoveries"] == 1
    assert by_critic[critics[1]]["valid_issues"] == 0
    assert metrics["rounds"][0]["valid_new_issues"] == 1


def test_measurements_preserve_credit_and_do_not_treat_agreement_as_truth(store, critics):
    a, b, lead = critics
    submit(
        store,
        "r",
        started(critics),
        invocation(a, "a"),
        invocation(b, "b"),
        invocation(lead, "lead"),
        finding("shared-a", "a"),
        finding("false", "a"),
        finding("shared-b", "b"),
        finding("unique-b", "b"),
        finding("disputed", "lead"),
        {
            "type": "issues_merged",
            "source_issue_id": "shared-b",
            "target_issue_id": "shared-a",
            "reason": "Same trigger and failure",
        },
        finish_inv("a"),
        finish_inv("b"),
        finish_inv("lead"),
    )
    first_challenge = None
    independent = calculate(store.snapshot(), store.critics())
    pair = next(p for p in independent["pairs"] if {p["left"], p["right"]} == {a, b})
    assert pair["disagreement_rate"] is None
    assert pair["compared"] == 0
    assert pair["discovery_overlap"] == 1 / 3
    assert pair["shared_discoveries"] == 1
    assert pair["combined_discoveries"] == 3
    assert pair["common_independent_runs"] == 1
    assert pair["run_ids"] == ["r"]
    for round_no in (1, 2):
        ai, bi = f"a{round_no}", f"b{round_no}"
        batch = submit(
            store,
            "r",
            invocation(a, ai, round_no),
            invocation(b, bi, round_no),
            dict(
                type="verdict_recorded",
                invocation_id=ai,
                finding_id="disputed",
                finding_version=1,
                verdict="AGREE",
                rationale="Supported",
            ),
            dict(
                type="verdict_recorded",
                invocation_id=bi,
                finding_id="disputed",
                finding_version=1,
                verdict="DISAGREE_CONCERN",
                rationale="Unsubstantiated",
            ),
            finish_inv(ai),
            finish_inv(bi),
        )
        if round_no == 1:
            first_challenge = batch.events[3].event_id
    submit(
        store,
        "r",
        judge("shared-a"),
        judge("false", "invalid"),
        judge("unique-b"),
        {
            "type": "outcome_recorded",
            "issue_id": "shared-a",
            "state": "fixed",
            "rationale": "Owner check added and reproduced",
            "reference": "fix-123",
        },
        {
            "type": "challenge_judged",
            "verdict_event_id": first_challenge,
            "result": "upheld",
            "effect": "improved_evidence",
            "assessor": "Operator",
            "evidence": "A reproduction was missing",
        },
        actor="operator",
    )
    result = calculate(store.snapshot(), store.critics())
    assert result["overview"]["raw_findings"] == 5
    assert result["overview"]["distinct_issues"] == 4
    assert result["overview"]["valid_issues"] == 2
    assert result["overview"]["unjudged_issues"] == 1
    stats = {c["critic_id"]: c for c in result["critics"]}
    assert stats[a]["validity_rate"] == 0.5
    assert stats[a]["unique_valid_discoveries"] == 0
    assert stats[b]["valid_issues"] == 2
    assert stats[b]["unique_valid_discoveries"] == 1
    assert stats[b]["upheld_challenges"] == 1
    assert result["pairs"][0]["compared"] == 1
    assert result["pairs"][0]["conflicts"] == 1
    assert result["overview"]["usage"]["complete_cost_usd"] is None
    assert stats[a]["cost_per_valid_issue"] is None
    assert result["rounds"][0]["valid_new_issues"] == 2
    assert result["overview"]["outcomes"] == {"fixed": 1}
    assert stats[a]["outcomes"] == {"fixed": 1}
    assert stats[b]["outcome_coverage"] == 0.5
    submit(
        store,
        "r",
        {
            "type": "outcome_recorded",
            "issue_id": "shared-a",
            "revision": 2,
            "state": "reopened",
            "rationale": "Follow-up execution showed the fix was incomplete",
            "reference": "follow-up-124",
        },
        actor="operator",
    )
    revised = calculate(store.snapshot(), store.critics())
    assert revised["overview"]["outcomes"] == {"reopened": 1}
    assert (
        len([e for e in store.run("r")["events"] if e["data"]["type"] == "outcome_recorded"]) == 2
    )


def test_authentication_operator_boundary_and_body_limit(live_server):
    app, client, settings = live_server
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/dashboard").status_code == 401
    writer = {"Authorization": f"Bearer {settings.ingest_token}"}
    assert client.get("/api/dashboard", headers=writer).status_code == 403
    critics = client.get("/api/critics", headers=writer).json()
    batch = {"events": [event("auth", started([critics[0]["id"]])), event("auth", judge("f"))]}
    assert client.post("/api/events", headers=writer, json=batch).status_code == 403
    assert app.state.store.snapshot()["runs"] == []
    assert client.post("/api/login", json={"token": settings.admin_token}).status_code == 200
    assert (
        client.post(
            "/api/login", headers={"X-Observer-Request": "1"}, json={"token": "雪" * 32}
        ).status_code
        == 401
    )
    assert "HttpOnly" in client.cookies.jar._cookies["127.0.0.1"]["/"]["observer_session"]._rest
    assert client.post("/api/critics", json={}).status_code == 403
    csrf = {"X-Observer-Request": "1"}
    assert (
        client.post(
            "/api/critics", headers={**csrf, "Origin": "https://evil.invalid"}, json={}
        ).status_code
        == 403
    )
    assert client.post("/api/events", headers=writer, content=b"x" * 2_000_001).status_code == 413
    assert client.get("/api/schema", headers=writer).status_code == 200


def test_durable_outbox_and_online_backup_restore(live_server, tmp_path):
    app, client, settings = live_server
    critics = app.state.store.critics()
    reporter = Reporter(settings.public_url, "wrong" * 10, tmp_path / "outbox")
    batch = {"events": [event("outbox", started([critics[0]["id"]]))]}
    with pytest.raises(DeliveryError, match="Unsent data"):
        reporter.send(batch)
    pending = list(reporter.directory.glob("*.json"))
    assert len(pending) == 1 and "wrongwrong" not in pending[0].read_text()
    reporter.token = settings.ingest_token
    assert reporter.flush()["delivered_batches"] == 1
    assert app.state.store.run("outbox")["run"]["status"] == "running"
    admin = {"Authorization": f"Bearer {settings.admin_token}"}
    response = client.get("/api/backup", headers=admin)
    assert response.status_code == 200
    backup = tmp_path / "backup.sqlite3"
    backup.write_bytes(response.content)
    restored = tmp_path / "restored.sqlite3"
    restore_database(backup, restored)
    assert Store(restored).run("outbox")["run"]["status"] == "running"
    with pytest.raises(ValueError, match="already exists"):
        restore_database(backup, restored)


def test_critic_versions_and_deleted_run_remove_measurements(store, critics):
    first = store.critic(critics[0])
    document = {k: v for k, v in first.items() if k not in {"id", "created_at"}}
    assert store.register_critic(Critic(**document))["id"] == first["id"]
    revised = store.register_critic(Critic(**{**document, "prompt": "A different role question"}))
    assert revised["id"] != first["id"]
    submit(store, "delete", started(critics), invocation(critics[0], "a"), finding("f", "a"))
    submit(store, "delete", judge("f"), actor="operator")
    store.delete_run("delete")
    assert calculate(store.snapshot(), store.critics())["overview"]["valid_issues"] == 0


def test_real_mcp_protocol_collection_and_replay(live_server):
    _, _, settings = live_server

    async def verify():
        import httpx

        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {settings.ingest_token}"}
        ) as client:
            async with streamable_http_client(
                settings.public_url + "/mcp", http_client=client
            ) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    assert {"record_review_events", "register_critic", "get_experiment_brief"} <= {
                        t.name for t in tools.tools
                    }
                    critics = await session.call_tool("list_critics", {})
                    definitions = json.loads(critics.content[0].text)
                    # FastMCP list results may be split into one text block per element.
                    first = definitions[0] if isinstance(definitions, list) else definitions
                    batch = Batch.model_validate(
                        {"events": [event("mcp", started([first["id"]]))]}
                    ).model_dump(mode="json")
                    result = await session.call_tool("record_review_events", {"batch": batch})
                    assert not result.isError
                    replay = await session.call_tool("record_review_events", {"batch": batch})
                    assert not replay.isError
                    value = replay.structuredContent or json.loads(replay.content[0].text)
                    assert len(value["duplicates"]) == 1
                    detail = await session.call_tool("get_review", {"run_id": "mcp"})
                    assert not detail.isError
                    assert "judgments" not in (detail.structuredContent or {})

    asyncio.run(verify())
