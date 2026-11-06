"""Review types separate observations without changing attribution or old identities."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from conftest import finding, finish_inv, invocation, started, submit
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from test_experiments import experiment

from critic_observer.client import Reporter
from critic_observer.models import Experiment
from critic_observer.store import Conflict, Store, identity
from critic_observer.trials import TrialResult, run_trial, skill_material

ROOT = Path(__file__).resolve().parents[1]


def test_http_cohorts_separate_shared_critics_and_survive_reopen(live_server):
    app, client, settings = live_server
    store = app.state.store
    critics = [c["id"] for c in store.critics()][:2]
    for kind, count in (("pull_request", 1), ("architecture", 2)):
        submit(store, kind, started(critics, review_type=kind))
        for i, critic in enumerate(critics):
            submit(store, kind, invocation(critic, f"i{i}"))
        for i in range(count):
            submit(store, kind, finding(f"f{i}", "i0"))
        submit(store, kind, finish_inv("i0"), finish_inv("i1"))
    headers = {"Authorization": f"Bearer {settings.admin_token}"}
    for params, kind, count in (
        ({}, "pull_request", 1),
        ({"review_type": "architecture"}, "architecture", 2),
    ):
        response = client.get("/api/dashboard", headers=headers, params=params)
        assert response.status_code == 200
        data = response.json()
        assert data["filters"]["review_type"] == kind
        assert [r["id"] for r in data["runs"]] == [kind]
        assert data["metrics"]["overview"]["distinct_issues"] == count
        assert data["assessment"]["total"] == count
        assert {i["run_id"] for i in data["assessment"]["items"]} == {kind}
        assert (
            next(c for c in data["metrics"]["critics"] if c["critic_id"] == critics[0])[
                "distinct_issues"
            ]
            == count
        )
    assert (
        client.get("/api/dashboard", headers=headers, params={"review_type": "typo"}).status_code
        == 422
    )
    assert (
        client.get("/api/dashboard", headers=headers, params={"review_type": ""}).json()["metrics"][
            "overview"
        ]["runs"]
        == 2
    )
    reopened = Store(settings.database)
    assert [r["id"] for r in reopened.snapshot({"review_type": "architecture"})["runs"]] == [
        "architecture"
    ]


def test_experiment_type_identity_legacy_ids_and_atomic_rejection(live_server):
    app, client, settings = live_server
    store = app.state.store
    critics = [c["id"] for c in store.critics()]
    old = experiment(store, critics)
    document = {k: v for k, v in old.items() if k not in {"id", "created_at", "review_type"}}
    assert old["id"] == identity("e_", document)
    assert store.create_experiment(Experiment.model_validate(document))["id"] == old["id"]
    architecture = store.create_experiment(
        Experiment.model_validate(document | {"review_type": "architecture"})
    )
    pr = store.create_experiment(
        Experiment.model_validate(document | {"review_type": "pull_request"})
    )
    assert len({old["id"], architecture["id"], pr["id"]}) == 3
    headers = {"Authorization": f"Bearer {settings.admin_token}"}
    assert [e["id"] for e in client.get("/api/experiments", headers=headers).json()] == [pr["id"]]
    for kind, expected in (("architecture", architecture), ("code", old)):
        assert [
            e["id"]
            for e in client.get(
                "/api/experiments", headers=headers, params={"review_type": kind}
            ).json()
        ] == [expected["id"]]
    payload = started(
        [critics[0]],
        experiment_id=architecture["id"],
        variant_id="base",
        case_id="case",
        dataset="benchmark",
    )
    with pytest.raises(Conflict, match="frozen review type"):
        submit(store, "wrong-kind", payload)
    with store.connect() as db:
        assert (
            db.execute("SELECT count(*) FROM events WHERE run_id='wrong-kind'").fetchone()[0] == 0
        )
    submit(store, "right-kind", payload | {"review_type": "architecture"})

    async def verify_brief():
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {settings.ingest_token}"}
        ) as http:
            async with streamable_http_client(
                settings.public_url + "/mcp", http_client=http
            ) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "get_experiment_brief",
                        {
                            "experiment_id": architecture["id"],
                            "variant_id": "base",
                            "case_id": "case",
                        },
                    )
                    assert not result.isError
                    brief = result.structuredContent or json.loads(result.content[0].text)
                    assert brief["review_type"] == "architecture"
                    assert "known_issues" not in brief["case"]

    asyncio.run(verify_brief())


def test_architecture_trial_uses_its_frozen_guide(live_server, tmp_path, monkeypatch):
    from critic_observer.trials import fingerprint

    app, _, settings = live_server
    store = app.state.store
    critics = [c["id"] for c in store.critics()]
    base = experiment(store, critics)
    definition = {k: v for k, v in base.items() if k not in {"id", "created_at"}}
    definition.update(
        review_type="architecture", skill_revision=skill_material(ROOT, "architecture")[0]
    )
    target = tmp_path / "design"
    target.mkdir()
    (target / "design.md").write_text("One service owns persistent state.")
    definition["cases"][0].update(
        target_revision=fingerprint(target), instructions="Review the design"
    )
    exp = store.create_experiment(Experiment.model_validate(definition))
    prompts = []

    def inspect(client, critic, directory, instructions, trace, timeout, *options):
        prompts.append(instructions)
        return (
            TrialResult(
                status="completed", inspected_paths=["design.md"], limitations=[], findings=[]
            ),
            None,
            None,
        )

    monkeypatch.setattr("critic_observer.trials.execute_critic", inspect)
    reporter = Reporter(settings.public_url, settings.ingest_token, tmp_path / "outbox")
    result = run_trial(
        reporter,
        exp["id"],
        "base",
        "case",
        1,
        "codex",
        target,
        ROOT,
        trace_root=tmp_path / "traces",
    )
    assert result["status"] == "completed"
    assert store.run(result["run_id"])["run"]["review_type"] == "architecture"
    assert "architecture/README.md\n" in prompts[0]
    assert "code/README.md\n" not in prompts[0]
    assert skill_material(ROOT, "architecture")[0] != skill_material(ROOT)[0]
