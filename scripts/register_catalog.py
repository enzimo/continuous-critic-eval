"""Register reusable critic candidates without running or scoring reviews."""

import argparse
import json
import logging
import sys
from pathlib import Path

import httpx

from critic_observer.client import Reporter
from critic_observer.models import Critic

log = logging.getLogger(__name__)
CATALOG = Path(__file__).resolve().parents[1] / "src/critic_observer/builtin_critics.json"


def register_catalog(reporter, catalog=CATALOG, names=(), provider=None, model=None, settings=None):
    definitions = [Critic.model_validate(d) for d in json.loads(catalog.read_text())]
    available = {d.name for d in definitions}
    if len(available) != len(definitions):
        raise ValueError("Catalog has duplicate critic names")
    if missing := set(names) - available:
        raise ValueError(f"Unknown catalog critics: {sorted(missing)}")
    if model and not provider:
        raise ValueError("An explicit model also needs a provider")
    # Validate the complete selection before mutating the collector.
    selected = []
    for definition in definitions:
        if names and definition.name not in names:
            continue
        data = definition.model_dump()
        data.update(provider=provider, model=model, settings=settings or {})
        selected.append(Critic.model_validate(data))
    registered = []
    for definition in selected:
        log.info("registering_critic name=%s", definition.name)
        result = reporter.request(
            "POST", "/api/critics", json=definition.model_dump(exclude_none=True)
        ).json()
        registered.append({"name": definition.name, "id": result["id"]})
    return registered


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", type=Path, default=Path.home() / ".codex/critic-observer/reporting.json"
    )
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--critic", action="append", default=[])
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--settings", default="{}", help="Actual runtime settings as JSON")
    args = parser.parse_args()
    config = json.loads(args.profile.read_text())
    reporter = Reporter(
        config["server"], Path(config["token_file"]).read_text().strip(), config.get("queue_dir")
    )
    result = register_catalog(
        reporter, args.catalog, args.critic, args.provider, args.model, json.loads(args.settings)
    )
    log.info("registered_catalog definitions=%s", len(result))
    sys.stdout.write(json.dumps({"critics": result}, indent=2) + "\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        main()
    except (OSError, ValueError, RuntimeError, httpx.HTTPError) as exc:
        log.error(
            "catalog_registration_failed error=%s; completed registrations remain saved; "
            "rerunning identical definitions is idempotent",
            type(exc).__name__,
        )
        raise SystemExit(2) from None
