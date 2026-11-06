# Review Principles

Shared rules for every review in this repo. Each area guide (pull requests,
code, architecture, troubleshooting) builds on these.

The goal of a review is to find the problems that matter most: wrong goal,
missing evidence, hidden risk, and work that will be hard to maintain. Style
nits and line-level polish come last, if at all.

Check for bugs, regressions, data loss, security weaknesses, and privacy risks.
Examine permissions, secrets, untrusted input, and how personally identifiable
information, PII, is collected, logged, stored, shared, retained, and deleted.

## 1. Start from intent

Meeting the intent matters more than anything else in the review. A finding
that the intent was not met outranks every other finding.

- Find the stated goal: the issue, request, plan, or PR description. If it is
  missing or unclear, write down your best reading of the goal, flag the gap,
  and list the questions the requester needs to answer.
- Judge the work against the goal, not against the author's summary of what
  they did. Generated work often describes itself accurately but solves a
  slightly different problem than the one asked.
- Judge the work against the intent, not against any written plan. Plans
  drift. If the work follows the plan but misses the intent, report that.
- Check for gaps (parts of the goal not addressed) and overreach (changes the
  goal did not ask for).
- When the goal comes with a list of requirements or acceptance criteria, check
  each one and mark it met, partly met, or missing, pointing to where it is met.
  If you cannot point to it, it is not met; a description that restates the
  goal is not evidence.

## 2. Evidence-grounded reviewer–critic pass

Apply this pass only to medium / high complexity reviews. If the change is small or trivial (e.g. an updated visual component), skip this section. Tell me verbally when you are applying the Evidence-grounded reviewer–critic so I know the review might take a while.

1. **Reviewer:** Inspect the diff and relevant surrounding code. Report only concrete, actionable defects. For each finding, include an ID, severity, changed `file:line`, the condition that triggers it, the specific failure or impact, and the code evidence. Mark an unproven possibility as a concern, not a confirmed bug.

2. **Critic:** In a separate critic pass (preferably a separate subagent/context), independently inspect the work and relevant context for missed defects across the shared review scope, then test each draft finding against the evidence. Report concrete failures with their trigger and impact; label unproven risks as concerns. For each finding, use exactly one verdict:
   - `AGREE` — the finding is supported, and there is no additional concrete bug to add.
   - `DISAGREE_EVIDENCE: <file:line or code snippet>` — cite code in the diff that contradicts the finding.
   - `DISAGREE_CONCERN: <specific concern>` — the finding is plausible but not substantiated yet; you cannot point to contradicting code.

   Add any missed bug only when you can support it with specific code evidence.

3. **Reviewer response:**
   - On `AGREE`, preserve the supported findings; do not drop or weaken them merely to converge.
   - On `DISAGREE_EVIDENCE`, revise or withdraw the contradicted claim based on the cited code.
   - On `DISAGREE_CONCERN`, cite code that confirms the bug and keep/strengthen the finding, or cite code that refutes it and withdraw the finding. Do not dismiss it solely as “speculative.”
   - Incorporate any additional bug from the critic if it is independently supported.

4. Repeat for no more than five critic rounds. If a finding remains disputed, report the unresolved point and the evidence on both sides; do not manufacture agreement. Keep the code unchanged throughout the review loop.

5. In the final review, separate supported findings from unresolved concerns. If none are supported, say that none were identified; do not claim the review is therefore bug-free or safe.

## 3. Treat claims as unverified until you see evidence

- "Tests pass", "works end to end", "no behavior change", and "backwards
  compatible" are claims. Look for the command that was run, its output, the
  screenshot, or the log.
- If you can check a claim cheaply, check it. If not, say what evidence would
  settle it.
- Label each conclusion: **verified** (you saw it yourself), **supported**
  (evidence exists but you did not reproduce it), **unverified** (claim only),
  or **contradicted** (evidence says otherwise).

## 4. Big picture first, details second

- First pass: does this make sense as a whole? Right problem, right place in the
  system, right size?
- Second pass: details.
- If the first pass finds a fundamental problem, report it before spending
  effort on line-level issues. A well-polished solution to the wrong problem is
  still the wrong solution.

## 5. Look for what is missing

Reviews are good at critiquing what is present and poor at noticing what is
absent. Ask explicitly whether any of these are missing:

- Tests for the important or risky paths
- Error handling and logging for new failure paths
- Documentation updates for changed behavior or configuration
- Migration and rollback steps for changed data or contracts
- Removal of code, config, or docs that the change made obsolete

## 6. Think in sequences, not single steps

Many serious failures only appear across several steps. Consider:

- Partial failure: step 2 of 3 fails. What state is left behind?
- Retries and repeats: is running it twice safe?
- Restarts mid-way, concurrent runs, and changes in ordering
- Circular dependencies and waits that never end
- Things that grow without a limit: queues, memory, retries, logs, cost

## 7. Common weaknesses of generated work

Generated content fails in recognizable ways. Check for these on every review:

- **References to things that do not exist**: functions, flags, config keys,
  library features, files, or endpoints that look plausible but are not real.
- **Tests that pass without proving anything**: tests that only check mocks,
  run the code without checking the result, assert the code's own output back
  to itself, or were edited to match new
  behavior without explaining why the old behavior was wrong.
- **Silent fallbacks**: catch-all error handling, default values, or retries
  that hide a failure instead of fixing its cause.
- **Symptom fixes**: a fix applied where the error appeared rather than where
  the bad state started.
- **Duplication**: new helpers that repeat existing ones; new patterns that
  ignore project conventions.
- **Scope creep**: unrelated refactors, renames, or reformatting mixed into the
  change.
- **Over-engineering**: abstractions with a single use, configuration options
  nobody asked for.
- **Stale or contradicting text**: docs and comments that describe what the code
  used to do, or that disagree with each other.
- **Overstated progress**: "done", "deployed", or "tested" reported for steps
  that did not happen.

## 8. Review from several perspectives, then combine

- Before reviewing, select a small team from the guide and the
  [critic catalog](references/critics.md), using its default core and active
  experimental additions unless an explicit scope or user constraint applies.
  Name each specialty and explain why
  it fits the change. Give each worker distinct reusable instructions rather
  than launching several copies of a general review. Honor explicit limits on
  agents and disclose omitted perspectives.
- Review from one perspective per pass, each with a distinct question. Each
  area guide suggests roles. With parallel agents, give each a role; without
  them, take the roles one after another rather than checking everything in a
  single read.
- Give at least one reviewer only the goal and the work, not the author's
  reasoning or conversation. A reviewer who shares the author's context tends
  to share its blind spots.
- Stop when a new perspective finds nothing significant; repeating the same
  pass mostly adds nitpicks. After fixes, review the changed parts and what
  they touch again.
- Keep one reviewer (or the lead) responsible for the overall picture: does the
  combination of findings change the overall verdict?
- Before reporting a finding, try to disprove it. Drop findings that do not
  survive. Merge duplicates.
- Check that nothing fell between reviewers: list the changed files, document
  sections, or components that no reviewer commented on. Review them, or
  report them as not checked.

## 9. Report so the reader can act

For each finding, give:

- **What** is wrong, in one sentence
- **Where**: file and line, document section, or component
- **Scenario**: the concrete inputs or steps that lead to the wrong result
- **Severity**: blocking, should fix, or consider
- **Confidence**: verified, likely, or possible
- **Direction**: what a fix would look like (a direction, not necessarily a patch)

Then give an overall verdict, such as: approve, approve with changes, needs
rework, or goal unclear (needs clarification from the requester). State what
was checked and what remains unverified. Redact personal data and secrets from
examples and evidence.

Write in plain language. Order findings from most to least severe.

