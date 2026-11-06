# Run Critic observer

Critic observer collects structured reviews through HTTP or MCP, serves the
dashboard, and stores history in SQLite. Python 3.13 or newer is required for
local use. Docker is the production runtime. It does not require a hosted model
API key; the optional trial runner uses your already installed agent CLI.
The local reporting/trial CLI currently targets Linux and macOS. Native MCP
clients on other platforms can connect directly to the same server.

## Try it locally

From this repository:

```bash
python3.13 -m venv .venv
.venv/bin/pip install -c requirements.lock -e '.[dev]'
.venv/bin/critic-observer init
```

This creates two private files in `.local/secrets/`. Their contents are not
displayed. Start the server with those files:

```bash
export OBSERVER_ADMIN_TOKEN_FILE="$PWD/.local/secrets/admin_token"
export OBSERVER_INGEST_TOKEN_FILE="$PWD/.local/secrets/ingest_token"
export OBSERVER_DATABASE="$PWD/.local/observer.sqlite3"
export OBSERVER_PUBLIC_URL="http://localhost:8000"
.venv/bin/critic-observer serve --host 127.0.0.1
```

The database must be on local disk. If your checkout or home directory is on NFS
or another network filesystem, set `OBSERVER_DATABASE` to a private local-disk
directory instead. Concurrent SQLite WAL access on NFS can stall or corrupt data.
The Docker stack uses a local volume pinned to one node for this reason.

Open `http://localhost:8000` and sign in with the contents of `admin_token`.
Production history starts empty. Twenty candidate critic definitions are available;
creating a variant saves a new immutable definition.

Architecture reviews use their own [starting team and recording workflow](docs/architecture-reviews.md).
Select Architecture in Review type to see their statistics and experiments.
The website defaults to PRs and never pools review types. Architecture and PR
reviews of the same revision use separate runs. When freezing an architecture
experiment, use `skill-fingerprint PATH --review-type architecture`.

Choose a small team from [the critic catalog](references/critics.md), rather than
launching every candidate. The definitions alone do not run any reviewers.
To publish catalog updates to an already running collector using an existing
private reporting profile:

```bash
rtk proxy python scripts/register_catalog.py
```

The default profile is `~/.codex/critic-observer/reporting.json`; use `--profile`
for another path. Run this in the installed reporting Python environment.
Identical definitions reuse their IDs. To register reproducible runtime variants,
select names with repeated `--critic` arguments and supply `--provider`, `--model`,
and actual JSON `--settings`. The script does not launch or score reviews.

The overview shows what each critic contributed as soon as a review is recorded:
issues raised, issues the reviewer kept or withdrew, issues only that critic
found, and challenges that changed the review. These are provisional (amber).
Use **Assess issues** to judge issues against independent evidence; those
judgments drive the validated (teal) results and show how often the reviewer's
decisions were right. Compare critics by role, by role and model, or by exact
definition. See [docs/measurements.md](docs/measurements.md) for definitions.

Use the ingestion credential for review clients. Use the operator credential
only for the dashboard, adjudication, experiment setup, and backup. Do not put
either credential in a review prompt or commit it.

Both credentials must contain at least 8 characters and must differ. This applies
to environment values and secret files. The initialization command generates
longer random values; existing longer credentials continue to work.

## Connect the skill

Install or link this repository as the `project-review-process` skill in your
CLI's skills directory, as described in [README.md](README.md#install-as-an-agent-skill).
Set the ingestion token in the CLI's environment, then configure its MCP server.

Codex's `config.toml`:

```toml
[mcp_servers.critic_observer]
url = "http://localhost:8000/mcp"
bearer_token_env_var = "OBSERVER_TOKEN"
default_tools_approval_mode = "writes"
```

Claude Code's `.mcp.json`:

```json
{
  "mcpServers": {
    "critic_observer": {
      "type": "http",
      "url": "http://localhost:8000/mcp",
      "headers": {"Authorization": "Bearer ${OBSERVER_TOKEN}"}
    }
  }
}
```

The client must inherit `OBSERVER_TOKEN` from its parent process. For example,
in your own terminal, read the ingestion credential from its private file into
that environment variable before starting the client. The reporting CLI can
instead use `OBSERVER_TOKEN_FILE` or `--token-file` directly. Restart or reload
the client and verify that the collector tools are connected.

Client permissions still apply. The Codex setting above permits read-only tools
and requests approval for writes. For unattended collection, deliberately allow
`record_review_events` and, if needed, `register_critic` in that server's tool
settings. Do not disable approval for unrelated tools. See the official
[Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
Claude likewise needs its normal MCP tool permissions. A connected server alone
does not mean a client has permission to record data.

Then ask:

> Use project-review-process to review this change. Record the review with
> Critic observer, including each critic's findings and verdicts.

The skill's conditional [recording reference](references/recording.md) instructs
the lead to record the run, even when workers cannot access the collector.
It does not modify your client configuration automatically.

After setup, invoking the skill records new reviews automatically whenever its
MCP tools or a machine-configured reporting wrapper are available.
The wrapper binds the existing reporting CLI to a server and a private token
file, so it can also deliver observations in sessions without MCP access. Keep
these machine-specific settings and credentials outside the skill and Git.
The skill can discover the reporter on PATH as `critic-observer-report` or at
`~/.codex/critic-observer/report`. For container installations, keep the complete
private profile, helper, credential, runtime, and outbox in a mounted persistent
directory; an ephemeral PATH launcher must not be the only way to discover it.

## Try a controlled experiment

Create a small pilot using the operator credential:

```bash
.venv/bin/python scripts/create_pilot.py \
  --server http://localhost:8000 \
  --token-file .local/secrets/admin_token \
  --client codex
```

Add `--model YOUR_EXPLICIT_MODEL` for a controlled model comparison. Use
`--client claude` for a separate Claude experiment. The helper registers two
critic configurations and two frozen cases, but does not run or score them.
Its printed IDs are public metadata. The small cases test collection mechanics;
they are not enough to select a generally superior critic.

On a host that cannot run the client's read-only sandbox, explicitly choose
`--input-mode snapshot` when creating the pilot. This freezes a different
experiment that supplies all case files as text, at most 100 UTF-8 files and
128 KB. It does not silently bypass or fall back from the client's sandbox.

Select **Code** in Review type, then open **Experiments** in the UI to see this
code pilot. Each case shows a command for each variant.
On the client machine, run it with the correct working directory and skill
directory, for example:

```bash
.venv/bin/critic-observer \
  --server http://localhost:8000 \
  --token-file .local/secrets/ingest_token \
  trial --experiment EXPERIMENT_ID --variant baseline --case queue-a \
  --trial 1 --client codex --workdir data/benchmarks/queue-a --skill-dir .
```

The runner verifies both content fingerprints, invokes the installed CLI in a
new context, validates its structured output, and records available runtime
usage. It restricts Codex to its read-only sandbox and Claude to read/search
tools. It does not bypass client permissions or choose a fallback model. Local
CLI customizations and provider account restrictions can still affect a trial.
Do not change the inputs while it runs. A failed trial stays failed; increment
the trial number to retry.

Use the same trial number for every variant on a case. Run the control case too.
In **Review runs**, choose the benchmark dataset, open each trial, merge duplicate
issues, and assess validity against independent evidence. **Assess issues** lists
every unjudged issue in the chosen cohort with its claims and evidence. Match known defects
where appropriate, then mark evaluation complete. Only matched evaluated trials
contribute to experiment scores. The answer key is visible to the operator,
never included in a client brief.

## Deploy to Docker Swarm

Follow [deploy/swarm.md](deploy/swarm.md) to configure your registry and service
URL, build and push the image, create Swarm secrets, choose the storage node,
and deploy the single service.

## Verify a development checkout

Dashboard navigation uses the cohort already loaded. Click **Refresh** to see
new reports from other sessions; applying filters and saving judgments also
refresh data. Review details are fetched when opened. If a refresh itself is
slow, inspect the `/api/dashboard` response's `Server-Timing` header and the
`dashboard_slow` server log, which separate snapshot reads from calculations.
SQLite must still be on local disk, including the database and WAL files.

The dashboard and experiment listing default to Pull requests. Select a review
type explicitly when comparing architecture or code reviews. Trial output is
delivered in ordered observation batches, with acquired measurements retained
when validation fails. Oversized atomic submissions are rejected before entering
the outbox; repair pending batches using their stable event IDs.

Use `/healthz` to check the running application version. Critic definitions
identify their specialty, and metric responses include the definition version.
See [metric definitions](docs/measurements.md) for the calculations and cohort rules.

```bash
.venv/bin/ruff check src tests scripts
.venv/bin/ruff format --check src tests scripts
.venv/bin/pytest -q
npm ci --include=dev
npm run format:check
npm run check
```

For the real browser test, install Chromium to a writable location:

```bash
PLAYWRIGHT_BROWSERS_PATH=/tmp/critic-observer-browsers .venv/bin/playwright install chromium
PLAYWRIGHT_BROWSERS_PATH=/tmp/critic-observer-browsers .venv/bin/pytest -m browser -q
```

The main suite uses real SQLite, HTTP, and MCP. Browser checks exercise actual
operator forms, adversarial text rendering, and desktop/mobile layouts. Agent
CLI trials use real accounts and can incur usage; they are explicit commands,
not part of routine automated tests.
