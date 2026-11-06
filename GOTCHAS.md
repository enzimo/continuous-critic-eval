# Operating constraints and lessons

## Keep live SQLite and queues on local storage

SQLite's database, WAL and shared-memory files must stay together on local
persistent storage. Network filesystems can stall or corrupt concurrent WAL
access. Keep one application process and one pinned Swarm replica, with stop-first
updates. Outbox delivery uses file locks and ordered atomic writes, so its state
also belongs on local storage. See [storage guidance](docs/artifact-storage.md).

## Keep definitions reusable

Critic definitions contain reusable role instructions. Put the reviewed project's
paths, revisions and task brief in invocation `scope`. Putting the task into a
definition creates one-use identities and prevents meaningful comparisons.

## Recording requires an actual connection

Installing the skill does not install or authorize a collector connection.
Confirm the HTTP or MCP connection and its permitted writes. Keep credentials
and machine-specific reporting profiles outside Git. Record real participation
only; a registered definition does not represent a completed review.

## Preserve event identity and dependencies

Deliver run, invocation, finding version, verdict, decision and completion events
in dependency order. Rejected atomic submissions stay pending. Correct the
underlying schema or ordering problem while retaining event IDs. New verdicts
require an active critique invocation. Do not turn an independent discovery pass
into a critique merely to satisfy storage validation.

## Interpret review metrics carefully

Reviewer acceptance is provisional. It is not an independent correctness judgment.
Unknown usage is null. Failed or blocked reviews cannot establish a clean result.
Issue merges preserve the original discoverers' credit. Keep PR, architecture,
and benchmark cohorts separate and compare teams on matched cases.

Controlled experiment trials use the benchmark dataset. Ingestion validates that
cohort atomically, keeping rejected trial submissions out of every dataset.

## Protect trial isolation

Reviewing a repository must not execute its hooks through inherited client
settings. Use the trial runner's explicit isolation and read-only input modes.
Account-limit detection examines the CLI's error output, not the reviewed text.
Do not retry against paid accounts as part of routine tests.

## Preserve evidence before reporting success

Use real SQLite, HTTP and MCP integration checks. Browser checks need installed
Chromium. Docker and Swarm behavior needs verification in the target hosting
environment. A passing application suite alone does not prove deployment works.
Startup fixtures should allow slow local-disk commits while still exposing
startup exceptions and real timeouts.

`MANIFEST.in` includes test helpers, review guides and synthetic input files so
tests can run from the source distribution. Build the wheel from that
distribution and inspect both outputs.

## Review complete exports before sharing

Run exports include all registered critic and experiment definitions and retain
original events and finding versions. Evidence revisions preserve earlier
versions. Keep exports in private storage and review their complete contents
for the intended recipients. See [data handling](docs/privacy.md).
