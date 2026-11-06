# How To Review an Existing Codebase

Read [REVIEW-PRINCIPLES.md](../REVIEW-PRINCIPLES.md) first.

This guide covers a health check of an existing codebase. The aim is a
prioritized picture of the biggest risks and cleanup opportunities.

## When to use

- Taking over a codebase, or returning to one after a long gap
- After a long run of agent-generated changes, to catch accumulated drift
- Before a major extension, to find what will get in the way

## What to gather

- `README.md`, architecture docs, `AGENTS.md`, `GOTCHAS.md`, `TODO.md`
- How to build, run, and test the project, and whether those steps work today
- Git history: which files change most often, and which changes were bug fixes.
  Frequently fixed areas are the best place to look first.

## Questions to answer

### Does the code match its description?

- Do the README and architecture docs describe what the code actually does?
- Do the build, run, and test instructions work as written?
- Are documented settings, commands, and features still present?

### Is the structure easy to change?

- Are responsibilities clear, or do some modules do too much?
- Is the same thing done in several different ways (two HTTP clients, three
  config loaders)? Are there opportunities for a shared component?
- Is there dead code, unused configuration, or old compatibility code that no
  longer serves a purpose?

### Are failures visible?

- Are errors swallowed, or replaced with default values, without a log entry?
- Do log messages include enough context (identifiers, inputs) to diagnose a
  problem in production?
- Do fallbacks hide problems that should be fixed at their cause?

### What do the tests actually protect?

- Which important behaviors have no test at all?
- Do the tests exercise real behavior, or mostly mocks?
- Are any tests flaky, skipped, or disabled? Why?
- Do the tests cover behavior that depends on external services, storage, or
  timing, or only isolated units?

### Dependencies and security basics

- Are dependencies pinned, maintained, and actually used?
- Are there secrets in the repository or its history?
- Is external input checked before it is trusted?

## Common weaknesses in generated code

On top of the list in the principles, codebases built over many agent sessions
tend to show:

- Patches layered on patches in the same area, each fixing a symptom of an
  earlier patch
- A new helper added in each session instead of reusing the one from the last
- Docs and comments that were accurate several sessions ago

## Suggested parallel reviewers

| Role | Focus |
| --- | --- |
| Mapper | Describes the actual structure: main components, data flow, entry points. |
| Docs checker | Compares docs and instructions with the code and with real runs. |
| Test auditor | What is covered, what is not, and how trustworthy the tests are. |
| Failure-handling auditor | Swallowed errors, silent fallbacks, missing logs. |
| Dependency and security reviewer | Dependencies, secrets, untrusted input. |
| Lead | Combines findings into a prioritized list. |

## What to report

Use the report format in [REVIEW-PRINCIPLES.md](../REVIEW-PRINCIPLES.md#9-report-so-the-reader-can-act).
Open with:

- The top three risks, in plain language
- Cleanup and consolidation opportunities, ordered by benefit versus effort
- What could not be checked (for example, the project could not be built)
