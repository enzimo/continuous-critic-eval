"""Exercise catalog registration against real HTTP and persistent critic identity."""

import json
import runpy
from pathlib import Path

import pytest

from critic_observer.client import Reporter
from critic_observer.models import Critic

ROOT = Path(__file__).resolve().parents[1]
REGISTER = runpy.run_path(str(ROOT / "scripts/register_catalog.py"))["register_catalog"]
CATALOG = ROOT / "src/critic_observer/builtin_critics.json"


def test_catalog_registration_is_idempotent_and_runtime_variants_keep_templates(live_server):
    app, _, settings = live_server
    reporter = Reporter(settings.public_url, settings.ingest_token)
    templates = REGISTER(reporter)
    assert REGISTER(reporter) == templates
    assert len(templates) == len(json.loads(CATALOG.read_text()))
    names = ["General reviewer", "Bug hunter", "Security reviewer", "Evidence auditor"]
    variants = REGISTER(reporter, names=names, provider="codex", model="test-model")
    assert REGISTER(reporter, names=names, provider="codex", model="test-model") == variants
    assert {c["name"] for c in variants} == set(names)
    assert {c["id"] for c in variants}.isdisjoint(c["id"] for c in templates)
    definitions = reporter.request("GET", "/api/critics").json()
    for variant in variants:
        actual = next(c for c in definitions if c["id"] == variant["id"])
        assert actual["model"] == "test-model" and actual["provider"] == "codex"
    # Definitions alone must not fabricate historical participation.
    with app.state.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def test_invalid_selection_is_rejected_before_any_registration(live_server, tmp_path):
    _, _, settings = live_server
    reporter = Reporter(settings.public_url, settings.ingest_token)
    before = reporter.request("GET", "/api/critics").json()
    with pytest.raises(ValueError, match="Unknown catalog"):
        REGISTER(reporter, names=["Bug hunter", "Not a critic"])
    with pytest.raises(ValueError, match="provider"):
        REGISTER(reporter, model="missing-provider")
    duplicate = tmp_path / "duplicates.json"
    candidate = Critic(name="Duplicated", role="Security", prompt="Inspect permissions")
    duplicate.write_text(json.dumps([candidate.model_dump(), candidate.model_dump()]))
    with pytest.raises(ValueError, match="duplicate"):
        REGISTER(reporter, catalog=duplicate)
    assert reporter.request("GET", "/api/critics").json() == before
