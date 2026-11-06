# How to review architecture, designs, and implementation plans

Read [REVIEW-PRINCIPLES.md](../REVIEW-PRINCIPLES.md) first.

## When to use

- Before implementing a design or plan
- When an existing architecture document is updated
- When reviewing the structure of an existing system, including document drift

Review the system's decisions and constraints, including the code needed to
check them. A PR review of a change is a separate review, even at the same revision.

## What to gather

- Goals, stakeholders, required behavior, quality constraints and non-goals
- The frozen design or plan and relevant code/configuration revision
- Component responsibilities, dependency and data flows, ownership and contracts
- Workload assumptions, deployment, trust boundaries and failure/recovery requirements
- Decision rationale, rejected alternatives and available operational evidence

List missing inputs. Do not replace absent requirements with reviewer preferences.

## Questions to answer

- Can the proposed responsibilities and contracts satisfy the stated requirements?
- Who owns each state transition and data invariant across component boundaries?
- What happens after partial failure, interruption, retry, restart and restoration?
- Do deployment and dependency capabilities support the claims made by the design?
- Which important assumptions have evidence, and how will the others be verified?
- Would a simpler alternative meet the same constraints? Why was it rejected?
- Does the implementation follow the design, or has either become stale?

## Common weaknesses in generated work

- Boilerplate sections that do not apply to this system
- Confident claims about what a library or service can do, without a source
- Numbers (throughput, latency, cost) with no stated basis
- More components than the problem needs
- The difficult part described in one sentence while easy parts get pages
- Security

## Suggested parallel reviewers

Use the four-role [architecture starting team](../references/critics.md#architecture-starting-team):
Architecture requirements tracer, Architecture boundary reviewer, Architecture
failure analyst and Architecture reality checker. The reference defines scope,
budget exceptions and relevant specialist additions. These roles are a starting
hypothesis; the current PR winners have no measured architecture ranking.

Give each worker the same frozen inputs and only its own prompt and brief.
The lead combines evidence and merges duplicate issues while preserving credit.
For recorded reviews, use a separate `architecture` run and the
[recording instructions](../references/recording.md).

## What to report

Use the report format in [REVIEW-PRINCIPLES.md](../REVIEW-PRINCIPLES.md#9-report-so-the-reader-can-act).
Include a separate list of decisions that need the requester's input, each with
the options and a recommendation.
Separate observed design contradictions, missing evidence and unresolved choices.
State what documents, code and operational evidence were actually checked.
