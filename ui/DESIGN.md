# Critic observer design

Use a consistent dark interface for the dashboard, tables, forms, dialogs and charts.

- Use a near-black blue background, slightly lighter panels, quiet gray borders,
  and readable off-white text. Use teal for verified positive results, amber for
  unresolved observations, and red for failures. Always pair color with text.
- Keep a stable left navigation on desktop and a compact wrapping navigation on
  narrow screens. The main view starts with its purpose and current cohort.
- Prefer tables for comparisons, simple bars for magnitude, and a chronological
  record for review decisions. Chart labels include units and sample counts.
- Typography uses system sans-serif for prose and monospace for IDs, commands,
  and evidence. Avoid decorative imagery and remote assets.
- Show two kinds of evidence side by side. The review
  team's own decisions (issues kept, withdrawn, challenges that changed the
  review) are provisional and use amber. Independently validated results use
  teal. Label provisional columns and legends as provisional, never as valid.
  Reviewer "supported" pills are amber for the same reason.
- In charts, provisional bars also carry a diagonal stripe texture, so the
  distinction does not rely on color. Every chart has a legend and a value at
  each bar's end in text color; the table below it is the full data view.
- Missing measurements display Unknown, never zero.
- Comparison tables offer "Compare by" (specialty, specialty and model, exact definition)
  and "Order by" controls. Changing them redraws the page without refetching.
  Long column names wrap rather than forcing horizontal scrolling.
- Default to exact definitions ordered by unique reported issues kept by the
  reviewer. This keeps differently prompted critics visible while specialty
  history accumulates. Coordinator-only definitions appear in review details,
  outside specialist rankings. Each unique count has an evidence list in its
  definition or group dialog. Distinguish reported exclusivity from independently
  compared discovery and from correctness. Solo reviews do not prove uniqueness.
- Navigation among loaded cohort pages renders locally. Refresh, applying
  filters, and successful edits reload data. Review and experiment details load
  on demand. Ignore obsolete async renders and cancel superseded cohort loads.
- The Assess issues page lists unjudged issues, most severe first, and the
  navigation shows how many are waiting. Opening one shows the critics' claims,
  evidence, and verdicts above the judgment form, so the operator can judge
  without leaving the queue.
- Start production views empty. Label benchmark and demo datasets visibly and
  keep them out of production aggregates unless the operator changes the filter.
- Keep review types separate. Default to Pull requests and offer Architecture,
  Code and Troubleshooting as individual cohorts, with no pooled website option.
  Label the loaded review type in cohort headings. Apply it to contributions,
  assessment, runs and experiments. Detail pages identify their actual type.
  Experiment definitions freeze one type; opening a variant's cohort preserves it.
  The shared critic authoring catalog is not a mixed performance comparison.
- Every aggregate links to critic definitions or source review records. Keep
  full prompts and evidence available without overwhelming comparison tables.
- Forms use visible labels, keyboard focus states, associated help text, and
  accessible dialogs. Tables may scroll horizontally on small screens; page
  layout must not overflow. Escape all submitted content before rendering it.
- Critic and experiment definitions are immutable. Editing creates a new
  definition, and the UI explains why historical measurements retain the old one.
