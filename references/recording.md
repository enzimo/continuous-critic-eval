# Record a review with Critic observer

Use this reference when the collector's reporting tools or a configured
reporter are available, or the user requests recorded
reviews. The review principles and selected area guide
still govern the review. Collection adds a record of the work, not a second
review process.

Reporting is automatic when a collector connection is configured. Do not require
the user to request statistics again for each review. Record only work actually
performed; a skipped critic pass stays skipped rather than creating synthetic
invocations to fill a dashboard.

## Connect and register

Prefer the connected MCP server named Critic observer. Read its
`observer://reporting` resource and use `observer://schema` for the exact event
contract. Tool prefixes vary by client; identify tools by their names and
descriptions rather than assuming a provider-specific prefix.

The tools are `list_critics`, `get_critic`, `register_critic`,
`record_review_events`, `get_review`, and `get_experiment_brief`.

A critic definition describes a reusable reviewer, not one task. The dashboard
compares critics by role across many reviews, so a definition that contains one
task's details is used once and never builds a history.

- `specialty`: what this reviewer checks, such as `Security`, `Bug hunting`,
  `Requirements`, `Evidence and testing`, or a new specialty being tested. Keep
  the spelling stable across prompt revisions. Use `General review` for a broad
  review. Do not call a specialty `lead`, `critic`, or `independent critic`.
- `role`: retained for compatibility with existing definitions. Keep its label
  stable; new general reviewers may use `reviewer`. Specialty is the comparison
  key. Invocation `phase` separately records responsibility: `lead` coordinates,
  `independent` reviews without earlier claims, and `critique` challenges claims.
- `name`: a short label for this version, such as `Bug hunter (Claude, high
  effort)`. Do not include project names, PR numbers, dates, or round numbers.
- `prompt`: the reusable role instructions only.
- `provider`, `model`, and `settings`: the actual configuration.

Put the task-specific brief in each invocation's `scope`: target, paths,
revisions, focus areas, and constraints. The definition prompt and the scope
together record what the critic was actually told, so nothing is substituted.
Rounds belong in the invocation's `round`, not in the critic name.

Before registering, call `list_critics` with the specialty to find an existing
definition; it returns short summaries, most-used first. Use `get_critic` for a
full prompt. Re-registering an identical definition returns its existing ID.
Unknown provider, resolved model, or usage remains unknown.

During a rolling client/server update, check the connected tools' input schemas.
Collectors before 0.1.2 do not accept `specialty` in registrations or list filters.
For those collectors, keep a specific specialty name in `role`, omit the new
field, and filter by `role`. Continue recording workflow duties in invocation
`phase`. Report that the collector needs upgrading; do not send unsupported
fields, guess a specialty, or replace it with a generic duty label.

The lead owns collection for the run and collates results from worker contexts.
Select actual reviewer specialties suited to the target from the guide. Tell
each worker its reusable specialty instructions and record that specialty.
Use the [candidate catalog](critics.md) to choose a small explicit team before
launching work; templates are not evidence that those specialists participated.
Registering a definition alone does not perform a review. Do not fabricate
specialist passes or retrospectively label a broad review as a specialist.
Workers need not have credentials or access to the collector. Pass them their
invocation ID and ask them to return structured findings or exact-version
verdicts. Avoid giving initial independent passes the earlier reviewers' claims.

## Record the review as it happens

1. Create a unique run ID and send `run_started` before starting review work.
   Record the project, review type, frozen target revision, skill revision,
   client, dataset, complexity, and expected critic IDs. Use `production` for
   actual project reviews and `benchmark` only for controlled evaluation cases.
   An architecture review uses `review_type=architecture` and its own run ID,
   even if the same revision also has a PR review. Freeze the design documents
   and relevant code/configuration together. Select the architecture starting
   team in [critics.md](critics.md); keep its statistics separate from PRs.
2. For each pass send `invocation_started` before its results, with the
   task-specific brief in `scope`. Independent
   discovery uses phase `independent`, round `0`, context `independent`.
   Critique uses phase `critique`, rounds `1` through `5`, and the actual context
   exposure. Lead work may use phase `lead`.
3. Record every concrete claim as `finding_recorded`. Give it a stable finding
   ID, issue ID, version starting at 1, invocation ID, title, severity,
   confidence, category, location, trigger, impact, and evidence. Redact secrets
   and personal data. Evidence need not include entire files or conversations.
4. Each critic assessment is `verdict_recorded`, referencing the exact finding
   ID and version. Use the existing `AGREE`, `DISAGREE_EVIDENCE`, and
   `DISAGREE_CONCERN` distinctions. An evidence disagreement needs contradicting
   evidence. Record missed concrete defects as new findings.
5. Record the reviewer's response to every claim as `decision_recorded`, with a contiguous
   decision revision, state `supported`, `withdrawn`, or `unresolved`, reason,
   and evidence. Revise a claim with the same finding ID and the next finding
   version in a new active invocation when needed. Discovery credit remains
   with the original finding's author, while the revision author is recorded.
6. Merge duplicate underlying issues explicitly with `issues_merged`, after
   checking they describe the same trigger and failure. Preserve independent
   co-discovery. Merge before the operator judges either issue. Semantic
   matching is an explicit review decision, not a string similarity heuristic.
7. Finish every invocation with `invocation_finished`, including failed and
   cancelled passes. Record runtime usage only when supplied by a reliable
   client or provider. Do not estimate tokens from prose or call API-equivalent
   estimates billed subscription costs.
8. End with `run_finished` and its reason. Keep unresolved concerns and absent
   reviewers visible in the final report, including any skipped critic pass.
   Do not change the reviewed code during the review loop.

Keep event IDs stable across retries. A batch commits completely or not at all.
Deliver dependencies in order: run, invocation, finding version, verdict and
decision, invocation finish, run finish. A conflict identifies a missing
dependency or incorrect version. Correct it rather than claiming the data saved.

Operator-only events are `issue_judged`, `challenge_judged`, `outcome_recorded`,
`run_evaluated`, and `run_invalidated`. Do not use the agent's agreement as independent truth, or
write operator judgments using an operator credential. The operator can add
human assessments and reproduction evidence later in the UI.

## If delivery fails

Continue the authorized review and clearly report the collection failure. Save
the unsent events with their original IDs in a private JSON bundle. Use the
installed reporting client when available:

```bash
critic-observer --server "$OBSERVER_SERVER" submit review-events.json
critic-observer --server "$OBSERVER_SERVER" flush
```

The CLI reads `OBSERVER_TOKEN` or `OBSERVER_TOKEN_FILE`, writes the bundle to a
private local outbox before delivery, and retains it on failure. It never puts
credentials in the event bundle. Check command results; a tool call in a
conversation does not establish that the collector committed it.

Some installations provide a machine-configured wrapper around the same CLI,
either `critic-observer-report` on PATH or `~/.codex/critic-observer/report`.
When either exists, use its actual path for `register-critic`,
`submit`, `flush`, and `queue` without supplying a server or credential. Its
private local configuration owns those settings. This also lets a lead record
results when the current client has not loaded its MCP connection yet. If no MCP
schema is available, the reporting contract is defined in
[models.py](../src/critic_observer/models.py). Use stable event IDs and private
bundle files with either delivery path.

For container-based clients, the reporter, private configuration, credential,
runtime, and outbox must all reside on persistent mounted storage. A launcher in
`~/.local/bin` alone does not establish that the connection survives recreation.

If neither MCP nor the CLI is configured, tell the user what is missing and
save the requested bundle. Change client configuration only when the user
explicitly requests setup; do not install a global connector as a side effect
of a review. Never invent successful collection. This server cannot discover a
review that never registered itself.

## Controlled experiments

Use `get_experiment_brief` for a frozen case and variant. It excludes the known
defect answer key. Use a new run per case/variant/trial and record its experiment
IDs. Never expose expected defects or prior trial outputs to the independent
critics. The local `critic-observer trial` command verifies the target and skill
fingerprints, runs installed CLI clients in separate contexts, records available
usage, and leaves independent adjudication to the operator.

The trial runner also requires an explicit completed/blocked result and inspected
file paths. An empty findings array without completed inspection is not a clean
review. Experiments freeze either filesystem inspection or direct text snapshots.
Snapshot mode supplies a small verified case directly; it is not an automatic
fallback for blocked tools. An operator can invalidate an unusable result while
retaining its event history and usage measurements.
