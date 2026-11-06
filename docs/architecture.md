# Critic observer architecture

The collector answers what critics discover, what they correct, and how those
contributions relate to independently assessed review quality. It works with
agent CLIs and MCP clients, without depending on T3 or a model provider API.

## Responsibilities

- `models.py` owns the versioned observation contract. The HTTP and MCP paths
  validate against the same Pydantic models and call the same store operations.
- `store.py` owns accepted event history and relational projections. Event
  insertion and projection changes share a SQLite transaction. Original events
  remain available even when duplicate issues merge or judgments change.
- `metrics.py` calculates measurements from one consistent read transaction.
  It reports the review team's decisions as provisional measures beside the
  operator's independent judgments and never converts one into the other. It
  also builds the queue of issues awaiting judgment.
- `app.py`, `auth.py`, and `mcp_server.py` adapt HTTP, browser sessions, and MCP
  requests. Review clients have ingestion access; operator adjudication and
  benchmark answer keys require the separate operator credential.
- `client.py` writes private event bundles before transmission. The outbox is
  separated by server URL, serialized with a file lock, and replayed in order.
- `trials.py` runs installed CLI clients locally on content-hashed targets.
  The server does not run models, inspect workstations, or execute commands.
- `web/` contains the dark browser UI. No frontend build step or remote asset
  dependency is needed. Node and Prettier are development tools only.

## Identities and revisions

Critic IDs and experiment IDs are SHA-256 hashes of their validated definitions.
An identical definition returns the same ID. A new prompt, model, role, or setting
creates a new definition, preserving historical attribution.

A critic definition is a reusable reviewer. Its optional `specialty` is the
primary grouping key, separately from invocation `phase` and `context`.
Specific historical roles map conservatively to specialties; broad roles remain
General review. Legacy role group responses remain available. An omitted/null
specialty is omitted from identity hashing, preserving old IDs and experiment
memberships. An explicit specialty creates a new immutable definition. JSON
documents need no SQLite schema migration. The task
brief for one review belongs in each invocation's `scope`. Reusable definitions
let comparisons accumulate across reviews; see `GOTCHAS.md`. MCP `list_critics`
returns short summaries ordered by use to keep responses within client limits.
`get_critic` returns one complete definition. The browser's `/api/critics` response
adds `effective_specialty` using the same mapping, without changing the stored
definition or its ID. Variant forms use this value so an unchanged legacy
specialist does not become an explicit General review definition.

The browser loads the cohort once and renders ordinary page navigation locally.
Refresh, filters, and successful mutations reload it; details load on demand.
There is no automatic polling or implicit freshness guarantee. Obsolete refreshes
are aborted, and render generations prevent late responses replacing newer pages.
Dashboard responses include `Server-Timing` for snapshot and calculation. Requests
taking at least one second log both durations and run count for diagnosis.

A run covers one target revision and one skill revision. Experiments additionally
freeze the case inputs, known-defect reference, variant membership, skill
fingerprint, hypothesis, and primary measure. One case/variant/trial combination
can register only one run. Failed trials remain part of the record; use a new
trial number to retry.

Review type selects a separate measurement cohort. Architecture runs are distinct
from PR runs, including at the same revision. The dashboard and experiment-list
HTTP endpoints default to PRs, and the website offers only individual review
types. Experiments freeze type and reject mismatched trials. Legacy experiment
documents imply `code`; omitting that default during identity hashing preserves
their IDs. Trial guidance and skill fingerprints use the selected area's guide.
See [architecture review setup](architecture-reviews.md).

Controlled experiment trials use the `benchmark` dataset. Ingestion validates
that cohort before accepting trial records, keeping experiment observations
separate from production and demonstration runs.

Experiments also freeze filesystem or snapshot input access. Invocations must
belong to the selected variant; a critic may run only once per phase and round.
This prevents extra participants or repeated passes from quietly changing a
comparison. The trial runner verifies the frozen skill and target fingerprints.

Trial critics receive the case and review guidance. Claude trials isolate user
and repository settings, skills,
slash commands or automatic memory; repository settings are excluded because a
reviewed repository's hooks would otherwise run commands during the review.
With
`--codex-file-tools` and `--codex-home`, Codex gets read-only file tools for the
case folder and a home holding only its login. This mode supports environments
where the CLI shell sandbox is unavailable. Both read the repository's `CLAUDE.md` or
`AGENTS.md`, which belong to the code under review. Account limits are recognized
in one place, `limits.py`, from the CLI's error output only, never from review
text; the runner's error then says `account usage limit reached`.

Each pass or critic round has its own invocation ID. Claims have stable finding
IDs with contiguous versions. A later invocation may revise an earlier claim,
but original discovery credit remains with its first invocation. Each version
records its actual revision author. Materially different defects need new issue
IDs rather than revisions of an unrelated claim.

An issue groups claims about the same underlying defect within a run. Duplicate
matching is explicit, with a reason and an event. It is not inferred from title
similarity. Both independent discoverers retain credit. Merge before adjudicating
either issue or recording outcomes; the service rejects ambiguous merges after
those decisions. Evidence export preserves the history. There is currently no
interactive unmerge operation.

## Acceptance and ordering

Every submitted event has a stable ID, run ID, schema version, UTC timestamp,
and typed payload. Identical replay returns a duplicate acknowledgment. Reusing
an ID with different content conflicts. A batch of up to 250 events and 2 MB
commits completely or not at all.

The reporting client checks the compact UTF-8 bytes it will actually send
before writing a new atomic bundle. Oversized caller batches are rejected
without changing the outbox. The trial producer validates its complete result,
then explicitly divides its generated observations into ordered batches within
the byte and event limits. Completion follows all findings. Generic caller
batches are never silently divided. Existing oversized outbox files are not
rewritten automatically; retain their IDs and explicitly repair their grouping.

Ordering checks parse timestamp instants rather than comparing their serialized
strings. Whole-second and fractional-second UTC timestamps remain valid together.
Stored event documents and timestamp precision are unchanged, preserving replay
identity without a database migration.

Deliver dependencies in order. A batch referencing an absent run, invocation,
or finding version is rejected with HTTP 409, not partially accepted or silently
reordered. Correct the dependency and retry the original IDs. The CLI leaves a
rejected bundle at the front of its outbox. Invalid bundles need operator repair;
retaining bad data does not make it deliverable. The outbox holds at most 1,000
batches per server and reports a full queue as an error.

Only active invocations can report claims and verdicts. Revisions use new active
invocations. Completing a run requires its active invocations to have ended.
Failed or cancelled runs retain incomplete participation. Post-review independent
judgments remain possible. Revising an issue judgment invalidates the run's
evaluation-complete marker so benchmark comparisons cannot retain stale scores.

A successful client process is insufficient evidence of a completed review.
Trial outputs declare completed or blocked status, inspected paths, and access
limitations. Blocked reviews retain usage and fail the run. A review counts as
inspected when at least one listed path is a file in the case; other entries,
such as a folder or a path with a note, are logged and returned with the trial
output rather than voiding a real review. Operators can
invalidate an unusable historical result; its claims leave quality calculations
and matched comparisons, while its events and resource use remain visible.

Post-execution validation failures and interruptions retain usage and model
information already returned by the client. Each invocation starts with unknown
measurements, preventing a failed critic from inheriting another critic's usage.

## Trust and data


Ingestion clients may record observations, register critic definitions, and read
sanitized review briefs and observations. MCP deliberately provides no operator
adjudication tools. An agent's ability to authenticate is not independent evidence
that its claim is correct.

The operator can inspect the complete record, manage experiments, independently
judge findings and challenges, record fix outcomes, and export a consistent
database backup. Browser login uses an HttpOnly, SameSite cookie, a request
verification header for mutations, and an exact-origin check. Bearer credentials
are supported for CLI access. Credentials load from environment variables or
Docker secret files, must differ, contain at least 8 characters, and have no
built-in default. Environment loading and directly constructed settings share
the same minimum.

Store redacted, minimal evidence and references rather than entire source trees
or conversations. Local CLI transcripts remain on the client with private file
permissions and are not uploaded as raw transcripts. Retention is an operator
duty. An authenticated operator can delete a run through the HTTP API; backups
and client files require their own retention policy.

## Runtime and deployment

Use one application process and one Swarm replica. SQLite's WAL files and main
database must live together on a local volume. The service also acquires an
exclusive process lock. The stack pins the task to a named storage node and uses
stop-first updates. Losing that node stops the service; it does not transparently
move the database elsewhere. Do not put SQLite WAL storage on NFS or scale the
service to several replicas.

Backups use SQLite's online backup API and verify integrity. Restoration writes
to a new path rather than overwriting a live database. The application supports
database schema version 1 and checks it during startup. Schema changes require
explicit migrations and restoration tests.

HTTP backups stream a temporary file from the database volume, avoiding the
container's memory-backed `/tmp`. Keep room for a second database copy. Normal
request completion removes it; after a process crash, inspect and remove any
abandoned `observer-backup-*` directories while the service is stopped.

The pinned MCP SDK is the supported 1.30 maintenance line. The collector uses its
FastMCP tools, JSON response transport, session lifespan, and host/origin checks.
This avoids hand-written protocol behavior. Re-evaluate the major-version
migration alongside client compatibility tests rather than changing it implicitly.
