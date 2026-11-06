"""Create a small, frozen benchmark experiment. Does not run or score any critic."""

import argparse
import json
import sys
from pathlib import Path

from critic_observer.client import Reporter
from critic_observer.trials import fingerprint, skill_material


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="http://localhost:8000")
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--client", choices=["codex", "claude"], default="codex")
    parser.add_argument("--model", help="Explicit model for reproducible comparisons")
    parser.add_argument("--input-mode", choices=["filesystem", "snapshot"], default="filesystem")
    args = parser.parse_args()
    reporter = Reporter(args.server, args.token_file.read_text().strip())
    definitions = reporter.request("GET", "/api/critics").json()
    chosen = []
    for name in ("Intent checker", "Counterexample seeker"):
        template = next(c for c in definitions if c["name"] == name and c["provider"] is None)
        definition = {k: v for k, v in template.items() if k not in {"id", "created_at"}}
        definition.update(provider=args.client, model=args.model)
        chosen.append(reporter.request("POST", "/api/critics", json=definition).json()["id"])
    root = Path(__file__).resolve().parents[1]
    instructions = "Review queue.py against README.md. Report concrete, evidenced defects only."
    cases = []
    for key, title in (
        ("queue-a", "Queue case A"),
        ("queue-b", "Queue case B"),
    ):
        path = root / "data/benchmarks" / key
        known = []
        if key == "queue-a":
            known = [
                {
                    "id": "duplicate-resets-claim",
                    "title": "Duplicate enqueue replaces a live claim",
                    "severity": "should_fix",
                    "evidence": "Enqueue x, claim x as a, enqueue x again. "
                    "Its state becomes pending and owner becomes None.",
                },
                {
                    "id": "wrong-owner-completes",
                    "title": "A different worker can complete a claimed job",
                    "severity": "should_fix",
                    "evidence": "Enqueue x, claim x as a, complete x as b. "
                    "The job becomes completed.",
                },
                {
                    "id": "snapshot-mutates-queue",
                    "title": "The returned snapshot can change queue state",
                    "severity": "should_fix",
                    "evidence": "Enqueue x, then snapshot()['x']['state']='completed'. "
                    "The underlying queue changes.",
                },
            ]
        cases.append(
            {
                "id": key,
                "title": title,
                "target": key,
                "target_revision": fingerprint(path),
                "instructions": instructions,
                "known_issues": known,
            }
        )
    experiment = {
        "name": f"Pilot: baseline and diverse team / {args.client}",
        "hypothesis": "Adding a counterexample seeker detects additional contract defects "
        "without adding false alarms on a clean control.",
        "primary_metric": "known_defect_recall",
        "skill_revision": skill_material(root)[0],
        "input_mode": args.input_mode,
        "variants": [
            {"id": "baseline", "name": "Intent checker", "critic_ids": [chosen[0]]},
            {"id": "diverse", "name": "Intent plus counterexamples", "critic_ids": chosen},
        ],
        "cases": cases,
    }
    result = reporter.request("POST", "/api/experiments", json=experiment).json()
    sys.stdout.write(
        json.dumps(
            {
                "experiment_id": result["id"],
                "variants": result["variants"],
                "cases": [
                    {"id": c["id"], "workdir": str(root / "data/benchmarks" / c["id"])}
                    for c in result["cases"]
                ],
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
