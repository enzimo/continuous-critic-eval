---
name: project-review-process
description: Review generated work - a pull request or diff, an existing codebase, an architecture or design document or implementation plan, or a failure and its proposed fix. Use when asked to review, audit, or critique code, a PR, a design, or a plan, or to investigate a bug or check whether a fix addresses its cause.
---

# Project Review

Find the problems that matter most: wrong goal, missing evidence, hidden risk,
and work that will be hard to maintain.

## Steps

At the start of a review, check for Critic observer reporting tools, the
machine-configured `critic-observer-report` command, or the persistent reporter
at `~/.codex/critic-observer/report`. If a connection is available, or the user
requests recorded reviews, first read
[references/recording.md](references/recording.md). Otherwise use the guides below
directly.

1. Pick the one guide below that matches what you are reviewing. Read only that
   guide.
2. Read [REVIEW-PRINCIPLES.md](REVIEW-PRINCIPLES.md). Every guide builds on it.
3. Follow the guide. Load [references/critics.md](references/critics.md) before
   selecting reviewers; it defines the default team and active experimental
   additions, with scope and budget exceptions.
4. Report in the format from the principles, section 9.

| Reviewing | Guide |
| --- | --- |
| A pull request or set of changes | [pull-requests/README.md](pull-requests/README.md) |
| An existing codebase | [code/README.md](code/README.md) |
| An architecture, design document, or implementation plan | [architecture/README.md](architecture/README.md) |
| A failure, unexpected behavior, or a proposed fix | [troubleshooting/README.md](troubleshooting/README.md) |

If no guide fits, use the closest one with the principles, and say in the
report which guide you used and what did not fit.

## Notes

- Files named in the guides, such as `AGENTS.md`, `README.md`, and
  `GOTCHAS.md`, mean the files of the project under review.
- This skill's own `AGENTS.md`, `TODO.md`, and `GOTCHAS.md` are for maintaining
  the skill. Do not read them during a review.
