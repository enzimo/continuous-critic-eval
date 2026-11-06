import os

import pytest
from conftest import finding, finish_inv, invocation, started, submit
from playwright.sync_api import expect, sync_playwright
from test_experiments import experiment

from critic_observer.models import Critic, Experiment


@pytest.mark.browser
def test_operator_workflow_and_mobile_layout(live_server, tmp_path):
    if not os.getenv("PLAYWRIGHT_BROWSERS_PATH"):
        pytest.skip("Set PLAYWRIGHT_BROWSERS_PATH to run the real browser check")
    app, _, settings = live_server
    first = app.state.store.critics()[0]
    critic = first["id"]
    payload = finding("f", "i")
    payload["title"] = '<img src=x onerror="window.compromised=true">'
    submit(
        app.state.store,
        "browser",
        started([critic], dataset="benchmark", review_type="pull_request"),
        invocation(critic, "i"),
        payload,
        finish_inv("i"),
        {"type": "run_finished", "status": "completed", "reason": "done"},
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(settings.public_url)
        page.get_by_label("Operator credential").fill(settings.admin_token)
        page.get_by_role("button", name="Open dashboard").click()
        expect(page.get_by_role("heading", name="What did the critics add?")).to_be_visible()
        assert page.locator('#filters [name="dataset"] option').evaluate_all(
            "options => options.map(option => option.value)"
        ) == ["production", "benchmark", "demo", ""]
        expect(page.get_by_role("link", name="Overview", exact=True)).to_have_attribute(
            "aria-current", "page"
        )
        page.locator('#filters [name="dataset"]').select_option("benchmark")
        page.get_by_role("button", name="Apply", exact=True).click()
        expect(page.get_by_role("link", name="Review sample")).to_be_visible()
        expect(page.get_by_role("heading", name="Who contributes")).to_be_visible()
        page.get_by_role("link", name="Connect clients", exact=True).click()
        expect(
            page.get_by_role("heading", name="One collector, several ways to report")
        ).to_be_visible()
        expect(
            page.get_by_text(
                '"headers": {"Authorization": "Bearer ${OBSERVER_TOKEN}"}', exact=False
            )
        ).to_be_visible()
        page.get_by_role("link", name="Critics", exact=True).click()
        results = page.locator("#content table").first
        expect(results.get_by_role("button", name=first["name"], exact=True)).to_be_visible()
        page.locator("[data-group-by]").select_option("definition")
        expect(results.get_by_role("button", name=first["name"], exact=True)).to_be_visible()
        page.get_by_role("button", name="Create critic", exact=True).click()
        editor = page.get_by_role("dialog")
        editor.get_by_label("Name", exact=True).fill("Adversarial role")
        editor.get_by_label("Specialty", exact=True).fill("Counterexamples")
        editor.get_by_label("Critic instructions", exact=True).fill(
            "Find reachable counterexamples and cite evidence."
        )
        editor.get_by_role("button", name="Save definition").click()
        expect(page.get_by_role("heading", name="Adversarial role", exact=True)).to_be_visible()
        page.get_by_role("link", name="Experiments", exact=True).click()
        page.get_by_role("button", name="Create experiment", exact=True).click()
        editor = page.get_by_role("dialog")
        editor.get_by_label("Experiment name", exact=True).fill("Browser experiment")
        editor.get_by_label("Hypothesis", exact=True).fill("A distinct role finds omitted cases.")
        editor.get_by_label("Skill fingerprint", exact=True).fill("test-v1")
        editor.locator("[data-variant]").nth(0).get_by_role("checkbox").nth(0).check()
        editor.locator("[data-variant]").nth(1).get_by_role("checkbox").nth(1).check()
        case = editor.locator("[data-case]")
        case.get_by_label("Case title", exact=True).fill("Frozen sample")
        case.get_by_label("Target label", exact=True).fill("sample")
        case.get_by_label("Target fingerprint", exact=True).fill("sha256:fixed")
        case.get_by_label("Review instructions", exact=True).fill("Check the documented contract.")
        case.get_by_role("button", name="Add known defect").click()
        case.get_by_label("Title", exact=True).fill("Owner mismatch")
        case.get_by_label("Independent evidence / reproduction", exact=True).fill(
            "A different owner can complete the task."
        )
        editor.get_by_role("button", name="Create experiment", exact=True).click()
        expect(page.get_by_role("heading", name="Browser experiment", exact=True)).to_be_visible()
        page.get_by_role("link", name="Assess issues").click()
        expect(
            page.get_by_role("heading", name="Which issues still need a judgment?")
        ).to_be_visible()
        expect(page.get_by_text(payload["title"], exact=True)).to_be_visible()
        page.get_by_role("button", name="Assess", exact=True).click()
        assert not errors, errors
        editor = page.get_by_role("dialog")
        expect(editor).to_be_visible()
        expect(editor.get_by_text("Evidence given by the critic")).to_be_visible()
        expect(editor.get_by_text(payload["evidence"])).to_be_visible()
        editor.get_by_label("Validity", exact=True).select_option("valid")
        editor.get_by_label("Adjudicated severity", exact=True).select_option("should_fix")
        editor.get_by_label("Rationale", exact=True).fill("Reproduced against the frozen target.")
        editor.get_by_label("Independent evidence", exact=True).fill(
            "The incorrect owner completed the job."
        )
        editor.get_by_role("button", name="Save judgment", exact=True).click()
        expect(page.get_by_role("heading", name="Nothing is waiting")).to_be_visible()
        page.goto(settings.public_url + "/#run/browser")
        expect(page.locator(".issue-card.valid")).to_be_visible()
        assert page.evaluate("window.compromised") is None
        page.get_by_role("button", name="Record outcome", exact=True).click()
        editor = page.get_by_role("dialog")
        editor.get_by_label("Rationale", exact=True).fill(
            "Executed the reproduction after the fix."
        )
        editor.get_by_label("Fix or decision reference", exact=True).fill("fix-123")
        editor.get_by_role("button", name="Record outcome", exact=True).click()
        expect(page.locator(".pill.fixed")).to_be_visible()
        page.get_by_role("button", name="Mark evaluation complete", exact=True).click()
        editor = page.get_by_role("dialog")
        editor.get_by_label("Evaluation evidence / notes", exact=True).fill(
            "Every reported issue was independently checked."
        )
        editor.get_by_role("button", name="Complete evaluation", exact=True).click()
        expect(page.locator(".pill.evaluated")).to_be_visible()
        for route in (
            "overview",
            "assess",
            "runs",
            "critics",
            "disagreements",
            "rounds",
            "quality",
            "experiments",
        ):
            page.goto(settings.public_url + "/#" + route)
            expect(page.locator("#connection-state")).to_have_text("Connected")
            expect(page.locator("#error-banner")).to_be_hidden()
        page.set_viewport_size({"width": 390, "height": 844})
        for route in ("overview", "assess", "critics", "run/browser", "connect"):
            page.goto(settings.public_url + "/#" + route)
            expect(page.locator("#connection-state")).to_have_text("Connected")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), {
                "route": route,
                "overflow": page.evaluate(
                    "[...document.querySelectorAll('*')].filter(e=>e.getBoundingClientRect().right>innerWidth).slice(0,12).map(e=>({tag:e.tagName,cls:e.className,width:e.getBoundingClientRect().width}))"
                ),
            }
        assert errors == []
        browser.close()


@pytest.mark.browser
def test_unique_specialist_ranking_opens_actual_issue_evidence(live_server):
    if not os.getenv("PLAYWRIGHT_BROWSERS_PATH"):
        pytest.skip("Set PLAYWRIGHT_BROWSERS_PATH to run the real browser check")
    app, _, settings = live_server
    store = app.state.store
    security, bugs = [
        store.register_critic(
            Critic(name=name, role="reviewer", specialty=specialty, prompt=f"Inspect {specialty}")
        )["id"]
        for name, specialty in (("Security probe", "Security"), ("Bug probe", "Bug hunting"))
    ]
    title = '<img src=x onerror="window.compromised=true">'
    submit(
        store,
        "unique-browser",
        started([security, bugs], review_type="pull_request"),
        invocation(security, "s"),
        invocation(bugs, "b"),
        finding("same-s", "s"),
        finding("same-b", "b"),
        {
            "type": "issues_merged",
            "source_issue_id": "same-b",
            "target_issue_id": "same-s",
            "reason": "Same trigger and failure",
        },
        {**finding("security-only", "s"), "title": title},
        {
            "type": "decision_recorded",
            "finding_id": "security-only",
            "finding_version": 1,
            "state": "supported",
            "rationale": "Source supports the claim",
        },
        finish_inv("s"),
        finish_inv("b"),
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.goto(settings.public_url)
        page.get_by_label("Operator credential").fill(settings.admin_token)
        page.get_by_role("button", name="Open dashboard").click()
        expect(page.get_by_role("heading", name="What did the critics add?")).to_be_visible()
        first_row = page.locator("#content table tbody tr").first
        expect(first_row.get_by_role("button", name="Security probe")).to_be_visible()
        first_row.get_by_role("button", name="Security probe").click()
        editor = page.get_by_role("dialog")
        expect(editor.get_by_role("heading", name="Unique reported issues")).to_be_visible()
        expect(editor.get_by_role("link", name=title, exact=True)).to_be_visible()
        expect(editor.get_by_text("Comparable", exact=True)).to_be_visible()
        assert page.evaluate("window.compromised") is None
        editor.get_by_role("button", name="Close", exact=True).click()
        page.locator("[data-group-by]").first.select_option("specialty")
        page.get_by_role("button", name="Security", exact=True).click()
        expect(editor.get_by_role("link", name=title, exact=True)).to_be_visible()
        assert page.evaluate("window.compromised") is None
        browser.close()


@pytest.mark.browser
def test_navigation_uses_loaded_cohort_and_refresh_fetches_new_data(live_server):
    if not os.getenv("PLAYWRIGHT_BROWSERS_PATH"):
        pytest.skip("Set PLAYWRIGHT_BROWSERS_PATH to run the real browser check")
    app, _, settings = live_server
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        requests = []
        page.on("request", lambda req: requests.append(req.url))
        page.goto(settings.public_url)
        page.get_by_label("Operator credential").fill(settings.admin_token)
        page.get_by_role("button", name="Open dashboard").click()
        expect(page.get_by_role("heading", name="What did the critics add?")).to_be_visible()
        baseline = len(requests)
        # Even unavailable/very slow APIs must not block a data-only navigation.
        page.route("**/api/**", lambda route: route.abort())
        page.get_by_role("link", name="Inspect data quality").click()
        expect(page.locator("#breadcrumb")).to_have_text("Workspace / quality", timeout=1000)
        for route in ("assess", "runs", "critics", "rounds", "experiments", "connect", "overview"):
            page.evaluate("route => location.hash = route", route)
            expect(page.locator('[data-page="' + route + '"]')).to_have_attribute(
                "aria-current", "page", timeout=1000
            )
        assert len(requests) == baseline
        page.unroute("**/api/**")
        critic = app.state.store.critics()[0]["id"]
        submit(
            app.state.store,
            "fresh",
            started([critic], review_type="pull_request"),
            invocation(critic, "p"),
            finding("new-f", "p"),
            finish_inv("p"),
            {"type": "run_finished", "status": "completed", "reason": "Done"},
        )
        page.get_by_role("button", name="Refresh", exact=True).click()
        expect(page.get_by_role("link", name="Review sample")).to_be_visible()
        assert any("/api/dashboard?" in url for url in requests[baseline:])
        assert page.locator("#error-banner").is_hidden()
        # A late detail response must not replace the newer quality page.
        held = []
        detail = app.state.store.run("fresh")
        page.route("**/api/runs/fresh", lambda route: held.append(route))
        with page.expect_request("**/api/runs/fresh"):
            page.evaluate("location.hash = 'run/fresh'")
        page.evaluate("location.hash = 'quality'")
        expect(page.locator("#breadcrumb")).to_have_text("Workspace / quality")
        with page.expect_response("**/api/runs/fresh"):
            held[0].fulfill(json=detail)
        page.wait_for_load_state("networkidle")
        expect(page.locator("#breadcrumb")).to_have_text("Workspace / quality")
        browser.close()


@pytest.mark.browser
@pytest.mark.parametrize(
    "role,specialty",
    [
        ("evidence", "Evidence and testing"),
        ("diverse hypotheses", "Counterexamples"),
        ("reviewer", "General review"),
        ("evidence", "Custom specialty"),
    ],
)
def test_variant_preserves_effective_specialty(live_server, role, specialty):
    if not os.getenv("PLAYWRIGHT_BROWSERS_PATH"):
        pytest.skip("Set PLAYWRIGHT_BROWSERS_PATH to run the real browser check")
    app, client, settings = live_server
    store = app.state.store
    source = store.register_critic(
        Critic(
            name="Variant source",
            role=role,
            prompt="Keep these instructions",
            specialty=specialty if specialty == "Custom specialty" else None,
        )
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.goto(settings.public_url)
        page.get_by_label("Operator credential").fill(settings.admin_token)
        page.get_by_role("button", name="Open dashboard").click()
        page.get_by_role("link", name="Critics", exact=True).click()
        card = page.locator(".critic-card").filter(
            has=page.get_by_role("heading", name=source["name"], exact=True)
        )
        card.get_by_role("button", name="Create variant", exact=True).click()
        editor = page.get_by_role("dialog")
        expect(editor.get_by_label("Specialty", exact=True)).to_have_value(specialty)
        editor.get_by_role("button", name="Save definition", exact=True).click()
        expect(
            page.get_by_role("heading", name="Variant source variant", exact=True)
        ).to_be_visible()
        saved = next(c for c in store.critics() if c["name"] == "Variant source variant")
        assert saved["specialty"] == specialty
        assert saved["role"] == source["role"]
        assert saved["prompt"] == source["prompt"]
        assert saved["id"] != source["id"]
        assert store.critic(source["id"]) == source
        response = client.get(
            "/api/critics", headers={"Authorization": f"Bearer {settings.admin_token}"}
        )
        original = next(c for c in response.json() if c["id"] == source["id"])
        assert original["effective_specialty"] == specialty
        assert original.get("specialty") == source.get("specialty")
        browser.close()


@pytest.mark.browser
def test_architecture_cohort_and_experiments_stay_separate(live_server):
    if not os.getenv("PLAYWRIGHT_BROWSERS_PATH"):
        pytest.skip("Set PLAYWRIGHT_BROWSERS_PATH to run the real browser check")
    app, _, settings = live_server
    store = app.state.store
    critics = [c["id"] for c in store.critics()]
    base = experiment(store, critics)
    document = {k: v for k, v in base.items() if k not in {"id", "created_at"}}
    for kind in ("pull_request", "architecture"):
        store.create_experiment(
            Experiment.model_validate(
                document
                | {
                    "name": f"{kind} experiment",
                    "review_type": kind,
                }
            )
        )
        submit(
            store,
            kind,
            started([critics[0]], review_type=kind, title=f"{kind} review"),
            invocation(critics[0], "i"),
            finding(f"{kind}-issue", "i"),
            finish_inv("i"),
        )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(settings.public_url)
        page.get_by_label("Operator credential").fill(settings.admin_token)
        page.get_by_role("button", name="Open dashboard").click()
        expect(page.get_by_role("link", name="pull_request review", exact=True)).to_be_visible()
        expect(page.get_by_role("link", name="architecture review", exact=True)).to_have_count(0)
        types = page.locator('#filters [name="review_type"]')
        assert "" not in types.locator("option").evaluate_all("els => els.map(e => e.value)")
        types.select_option("architecture")
        expect(page.get_by_role("link", name="architecture review", exact=True)).to_be_visible()
        expect(page.get_by_role("link", name="pull_request review", exact=True)).to_have_count(0)
        expect(page.locator("#cohort-summary")).to_contain_text("Architecture")
        page.get_by_role("link", name="Assess issues").click()
        expect(page.get_by_text("Defect architecture-issue", exact=True)).to_be_visible()
        expect(page.get_by_text("Defect pull_request-issue", exact=True)).to_have_count(0)
        page.get_by_role("link", name="Experiments", exact=True).click()
        expect(page.get_by_role("link", name="architecture experiment", exact=True)).to_be_visible()
        expect(page.get_by_role("link", name="pull_request experiment", exact=True)).to_have_count(
            0
        )
        page.get_by_role("link", name="architecture experiment", exact=True).click()
        expect(page.locator("#content .eyebrow")).to_contain_text("Architecture")
        page.get_by_role("button", name="Baseline", exact=True).click()
        expect(types).to_have_value("architecture")
        expect(page.locator('#filters [name="dataset"]')).to_have_value("benchmark")
        expect(page.locator('#filters [name="variant_id"]')).to_have_value("base")
        # Switching type must clear a hidden experiment filter from the old type.
        types.select_option("pull_request")
        expect(page.locator('#filters [name="experiment_id"]')).to_have_value("")
        page.locator('#filters [name="dataset"]').select_option("production")
        page.get_by_role("button", name="Apply", exact=True).click()
        expect(page.get_by_role("link", name="pull_request review", exact=True)).to_be_visible()
        page.get_by_role("link", name="Experiments", exact=True).click()
        expect(page.get_by_role("link", name="pull_request experiment", exact=True)).to_be_visible()
        expect(page.get_by_role("link", name="architecture experiment", exact=True)).to_have_count(
            0
        )
        page.set_viewport_size({"width": 390, "height": 844})
        types.select_option("architecture")
        expect(page.get_by_role("link", name="architecture experiment", exact=True)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        browser.close()
