"""Public and workspace routing, keyboard motion, and report-scope acceptance."""
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

from browser_release import ORIGIN, project_scan, report_locale


def reflows(page):
    assert page.evaluate("document.documentElement.scrollWidth === innerWidth"), page.url


def landing(browser):
    """The public home is the overview with demo data: heading, sign-in route, demo page, no overflow or script errors."""
    for width in (320, 390, 566, 1280):
        for language in ("ar", "en"):
            context = browser.new_context(locale="ar-EG" if language == "ar" else "en-US",
                                          viewport={"width": width, "height": 850})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(ORIGIN)
            expect(page.locator("html")).to_have_attribute("dir", "rtl" if language == "ar" else "ltr")
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            expect(page.locator("#entry-title")).to_be_visible()
            expect(page.locator("a.entry-cta[href='/signin']").first).to_be_visible()
            assert page.locator(".overview-sidebar, .workspace-sidebar").count() == 0
            reflows(page)
            page.goto(ORIGIN + "/overview")
            expect(page.locator("#landing-title")).to_be_visible()
            expect(page.locator(".command-metric, .command-metrics > *").first).to_be_visible()
            assert page.locator(".landing-marquee-track, .landing-motion-control").count() == 0
            reflows(page)
            assert page.goto(ORIGIN + "/demo").status == 200
            page.wait_for_url("**/signin")  # the retired demo page sends signed-out visitors to sign-in
            reflows(page)
            assert page.goto(ORIGIN + "/signin").ok
            reflows(page)
            assert not errors, errors
            context.close()

    context = browser.new_context(locale="ar-EG", viewport={"width": 390, "height": 820}, reduced_motion="reduce")
    page = context.new_page()
    page.goto(ORIGIN + "/overview")
    expect(page.locator("#landing-title")).to_be_visible()
    reflows(page)
    context.close()


def workspace(browser):
    context = browser.new_context(locale="ar-EG", viewport={"width": 390, "height": 844})
    page = context.new_page()
    issues = []
    page.on("pageerror", lambda error: issues.append(str(error)))
    for route in ("/signin", "/dashboard", "/projects", "/new-scan", "/scans", "/findings", "/reports", "/settings", "/demo"):
        assert page.goto(ORIGIN + route).status == 200, route
        reflows(page)
    assert context.request.get(ORIGIN + "/api/unknown-route").status == 404
    account = context.request.post(ORIGIN + "/api/platform/auth/password/register", data={
        "email": f"workspace-{uuid4().hex[:12]}@example.test",
        "password": str(uuid4()) + str(uuid4()),
    })
    assert account.status == 201, account.text()
    assert page.goto(ORIGIN + "/signin").ok
    page.wait_for_url("**/projects")
    org = context.request.post(ORIGIN + "/api/platform/organizations", data={"name": "Workspace QA"})
    assert org.status == 201
    project = context.request.post(f"{ORIGIN}/api/platform/organizations/{org.json()['id']}/projects", data={"name": "Workspace scope"})
    assert project.status == 201
    project_id = project.json()["id"]
    report_id = project_scan(page, project_id, '<form action="http://example.test/"></form>')

    page.goto(ORIGIN + "/reports")
    expect(page.get_by_role("combobox", name="المشروع", exact=True)).to_be_visible()
    page.get_by_role("combobox", name="المشروع", exact=True).select_option(project_id)
    expect(page.get_by_role("link", name="portal.html")).to_be_visible()
    assert parse_qs(urlsplit(page.url).query)["project"] == [project_id]

    page.goto(f"{ORIGIN}/findings?project={project_id}&report={report_id}")
    page.wait_for_url(f"**/reports/{report_id}?*#report-findings")
    expect(page.locator(".reports-finding")).to_have_count(1)
    expect(page.get_by_role("heading", name="تقرير فحص المشروع")).to_be_visible()
    expect(page.locator(".reports-coverage")).to_have_count(0)
    coverage = page.locator('a[data-report-section="coverage"]')
    coverage.focus()
    page.keyboard.press("Enter")
    expect(coverage).to_be_focused()
    expect(page.locator(".reports-coverage")).to_be_visible()
    report_locale(page, "en")
    expect(page.locator(".reports-workspace")).to_have_attribute("dir", "ltr")
    report_locale(page, "ar")
    expect(page.locator(".reports-workspace")).to_have_attribute("dir", "rtl")
    assert parse_qs(urlsplit(page.url).query)["lang"] == ["ar"]
    reflows(page)

    anonymous = browser.new_context()
    assert anonymous.request.get(f"{ORIGIN}/api/platform/projects/{project_id}/reports/{report_id}").status == 401
    anonymous.close()
    assert not issues, issues
    context.close()


def main():
    with sync_playwright() as testing:
        browser = testing.chromium.launch()
        landing(browser)
        workspace(browser)
        browser.close()
    print("Workspace browser checks passed for layout, locales, motion, auth, wizard, and report scope.")


if __name__ == "__main__":
    main()
