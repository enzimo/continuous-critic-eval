"""Operator and portable reporting commands."""

import argparse
import json
import logging
import os
import secrets
import sqlite3
import sys
from pathlib import Path

import httpx

from .client import DeliveryError, Reporter
from .config import secret
from .models import Batch
from .store import Conflict
from .trials import REVIEW_GUIDES, fingerprint, run_trial, skill_material

log = logging.getLogger(__name__)


def output(value):
    sys.stdout.write(json.dumps(value, indent=2) + "\n")


def parser():
    cli = argparse.ArgumentParser(description="Collect and compare evidence from critic reviews")
    cli.add_argument("--server", default=os.getenv("OBSERVER_SERVER", "http://localhost:8000"))
    cli.add_argument(
        "--token-file", type=Path, help="Credential file; otherwise OBSERVER_TOKEN[_FILE]"
    )
    cli.add_argument("--queue-dir", type=Path)
    commands = cli.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    init = commands.add_parser("init", help="Create local credentials without displaying them")
    init.add_argument("--directory", type=Path, default=Path(".local/secrets"))
    submit = commands.add_parser("submit", help="Persist a batch locally, then deliver in order")
    submit.add_argument("bundle", type=Path)
    submit.add_argument("--queue-only", action="store_true")
    commands.add_parser("flush", help="Replay pending batches, stopping on the first error")
    commands.add_parser("queue", help="Inspect pending delivery without reading credentials")
    for name in ("register-critic", "create-experiment"):
        command = commands.add_parser(name)
        command.add_argument("definition", type=Path)
    backup = commands.add_parser("backup")
    backup.add_argument("--output", type=Path, required=True)
    restore = commands.add_parser(
        "restore", help="Restore to a new database path while the service is stopped"
    )
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--database", type=Path, required=True)
    export = commands.add_parser("export")
    export.add_argument("run_id")
    export.add_argument("--output", type=Path, required=True)
    digest = commands.add_parser("fingerprint")
    digest.add_argument("directory", type=Path)
    skill_digest = commands.add_parser("skill-fingerprint")
    skill_digest.add_argument("directory", type=Path)
    skill_digest.add_argument("--review-type", choices=REVIEW_GUIDES, default="code")
    trial = commands.add_parser(
        "trial", help="Run installed agent CLIs against a frozen experiment case"
    )
    for flag in ("experiment", "variant", "case"):
        trial.add_argument("--" + flag, required=True)
    trial.add_argument("--skill-dir", type=Path, required=True)
    trial.add_argument("--trial", type=int, required=True)
    trial.add_argument("--client", choices=["codex", "claude"], required=True)
    trial.add_argument("--workdir", type=Path, required=True)
    trial.add_argument("--timeout", type=int, default=300)
    trial.add_argument("--trace-dir", type=Path)
    trial.add_argument(
        "--codex-file-tools",
        action="store_true",
        help="Codex: no shell; read-only file tools (when its sandbox cannot run here)",
    )
    trial.add_argument("--codex-home", type=Path, help="Codex: isolated CODEX_HOME")
    return cli


def restore_database(source, destination):
    if destination.exists():
        raise ValueError(
            "Restore destination already exists; stop the service and choose a new path"
        )
    # Read-only URI prevents a typo from silently creating an empty source database.
    with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as backup:
        if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Backup failed its integrity check")
        if backup.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ValueError("Backup has an unsupported schema version")
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        with sqlite3.connect(destination) as target:
            backup.backup(target)
    return {"restored": str(destination)}


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s level=%(levelname)s %(message)s")
    args = parser().parse_args(argv)
    try:
        if args.command == "serve":
            import uvicorn

            uvicorn.run(
                "critic_observer.app:create_app",
                factory=True,
                host=args.host,
                port=args.port,
                proxy_headers=False,
            )
            return 0
        if args.command == "init":
            args.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            paths = []
            for name in ("admin_token", "ingest_token"):
                path = args.directory / name
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as file:
                    file.write(secrets.token_urlsafe(48) + "\n")
                paths.append(str(path))
            output({"credential_files": paths})
            return 0
        if args.command == "restore":
            output(restore_database(args.backup, args.database))
            return 0
        if args.command == "fingerprint":
            output({"target_revision": fingerprint(args.directory)})
            return 0
        if args.command == "skill-fingerprint":
            output({"skill_revision": skill_material(args.directory, args.review_type)[0]})
            return 0
        token = (
            args.token_file.read_text().strip()
            if args.token_file
            else "x" * 32
            if args.command == "queue"
            else secret("OBSERVER_TOKEN")
        )
        reporter = Reporter(args.server, token, args.queue_dir)
        if args.command == "queue":
            output(
                {
                    "directory": str(reporter.directory),
                    "pending_batches": len(list(reporter.directory.glob("*.json"))),
                }
            )
        elif args.command == "flush":
            output(reporter.flush())
        elif args.command == "submit":
            batch = Batch.model_validate_json(args.bundle.read_text())
            output(reporter.send(batch, queue_only=args.queue_only))
        elif args.command in {"register-critic", "create-experiment"}:
            path = "/api/critics" if args.command == "register-critic" else "/api/experiments"
            output(
                reporter.request("POST", path, json=json.loads(args.definition.read_text())).json()
            )
        elif args.command in {"backup", "export"}:
            path = "/api/backup" if args.command == "backup" else f"/api/runs/{args.run_id}/export"
            response = reporter.request("GET", path)
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as file:
                file.write(response.content)
            output({"saved": str(args.output)})
        elif args.command == "trial":
            if not 1 <= args.timeout <= 3600 or args.trial < 1:
                raise ValueError("Use a positive trial number and a timeout of 1..3600 seconds")
            result = run_trial(
                reporter,
                args.experiment,
                args.variant,
                args.case,
                args.trial,
                args.client,
                args.workdir,
                args.skill_dir,
                args.timeout,
                args.trace_dir,
                args.codex_file_tools,
                args.codex_home,
            )
            output(result)
            return 0 if result["status"] == "completed" and not result["pending_batches"] else 2
        return 0
    except (OSError, ValueError, RuntimeError, Conflict, DeliveryError, httpx.HTTPError) as exc:
        log.error("command_failed command=%s reason=%s", args.command, exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
