import pytest
from conftest import finding, finish_inv, invocation, judge, started, submit

from critic_observer.metrics import compare_experiment
from critic_observer.models import Experiment
from critic_observer.store import Conflict
from critic_observer.trials import event


def experiment(store, critics):
    return store.create_experiment(
        Experiment.model_validate(
            {
                "name": "Diverse feedback",
                "hypothesis": "Different roles find different defects",
                "skill_revision": "test-v1",
                "primary_metric": "known_defect_recall",
                "variants": [
                    {"id": "base", "name": "Baseline", "critic_ids": [critics[0]]},
                    {"id": "candidate", "name": "Candidate", "critic_ids": [critics[1]]},
                ],
                "cases": [
                    {
                        "id": "case",
                        "title": "Frozen code",
                        "target": "fixture",
                        "target_revision": "sha256:fixed",
                        "instructions": "Review the queue",
                        "known_issues": [
                            {
                                "id": "owner",
                                "title": "Wrong owner completes",
                                "severity": "should_fix",
                                "evidence": "Reproduction: complete as another owner",
                            }
                        ],
                    }
                ],
            }
        )
    )


def trial(store, exp, critic, run_id, variant, number, has_finding):
    submit(
        store,
        run_id,
        started(
            [critic],
            experiment_id=exp["id"],
            variant_id=variant,
            case_id="case",
            trial=number,
            dataset="benchmark",
        ),
        invocation(critic, "i"),
    )
    if has_finding:
        submit(store, run_id, finding("f", "i"))
    submit(
        store,
        run_id,
        finish_inv("i"),
        {"type": "run_finished", "status": "completed", "reason": "done"},
    )
    if has_finding:
        submit(store, run_id, judge("f", known_issue_id="owner"), actor="operator")
    submit(
        store,
        run_id,
        {
            "type": "run_evaluated",
            "assessor": "Operator",
            "evidence": "Compared every finding with frozen ground truth",
        },
        actor="operator",
    )


def test_frozen_trials_matched_cohorts_and_changed_judgment_invalidation(store, critics):
    exp = experiment(store, critics)
    assert "known_issues" not in store.brief(exp["id"], "base", "case")["case"]
    trial(store, exp, critics[0], "base1", "base", 1, False)
    trial(store, exp, critics[1], "candidate2", "candidate", 2, True)
    result = compare_experiment(exp, store.snapshot())
    assert result["matched_trials"] == 0
    assert all(v["known_defect_recall"] is None for v in result["variants"])
    trial(store, exp, critics[1], "candidate1", "candidate", 1, True)
    result = compare_experiment(exp, store.snapshot())
    assert result["matched_trials"] == 1
    assert result["variants"][0]["known_defect_recall"] == 0
    assert result["variants"][1]["known_defect_recall"] == 1
    assert result["comparisons"][0]["difference"] == 1
    with pytest.raises(Conflict, match="already has a run"):
        trial(store, exp, critics[1], "duplicate", "candidate", 1, True)
    submit(store, "candidate1", judge("f", "unknown", revision=2), actor="operator")
    assert compare_experiment(exp, store.snapshot())["matched_trials"] == 0


def test_trial_revision_and_truth_access_boundaries(live_server):
    app, client, settings = live_server
    critics = [c["id"] for c in app.state.store.critics()]
    exp = experiment(app.state.store, critics)
    writer = {"Authorization": f"Bearer {settings.ingest_token}"}
    assert client.get(f"/api/experiments/{exp['id']}", headers=writer).status_code == 403
    brief = client.get(
        f"/api/experiments/{exp['id']}/brief",
        headers=writer,
        params={"variant_id": "base", "case_id": "case"},
    ).json()
    assert "known_issues" not in brief["case"]
    with pytest.raises(Conflict, match="frozen"):
        submit(
            app.state.store,
            "wrong",
            dict(
                started(
                    [critics[0]],
                    experiment_id=exp["id"],
                    variant_id="base",
                    case_id="case",
                    dataset="benchmark",
                ),
                target_revision="changed",
            ),
        )
    submit(
        app.state.store,
        "members",
        started(
            [critics[0]],
            experiment_id=exp["id"],
            variant_id="base",
            case_id="case",
            dataset="benchmark",
        ),
    )
    with pytest.raises(Conflict, match="frozen variant"):
        submit(app.state.store, "members", invocation(critics[1], "extra"))
    submit(app.state.store, "members", invocation(critics[0], "first"), finish_inv("first"))
    with pytest.raises(Conflict, match="One invocation"):
        submit(app.state.store, "members", invocation(critics[0], "repeat"))
    admin = {"Authorization": f"Bearer {settings.admin_token}"}
    matching = client.get(
        "/api/dashboard",
        headers=admin,
        params={
            "dataset": "benchmark",
            "review_type": "code",
            "experiment_id": exp["id"],
            "variant_id": "base",
        },
    ).json()
    assert matching["metrics"]["overview"]["runs"] == 1
    empty = client.get(
        "/api/dashboard",
        headers=admin,
        params={
            "dataset": "benchmark",
            "review_type": "code",
            "experiment_id": exp["id"],
            "variant_id": "candidate",
        },
    ).json()
    assert empty["metrics"]["overview"]["runs"] == 0


@pytest.mark.parametrize("dataset", ["production", "demo"])
def test_experiment_trials_keep_other_cohorts_empty_on_rejection(live_server, dataset):
    app, client, settings = live_server
    store = app.state.store
    critics = [c["id"] for c in store.critics()]
    exp = experiment(store, critics)
    payload = started(
        [critics[0]],
        experiment_id=exp["id"],
        variant_id="base",
        case_id="case",
        dataset=dataset,
    )
    response = client.post(
        "/api/events",
        headers={"Authorization": f"Bearer {settings.ingest_token}"},
        json={"events": [event("trial", payload)]},
    )
    assert response.status_code == 409
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM events WHERE run_id='trial'").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM runs WHERE id='trial'").fetchone()[0] == 0
    response = client.post(
        "/api/events",
        headers={"Authorization": f"Bearer {settings.ingest_token}"},
        json={"events": [event("trial", payload | {"dataset": "benchmark"})]},
    )
    assert response.status_code == 200
    assert len(store.snapshot({"dataset": "benchmark"})["runs"]) == 1
    assert store.snapshot({"dataset": dataset})["runs"] == []
