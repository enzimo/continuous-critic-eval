"""Specialties, immutable compatibility, and evidence-backed unique contributions."""

import pytest
from conftest import finding, finish_inv, invocation, started, submit

from critic_observer.metrics import calculate
from critic_observer.models import Critic
from critic_observer.specialties import specialty_of
from critic_observer.store import identity


def test_optional_specialty_preserves_historical_identity(store):
    old = dict(
        name="Reviewer",
        role="critic",
        prompt="Inspect the work",
        provider=None,
        model=None,
        settings={},
    )
    original = store.register_critic(Critic(**old))
    assert original["id"] == identity("c_", old)
    assert store.register_critic(Critic(**old, specialty=None))["id"] == original["id"]
    security = store.register_critic(Critic(**old, specialty="Security"))
    assert security["id"] != original["id"]
    assert store.critic_summaries(specialty=" security ")[0]["id"] == security["id"]
    assert specialty_of(original) == "General review"
    assert specialty_of({"role": "independent_critic"}) == "General review"
    assert specialty_of({"role": "Bug hunter"}) == "Bug hunting"
    for duty in ("lead", "independent_critic", "reviewer", "   "):
        with pytest.raises(ValueError, match="Specialty must describe"):
            Critic(**old, specialty=duty)


def test_unique_reports_need_comparison_preserve_credit_and_link_evidence(store):
    def critic(name, specialty):
        return store.register_critic(
            Critic(name=name, role="reviewer", specialty=specialty, prompt=f"Inspect {specialty}")
        )["id"]

    security, bugs = critic("Security reviewer", "Security"), critic("Bug hunter", "Bug hunting")
    submit(
        store,
        "r",
        started([security, bugs]),
        invocation(security, "s"),
        invocation(bugs, "b"),
        finding("shared-s", "s", issue="shared"),
        finding("shared-b", "b", issue="shared"),
        finding("security-only", "s"),
        finding("revised", "s"),
        finish_inv("s"),
        finish_inv("b"),
        invocation(bugs, "edit", 1),
        finding("revised", "edit", version=2),
        finish_inv("edit"),
    )
    submit(
        store,
        "solo",
        started([bugs]),
        invocation(bugs, "solo"),
        finding("solo-f", "solo"),
        finish_inv("solo"),
    )
    submit(
        store,
        "blocked",
        started([security, bugs]),
        invocation(security, "s"),
        finding("blocked-f", "s"),
        finish_inv("s"),
        invocation(bugs, "b"),
        {
            "type": "invocation_finished",
            "invocation_id": "b",
            "status": "failed",
            "error": "Cannot inspect",
        },
    )
    m = calculate(store.snapshot(), store.critics())
    rows = {c["critic_id"]: c for c in m["critics"]}
    assert rows[security]["unique_discoveries"] == 2
    assert rows[security]["comparison_reviews"] == 1
    assert rows[security]["report_comparison_reviews"] == 1
    assert rows[security]["exclusive_kept_per_review"] == 0
    assert rows[bugs]["unique_discoveries"] == 0
    assert rows[bugs]["exclusive_issues"] == 0
    assert {r["issue_id"] for r in rows[security]["unique_issue_refs"]} == {
        "security-only",
        "revised",
    }
    assert all(r["independent_comparison"] for r in rows[security]["unique_issue_refs"])
    groups = {g["label"]: g for g in m["groups"]["specialty"]}
    assert groups["Security"]["unique_discoveries"] == 2
    assert groups["Bug hunting"]["unique_discoveries"] == 0
    # A later participant reporting the same underlying defect removes exclusivity.
    submit(
        store,
        "r",
        invocation(bugs, "later", 2),
        finding("cofound", "later", issue="security-only"),
        finish_inv("later"),
    )
    after = calculate(store.snapshot(), store.critics())
    row = next(c for c in after["critics"] if c["critic_id"] == security)
    assert row["exclusive_issues"] == row["unique_discoveries"] == 1


def test_coordinator_is_identified_but_not_a_specialty_group(store, critics):
    submit(
        store,
        "r",
        started(critics),
        {**invocation(critics[0], "lead"), "phase": "lead", "context": "shared"},
        finding("lead-f", "lead"),
        finish_inv("lead"),
        invocation(critics[1], "review"),
        finding("review-f", "review"),
        finish_inv("review"),
    )
    m = calculate(store.snapshot(), store.critics())
    rows = {c["critic_id"]: c for c in m["critics"]}
    assert rows[critics[0]]["responsibilities"] == ["Coordinator"]
    assert rows[critics[1]]["exclusive_issues"] == 1
    assert rows[critics[1]]["unique_discoveries"] == 0
    assert rows[critics[1]]["unique_issue_refs"][0]["independent_comparison"] is False
    assert critics[0] not in m["groups"]["specialty"][0]["critic_ids"]


def test_dashboard_exposes_storage_and_calculation_timing(live_server):
    _, client, settings = live_server
    response = client.get(
        "/api/dashboard", headers={"Authorization": f"Bearer {settings.admin_token}"}
    )
    assert response.status_code == 200
    durations = response.headers["Server-Timing"].split(", ")
    assert [d.split(";")[0] for d in durations] == ["snapshot", "metrics"]
    assert all(float(d.split("dur=")[1]) >= 0 for d in durations)
    assert response.json()["metrics"]["metric_version"] == "1.3"
