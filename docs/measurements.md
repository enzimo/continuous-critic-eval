# What the measurements mean

Metric definitions are versioned as `1.3` in responses. Rates include their
counts. Production, benchmark and demonstration datasets are separate by default.
Controlled experiment trials use the benchmark dataset.
Project, client, review type, skill revision, complexity, and date filters select
the cohort before calculations.

The website always selects one review type and defaults to PRs. Architecture
reviews have their own cohorts, assessment queues and experiment lists. A shared
critic definition can participate in both, but its results are calculated only
within the chosen type. Experiments freeze one type and trials must match it.
PR winning teams are not architecture results. API clients that deliberately
need cross-type analysis can explicitly pass an empty `review_type`; omitting
it selects PRs. This changes selection defaults, not metric definitions.

Discovery eligibility requires completion of the original discovery invocation. An empty completed retry by the same critic cannot qualify
a failed origin. Raw authorship, reported exclusivity and independent judgments
remain recorded. Assessment queue verdict counts now include only the latest
version of each claim, matching the detail dialog; older verdicts remain history.

## Two kinds of evidence

Specialty grouping and unique reported-issue evidence support comparisons among
critics. Independent uniqueness requires a discoverer and a different critic
outside the selected group to complete independent passes. Solo reviews no longer
establish independent uniqueness.

The default ranking compares exact definitions by unique reported issues kept.
A unique reported issue has original claims only from this definition or group,
after explicit duplicate merges, and another participant outside the group has
completed a pass in the same review, as has a member of the selected group.
The per-review rate uses only these compared reviews; solo or failed-only passes
do not inflate the sample or depress the rate. It can originate in any review phase.
Raised, reviewer-kept, and independently valid counts remain separate. Each
definition/group dialog lists the source review, issue, decision, validity, and
whether independent comparison was established. Unmerged duplicates can overstate
uniqueness. A recorded exclusive contribution is not proof that others could
not discover it or that it is correct.

Specialty is explicit, for example Security, Bug hunting, or Evidence and testing.
Invocation phase records the coordinator, independent reviewer, or challenger;
context records exposure to earlier claims. Only specific historical roles have
the conservative mapping in `specialties.py`; generic roles remain General review.
Coordinator-only definitions remain in review details, outside specialist rankings.
Specialty and specialty/model groups are available alongside exact definitions;
legacy role groups remain in API responses for compatibility. Zero completed
independent comparisons means independence is unestablished, not poor performance.

Each contribution is reported twice, side by side:

- **Reviewer-accepted (provisional)** measures come from the review team's own
  decisions. They are available as soon as a review is recorded. The dashboard
  shows them in amber.
- **Independently validated** measures come only from the operator's judgments.
  The dashboard shows them in teal.

Provisional measures make recorded work visible while independent judgments are
pending. Validated measures reflect the operator's assessment of correctness.

## Reviewer-accepted measures

- The reviewer state of an issue comes from `decision_recorded` on the latest
  version of its claims: supported if any claim was kept, otherwise withdrawn,
  otherwise unresolved, otherwise undecided. A decision on an older version does
  not apply to a newer revision.
- Kept by reviewer counts issues where the critic's own claims were supported.
  Withdrawn counts issues where they were withdrawn and none was kept. Keep rate
  is kept / kept plus withdrawn.
- Issues per review is distinct issues / reviews with an invocation by the
  critic, excluding invalidated reviews.
- Found only by this critic (kept) uses the same independence rule as unique
  valid discovery: exactly one critic, or only members of the group, found the
  issue in a completed independent pass with independent context, a different
  independent critic outside the group completed a pass, no outside participant
  reported the issue, and the reviewer kept
  it. Issues first raised in critique rounds are not independent discoveries;
  they appear in the round statistics.
- Claimed severity of kept issues uses the most severe claim the critic made on
  each issue. It is the critic's claim, not an adjudicated severity.
- A challenge is a `DISAGREE_EVIDENCE` or `DISAGREE_CONCERN` verdict. Its
  reviewer response is: revised if a later version of the challenged claim
  exists, withdrawn or kept from the decision on the challenged version, and
  pending otherwise. Challenges that changed the review are withdrawn plus
  revised. An upheld challenge still requires an operator judgment.

## Critic groups

Critic definitions are immutable, so a revised prompt creates a new ID. To build
a history across revisions, contributions are also calculated per group:

- **Role** groups definitions whose `role` matches after ignoring case and
  repeated spaces. The group's label uses the most common spelling, or the
  oldest definition's spelling on a tie.
- **Role and model** additionally splits by the definition's model.
- **Exact definition** is the per-definition view.

Group measures use set unions, never sums of member rows. An issue raised by
two members counts once, and a group-unique discovery means no critic outside
the group found the issue independently. Grouping depends on reporters using
stable role names; the recording guide asks them to.

## Reviewer calibration

For every issue with a reviewer state of supported or withdrawn and an operator
judgment of valid or invalid, the decision matches when supported meets valid
or withdrawn meets invalid. The dashboard reports matched / compared and the
full table by state. A high match rate suggests the provisional measures are a
reasonable guide in this cohort; it is not proof for any single issue.

## Assessment queue

The queue lists every distinct issue in the cohort without a valid or invalid
judgment, including issues judged unknown, and excludes invalidated reviews. It
orders by the most severe claimed severity, then the newest review, and returns
at most 200 items with the total count. Agreement and disagreement counts refer
to each claim's latest version, including separate claims merged into one issue.

## Quality and attribution

- Raw findings count distinct claim IDs, not revisions. Distinct issues count
  explicit issue groups. Neither count establishes correctness.
- A critic receives discovery credit through the original invocation of its
  finding, even when another invocation improves its evidence later.
- Valid and invalid counts come from the operator's latest independent judgment.
  Unassessed and unknown judgments remain outside the validity denominator.
- Validity rate is valid / valid plus invalid. Judgment coverage is valid plus
  invalid / proposed distinct issues. Always inspect both rates.
- Impact uses adjudicated severity counts: blocking, should fix, and consider.
  The service does not claim to calculate money saved or harm prevented.
- Outcomes count the latest operator-recorded fixed, deferred, or reopened state
  on valid issues. Team totals count the issue once; credited critics share its
  outcome. Missing outcomes stay unknown. A recorded fix reference does not
  independently prove the patch improved quality or prevented harm.
- Unique valid discovery means exactly one independent critic found that issue
  in this run. Independent co-discovery retains credit for every discoverer;
  summing per-critic counts therefore exceeds the team's distinct issue count.
- Confidence calibration groups the original claim's qualitative confidence
  labels against later issue validity. These are proportions, not probabilities
  inferred from the words verified, likely, and possible.

## Challenges and disagreement

Critic verdicts reference an exact finding version. A pair comparison requires
both critics to assess that version in the same round and with the same recorded
context exposure. One agreement and one objection is a stance conflict; two
different objection types are not opposite stances. Silence never counts as
agreement.

The primary pair rate uses the earliest comparable assessment per underlying
issue/run/pair. Repeated rounds and revised claims cannot inflate that denominator.
Evidence objections and concern objections are counted separately. Discovery
overlap is the intersection / union of independent discovery sets, restricted to
runs where both critics completed independent passes with independent context.
Overlap appears even when neither critic has assessed the other's claims;
disagreement remains unknown until comparable verdicts exist. The table shows
shared and combined issue counts and the number of common reviews.

An upheld challenge needs an independent operator assessment. Reviewer withdrawal
alone is not a successful challenge. Useful effects include removing an invalid
claim, rescuing a valid one, and improving the evidence. Claims, objections,
reviewer decisions, and challenge judgments remain separately inspectable.

Round statistics attribute a new issue to its earliest discovery invocation.
They include later independent validation and upheld challenges. They suggest
which stopping rules to test, but do not establish that a later round was useless.

## Costs and completion

The trial runner preserves acquired usage and resolved model when later target
validation or observation validation fails, and when interrupted after execution.
Measurements unavailable before a failure remain null. A critic's measurements
never carry into another invocation. These corrections preserve the existing
metric definitions rather than creating a new cost estimate.

Input and output tokens come from available runtime reports. Cache and reasoning
tokens are recorded as subsets and are not added to input/output totals again.
The Claude adapter normalizes cache-read and cache-creation input into its input
total; the Codex adapter uses turn-completed totals that already include cache.

Costs remain separated as billed, provider-estimated, or price-estimated. Provider
estimates from a subscription CLI are not the subscription invoice. No measurement
is represented by null, not zero. Complete cost and cost-per-valid-issue require
every invocation to have a cost measurement with one common basis. A zero valid
issue denominator remains undefined, even if the run had a real cost.

Review duration is elapsed time between recorded start and finish, not summed
critic time. The dashboard provides median and nearest-rank p95 duration. The
service retains failed invocations and missing expected participants instead of
interpreting them as clean passes.

Invalidated runs retain their history, failure counts, and measured resource use.
Their claims do not contribute to quality or experiment scores. This separates
the cost of an unusable attempt from evidence about the reviewed work.

## Experiments

Matched comparisons include only the same case/trial across every variant, with
completed runs, all expected critics represented by completed invocations, and
an explicit full-evaluation marker. Unmatched, failed, and unevaluated trials
remain counted and visible outside the matched scores.

The operator must merge duplicate claims and judge every distinct reported issue
valid or invalid before marking evaluation complete. Match valid issues to known
defect IDs where justified. One known defect cannot match several distinct issues.
Known-defect recall is distinct known defects detected / expected known defects,
across the matched trials. A clean case has no recall denominator and helps
measure false alarms. A valid novel finding is still valid even if the reference
did not anticipate it.

The primary comparison reports candidate minus baseline on these matched results.
It does not declare statistical significance or automatically change the default
critic team. Repeat trials, review outcome judgments, and keep held-out cases.
Small pilot cases prove collection mechanics, not which critic is generally best.

## Limits

Observational history has selection effects: different projects, task difficulty,
tools, input access, model versions, and human judgment can explain changes. Use
fixed case and skill fingerprints for controlled comparisons and inspect the
underlying evidence before making decisions.

The server cannot see an unregistered skill invocation, client-side pending
bundles, human effort not recorded, all defects that escaped a review, or native
token usage hidden by a client. General production recall, causal reviewer
influence, and actual harm prevented are not inferred from the available record.
The current UI does not provide automated semantic matching, experiment model
execution on the server, significance tests, or automatic critic retirement.
