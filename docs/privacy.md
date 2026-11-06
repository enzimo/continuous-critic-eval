# Privacy and data handling

## Data collected by an instance

The application accepts free-text reviewer evidence, prompts, experiment cases,
assessment rationale, critic settings and resource usage. Free-text fields can
contain personal data or confidential source code. Submit minimal, redacted
evidence that the collector is permitted to retain. Validation enforces the
reporting contract; contributors and operators review the content.

Keep operator and ingestion credentials separate. Use ingestion access for review
clients and operator access for adjudication, experiments, backups and other
administrative operations. Review downloaded records before sharing them.

## Exports and evidence versions

The `export_bundle()` implementation includes every registered critic and
experiment. Experiment definitions include case instructions and known-issue
answer keys. The selected run includes all finding versions and original event
documents.

Evidence revisions preserve earlier versions in storage and exports. Treat
exports as private archival records. Prepare a separate dataset containing
approved fields when sharing results.

## Retention and deletion

Operators can delete a run through the authenticated HTTP API. Backups, client
outboxes, model traces and exported files have separate retention
requirements. Critic and experiment definitions also have their own lifecycle.
Apply a retention policy to each location.

Stored evidence is versioned to preserve discovery credit and assessment context.
Keep research originals as required by your retention policy and review each
derived dataset for its intended recipients.

