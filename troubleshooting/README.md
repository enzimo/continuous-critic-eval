# How To Investigate Failures and Review Fixes

Read [REVIEW-PRINCIPLES.md](../REVIEW-PRINCIPLES.md) first.

This guide covers finding the cause of a failure or unexpected behavior, and
checking whether a proposed fix actually addresses that cause.

## When to use

- Something broke, or behaves differently from what was expected
- A test fails intermittently
- A previous fix did not hold, or the same problem keeps returning
- Someone (or an agent) proposed a fix and it needs a second opinion

## Approach

1. **Describe the symptom precisely.** Expected versus actual behavior, when it
   started, how often it happens, and in which environment.
2. **Gather evidence before forming theories.** Error messages, logs, recent
   changes, and steps to reproduce.
3. **Reproduce it.** If you cannot, say so, and list what differs between the
   environment where it fails and where it works.
4. **List several possible causes.** For each, note what evidence would confirm
   or rule it out. Check the cheapest ones first.
5. **Trace back to where it started.** Find where the bad state first appeared,
   not just where it was noticed. Keep asking "why did that happen?"
6. **Confirm the cause.** Can you make the problem appear and disappear by
   changing only that one thing?
7. **Look for the same problem elsewhere.** Other code with the same pattern may
   have the same flaw.
8. **Propose a fix and a guardrail.** Fix the cause, then add something that
   would catch a recurrence: a test, an input check, an alert, or an entry in
   `GOTCHAS.md`.

## High-level checks that often find the cause

- **What changed?** Code, configuration, dependencies, data, environment,
  external services, and time-based factors (expired certificates, date
  boundaries, quotas that reset).
- **What differs between environments?** Local versus CI versus production:
  environment variables, versions, permissions, network access, data size.
- **Which assumptions no longer hold?** About input shape, ordering, uniqueness,
  or a service always being available.
- **What is the first error?** Retries and fallbacks often hide the original
  failure behind later, misleading ones.
- **What is left over from earlier runs?** Caches, partial migrations, lock
  files, stale builds.
- **Is timing involved?** Concurrency, timeouts, ordering, clock differences.
- **Was a limit reached?** Disk, memory, rate limits, quotas, connection pools.

## Reviewing a proposed fix

- Does the explanation of the cause account for all the observed evidence, or
  only some of it?
- Does the fix change the cause, or does it suppress the symptom (catch the
  error, add a retry, supply a default value)?
- Is there a test that fails without the fix and passes with it?
- If a fallback must remain, is it logged clearly and treated as secondary?

## Suggested parallel reviewers

| Role | Focus |
| --- | --- |
| Timeline builder | What changed and when, lined up against when the problem started. |
| Log analyst | Finds the first error and the sequence of events around it. |
| Hypothesis testers | One per candidate cause; each tries to confirm or rule it out. |
| Pattern searcher | Looks for the same flaw elsewhere in the code. |
| Lead | Decides which cause the evidence supports and checks the proposed fix. |

## What to report

- The symptom, in one or two sentences
- The cause, with confidence and the evidence behind it
- The chain of events from cause to symptom
- The proposed fix and guardrail
- Other places with the same flaw
- Open questions and what was not checked
