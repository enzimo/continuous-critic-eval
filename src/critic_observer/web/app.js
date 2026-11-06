const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const h = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const num = (value) =>
  value == null ? "Unknown" : new Intl.NumberFormat().format(value);
const pct = (value) =>
  value == null ? "Unknown" : `${(value * 100).toFixed(0)}%`;
const money = (value) => (value == null ? "Unknown" : `$${value.toFixed(4)}`);
const duration = (value) =>
  value == null
    ? "Unknown"
    : value < 60
      ? `${value.toFixed(1)} s`
      : `${(value / 60).toFixed(1)} min`;
const when = (value) =>
  value ? new Date(value).toLocaleString() : "Not finished";
const short = (value) => String(value).slice(0, 12);
const eventId = () =>
  "ui-" +
  [...crypto.getRandomValues(new Uint8Array(16))]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
const titleCase = (value) => String(value).replaceAll("_", " ");
const REVIEW_TYPES = [
  ["pull_request", "Pull requests"],
  ["architecture", "Architecture"],
  ["code", "Code"],
  ["troubleshooting", "Troubleshooting"],
];
const reviewLabel = (value) =>
  REVIEW_TYPES.find(([key]) => key === value)?.[1] || titleCase(value);
const pill = (value) =>
  `<span class="pill ${h(value)}">${h(titleCase(value))}</span>`;
let fieldSequence = 0;
const field = (label, control, help = "") => {
  const id = `field-${++fieldSequence}`;
  const labeled = control.replace(
    /^<(input|select|textarea)/,
    `<$1 id="${id}"`,
  );
  return `<div class="field"><label for="${id}">${h(label)}</label>${labeled}${help ? `<p class="help">${h(help)}</p>` : ""}</div>`;
};
const input = (name, value = "", required = true, type = "text") =>
  `<input name="${h(name)}" type="${type}" value="${h(value)}" ${required ? "required" : ""}>`;
const area = (name, value = "", required = true) =>
  `<textarea name="${h(name)}" ${required ? "required" : ""}>${h(value)}</textarea>`;
const select = (name, options, current) =>
  `<select name="${h(name)}">${options.map(([v, t]) => `<option value="${h(v)}" ${v === current ? "selected" : ""}>${h(t)}</option>`).join("")}</select>`;
const actions = (label) =>
  `<div class="form-actions"><button type="button" data-close>Cancel</button><button class="primary" type="submit">${h(label)}</button></div><p class="error" data-form-error role="alert"></p>`;
const empty = (title, text, action = "") =>
  `<div class="empty"><h3>${h(title)}</h3><p>${h(text)}</p>${action}</div>`;
const table = (headers, rows) =>
  `<div class="table-wrap"><table><thead><tr>${headers.map((t) => `<th scope="col">${h(t)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
const state = {
  critics: [],
  dashboard: null,
  detail: null,
  experiment: null,
  experiments: [],
  generation: 0,
  groupBy: "definition",
  sortBy: "exclusive_supported_issues",
  refreshController: null,
  renderGeneration: 0,
  detailGeneration: 0,
  knownIssues: [],
};
let toastTimer;

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: {
      "X-Observer-Request": "1",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  if (response.status === 401) {
    showLogin();
    throw new Error("Your session has expired. Sign in again.");
  }
  if (!response.ok) {
    const data = await response
      .json()
      .catch(() => ({ detail: `Request failed: ${response.status}` }));
    throw new Error(
      Array.isArray(data.detail)
        ? data.detail.map((d) => `${d.loc.join(".")}: ${d.msg}`).join("; ")
        : data.detail,
    );
  }
  return response.status === 204 ? null : response.json();
}

function showLogin() {
  $("#login-view").hidden = false;
  $("#shell").hidden = true;
}
function showShell() {
  $("#login-view").hidden = true;
  $("#shell").hidden = false;
}
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    $("#toast").hidden = true;
  }, 4500);
}
function showError(error) {
  $("#error-banner").textContent = error.message;
  $("#error-banner").hidden = false;
}
function heading(eyebrow, title, text, buttons = "") {
  return `<div class="heading"><div><p class="eyebrow">${h(eyebrow)}</p><h1>${h(title)}</h1><p class="subtle">${h(text)}</p></div>${buttons ? `<div class="heading-actions">${buttons}</div>` : ""}</div>`;
}
function card(label, value, note, color = "", extra = "") {
  return `<div class="metric"><div class="label">${h(label)}</div><div class="number ${color}">${h(value)}</div><div class="note">${h(note)}</div>${extra}</div>`;
}
function criticName(id) {
  return state.critics.find((c) => c.id === id)?.name || short(id);
}
function criticButton(id) {
  return `<button class="text-link" data-critic="${h(id)}">${h(criticName(id))}</button>`;
}
function cohort() {
  const filters = state.dashboard.filters;
  return `${reviewLabel(filters.review_type)} / ${titleCase(filters.dataset || "All datasets")}`;
}
const decimal = (value) => (value == null ? "Unknown" : value.toFixed(1));
const plural = (count, word) =>
  `${num(count)} ${count === 1 ? word : `${word}s`}`;
// Reviewer decisions are the review team's own, so they use the provisional style.
const REVIEWER_STATES = {
  supported: ["Kept by reviewer", "provisional"],
  withdrawn: ["Withdrawn", ""],
  unresolved: ["Unresolved", "unknown"],
  undecided: ["No decision", ""],
};
const reviewerPill = (value) => {
  const [label, style] = REVIEWER_STATES[value] || [titleCase(value), ""];
  return `<span class="pill ${style}">${h(label)}</span>`;
};
const GROUPINGS = [
  ["specialty", "Specialty"],
  ["specialty_model", "Specialty and model"],
  ["definition", "Exact definition"],
];
const SORTS = [
  ["exclusive_supported_issues", "Unique reported issues kept"],
  ["exclusive_issues", "Unique reported issues raised"],
  ["exclusive_kept_per_review", "Unique kept issues per compared review"],
  ["reviewer_supported_issues", "Kept by reviewer"],
  ["distinct_issues", "Issues raised"],
  ["issues_per_review", "Issues per review"],
  ["unique_supported_discoveries", "Unique independent discoveries kept"],
  ["challenges_changed_review", "Challenges that changed the review"],
  ["valid_issues", "Independently valid"],
  ["unique_valid_discoveries", "Unique valid discoveries"],
  ["run_count", "Reviews"],
];
const choice = (attribute, label, options, current) =>
  `<label class="inline-control">${h(label)}<select ${attribute}>${options.map(([v, t]) => `<option value="${h(v)}" ${v === current ? "selected" : ""}>${h(t)}</option>`).join("")}</select></label>`;
const groupChoice = () =>
  choice("data-group-by", "Compare by", GROUPINGS, state.groupBy);
const sortChoice = () =>
  choice("data-sort-by", "Order by", SORTS, state.sortBy);
function sortRows(rows, key) {
  // Unknown values sort last instead of breaking the numeric comparison.
  const value = (row) => row[key] ?? -1;
  return [...rows].sort(
    (a, b) => value(b) - value(a) || a.label.localeCompare(b.label),
  );
}
function contributionRows() {
  const m = state.dashboard.metrics;
  const rows =
    state.groupBy === "definition"
      ? m.critics
          .filter((c) => c.responsibilities.some((r) => r !== "Coordinator"))
          .map((c) => ({ ...c, label: c.name }))
      : m.groups[state.groupBy];
  return sortRows(rows, state.sortBy);
}
function contributorCell(row) {
  if (row.critic_id)
    return `${criticButton(row.critic_id)}<small>${h(row.specialty)} · ${h(row.model || "Model not recorded")}</small><small>${h(row.responsibilities.join(", "))}</small>`;
  const count = row.critic_ids.length;
  return `<button class="text-link" data-group="${h(row.group_key)}">${h(row.label)}</button><small>${count} ${count === 1 ? "definition" : "definitions"}</small>`;
}
function contributionTable(rows) {
  return table(
    [
      "Critic",
      "Reviews",
      "Issues raised",
      "Kept by reviewer (provisional)",
      "Unique reported issues",
      "Challenges that changed the review",
      "Independently valid",
    ],
    rows.map(
      (c) =>
        `<tr><td class="title-cell">${contributorCell(c)}</td><td>${num(c.run_count)}<small>${num(c.invocations)} passes</small></td><td>${num(c.distinct_issues)}<small>${decimal(c.issues_per_review)} per review</small></td><td><span class="warning">${num(c.reviewer_supported_issues)}</span><small>${num(c.reviewer_withdrawn_issues)} withdrawn · ${num(c.reviewer_decisions.unresolved + c.reviewer_decisions.undecided)} undecided</small></td><td>${num(c.exclusive_supported_issues)} kept / ${num(c.exclusive_issues)} raised<small>${decimal(c.exclusive_kept_per_review)} kept per compared review · ${num(c.report_comparison_reviews)} reviews</small><small>${num(c.unique_supported_discoveries)} kept with independent comparison · ${num(c.comparison_reviews)} comparable reviews</small></td><td>${num(c.challenges_changed_review)} / ${num(c.challenges)}<small>${num(c.challenge_responses.withdrawn)} withdrawn · ${num(c.challenge_responses.revised)} revised</small></td><td><span class="positive">${num(c.valid_issues)}</span> / ${num(c.valid_issues + c.invalid_issues)} judged<small>${num(c.unique_valid_discoveries)} unique · ${pct(c.judgment_coverage)} assessed</small></td></tr>`,
    ),
  );
}
function contributionChart(rows) {
  const top = sortRows(rows, "exclusive_supported_issues")
    .filter((r) => r.distinct_issues > 0)
    .slice(0, 6);
  if (!top.length)
    return `<div class="chart-empty">Recorded findings will populate this chart.</div>`;
  const max = Math.max(
    ...top.map((r) =>
      Math.max(r.exclusive_supported_issues, r.exclusive_valid_issues),
    ),
    1,
  );
  const bar = (style, value, meaning, row) =>
    `<div class="pair-bar" title="${h(row.label)}: ${h(num(value))} ${h(meaning)}"><div class="pair-track"><div class="bar-fill ${style}" style="width:${(value / max) * 100}%"></div></div><span class="bar-value">${num(value)}</span></div>`;
  return (
    `<div class="legend"><span class="provisional">Unique reported, kept (provisional)</span><span class="validated">Unique reported, judged valid</span></div>` +
    top
      .map(
        (r) =>
          `<div class="bar-row paired"><span class="bar-label" title="${h(r.label)}">${h(r.label)}</span><div class="bar-pair">${bar("provisional", r.exclusive_supported_issues, "unique reported issues kept by the reviewer", r)}${bar("validated", r.exclusive_valid_issues, "unique reported issues judged valid", r)}</div></div>`,
      )
      .join("")
  );
}
function runTable(runs) {
  const summaries = state.dashboard?.metrics.run_summaries || {};
  const outside = '<span class="subtle">Not in current cohort</span>';
  return table(
    [
      "Review / target",
      "Status",
      "Client",
      "Started",
      "Issues",
      "Kept by reviewer",
      "Judged",
    ],
    runs.map((r) => {
      const s = summaries[r.id];
      return `<tr><td class="title-cell"><a href="#run/${encodeURIComponent(r.id)}">${h(r.title)}</a><small>${h(r.project)} · ${h(r.review_type)} ${pill(r.dataset)}</small></td><td>${pill(r.status)}</td><td>${h(r.client)}</td><td>${h(when(r.started_at))}</td><td>${s ? `${num(s.issues)}<small>${plural(s.critics, "critic")}</small>` : outside}</td><td>${s ? `${num(s.reviewer_supported)}<small>${s.reviewer_withdrawn} withdrawn</small>` : ""}</td><td>${s ? `${s.judged} / ${s.issues}` : ""}${r.evaluation ? `<small>${pill("evaluated")}</small>` : ""}</td></tr>`;
    }),
  );
}

function overview() {
  const { metrics: m, runs, assessment } = state.dashboard;
  const o = m.overview;
  const d = o.reviewer_decisions;
  const c = m.reviewer_calibration;
  const rows = contributionRows();
  return (
    heading(
      cohort(),
      "What did the critics add?",
      "Contributions appear as soon as a review is recorded. Amber numbers are the review team's own decisions and are provisional. Teal numbers come from your independent judgments.",
      `<button data-refresh>Refresh</button>`,
    ) +
    `<div class="metrics-grid">${card("Recorded reviews", num(o.runs), `${o.status.completed || 0} completed · ${o.status.running || 0} running`)}${card("Issues raised", num(o.distinct_issues), `${d.supported} kept by reviewer · ${d.withdrawn} withdrawn · ${d.unresolved + d.undecided} undecided`, "warning")}${card("Independently valid", num(o.valid_issues), `${o.valid_issues + o.invalid_issues} of ${o.distinct_issues} issues judged${o.validity_rate == null ? "" : ` · ${pct(o.validity_rate)} valid`}`, "positive")}${card("Awaiting your judgment", num(assessment.total), "Issues without a valid or invalid judgment", "", '<a class="metric-link" href="#assess">Open the assessment queue →</a>')}</div>` +
    (runs.length
      ? ""
      : `<div class="notice info">No ${h($("#filters [name=dataset]").selectedOptions[0].textContent.toLowerCase())} runs are recorded. Other datasets stay separate. <a href="#connect">Connect a review client</a> to start collecting.</div>`) +
    `<div class="grid-two"><section class="panel"><div class="panel-title"><h2>Who contributes</h2>${groupChoice()}</div>${contributionChart(rows)}<p class="help section-gap">Issues the reviewer kept are provisional until judged. Unique means no other participating reviewer reported the issue. Counts depend on explicit duplicate merges. Independent discoveries additionally require another completed independent reviewer outside the selected group. Open a critic to inspect its unique issues.</p></section><section class="panel"><div class="panel-title"><h2>What we can trust</h2><a href="#quality">Inspect data quality →</a></div><div class="progress-list"><div><span>Independent judgments</span><span>${o.valid_issues + o.invalid_issues} / ${o.distinct_issues} issues</span></div><div><span>Reviewer decisions recorded</span><span>${d.supported + d.withdrawn + d.unresolved} / ${o.distinct_issues} issues</span></div><div><span>Reviewer decisions matching your judgment</span><span>${c.compared ? `${c.matched} / ${c.compared} · ${pct(c.agreement_rate)}` : "No judged issues yet"}</span></div><div><span>Completed evaluation</span><span>${m.data_health.fully_evaluated_runs} / ${o.runs} reviews</span></div><div><span>Cost measurements</span><span>${o.usage.cost_measured} / ${o.usage.invocations} invocations</span></div><div><span>Recorded fixed outcomes</span><span>${o.outcomes.fixed || 0} / ${o.valid_issues} valid issues</span></div><div><span>Missing expected critics</span><span class="warning">${m.data_health.missing_expected_critics.length} reviews</span></div><div><span>Median review duration</span><span>${duration(o.median_seconds)}</span></div><div><span>95th percentile duration</span><span>${duration(o.p95_seconds)}</span></div></div><p class="help section-gap">Matching decisions show how far the provisional numbers can be trusted. Agreement between critics is not proof.</p></section></div>` +
    `<section class="panel"><div class="panel-title"><h2>Critic contributions</h2><div class="inline-actions">${groupChoice()}${sortChoice()}</div></div>${rows.length ? contributionTable(rows) : empty("Measurements start with a review", "Registered critics are ready to use. Their measurements appear after a recorded invocation.")}</section>` +
    `<section class="panel"><div class="panel-title"><h2>Recent reviews</h2><a href="#runs">View all →</a></div>${runs.length ? runTable(runs.slice(0, 8)) : empty("No reviews in this cohort", "Production, benchmark, and demonstration records are kept separate.")}</section>`
  );
}

function runsPage() {
  const runs = state.dashboard.runs;
  return (
    heading(
      cohort(),
      "Review runs",
      "Open a run to inspect its findings, evidence, critic responses, and independent judgments.",
      `<button data-refresh>Refresh</button>`,
    ) +
    `<section class="panel">${runs.length ? runTable(runs) : empty("No recorded runs", "Connect a client or change the cohort filters.", '<a href="#connect">Connect clients →</a>')}</section>`
  );
}

function assessPage() {
  const { assessment: a } = state.dashboard;
  return (
    heading(
      cohort(),
      "Which issues still need a judgment?",
      "The review team's decisions are provisional. Check each issue against independent evidence, such as the code or a reproduction, and record whether it is valid. The most severe issues come first.",
      `<button data-refresh>Refresh</button>`,
    ) +
    (a.total > a.items.length
      ? `<div class="notice info">Showing the first ${a.items.length} of ${a.total} issues. Narrow the cohort filters to see the rest.</div>`
      : "") +
    `<section class="panel">${
      a.items.length
        ? table(
            ["Issue", "Claimed severity", "Reported by", "Review team", ""],
            a.items.map(
              (i) =>
                `<tr><td class="title-cell"><strong>${h(i.title || i.issue_id)}</strong><small><a href="#run/${encodeURIComponent(i.run_id)}">${h(i.run_title)}</a> · ${h(i.project)}</small></td><td>${pill(i.severity)}<small>${h(titleCase(i.category))}</small></td><td class="title-cell">${i.critic_ids.map(criticButton).join(", ")}<small>${i.claims} ${i.claims === 1 ? "claim" : "claims"}</small></td><td>${reviewerPill(i.reviewer_state)}<small>${i.agree} agree · ${i.disagree} disagree</small>${i.judgment === "unknown" ? "<small>Judged unknown so far</small>" : ""}</td><td><button class="small primary" data-assess-run="${h(i.run_id)}" data-assess-issue="${h(i.issue_id)}">Assess</button></td></tr>`,
            ),
          )
        : empty(
            "Nothing is waiting",
            "Every issue in this cohort has a valid or invalid judgment.",
          )
    }</section>`
  );
}

function criticsPage() {
  const rows = contributionRows();
  const usage = Object.fromEntries(
    state.dashboard.metrics.critics.map((c) => [c.critic_id, c.run_count]),
  );
  const definitions = [...state.critics].sort(
    (a, b) =>
      (usage[b.id] || 0) - (usage[a.id] || 0) ||
      b.created_at.localeCompare(a.created_at),
  );
  return (
    heading(
      cohort(),
      "Build a more useful critic team",
      "Compare unique contributions by specialty, specialty and model, or exact definition. General review means no specialty was recorded; coordinator and challenger describe responsibilities, not specialties.",
      '<button class="primary" data-new-critic>Create critic</button>',
    ) +
    `<section class="panel"><div class="panel-title"><h2>Results in the current cohort</h2><div class="inline-actions">${groupChoice()}${sortChoice()}</div></div>${rows.length ? contributionTable(rows) : empty("No measurements in this cohort", "Definitions below are available even before their first review.")}</section>` +
    `<div class="notice info">Record a reusable specialty such as Security or Bug hunting, and keep task details in the pass scope. Review phase records whether the agent coordinates, independently reviews, or challenges earlier findings. A definition alone does not mean that specialist ran.</div>` +
    `<div class="critic-grid">${definitions.map((c) => `<article class="critic-card"><span class="pill">${h(c.specialty || "Specialty not recorded")}</span><h3>${h(c.name)}</h3><p>${h(c.prompt.slice(0, 175))}${c.prompt.length > 175 ? "…" : ""}</p><small>${h(c.provider || "Client selected")} · ${h(c.model || "Runtime default, unresolved")}</small><small>${usage[c.id] ? `Used in ${usage[c.id]} ${usage[c.id] === 1 ? "review" : "reviews"} in this cohort` : "Not used in this cohort"}</small><p class="mono">${h(short(c.id))}</p><div class="card-foot"><button class="small" data-critic="${h(c.id)}">Inspect definition</button><button class="small" data-fork-critic="${h(c.id)}">Create variant</button></div></article>`).join("")}</div>`
  );
}

function disagreementsPage() {
  const pairs = state.dashboard.metrics.pairs;
  return (
    heading(
      cohort(),
      "Which critics challenge each other?",
      "Compare opposing stances on the same finding version, in the same round and context. Repeated rounds do not inflate the primary rate.",
    ) +
    `<div class="notice info">One critic agreeing while another objects is a stance conflict. Two critics objecting for different reasons are not opposite stances. No assessment is not agreement.</div>` +
    `<section class="panel">${
      pairs.length
        ? table(
            [
              "Critic pair",
              "Opposing / comparable",
              "Conflict rate",
              "Evidence objections",
              "Concern objections",
              "Discovery overlap",
            ],
            pairs.map(
              (p) =>
                `<tr><td>${criticButton(p.left)}<small>with</small>${criticButton(p.right)}<small>${p.run_ids.map((id) => `<a href="#run/${encodeURIComponent(id)}">Review ${h(short(id))}</a>`).join(" · ")}</small></td><td>${p.conflicts} / ${p.compared}</td><td>${pct(p.disagreement_rate)}</td><td>${p.evidence_objections}</td><td>${p.concern_objections}</td><td>${pct(p.discovery_overlap)}<small>${p.shared_discoveries} shared / ${p.combined_discoveries} combined issues · ${p.common_independent_runs} common reviews</small></td></tr>`,
            ),
          )
        : empty(
            "No comparable assessments yet",
            "Record two different critics assessing the same finding version in the same round. Independent discoveries alone do not create a disagreement score.",
          )
    }</section>` +
    `<section class="panel"><h2>Inspect the conversations</h2>${state.dashboard.runs.length ? runTable(state.dashboard.runs) : '<p class="subtle">Recorded conversations will appear here.</p>'}</section>`
  );
}

function roundsPage() {
  const rounds = state.dashboard.metrics.rounds;
  return (
    heading(
      cohort(),
      "What did another round buy?",
      "Round zero is independent discovery. Later rounds can add issues or correct prior claims. These observational totals help choose experiments.",
    ) +
    `<section class="panel">${
      rounds.length
        ? table(
            [
              "Round",
              "Invocations",
              "New distinct issues",
              "New, kept by reviewer",
              "New validated",
              "Challenges that changed the review",
              "Upheld challenges",
              "Cost coverage",
            ],
            rounds.map(
              (r) =>
                `<tr><td>${r.round === 0 ? "0 · Independent" : r.round}</td><td>${r.invocations}</td><td>${r.new_issues}</td><td class="warning">${r.reviewer_supported_new_issues}</td><td class="positive">${r.valid_new_issues}</td><td>${r.challenges_changed_review} / ${r.challenges}</td><td>${r.upheld_challenges}</td><td>${pct(r.usage.cost_coverage)}<small>${r.usage.cost_measured} / ${r.invocations}</small></td></tr>`,
            ),
          )
        : empty(
            "No recorded rounds",
            "Every independent pass and critique round needs its own invocation record.",
          )
    }</section>` +
    `<div class="notice info">Later rounds often contain harder disputes. Test a shorter review policy on matched, frozen cases before attributing a cost or quality difference to the round limit.</div>`
  );
}

function qualityPage() {
  const { overview: o, data_health: d } = state.dashboard.metrics;
  return (
    heading(
      cohort(),
      "Know the limits of the record",
      "Missing outputs, unknown usage, and unassessed findings remain visible.",
    ) +
    `<div class="metrics-grid">${card("Missing expected critics", num(d.missing_expected_critics.length), "Registered reviews with incomplete participation", "warning")}${card("Active invocations", num(d.active_invocations), "May include interrupted clients")}${card("Failed invocations", num(d.failed_invocations), "Retained even after a successful retry", "negative")}${card("Unresolved model", num(d.unknown_model_invocations), "Configure an explicit model for comparisons")}</div>` +
    `<section class="panel"><h2>Measurement availability</h2><div class="progress-list"><div><span>Issue validity assessed</span><span>${o.valid_issues + o.invalid_issues} / ${o.distinct_issues}</span></div><div><span>Input and output token measurements</span><span>${o.usage.tokens_measured} / ${o.usage.invocations} invocations</span></div><div><span>Cost measurements</span><span>${o.usage.cost_measured} / ${o.usage.invocations} invocations</span></div>${Object.entries(
      o.usage.cost_by_basis,
    )
      .map(
        ([basis, value]) =>
          `<div><span>${h(titleCase(basis))} subtotal</span><span>${money(value)}</span></div>`,
      )
      .join("")}</div></section>` +
    `<section class="panel"><h2>Incomplete participation</h2>${
      d.missing_expected_critics.length
        ? table(
            ["Run", "Critics without a completed pass"],
            d.missing_expected_critics.map(
              (v) =>
                `<tr><td><a href="#run/${encodeURIComponent(v.run_id)}">${h(short(v.run_id))}</a></td><td class="title-cell">${v.critic_ids.map(criticButton).join(", ")}</td></tr>`,
            ),
          )
        : '<p class="subtle">No missing expected participants in this cohort.</p>'
    }</section>` +
    `<div class="notice info">This server knows only registered runs. It cannot discover skill invocations that never report. MCP observations do not expose native token usage automatically. The local trial runner records available runtime usage; the reporting CLI retains undelivered batches on the client. Use <code>critic-observer queue</code> there to inspect its outbox.</div>`
  );
}

async function experimentsPage() {
  const experiments = state.experiments;
  return (
    heading(
      cohort(),
      "Try a different critic team",
      "Freeze the target and hypothesis. Compare complete, independently adjudicated trials on the same cases.",
      '<button class="primary" data-new-experiment>Create experiment</button>',
    ) +
    (experiments.length
      ? experiments
          .map(
            (e) =>
              `<section class="panel"><div class="panel-title"><h2><a href="#experiment/${encodeURIComponent(e.id)}">${h(e.name)}</a></h2><span class="pill">${h(titleCase(e.primary_metric))}</span></div><p class="subtle">${h(e.hypothesis)}</p><small>${e.variants.length} variants · ${e.cases.length} frozen cases · ${h(when(e.created_at))}</small></section>`,
          )
          .join("")
      : `<section class="panel">${empty("Start with a specific hypothesis", "For example: adding a counterexample seeker finds more known defects than the baseline team, with no increase in false alarms.", "<button data-new-experiment>Create your first experiment</button>")}</section>`)
  );
}

async function experimentDetail(id) {
  const rendering = state.renderGeneration;
  const e = await api(`/api/experiments/${encodeURIComponent(id)}`);
  if (rendering === state.renderGeneration) state.experiment = e;
  const exp = e.experiment;
  return (
    heading(
      `${reviewLabel(exp.review_type)} / Experiment / Frozen definition`,
      exp.name,
      exp.hypothesis,
      '<a href="#experiments">All experiments →</a>',
    ) +
    `<div class="metrics-grid">${card("Matched evaluated trials", e.matched_trials, "All variants complete on the same case and trial")}${card("Pending trial groups", e.unmatched_or_unevaluated_trials, "Missing a variant, participation, or adjudication", "warning")}${card("Variants", exp.variants.length, "Immutable team membership")}${card("Cases", exp.cases.length, "Frozen targets with an operator answer key")}</div>` +
    `<section class="panel"><div class="panel-title"><h2>Matched results</h2><small>Primary measure: ${h(titleCase(exp.primary_metric))}</small></div>${table(
      [
        "Variant",
        "Registered / failed",
        "Matched trials",
        "Known detected / total",
        "Recall",
        "Mean valid",
        "Mean false alarms",
        "Mean cost",
      ],
      e.variants.map(
        (v) =>
          `<tr><td><button class="text-link" data-scope-experiment="${h(exp.id)}" data-review-type="${h(exp.review_type)}" data-scope-variant="${h(v.variant_id)}">${h(v.name)}</button></td><td>${v.registered} / ${v.failed}</td><td>${v.matched_trials}</td><td>${v.known_detected} / ${v.known_total}</td><td>${pct(v.known_defect_recall)}</td><td>${v.mean_valid_issues == null ? "Unknown" : v.mean_valid_issues.toFixed(2)}</td><td>${v.mean_false_alarms == null ? "Unknown" : v.mean_false_alarms.toFixed(2)}</td><td>${money(v.mean_cost_usd)}<small>${h(v.cost_bases.join(", ") || "No complete measurement")}</small></td></tr>`,
      ),
    )}<p class="help section-gap">${h(e.interpretation)}</p>${e.comparisons.map((c) => `<p class="help">${h(exp.variants.find((v) => v.id === c.variant).name)} minus baseline, ${h(titleCase(c.metric))}: <strong>${c.difference == null ? "Unknown" : c.difference.toFixed(3)}</strong></p>`).join("")}</section>` +
    exp.cases
      .map(
        (c) =>
          `<section class="panel"><h2>${h(c.title)}</h2><p class="subtle">${h(c.instructions)}</p><code>${h(c.target_revision)}</code><h3 class="section-gap">Run each variant on your client</h3><p class="help">Replace the credential file, working directory, client, and skill revision. Increment the trial number for each repeat. The runner checks this fingerprint before execution.</p>${exp.variants
            .map(
              (
                v,
              ) => `<p>${h(v.name)}</p><pre>critic-observer --server ${h(location.origin)} --token-file /path/to/ingest_token trial \
  --experiment ${h(exp.id)} --variant ${h(v.id)} --case ${h(c.id)} \
  --trial 1 --client codex --workdir /path/to/frozen/case \
  --skill-dir /path/to/project-review-process</pre>`,
            )
            .join(
              "",
            )}<details><summary>Operator reference: ${c.known_issues.length} known defects</summary>${c.known_issues.map((i) => `<div class="verdict"><strong>${h(i.title)}</strong> ${pill(i.severity)}<p class="mono">${h(i.id)}</p><pre>${h(i.evidence)}</pre></div>`).join("") || '<p class="subtle">Clean control case. Do not assume every reported issue is false without adjudicating it.</p>'}</details></section>`,
      )
      .join("") +
    `<section class="panel"><h2>Registered trials</h2>${e.runs.length ? runTable(e.runs) : '<p class="subtle">No trials have been registered yet.</p>'}</section>`
  );
}

function connectPage() {
  return (
    heading(
      "Client setup",
      "One collector, several ways to report",
      "Connect through MCP for normal skill use. Use the local CLI for durable delivery and controlled experiments.",
    ) +
    `<section class="panel"><h2>MCP endpoint</h2><pre>${h(location.origin)}/mcp</pre><p class="subtle">Configure a bearer token using the server's ingestion credential. Keep it out of source control and review prompts.</p><h3>Codex</h3><pre>[mcp_servers.critic_observer]
url = "${h(location.origin)}/mcp"
bearer_token_env_var = "OBSERVER_TOKEN"</pre><h3>Claude Code</h3><pre>{
  "mcpServers": {
    "critic_observer": {
      "type": "http",
      "url": "${h(location.origin)}/mcp",
      "headers": {"Authorization": "Bearer \${OBSERVER_TOKEN}"}
    }
  }
}</pre><p class="help">After installing the updated project-review-process skill, ask it to record the review with Critic observer. The lead reports results from all critic contexts.</p></section>` +
    `<section class="panel"><h2>Durable command-line reporting</h2><pre>critic-observer --server ${h(location.origin)} --token-file /path/to/ingest_token submit review-events.json
critic-observer --server ${h(location.origin)} --token-file /path/to/ingest_token flush
critic-observer --server ${h(location.origin)} queue</pre><p class="help">A batch is stored locally before delivery. Dependencies must be delivered in order. A failed batch stays in the outbox and blocks later batches until corrected or delivered.</p></section>` +
    `<section class="panel"><h2>Back up the server</h2><pre>critic-observer --server ${h(location.origin)} --token-file /path/to/admin_token backup --output observer-backup.sqlite3</pre><p class="help">This uses SQLite's online backup API. Store backups outside the Swarm node that owns the volume, and test restoration before depending on them.</p><a href="/api/docs">Authenticated HTTP API reference →</a></section>`
  );
}

function latestFindings(detail) {
  const map = new Map();
  detail.findings.forEach((f) => {
    if (!map.has(f.id) || map.get(f.id).version < f.version) map.set(f.id, f);
  });
  return [...map.values()];
}

async function loadRun(id) {
  const request = ++state.detailGeneration;
  const detail = await api(`/api/runs/${encodeURIComponent(id)}`);
  const r = detail.run;
  const knownIssues = r.experiment_id
    ? (
        await api(`/api/experiments/${encodeURIComponent(r.experiment_id)}`)
      ).experiment.cases.find((c) => c.id === r.case_id).known_issues
    : [];
  if (request === state.detailGeneration) {
    state.knownIssues = knownIssues;
    state.detail = detail;
    return detail;
  }
  return null;
}

async function runDetail(id) {
  const detail = await loadRun(id);
  if (!detail) return "";
  const r = detail.run;
  const findings = latestFindings(detail);
  const issues = Map.groupBy(findings, (f) => f.issue_id);
  const invocation = (id) => detail.invocations.find((i) => i.id === id);
  const issueCards = [...issues]
    .map(([issueId, claims]) => {
      const judgment = detail.judgments.find((j) => j.issue_id === issueId);
      const outcome = detail.outcomes.find((o) => o.issue_id === issueId);
      return `<article class="panel issue-card ${h(judgment?.validity || "unknown")}"><div class="issue-header"><div>${pill(judgment?.validity || "unknown")} ${pill(judgment?.severity || claims[0].severity)}<h2>${h(claims[0].title)}</h2><small class="mono">Issue ${h(short(issueId))} · ${claims.length} reporting ${claims.length === 1 ? "critic" : "critics"}</small></div><div class="issue-controls"><button class="small" data-judge="${h(issueId)}">${judgment ? "Revise judgment" : "Assess validity"}</button><button class="small" data-merge="${h(issueId)}">Merge duplicate</button><button class="small" data-outcome="${h(issueId)}">Record outcome</button></div></div>${judgment ? `<div class="notice info"><strong>${h(judgment.assessor)}</strong> · ${h(judgment.method)} · revision ${judgment.revision}<p class="tight">${h(judgment.rationale)}</p><pre>${h(judgment.evidence)}</pre>${judgment.known_issue_id ? `<small>Matches known defect ${h(judgment.known_issue_id)}</small>` : ""}</div>` : '<p class="help">No independent judgment. Critic agreement does not establish whether this issue is valid.</p>'}${outcome ? `<p>${pill(outcome.state)} ${h(outcome.rationale)} · ${h(outcome.reference)}</p>` : ""}${claims
        .map((f) => {
          const inv = invocation(f.origin_invocation_id || f.invocation_id);
          const decision = detail.decisions.find(
            (d) => d.finding_id === f.id && d.finding_version === f.version,
          );
          const verdicts = detail.verdicts.filter(
            (v) => v.finding_id === f.id && v.finding_version === f.version,
          );
          return `<div class="claim"><h3>${criticButton(inv.critic_id)} ${pill(f.confidence)} <span class="subtle">version ${f.version} · round ${inv.round}</span></h3><p class="mono">${h(f.location)}</p><p class="claim-label">Trigger</p><p>${h(f.trigger)}</p><p class="claim-label">Impact</p><p>${h(f.impact)}</p><p class="claim-label">Evidence</p><pre>${h(f.evidence)}</pre>${decision ? `<p>Reviewer decision: ${reviewerPill(decision.state)} ${h(decision.rationale)}</p>` : ""}${r.status === "running" ? `<button class="small" data-decision="${h(f.id)}">Record reviewer decision</button>` : ""}${verdicts
            .map((v) => {
              const critic = invocation(v.invocation_id);
              const judged = detail.challenge_judgments.find(
                (j) => j.verdict_event_id === v.event_id,
              );
              return `<div class="verdict">${criticButton(critic.critic_id)} · ${pill(v.verdict)}<p class="rationale">${h(v.rationale)}</p>${v.evidence ? `<pre>${h(v.evidence)}</pre>` : ""}${judged ? `<p>${pill(judged.result)} ${h(titleCase(judged.effect))} · ${h(judged.assessor)}</p><p>${h(judged.evidence)}</p>` : ""}${v.verdict !== "AGREE" ? `<button class="small" data-judge-challenge="${h(v.event_id)}">${judged ? "Revise challenge judgment" : "Assess this challenge"}</button>` : ""}</div>`;
            })
            .join("")}</div>`;
        })
        .join("")}</article>`;
    })
    .join("");
  return (
    heading(
      `${r.dataset} / ${r.review_type}`,
      r.title,
      `${reviewLabel(r.review_type)} · ${r.project} · ${r.client}`,
      `<a href="/api/runs/${encodeURIComponent(id)}/export"><button>Export evidence</button></a>${r.status !== "running" && r.status !== "invalidated" ? "<button data-invalidate>Invalidate result</button>" : ""}`,
    ) +
    `<section class="panel"><div class="inline-actions">${pill(r.status)} ${r.evaluation ? pill("evaluated") : pill("assessment_pending")} ${pill(r.dataset)}</div><div class="key-values"><div><small>Target</small>${h(r.target)}</div><div><small>Target revision</small><code>${h(r.target_revision)}</code></div><div><small>Skill revision</small><code>${h(r.skill_revision)}</code></div><div><small>Coordinating agent</small>${h(
      detail.invocations
        .filter((i) => i.phase === "lead")
        .map(
          (i) =>
            `${criticName(i.critic_id)} · ${i.resolved_model || i.model || "Model unknown"}`,
        )
        .join("; ") || "Coordinator not recorded",
    )}</div><div><small>Run ID</small><code>${h(r.id)}</code></div><div><small>Started</small>${h(when(r.started_at))}</div><div><small>Finished</small>${h(when(r.finished_at))}</div></div><div class="record-actions">${r.status === "completed" ? '<button class="primary" data-evaluate>Mark evaluation complete</button>' : ""}${r.status === "running" ? "<button data-cancel-run>Close interrupted run</button>" : ""}${r.experiment_id ? `<a href="#experiment/${encodeURIComponent(r.experiment_id)}">Open experiment →</a>` : ""}</div><p class="help section-gap">Evaluation is complete only after every distinct issue has a valid or invalid judgment. Clean cases with no findings still need an explicit evaluation.</p></section>` +
    `<section class="panel"><h2>Participation</h2>${table(
      ["Critic", "Phase / context", "Round", "State", "Model", "Usage"],
      detail.invocations.map(
        (i) =>
          `<tr><td>${criticButton(i.critic_id)}</td><td>${h({ lead: "Coordinator", independent: "Independent reviewer", critique: "Challenger" }[i.phase] || i.phase)}<small>${h(i.context)}</small></td><td>${i.round}</td><td>${pill(i.status)}${i.error ? `<small>${h(i.error)}</small>` : ""}</td><td>${h(i.resolved_model || i.model || "Unknown")}</td><td>${i.usage ? `${num(i.usage.input_tokens)} in / ${num(i.usage.output_tokens)} out<small>${money(i.usage.cost_usd)} · ${h(i.usage.cost_basis || "No cost measured")}</small>` : "Unknown"}</td></tr>`,
      ),
    )}</section>` +
    issueCards +
    (!issues.size
      ? `<section class="panel">${empty("No findings recorded", "This does not establish that the reviewed work has no defects. Check participation and scope.")}</section>`
      : "") +
    `<section class="panel timeline"><h2>Full event history</h2><p class="help">Received order is authoritative for dependency processing. Original event timestamps and actor permissions remain in each record.</p>${detail.events.map((e) => `<details><summary><time>${h(when(e.occurred_at))}</time><span>${h(titleCase(e.data.type))}</span><span class="pill">${h(e.actor)}</span></summary><pre>${h(JSON.stringify(e, null, 2))}</pre></details>`).join("")}</section>`
  );
}

function dialog(title, body, onSubmit) {
  $("#editor-title").textContent = title;
  $("#editor-body").innerHTML = body;
  $$("[data-close]", $("#editor")).forEach((b) =>
    b.addEventListener("click", () => $("#editor").close()),
  );
  const form = $("form", $("#editor-body"));
  if (form && onSubmit)
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submit = $("button[type=submit]", form);
      submit.disabled = true;
      try {
        await onSubmit(new FormData(form), form);
        $("#editor").close();
        await refresh();
      } catch (error) {
        $("[data-form-error]", form).textContent = error.message;
      } finally {
        submit.disabled = false;
      }
    });
  // A dialog may open another (for example a critic from a group's member list).
  if (!$("#editor").open) $("#editor").showModal();
}

function criticEditor(source = {}) {
  dialog(
    source.id ? "Create a critic variant" : "Create a critic",
    `<form><p class="help">Saving creates an immutable definition. Existing reviews keep their original prompt and configuration.</p>${field("Name", input("name", source.id ? `${source.name} variant` : ""))}${field("Specialty", input("specialty", source.effective_specialty || source.specialty || "General review"), "For example Security, Bug hunting, Evidence and testing, or a new specialty to experiment with.")}<input type="hidden" name="role" value="${h(source.role || "reviewer")}"><div class="form-grid">${field(
      "Provider",
      select(
        "provider",
        [
          ["", "Selected by client"],
          ["codex", "Codex"],
          ["claude", "Claude"],
        ],
        source.provider || "",
      ),
    )}${field("Model", input("model", source.model || "", false), "Use an explicit model for controlled comparisons. Otherwise its identity may remain unknown.")}</div>${field("Critic instructions", area("prompt", source.prompt || ""))}${field("Runtime settings", area("settings", JSON.stringify(source.settings || {}, null, 2), false), "JSON object. Trial runner accepts reasoning_effort for Codex; effort and max_budget_usd for Claude.")}${actions("Save definition")}</form>`,
    async (data) => {
      await api("/api/critics", {
        method: "POST",
        body: JSON.stringify({
          name: data.get("name"),
          role: data.get("role"),
          specialty: data.get("specialty"),
          prompt: data.get("prompt"),
          provider: data.get("provider") || null,
          model: data.get("model") || null,
          settings: JSON.parse(data.get("settings") || "{}"),
        }),
      });
      toast("Critic definition saved");
    },
  );
}

function contributionSummary(stats) {
  return `<section class="panel"><h3>Contributions in this cohort</h3><div class="progress-list"><div><span>Issues raised</span><span>${num(stats.distinct_issues)} in ${plural(stats.run_count, "review")} · ${decimal(stats.issues_per_review)} per review</span></div><div><span>Kept by reviewer (provisional)</span><span>${num(stats.reviewer_supported_issues)} kept · ${num(stats.reviewer_withdrawn_issues)} withdrawn</span></div><div><span>Unique reported issues, kept / raised</span><span>${num(stats.exclusive_supported_issues)} / ${num(stats.exclusive_issues)}</span></div><div><span>Kept independent discoveries / comparable reviews</span><span>${num(stats.unique_supported_discoveries)} / ${num(stats.comparison_reviews)}</span></div><div><span>Challenges that changed the review</span><span>${num(stats.challenges_changed_review)} / ${num(stats.challenges)}</span></div><div><span>Independently valid</span><span>${num(stats.valid_issues)} / ${num(stats.valid_issues + stats.invalid_issues)} judged</span></div><div><span>Fixed / deferred / reopened</span><span>${stats.outcomes.fixed || 0} / ${stats.outcomes.deferred || 0} / ${stats.outcomes.reopened || 0}</span></div><div><span>Median elapsed pass</span><span>${duration(stats.median_pass_seconds)}</span></div><div><span>Runtime tokens</span><span>${num(stats.usage.input_tokens)} in / ${num(stats.usage.output_tokens)} out</span></div><div><span>Complete cost per valid issue</span><span>${money(stats.cost_per_valid_issue)}</span></div></div></section>`;
}

function uniqueEvidence(stats) {
  const refs = stats.unique_issue_refs || [];
  return `<h3>Unique reported issues</h3><p class="help">No other participant reported these issues after explicit duplicate merges. This does not establish correctness or that another reviewer could not find them. Solo reviews are excluded. Group totals mean unique outside the entire group.</p>${
    refs.length
      ? table(
          [
            "Issue / review",
            "Reviewer decision",
            "Independent comparison",
            "Validity",
          ],
          refs.map(
            (r) =>
              `<tr><td><a href="#run/${encodeURIComponent(r.run_id)}">${h(r.title)}</a><small>${h(r.issue_id)} · ${h(r.run_id)}</small></td><td>${reviewerPill(r.reviewer_state)}</td><td>${r.independent_comparison ? "Comparable" : "Not established"}</td><td>${pill(r.validity)}</td></tr>`,
          ),
        )
      : '<p class="subtle">No unique reported issues established in this cohort.</p>'
  }`;
}

function inspectCritic(id) {
  const critic = state.critics.find((c) => c.id === id);
  const stats = state.dashboard.metrics.critics.find((c) => c.critic_id === id);
  dialog(
    critic.name,
    `<p class="subtle">${h(stats?.specialty || critic.specialty || "Specialty not recorded")}</p><p class="mono">${h(critic.id)}</p><div class="key-values"><div><small>Provider</small>${h(critic.provider || "Client selected")}</div><div><small>Model</small>${h(critic.model || "Unresolved runtime default")}</div></div>${stats ? contributionSummary(stats) + uniqueEvidence(stats) : ""}<h3>Instructions</h3><pre>${h(critic.prompt)}</pre><h3>Settings</h3><pre>${h(JSON.stringify(critic.settings, null, 2))}</pre>${
      stats
        ? `<h3>Confidence calibration in this cohort</h3>${table(
            ["Claimed confidence", "Proposed", "Valid / decided", "Validity"],
            Object.entries(stats.confidence).map(
              ([label, c]) =>
                `<tr><td>${h(label)}</td><td>${c.proposed}</td><td>${c.valid} / ${c.valid + c.invalid}</td><td>${pct(c.validity_rate)}</td></tr>`,
            ),
          )}<h3 class="section-gap">Validated impact</h3>${
            Object.entries(stats.severity)
              .map(
                ([severity, count]) =>
                  `<p>${pill(severity)} ${count} issues</p>`,
              )
              .join("") || '<p class="subtle">No validated impact yet.</p>'
          }<h3 class="section-gap">Contributing reviews</h3>${runTable(state.dashboard.runs.filter((r) => stats.run_ids.includes(r.id)))}`
        : ""
    }<div class="form-actions"><button data-close>Close</button><button data-fork-critic="${h(id)}">Create variant</button></div>`,
  );
}

function inspectGroup(key) {
  const metrics = state.dashboard.metrics;
  const group = metrics.groups[state.groupBy]?.find((g) => g.group_key === key);
  if (!group) return;
  const members = metrics.critics.filter((c) =>
    group.critic_ids.includes(c.critic_id),
  );
  dialog(
    group.label,
    `<p class="subtle">${members.length} ${members.length === 1 ? "definition shares" : "definitions share"} this specialty grouping. Totals count each issue once, even when several of these definitions found it.</p>${contributionSummary(group)}${uniqueEvidence(group)}<h3>Definitions</h3>${table(
      [
        "Definition",
        "Reviews",
        "Issues raised",
        "Kept by reviewer",
        "Independently valid",
      ],
      members.map(
        (c) =>
          `<tr><td class="title-cell">${criticButton(c.critic_id)}<small>${h(c.model || "Model not recorded")}</small></td><td>${num(c.run_count)}</td><td>${num(c.distinct_issues)}</td><td>${num(c.reviewer_supported_issues)}</td><td>${num(c.valid_issues)}</td></tr>`,
      ),
    )}<h3 class="section-gap">Contributing reviews</h3>${runTable(state.dashboard.runs.filter((r) => group.run_ids.includes(r.id)))}<div class="form-actions"><button data-close>Close</button></div>`,
  );
}

function experimentEditor() {
  let variants = 2,
    cases = 1;
  const variantBlock = (i) =>
    `<section class="builder-block" data-variant><h3>Variant ${i + 1}</h3>${field("Name", input(`variant_name_${i}`, i ? "Candidate" : "Baseline"))}<div class="checkbox-grid">${state.critics.map((c) => `<label><input type="checkbox" name="variant_critics_${i}" value="${h(c.id)}"><span>${h(c.name)}<small class="mono"> ${h(short(c.id))}</small></span></label>`).join("")}</div></section>`;
  const caseBlock = (i) =>
    `<section class="builder-block" data-case data-index="${i}"><h3>Frozen case ${i + 1}</h3>${field("Case title", input(`case_title_${i}`))}${field("Target label", input(`case_target_${i}`))}${field("Target fingerprint", input(`case_revision_${i}`), "Get the exact value with critic-observer fingerprint /path/to/case.")}${field("Review instructions", area(`case_instructions_${i}`))}<div data-known-list></div><button type="button" class="small" data-add-known>Add known defect</button><p class="help section-gap">An empty reference can be a control or an unknown answer key; it does not establish that the case has no defects. Answer keys are excluded from client review briefs.</p></section>`;
  dialog(
    "Create an experiment",
    `<form><p class="help">Definitions freeze on save. Use a new experiment to change cases, team membership, or the primary measure.</p>${field("Experiment name", input("name"))}${field("Hypothesis", area("hypothesis"))}${field(
      "Skill fingerprint",
      input("skill_revision"),
      "Run critic-observer skill-fingerprint /path/to/project-review-process --review-type TYPE, using the review type selected below, for example architecture or pull_request.",
    )}${field("Review type", select("review_type", REVIEW_TYPES, state.dashboard.filters.review_type), "Each experiment belongs to one review type. Its trials use that review guide.")}${field(
      "Input mode",
      select(
        "input_mode",
        [
          ["filesystem", "CLI inspects local files"],
          ["snapshot", "Verified text snapshot, up to 128 KB"],
        ],
        "filesystem",
      ),
      "Snapshot mode supplies all case files directly. It is frozen for every variant.",
    )}${field(
      "Primary measure",
      select(
        "primary_metric",
        [
          ["known_defect_recall", "Known-defect recall"],
          ["valid_issues", "Validated issues"],
          ["false_alarms", "False alarms"],
          ["cost_usd", "Review cost"],
        ],
        "known_defect_recall",
      ),
    )}<h3>Critic teams</h3><div id="variant-builder">${variantBlock(0)}${variantBlock(1)}</div><button type="button" id="add-variant">Add variant</button><h3 class="section-gap">Frozen cases</h3><div id="case-builder">${caseBlock(0)}</div><button type="button" id="add-case">Add case</button>${actions("Create experiment")}</form>`,
    async (data, form) => {
      const knownIssue = (row) => ({
        id: $("[data-known-id]", row).value,
        title: $("[data-known-title]", row).value,
        severity: $("[data-known-severity]", row).value,
        evidence: $("[data-known-evidence]", row).value,
      });
      const document = {
        name: data.get("name"),
        hypothesis: data.get("hypothesis"),
        skill_revision: data.get("skill_revision"),
        review_type: data.get("review_type"),
        input_mode: data.get("input_mode"),
        primary_metric: data.get("primary_metric"),
        variants: Array.from({ length: variants }, (_, i) => ({
          id: `variant-${i + 1}`,
          name: data.get(`variant_name_${i}`),
          critic_ids: data.getAll(`variant_critics_${i}`),
        })),
        cases: Array.from({ length: cases }, (_, i) => ({
          id: `case-${i + 1}`,
          title: data.get(`case_title_${i}`),
          target: data.get(`case_target_${i}`),
          target_revision: data.get(`case_revision_${i}`),
          instructions: data.get(`case_instructions_${i}`),
          known_issues: $$(
            `[data-case][data-index="${i}"] .known-row`,
            form,
          ).map(knownIssue),
        })),
      };
      const result = await api("/api/experiments", {
        method: "POST",
        body: JSON.stringify(document),
      });
      toast("Experiment definition frozen");
      $("#filters [name=review_type]").value = result.review_type;
      clearExperimentFilters();
      location.hash = `experiment/${result.id}`;
    },
  );
  $("#add-variant").addEventListener("click", () => {
    if (variants < 10)
      $("#variant-builder").insertAdjacentHTML(
        "beforeend",
        variantBlock(variants++),
      );
  });
  $("#add-case").addEventListener("click", () => {
    if (cases < 100)
      $("#case-builder").insertAdjacentHTML("beforeend", caseBlock(cases++));
  });
  $("#case-builder").addEventListener("click", (event) => {
    if (!event.target.closest("[data-add-known]")) return;
    const block = event.target.closest("[data-case]");
    const count = $$(".known-row", block).length + 1;
    $("[data-known-list]", block).insertAdjacentHTML(
      "beforeend",
      `<div class="known-row">${field("Known defect ID", `<input data-known-id value="defect-${count}" required pattern="[A-Za-z0-9_.:-]+">`)}${field("Title", "<input data-known-title required>")}${field("Severity", '<select data-known-severity><option value="blocking">Blocking</option><option value="should_fix" selected>Should fix</option><option value="consider">Consider</option></select>')}${field("Independent evidence / reproduction", "<textarea data-known-evidence required></textarea>")}</div>`,
    );
  });
}

async function record(payloads) {
  const list = Array.isArray(payloads) ? payloads : [payloads];
  const events = list.map((data) => ({
    event_id: eventId(),
    run_id: state.detail.run.id,
    occurred_at: new Date().toISOString(),
    data,
  }));
  await api("/api/events", {
    method: "POST",
    body: JSON.stringify({ events }),
  });
}
function claimContext(issueId) {
  const detail = state.detail;
  const invocation = (id) => detail.invocations.find((i) => i.id === id);
  const claims = latestFindings(detail).filter((f) => f.issue_id === issueId);
  return `<section class="claim-context" aria-label="What the critics claimed"><p class="help">${h(detail.run.title)} · ${h(detail.run.target)} at <code>${h(detail.run.target_revision)}</code></p>${claims
    .map((f) => {
      const origin = invocation(f.origin_invocation_id || f.invocation_id);
      const decision = detail.decisions.find(
        (d) => d.finding_id === f.id && d.finding_version === f.version,
      );
      const verdicts = detail.verdicts.filter(
        (v) => v.finding_id === f.id && v.finding_version === f.version,
      );
      return `<div class="claim"><h3>${h(f.title)}</h3><p>${h(criticName(origin.critic_id))} · ${pill(f.severity)} ${pill(f.confidence)} <span class="subtle">version ${f.version} · round ${origin.round}</span></p><p class="mono">${h(f.location)}</p><p class="claim-label">Trigger</p><p>${h(f.trigger)}</p><p class="claim-label">Impact</p><p>${h(f.impact)}</p><p class="claim-label">Evidence given by the critic</p><pre>${h(f.evidence)}</pre>${decision ? `<p>Review team: ${reviewerPill(decision.state)} ${h(decision.rationale)}</p>` : ""}${verdicts.map((v) => `<div class="verdict">${h(criticName(invocation(v.invocation_id).critic_id))} · ${pill(v.verdict)}<p class="rationale">${h(v.rationale)}</p>${v.evidence ? `<pre>${h(v.evidence)}</pre>` : ""}</div>`).join("")}</div>`;
    })
    .join("")}</section>`;
}
async function assessIssue(runId, issueId) {
  if (!(await loadRun(runId))) return;
  issueJudgment(issueId, true);
}
function issueJudgment(issueId, withContext = false) {
  const old = state.detail.judgments.find((j) => j.issue_id === issueId);
  const claimed = latestFindings(state.detail)
    .filter((f) => f.issue_id === issueId)
    .map((f) => titleCase(f.severity));
  dialog(
    "Assess issue validity",
    `<form>${withContext ? claimContext(issueId) : ""}<p class="help">Use independent evidence. Acceptance by the review team does not establish correctness.</p><div class="form-grid">${field(
      "Validity",
      select(
        "validity",
        [
          ["unknown", "Unknown"],
          ["valid", "Valid"],
          ["invalid", "Invalid"],
        ],
        old?.validity || "unknown",
      ),
    )}${field(
      "Adjudicated severity",
      select(
        "severity",
        [
          ["", "Not assessed"],
          ["blocking", "Blocking"],
          ["should_fix", "Should fix"],
          ["consider", "Consider"],
        ],
        old?.severity || "",
      ),
      `Required when valid. Claimed: ${[...new Set(claimed)].join(", ")}.`,
    )}${field(
      "Assessment method",
      select(
        "method",
        [
          ["human", "Human review"],
          ["reproduction", "Reproduced behavior"],
          ["benchmark", "Benchmark evidence"],
        ],
        old?.method || "human",
      ),
    )}${field("Assessor", input("assessor", old?.assessor || "Operator"))}</div>${field("Rationale", area("rationale", old?.rationale || ""))}${field("Independent evidence", area("evidence", old?.evidence || ""))}${state.knownIssues.length ? field("Known defect match", select("known_issue_id", [["", "No known-defect match"], ...state.knownIssues.map((i) => [i.id, i.title])], old?.known_issue_id || "")) : ""}${actions("Save judgment")}</form>`,
    async (data) => {
      await record({
        type: "issue_judged",
        issue_id: issueId,
        revision: (old?.revision || 0) + 1,
        validity: data.get("validity"),
        severity: data.get("severity") || null,
        method: data.get("method"),
        assessor: data.get("assessor"),
        rationale: data.get("rationale"),
        evidence: data.get("evidence"),
        known_issue_id: data.get("known_issue_id") || null,
      });
      toast(
        "Independent judgment saved. Re-mark evaluation complete after revisions.",
      );
    },
  );
}
function mergeIssue(issueId) {
  const others = [
    ...new Map(
      latestFindings(state.detail)
        .filter((f) => f.issue_id !== issueId)
        .map((f) => [f.issue_id, f]),
    ).values(),
  ];
  if (!others.length) return toast("No other issue is available to merge.");
  dialog(
    "Merge duplicate issues",
    `<form><p class="help">Both claims retain discovery credit and source history. Merge before adjudicating either issue. A merge cannot be undone through this UI; export the evidence first if uncertain.</p>${field(
      "Merge this issue into",
      select(
        "target",
        others.map((f) => [f.issue_id, f.title]),
        others[0].issue_id,
      ),
    )}${field("Why these claims describe the same defect", area("reason"))}${actions("Merge issues")}</form>`,
    async (data) => {
      await record({
        type: "issues_merged",
        source_issue_id: issueId,
        target_issue_id: data.get("target"),
        reason: data.get("reason"),
      });
      toast("Duplicate issues merged");
    },
  );
}
function outcomeEditor(issueId) {
  const old = state.detail.outcomes.find((o) => o.issue_id === issueId);
  dialog(
    "Record what happened next",
    `<form>${field(
      "Outcome",
      select(
        "state",
        [
          ["fixed", "Fixed"],
          ["deferred", "Deferred"],
          ["reopened", "Reopened"],
        ],
        old?.state || "fixed",
      ),
    )}${field("Rationale", area("rationale", old?.rationale || ""))}${field("Fix or decision reference", area("reference", old?.reference || ""))}${actions("Record outcome")}</form>`,
    async (data) => {
      await record({
        type: "outcome_recorded",
        issue_id: issueId,
        revision: (old?.revision || 0) + 1,
        state: data.get("state"),
        rationale: data.get("rationale"),
        reference: data.get("reference"),
      });
      toast("Outcome recorded");
    },
  );
}
function challengeEditor(id) {
  const old = state.detail.challenge_judgments.find(
    (j) => j.verdict_event_id === id,
  );
  dialog(
    "Assess a critic's challenge",
    `<form><p class="help">Judge whether the objection held up against evidence. A reviewer withdrawing a claim is not sufficient proof.</p>${field(
      "Result",
      select(
        "result",
        [
          ["unknown", "Unknown"],
          ["upheld", "Upheld"],
          ["rejected", "Rejected"],
        ],
        old?.result || "unknown",
      ),
    )}${field(
      "Effect",
      select(
        "effect",
        [
          ["none", "None / not established"],
          ["removed_invalid_claim", "Removed an invalid claim"],
          ["rescued_valid_claim", "Rescued a valid claim"],
          ["improved_evidence", "Improved the evidence"],
        ],
        old?.effect || "none",
      ),
    )}${field("Assessor", input("assessor", old?.assessor || "Operator"))}${field("Independent evidence", area("evidence", old?.evidence || ""))}${actions("Save assessment")}</form>`,
    async (data) => {
      await record({
        type: "challenge_judged",
        verdict_event_id: id,
        revision: (old?.revision || 0) + 1,
        result: data.get("result"),
        effect: data.get("effect"),
        assessor: data.get("assessor"),
        evidence: data.get("evidence"),
      });
      toast("Challenge assessment saved");
    },
  );
}
function decisionEditor(id) {
  const finding = latestFindings(state.detail).find((f) => f.id === id);
  const old = state.detail.decisions.find(
    (d) => d.finding_id === id && d.finding_version === finding.version,
  );
  dialog(
    "Record the reviewer response",
    `<form>${field(
      "Decision",
      select(
        "state",
        [
          ["supported", "Supported"],
          ["withdrawn", "Withdrawn"],
          ["unresolved", "Unresolved"],
        ],
        old?.state || "unresolved",
      ),
    )}${field("Reason", area("rationale", old?.rationale || ""))}${field("Evidence", area("evidence", old?.evidence || "", false))}${actions("Save decision")}</form>`,
    async (data) => {
      await record({
        type: "decision_recorded",
        finding_id: id,
        finding_version: finding.version,
        revision: (old?.revision || 0) + 1,
        state: data.get("state"),
        rationale: data.get("rationale"),
        evidence: data.get("evidence"),
      });
      toast("Reviewer response saved");
    },
  );
}
function invalidateRun() {
  dialog(
    "Invalidate an unusable result",
    `<form><p class="help">This preserves history and usage costs but excludes the claims from quality statistics and matched results. Use it when context or inspection was unavailable.</p>${field("Reason", area("reason"))}${actions("Invalidate result")}</form>`,
    async (data) => {
      await record({ type: "run_invalidated", reason: data.get("reason") });
      toast("Result invalidated; history preserved");
    },
  );
}
function evaluateRun() {
  dialog(
    "Mark evaluation complete",
    `<form><p class="help">Confirm that you have assessed every reported issue, merged duplicates, and matched known defects where applicable. Review known defects that nobody reported too. This enables matched experiment comparisons.</p>${field("Assessor", input("assessor", "Operator"))}${field("Evaluation evidence / notes", area("evidence"))}${actions("Complete evaluation")}</form>`,
    async (data) => {
      await record({
        type: "run_evaluated",
        assessor: data.get("assessor"),
        evidence: data.get("evidence"),
      });
      toast("Evaluation marked complete");
    },
  );
}
function cancelRun() {
  dialog(
    "Close an interrupted run",
    `<form><p class="help">Use this after confirming the original review client has stopped. Active invocation records will be cancelled.</p>${field("Reason", area("reason"))}${actions("Close run")}</form>`,
    async (data) => {
      const payloads = state.detail.invocations
        .filter((i) => i.status === "running")
        .map((i) => ({
          type: "invocation_finished",
          invocation_id: i.id,
          status: "cancelled",
          error: data.get("reason"),
        }));
      payloads.push({
        type: "run_finished",
        status: "cancelled",
        reason: data.get("reason"),
      });
      await record(payloads);
      toast("Interrupted run closed");
    },
  );
}

function cohortOptions() {
  const put = (name, options, label) => {
    const el = $(`#filters [name=${name}]`),
      current = el.value;
    el.innerHTML =
      `<option value="">${label}</option>` +
      options
        .map(
          (o) => `<option value="${h(o.id)}">${h(o.name || o.title)}</option>`,
        )
        .join("");
    el.value = options.some((o) => o.id === current) ? current : "";
  };
  put("experiment_id", state.experiments, "All experiments");
  const chosen = state.experiments.find(
    (e) => e.id === $("#filters [name=experiment_id]").value,
  );
  put("variant_id", chosen?.variants || [], "All variants");
  put("case_id", chosen?.cases || [], "All cases");
}
function clearExperimentFilters() {
  for (const name of ["experiment_id", "variant_id", "case_id"])
    $(`#filters [name=${name}]`).value = "";
}
const PAGE_NAMES = {
  run: "Review details",
  experiment: "Experiment details",
  assess: "Assess issues",
};

async function refresh() {
  const generation = ++state.generation;
  state.refreshController?.abort();
  const controller = new AbortController();
  state.refreshController = controller;
  $("#error-banner").hidden = true;
  $("#connection-state").textContent = "Loading";
  try {
    const query = new URLSearchParams(new FormData($("#filters")));
    const [dashboard, critics, experiments] = await Promise.all([
      api(`/api/dashboard?${query}`, { signal: controller.signal }),
      api("/api/critics", { signal: controller.signal }),
      api(
        `/api/experiments?review_type=${encodeURIComponent(query.get("review_type"))}`,
        { signal: controller.signal },
      ),
    ]);
    if (generation !== state.generation) return;
    state.dashboard = dashboard;
    state.critics = critics;
    state.experiments = experiments;
    cohortOptions();
    await render(generation);
  } catch (error) {
    if (generation === state.generation) {
      showError(error);
      $("#connection-state").textContent = "Needs attention";
    }
  }
}

// Draws the current page from loaded data. Changing a view option (grouping,
// order) calls this directly instead of fetching the cohort again.
async function render(generation = state.generation) {
  const rendering = ++state.renderGeneration;
  const [route, id] = location.hash.slice(1).split("/");
  const page = route || "overview";
  if (page !== "run") ++state.detailGeneration;
  const routes = {
    overview,
    assess: assessPage,
    runs: runsPage,
    critics: criticsPage,
    disagreements: disagreementsPage,
    rounds: roundsPage,
    quality: qualityPage,
    connect: connectPage,
    experiments: experimentsPage,
  };
  let html;
  try {
    html =
      page === "run"
        ? await runDetail(decodeURIComponent(id))
        : page === "experiment"
          ? await experimentDetail(decodeURIComponent(id))
          : await (routes[page] || overview)();
  } catch (error) {
    if (generation === state.generation && rendering === state.renderGeneration)
      throw error;
    return;
  }
  if (generation !== state.generation || rendering !== state.renderGeneration)
    return;
  $("#content").innerHTML = html;
  $("#breadcrumb").textContent =
    `Workspace / ${PAGE_NAMES[page] || titleCase(page)}`;
  $$("[data-page]").forEach((a) => {
    if (a.dataset.page === page) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  $("#assess-count").textContent = state.dashboard.assessment.total || "";
  $("#metric-version").textContent =
    `Metric definitions ${state.dashboard.metrics.metric_version}`;
  $("#connection-state").textContent = "Connected";
  $("#filters").hidden = ["run", "experiment", "connect"].includes(page);
  const chosenExperiment = state.experiments.find(
    (e) => e.id === $("#filters [name=experiment_id]").value,
  );
  const chosenVariant = chosenExperiment?.variants.find(
    (v) => v.id === $("#filters [name=variant_id]").value,
  );
  const chosenCase = chosenExperiment?.cases.find(
    (c) => c.id === $("#filters [name=case_id]").value,
  );
  $("#cohort-summary").hidden = $("#filters").hidden;
  $("#cohort-summary").textContent =
    [cohort(), chosenExperiment?.name, chosenVariant?.name, chosenCase?.title]
      .filter(Boolean)
      .join(" / ") || "All experiments and variants in this cohort";
}

document.addEventListener("click", (event) => {
  const target = event.target.closest("button");
  if (!target) return;
  const d = target.dataset;
  if ("refresh" in d) refresh();
  if ("newCritic" in d) criticEditor();
  if (d.scopeExperiment) {
    $("#filters").reset();
    $("#filters [name=review_type]").value = d.reviewType;
    $("#filters [name=dataset]").value = "benchmark";
    // A direct experiment link may belong to another cohort than the loaded list.
    if (!state.experiments.some((e) => e.id === d.scopeExperiment))
      state.experiments.push(state.experiment.experiment);
    cohortOptions();
    $("#filters [name=experiment_id]").value = d.scopeExperiment;
    cohortOptions();
    $("#filters [name=variant_id]").value = d.scopeVariant;
    history.replaceState(null, "", "#overview");
    refresh();
  }
  if (d.critic) inspectCritic(d.critic);
  if (d.group) inspectGroup(d.group);
  if (d.assessRun) assessIssue(d.assessRun, d.assessIssue).catch(showError);
  if (d.forkCritic) {
    $("#editor").close();
    criticEditor(state.critics.find((c) => c.id === d.forkCritic));
  }
  if ("newExperiment" in d) experimentEditor();
  if (d.judge) issueJudgment(d.judge);
  if (d.merge) mergeIssue(d.merge);
  if (d.outcome) outcomeEditor(d.outcome);
  if (d.judgeChallenge) challengeEditor(d.judgeChallenge);
  if (d.decision) decisionEditor(d.decision);
  if ("evaluate" in d) evaluateRun();
  if ("invalidate" in d) invalidateRun();
  if ("cancelRun" in d) cancelRun();
});
document.addEventListener("change", (event) => {
  const control = event.target;
  if (control.matches("[data-group-by]")) state.groupBy = control.value;
  else if (control.matches("[data-sort-by]")) state.sortBy = control.value;
  else return;
  render().catch(showError);
});
$("#close-editor").addEventListener("click", () => $("#editor").close());
$("#filters [name=experiment_id]").addEventListener("change", () => {
  $("#filters [name=variant_id]").value = "";
  $("#filters [name=case_id]").value = "";
  cohortOptions();
});
$("#filters [name=review_type]").addEventListener("change", () => {
  clearExperimentFilters();
  // Apply the review-type switch immediately, so no old results are relabelled.
  refresh();
});
$("#editor").addEventListener("click", (event) => {
  if (event.target.closest('a[href^="#"]')) $("#editor").close();
});
$("#filters").addEventListener("submit", (event) => {
  event.preventDefault();
  refresh();
});
window.addEventListener("hashchange", () => {
  if (!$("#shell").hidden && state.dashboard) render().catch(showError);
});
$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("button", event.target);
  button.disabled = true;
  try {
    await api("/api/login", {
      method: "POST",
      body: JSON.stringify({ token: $("#credential").value }),
    });
    $("#credential").value = "";
    $("#login-error").textContent = "";
    showShell();
    await refresh();
  } catch (error) {
    $("#login-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
$("#logout").addEventListener("click", async () => {
  try {
    await api("/api/logout", { method: "POST" });
    showLogin();
  } catch (error) {
    showError(error);
  }
});
try {
  await api("/api/session");
  showShell();
  await refresh();
} catch {
  showLogin();
}
