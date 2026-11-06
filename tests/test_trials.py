import json
from pathlib import Path

import pytest
from conftest import finding, finish_inv, invocation, judge, started, submit

from critic_observer import trials
from critic_observer.client import DeliveryError, Reporter
from critic_observer.limits import LIMIT_REACHED
from critic_observer.metrics import calculate, compare_experiment
from critic_observer.models import Experiment, Usage
from critic_observer.trials import (
    TrialResult,
    codex_usage,
    event,
    fingerprint,
    run_trial,
    skill_material,
)


def two_variant_experiment(app, root, case):
    critics = app.state.store.critics()
    definition = {
        "name": "Blocked check",
        "hypothesis": "Blocked execution is visible",
        "skill_revision": skill_material(root)[0],
        "primary_metric": "valid_issues",
        "variants": [
            {"id": "a", "name": "A", "critic_ids": [critics[0]["id"]]},
            {"id": "b", "name": "B", "critic_ids": [critics[1]["id"]]},
        ],
        "cases": [
            {
                "id": "c",
                "title": "Case",
                "target": "queue",
                "target_revision": fingerprint(case),
                "instructions": "Inspect the code",
            }
        ],
    }
    return app.state.store.create_experiment(Experiment.model_validate(definition))


def test_blocked_review_never_becomes_clean_success(live_server, tmp_path, monkeypatch):
    app, _, settings = live_server
    root = Path(__file__).resolve().parents[1]
    case = root / "data/benchmarks/queue-a"
    experiment = two_variant_experiment(app, root, case)
    blocked = TrialResult(
        status="blocked", inspected_paths=[], limitations=["Sandbox could not start"], findings=[]
    )
    monkeypatch.setattr(
        "critic_observer.trials.execute_critic",
        lambda *args: (blocked, Usage(source="runtime", input_tokens=7, output_tokens=3), None),
    )
    reporter = Reporter(settings.public_url, settings.ingest_token, tmp_path / "outbox")
    result = run_trial(
        reporter, experiment["id"], "a", "c", 1, "codex", case, root, trace_root=tmp_path / "traces"
    )
    assert result["status"] == "failed"
    detail = app.state.store.run(result["run_id"])
    assert detail["run"]["status"] == "failed"
    assert detail["invocations"][0]["status"] == "failed"
    assert detail["invocations"][0]["usage"]["input_tokens"] == 7
    assert compare_experiment(experiment, app.state.store.snapshot())["matched_trials"] == 0


def test_invalidation_retains_audit_but_excludes_quality(store, critics):
    submit(
        store,
        "r",
        started(critics),
        invocation(critics[0], "i"),
        finding("f", "i"),
        finish_inv("i"),
        {"type": "run_finished", "status": "completed", "reason": "done"},
    )
    submit(store, "r", judge("f"), actor="operator")
    assert calculate(store.snapshot(), store.critics())["overview"]["valid_issues"] == 1
    submit(
        store,
        "r",
        {"type": "run_invalidated", "reason": "Required context was unavailable"},
        actor="operator",
    )
    assert calculate(store.snapshot(), store.critics())["overview"]["valid_issues"] == 0
    assert len(store.run("r")["findings"]) == 1
    assert store.run("r")["run"]["evaluation"] is None


def test_outbox_requires_every_acknowledgment(live_server, tmp_path, monkeypatch):
    app, _, settings = live_server
    reporter = Reporter(settings.public_url, settings.ingest_token, tmp_path / "queue")
    critic = app.state.store.critics()[0]["id"]
    reporter.enqueue({"events": [event("ack", started([critic]))]})

    class MissingAck:
        def json(self):
            return {"accepted": [], "duplicates": []}

    monkeypatch.setattr(reporter, "request", lambda *args, **kwargs: MissingAck())
    with pytest.raises(DeliveryError, match="Unsent data"):
        reporter.flush()
    assert len(list(reporter.directory.glob("*.json"))) == 1
    assert not list(reporter.directory.glob("*.tmp"))


def test_codex_runtime_usage_and_missing_measurements():
    assert codex_usage([]) is None
    usage = codex_usage(
        [
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 20, "cached_input_tokens": 10, "output_tokens": 4},
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 5, "cached_input_tokens": 0, "output_tokens": 2},
            },
        ]
    )
    assert usage.input_tokens == 25 and usage.output_tokens == 6 and usage.cache_read_tokens == 10
    assert usage.cost_usd is None


def test_swarm_contract_and_package_payload():
    import yaml

    root = Path(__file__).resolve().parents[1]
    stack = yaml.safe_load((root / "deploy/stack.yml").read_text())
    service = stack["services"]["observer"]
    assert service["deploy"]["replicas"] == 1
    assert service["deploy"]["update_config"]["order"] == "stop-first"
    assert "node.hostname ==" in service["deploy"]["placement"]["constraints"][0]
    assert (
        service["environment"]["OBSERVER_ADMIN_TOKEN_FILE"] == "/run/secrets/observer_admin_token"
    )
    assert service["ports"][0]["mode"] == "host"
    assert all(secret["external"] for secret in stack["secrets"].values())
    assert json.loads((root / "src/critic_observer/builtin_critics.json").read_text())


def fake_cli(monkeypatch, returncode, stdout, captured=None):
    def run(command, **kwargs):
        if captured is not None:
            captured.update(command=command, env=kwargs.get("env"))
        kwargs["stdout"].write(stdout)
        return type("Done", (), {"returncode": returncode})()

    monkeypatch.setattr(trials.subprocess, "run", run)


CRITIC = {"prompt": "Review", "provider": None, "model": None, "settings": {}}


@pytest.mark.parametrize(
    ("client", "returncode", "stdout", "limited"),
    [
        (
            "claude",
            1,
            json.dumps({"is_error": True, "result": "You've hit your 5-hour limit · resets 11am"}),
            True,
        ),
        ("claude", 0, json.dumps({"is_error": True, "result": "Claude AI usage limit"}), True),
        ("claude", 1, json.dumps({"is_error": True, "result": "Tool use failed"}), False),
        (
            "codex",
            1,
            "\n".join(
                json.dumps(e)
                for e in [
                    {"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}},
                    {"type": "turn.failed", "error": {"message": "You've hit your usage limit."}},
                ]
            ),
            True,
        ),
        (
            "codex",
            1,
            "\n".join(
                json.dumps(e)
                for e in [
                    # Review text about rate limits is not an account limit.
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "The rate limit check is wrong"},
                    },
                    {"type": "error", "message": "stream disconnected before completion"},
                ]
            ),
            False,
        ),
    ],
)
def test_account_limits_come_from_cli_errors_only(
    tmp_path, monkeypatch, client, returncode, stdout, limited
):
    fake_cli(monkeypatch, returncode, stdout)
    with pytest.raises(RuntimeError) as failure:
        trials.execute_critic(client, CRITIC, tmp_path, "Goal", tmp_path, 60)
    assert (LIMIT_REACHED in str(failure.value)) is limited


def test_claude_critics_skip_user_and_repository_settings(tmp_path, monkeypatch):
    captured = {}
    result = {"status": "completed", "inspected_paths": ["a.py"], "limitations": [], "findings": []}
    fake_cli(monkeypatch, 0, json.dumps({"structured_output": result}), captured)
    trials.execute_critic("claude", CRITIC, tmp_path, "Goal", tmp_path, 60)
    command = captured["command"]
    assert "--disable-slash-commands" in command
    assert command[command.index("--setting-sources") + 1] == ""
    assert captured["env"]["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    assert command[command.index("--tools") + 1] == "Read,Grep,Glob"


@pytest.mark.parametrize(
    ("paths", "status", "other"),
    [
        (["pkg/mod.py", "pkg", "pkg (grep for x)"], "completed", ["pkg", "pkg (grep for x)"]),
        (["./pkg/mod.py"], "completed", []),
        (["pkg", "missing.py"], "failed", None),
    ],
)
def test_one_real_file_keeps_a_review_and_other_entries_are_reported(
    live_server, tmp_path, monkeypatch, paths, status, other
):
    app, _, settings = live_server
    root = Path(__file__).resolve().parents[1]
    case = tmp_path / "case"
    (case / "pkg").mkdir(parents=True)
    (case / "pkg/mod.py").write_text("x = 1\n")
    experiment = two_variant_experiment(app, root, case)
    result = TrialResult(status="completed", inspected_paths=paths, limitations=[], findings=[])
    monkeypatch.setattr(
        "critic_observer.trials.execute_critic",
        lambda *args: (result, Usage(source="runtime", input_tokens=5, output_tokens=2), None),
    )
    reporter = Reporter(settings.public_url, settings.ingest_token, tmp_path / "outbox")
    output = run_trial(
        reporter, experiment["id"], "a", "c", 1, "codex", case, root, trace_root=tmp_path / "traces"
    )
    assert output["status"] == status
    invocation = app.state.store.run(output["run_id"])["invocations"][0]
    assert invocation["status"] == status
    if other is None:
        assert output["critics"] == []
        assert "No inspected path is a file in the case" in invocation["error"]
    else:
        assert output["critics"][0]["non_file_paths"] == other
