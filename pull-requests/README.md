# How To Review Pull Requests

Read [REVIEW-PRINCIPLES.md](../REVIEW-PRINCIPLES.md) first.

When reviewing a pull request, critically review the stated objective, the
actual implementation, and the provided evidence. Pay attention to potential concurrent reviews happening for other PRs and don't stomp on them. Also make sure the final PR code is still applicable as the overall code may have already been changed by other PRs.

## What to gather

- The PR description and the issue, request, or plan it links to
- The full diff
- Project guidance: `AGENTS.md`, `README.md`, `GOTCHAS.md`, contribution or
  convention docs, and any architecture docs for the area being changed
- Earlier review comments on the PR, so you do not repeat them and can note
  which ones the latest changes resolved

## Questions to answer

### Goal and approach

- Does the PR solve the stated problem, and all of it?
- Given the problem statement and the supplied implementation, what would you do
  differently, and why?
- Is the change in the right place in the system? Does it fix the root cause or
  only the visible symptom?
- Is it the right size? Would it be safer as several smaller PRs?

### Evidence

- Does the provided evidence actually show the goal is met?
- Did CI run the relevant tests? Were any tests skipped, disabled, or deleted? Why?
- Were existing tests changed and was it done appropriately?

### Failure modes

- What logical sequences have not been tested that could break this solution?
  Pay attention to edge cases and multi-step failures (for example, circular
  dependencies, resources that block forever, partial failure followed by a
  retry). Report any issues or edge cases you find.

### Impact beyond the diff

- Who else calls or depends on the changed code? Did any contract change: API,
  database schema, message format, configuration, command-line options?
- What happens with old data, old clients, or an upgrade from the previous
  version?
- Security and privacy: is new input trusted without checks? Are secrets
  handled safely? Were permissions widened?
- Operations: are new failure paths logged with enough context to diagnose?
  Does the change affect performance or cost? Does it add unnecessary or complex dependencies?

### Consistency and upkeep

- Does it follow project conventions and reuse existing helpers?
- Are docs updated for changed behavior or configuration?
- Is code made obsolete by this change removed?
- Are there unrelated changes that should be split out?

## Suggested parallel reviewers

Feel free to launch multiple agents in parallel with their own narrower tasks,
but do not forget the big picture.

| Role | Focus |
| --- | --- |
| Intent checker | Does the diff match the stated goal? Gaps and overreach. |
| Bug hunter | Edge cases, multi-step failures, error handling. |
| Evidence auditor | Do the tests and other evidence prove what is claimed? |
| Impact tracer | Callers, contracts, data, security, and operational effects outside the diff. |
| Conventions reviewer | Lists the project's written rules (`AGENTS.md`, convention docs) and checks each changed file against them; existing patterns. |
| Lead | Combines findings, checks they hold up, and decides the overall verdict. |

## What to report

Use the report format in [REVIEW-PRINCIPLES.md](../REVIEW-PRINCIPLES.md#9-report-so-the-reader-can-act).
Open with a short summary: what the PR is trying to do, whether it does it, and
the verdict.
