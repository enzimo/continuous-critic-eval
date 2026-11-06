# Continuous Critic Evaluation

Evaluate AI code-review critics using recorded findings, disagreements,
verification results and resource usage. Use the results to compare critic roles
and configurations, understand which reviewers contribute useful discoveries,
and improve review teams through repeatable experiments.

The project combines:

- **Review guides** for code, pull requests, architecture and troubleshooting.
- **Critic observer**, a collector with HTTP and MCP reporting, SQLite storage
  and a dashboard for inspecting findings and comparing critics.
- **Controlled experiments** that freeze review inputs, critic configurations
  and evaluation criteria.

The dashboard distinguishes provisional reviewer decisions from independently
assessed correctness. It tracks discovery credit, overlap, challenges, completion
and available usage. Separate cohorts support comparisons within each review type
and dataset. See [metric definitions](docs/measurements.md).

## Use the review guides

Start with [REVIEW-PRINCIPLES.md](REVIEW-PRINCIPLES.md), then choose one guide.

| Reviewing | Guide |
| --- | --- |
| A pull request or set of changes | [Pull requests](pull-requests/README.md) |
| An existing codebase | [Code](code/README.md) |
| An architecture or implementation plan | [Architecture](architecture/README.md) |
| A failure or proposed fix | [Troubleshooting](troubleshooting/README.md) |

For example, ask an agent to review a change using `REVIEW-PRINCIPLES.md` and
`pull-requests/README.md`. Reports identify concrete triggers, consequences,
locations and evidence, and distinguish verified findings from unresolved concerns.
[The critic catalog](references/critics.md) explains team selection.

## Install as an agent skill

[SKILL.md](SKILL.md) routes an agent to the appropriate guide. Keep one canonical
checkout per machine and link it into each client's skill directory. On Linux or
macOS, from this repository root:

```bash
mkdir -p "$HOME/.claude/skills"
ln -s "$PWD" "$HOME/.claude/skills/project-review-process"
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s "$PWD" "${CODEX_HOME:-$HOME/.codex}/skills/project-review-process"
```

Use a directory junction for clients running directly on Windows. Confirm each
client can read `SKILL.md` and its relative references. For multiple Codex homes,
create a link in each home. Ask the client to use `project-review-process`.

## Run Critic observer

The application requires Python 3.13 or newer and a POSIX environment such as
Linux or WSL. SQLite and lock-based queues need local persistent storage.
Node.js and npm support frontend development checks. Agent CLI trials require
the chosen CLI, its login and available account usage.

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -c requirements.lock -e '.[dev]'
.venv/bin/critic-observer init

export OBSERVER_ADMIN_TOKEN_FILE="$PWD/.local/secrets/admin_token"
export OBSERVER_INGEST_TOKEN_FILE="$PWD/.local/secrets/ingest_token"
export OBSERVER_DATABASE="$HOME/.local/state/critic-observer/observer.sqlite3"
export OBSERVER_PUBLIC_URL="http://localhost:8000"
mkdir -p "$(dirname "$OBSERVER_DATABASE")"
.venv/bin/critic-observer serve --host 127.0.0.1
```

Choose a local database directory appropriate for your filesystem. Open
`http://localhost:8000` and sign in with the generated operator credential.
`init` creates separate operator and ingestion credential files. Use ingestion
access for reporting clients and operator access for the dashboard, judgments,
experiments and backups.

[QUICKSTART.md](QUICKSTART.md) covers MCP setup, reporting permissions, controlled
trials and browser checks. [The deployment guide](deploy/swarm.md) covers Docker,
secrets, one pinned Swarm replica, backup and recovery.

## Data handling

The collector stores submitted prompts, findings, assessor fields and versioned
events. Keep credentials, databases, traces and review outputs in private storage.
Run exports include registered critic and experiment definitions, original events
and finding versions. Review the complete export before sharing it. See
[privacy and data handling](docs/privacy.md) and
[storage guidance](docs/artifact-storage.md).

## Development checks

```bash
.venv/bin/ruff check src tests scripts
.venv/bin/ruff format --check src tests scripts
.venv/bin/pytest -q
npm ci --include=dev
npm run format:check
npm run check
```

The suite primarily uses real SQLite, HTTP and MCP integrations. Browser checks
use an installed Chromium; see `QUICKSTART.md`. Live agent CLI trials run through
explicit commands with the configured accounts.

## Documentation

- [Architecture](docs/architecture.md) and [architecture reviews](docs/architecture-reviews.md)
- [Measurements](docs/measurements.md) and [recording reviews](references/recording.md)
- [Building packages](docs/release.md)
- [Operating constraints](GOTCHAS.md) and [deferred decisions](TODO.md)
- [Development guidance](AGENTS.md) and [UI design](ui/DESIGN.md)

Each review guide uses the same section order: When to use, What to gather,
Questions to answer, Common weaknesses in generated work, Suggested parallel
reviewers, and What to report.

## License

Licensed under the [Apache License, Version 2.0](LICENSE). Package metadata
declares `Apache-2.0`. Dependencies retain their own licenses.
