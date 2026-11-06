# Deferred Work and Decisions

Use this file to track deferred technical work and unresolved technical decisions that should influence future implementation.
Do not use this file as a generic product backlog, or duplicate record of lessons that belong in `GOTCHAS.md`.

Use `GOTCHAS.md` for lessons learned from failures, side effects, and root-cause discoveries. Use this file for planned revisits, known follow-up work, and technical questions that still need a decision.

Suggested entry format:
- Area
- Item
- Why it was deferred
- Trigger to revisit
- Owner or decision-maker, if known

Suggested sections:
- Open decisions
- Deferred work

## Deferred work

- Area: Collector completeness
- Item: Client lifecycle hooks and richer native telemetry adapters beyond explicit skill reporting and local controlled trials.
- Why it was deferred: The MCP/HTTP contract works across clients now. Each CLI exposes different runtime events and requires verified correlation with a review invocation.
- Trigger to revisit: Missing registrations or native usage prevent a specific operational decision.

- Area: Historical query scale
- Item: Incremental SQL metric projections and paginated cohort exploration for large histories.
- Why it was deferred: The implementation calculates metrics from compact cohort records, and detail queries load only their selected run. Preserve correct definitions before adding caches.
- Trigger to revisit: Measured dashboard latency or memory use becomes unacceptable on the actual history volume.

- Area: Operator access and availability
- Item: Multiple operator identities, scoped project access, and a database service supporting several application replicas.
- Why it was deferred: The requested deployment is one internal collector container. Current credentials distinguish ingestion from operator access; SQLite deployment deliberately uses one pinned replica.
- Trigger to revisit: Multiple independent operators or high availability become requirements.

- Area: Review guides
- Item: Candidate additional guides: documentation review, test-suite review, dependency and security review, UI review.
- Why it was deferred: The first set covers the review types named in the project purpose (code, pull requests, architecture) plus troubleshooting. Further areas should be added when there is a real review to shape them.
- Trigger to revisit: A review that does not fit any existing guide.

- Area: Review guides
- Item: Worked examples and report templates in each guide folder.
- Why it was deferred: The guides should be tried on real reviews first so examples reflect actual use.
- Trigger to revisit: After the guides have been used on a few real reviews.

- Area: Critic grouping
- Item: Operator-managed role aliases, so historical definitions recorded with
  inconsistent roles (for example `critic` and `reviewer`) can be grouped together.
- Why it was deferred: Specialty is now separate from invocation responsibility.
  Broad historical roles remain General review; no prompt-based reclassification
  or mutable alias table was added. This supersedes the earlier role-only grouping.
- Trigger to revisit: Evidence supports a narrower classification of historical
  definitions, or specialty spellings keep diverging.

- Area: Dashboard history
- Item: Trends over time per critic group, and paging beyond the first 200
  queued issues.
- Why it was deferred: Cohort date filters narrow both views for inspection
  and comparison.
- Trigger to revisit: Several weeks of history accumulate, or the queue regularly
  exceeds 200 issues.
