# Select and test a critic team

Use this catalog with the selected review guide and
[review principles](../REVIEW-PRINCIPLES.md). Reusable definitions live in
[builtin_critics.json](../src/critic_observer/builtin_critics.json). They are
candidate prompts, not a ranking or proof of effectiveness. Registering a
definition does not launch it.

## Default team and active experiments

Select the team by review type. Architecture has its own starting team below;
PR observations do not establish which team works best on architecture.

For implementation reviews that warrant multiple perspectives, use this default core:

- General reviewer
- Evidence auditor
- Failure analyst

Intent checker may replace General reviewer when the review primarily checks
requirements. Keep that substitution explicit in the invocation scope.
Choose team adjustments according to the requested scope, and record the reason
for any substitution.

The experimental additions cover:

- **Concurrency reviewer:** races, shared state, ordering and overlapping work.
- **Data integrity reviewer:** transactions, persisted invariants, identity and
  recovery consistency.

Add both to the core for applicable reviews during this rotation. This means
five independent passes, not five simultaneous workers; run at most three at
once unless the user specifies otherwise. Preserve the same frozen target and
give each only its own prompt and brief. If an experimental specialty has no
applicable scope, disclose it as skipped rather than manufacturing a pass.
Respect user limits, and keep trivial reviews proportionate to the guide.
Security or Privacy may still be needed for a relevant trust-boundary change;
the experiment does not replace required checks.

Use the existing automatic collector reporting for actual participation. Keep
the two experimental definitions distinct from the core, register actual
provider/model/settings, and record scope, completion, claims, merges and
decisions. Ordinary reviews use `production`; controlled historical trials use
`benchmark`. Do not invent usage or create benchmark runs merely to activate
this policy. Compare each addition's marginal supported discoveries on the
same cases, with unresolved claims and missing usage visible. Select specialties
using matched-case results and independent assessments.

## Catalog

### Architecture starting team

For an architecture, design document, implementation plan, or existing system's
architecture, start with four architecture-specific definitions:

- **Architecture requirements tracer** maps goals and constraints to decisions.
- **Architecture boundary reviewer** checks responsibilities, contracts, ownership
  and whether a simpler design meets the constraints.
- **Architecture failure analyst** traces partial failure and recovery across components.
- **Architecture reality checker** checks design claims against code, configuration
  and evidence, and identifies assumptions that need verification.

This is a promising starting hypothesis based on the work each role covers,
not an observed architecture winner. Run at most three workers concurrently.
Keep the PR core and its Concurrency/Data integrity rotation separate; those
additions are not automatically required for architecture. Add Security, Privacy,
Operations or another specialist when the target warrants it, stating why.
Respect explicit budget limits and disclose omitted perspectives.

Freeze the architecture documents, relevant code/configuration revision, goals,
constraints and available evidence for all passes. Record actual architecture
reviews as `review_type=architecture`, `dataset=production`, with their own run
IDs even when a PR review covers the same repository or commit. Record discovery,
merges, decisions, challenges, completion and available usage through the same
collector. Use `benchmark` only for controlled trials. Compare architecture
teams only on shared architecture cases; do not pool their results with PRs or
carry a PR winning label into this cohort. Reuse these exact definitions and
put the actual design brief in invocation scope.

### Implementation candidates

| Critic | Specialty | Useful when |
| --- | --- | --- |
| General reviewer | General review | Broad baseline for comparisons; unfamiliar change scope. |
| Intent checker | Requirements | Acceptance criteria or behavior may drift from the request. |
| Bug hunter | Bug hunting | Logic, transformations, boundary inputs, and error paths change. |
| Security reviewer | Security | Trust boundaries, input handling, permissions, or credentials change. |
| Privacy reviewer | Privacy | Sensitive data collection, logging, export, retention, or deletion changes. |
| Failure analyst | Failure handling | Partial failures, retries, interruption, or recovery can change state. |
| Concurrency reviewer | Concurrency | Concurrent requests or workers share resources or state. |
| Data integrity reviewer | Data integrity | Persistence, migrations, transactions, or identity invariants change. |
| Boundary explorer | Boundaries and integration | Callers and consumers outside the diff can be affected. |
| Evidence auditor | Evidence and testing | Test coverage or the evidence for a claimed fix matters. |
| Performance reviewer | Performance | Data volume, I/O, blocking, or resource growth matters. |
| Compatibility reviewer | Compatibility | Older clients, data, configuration, upgrades, or rollback matter. |
| Operations reviewer | Operations | Deployment, readiness, monitoring, restart, or recovery changes. |
| Conventions reviewer | Conventions | Written project rules or competing sources of truth matter. |
| Counterexample seeker | Counterexamples | Assumptions need a perspective different from the initial approach. |
| Accessibility reviewer | Accessibility | User interactions, keyboard flow, semantics, or focus change. |

## Assemble a small team before review

The lead names a small team and explains its fit to the changed behavior before
launching independent passes. Start from the default core and active additions
above; use General as the control when comparing prompts. Do not launch the
whole catalog. Security and privacy checks in the principles still apply when
no dedicated specialist is selected. Follow explicit user limits on agents,
models, time, or scope. If separate agents are unavailable, report sequential
perspective passes honestly rather than calling them independent contexts.

Give each selected worker its actual reusable prompt and the same frozen target
and goal. Put paths, PR numbers, revisions, and constraints in invocation scope,
not critic definitions. Keep independent workers blind to other findings. A
specialist may identify a serious issue outside its specialty, but should say
which scope it inspected. Record blocked or skipped work and coverage gaps.

The lead collects findings, checks evidence, and merges underlying duplicates
without erasing co-discovery credit. A critic may then act as a challenger:
specialty describes what it checks, while phase and context describe how it
participates. Register the actual provider, model, and settings, and preserve
unknown usage. Read [recording.md](recording.md) for delivery and attribution.

## Compare a few candidates at a time

Freeze base/head, goal, skill revision, prompts, and execution conditions for
each pilot. Hold model and effort constant when testing specialties; test model
changes separately. Log elapsed time and available runtime usage. Never estimate
subscription charges from API prices or fill missing usage with zero.

Supply each worker only its own brief. A shared manifest containing every
candidate's prompt can leak those instructions into a nominally isolated pass.
Disclose any such exposure and distinguish blindness to earlier findings from
isolation of the tested prompts; do not use a contaminated pass to claim a
causal advantage for one specialty prompt.

Compare distinct underlying issues, reviewer-supported issues, unique
independent discoveries, overlap, unresolved and withdrawn claims, coverage,
failures, and time. Raw issue count rewards noisy reviewers. Reviewer acceptance
and agent reproduction checks remain provisional; independent operator judgments
and recorded fix outcomes establish validated impact in the collector.

The union of independent findings allows descriptive subset comparisons.
These are not separately rerun team experiments and do not establish how a
team behaves after discussion.

Keep the core stable while testing the two active additions. Include different PR types,
known-defect cases and clean controls, and repeat trials before ranking teams.
Evaluate marginal independently validated issues, false alarms, and resource use
on shared cases. Keep an exploration slot so an untested specialist is not
excluded merely because it has no history. Stop adding rounds when the observed
incremental evidence does not justify their cost, while retaining unresolved
risks. Do not declare a winner from one PR or retroactively relabel broad reviews.
