"""Phase 8 public/workspace routing, keyboard motion, and report-scope acceptance."""
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

from browser_phase6 import ORIGIN, project_scan


def reflows(page):
    assert page.evaluate("document.documentElement.scrollWidth === innerWidth"), page.url


def landing(browser):
    for width in (320, 390, 1280):
        for language in ("ar", "en"):
            context = browser.new_context(viewport={"width": width, "height": 850})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(ORIGIN)
            if language == "en":
                page.get_by_role("button", name="Switch to English").click()
            expect(page.locator("html")).to_have_attribute("dir", "rtl" if language == "ar" else "ltr")
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            expect(page.locator(".landing-marquee-group:not([aria-hidden]) > li")).to_have_count(6)
            pause = page.get_by_role("button", name="أوقف الحركة" if language == "ar" else "Pause motion")
            pause.focus()
            page.keyboard.press("Enter")
            expect(page.locator(".marsad-landing")).to_have_attribute("data-motion", "paused")
            metric = page.get_by_role("button", name="قاعدة انطبقت" if language == "ar" else "Applicable checks")
            metric.click()
            expect(metric).to_have_attribute("aria-pressed", "true")
            reflows(page)
            page.get_by_role("button", name="الوضع الفاتح" if language == "ar" else "Light theme").click()
            page.reload()
            expect(page.locator("html")).to_have_attribute("data-theme", "light")
            expect(page.locator("html")).to_have_attribute("lang", language)
            reflows(page)
            assert page.goto(ORIGIN + "/demo").status == 200
            expect(page.get_by_role("button", name="تشغيل الفحص" if language == "ar" else "Run scan")).to_be_disabled()
            expect(page.get_by_role("button", name="تحميل العينة" if language == "ar" else "Load sample")).to_be_visible()
            reflows(page)
            if width != 1280:
                menu = page.get_by_role("button", name="افتح القائمة" if language == "ar" else "Open menu")
                menu.focus()
                page.keyboard.press("Enter")
                expect(page.locator(".site-mobile-menu")).to_have_attribute("aria-expanded", "true")
                expect(page.get_by_role("navigation").get_by_role("link", name="التغطية" if language == "ar" else "Coverage")).to_be_visible()
            assert not errors, errors
            context.close()

    context = browser.new_context(viewport={"width": 390, "height": 820}, reduced_motion="reduce")
    page = context.new_page()
    page.goto(ORIGIN)
    expect(page.get_by_role("button", name="أوقف الحركة")).to_be_hidden()
    assert page.locator(".landing-marquee-track").evaluate("(node) => getComputedStyle(node).animationName") == "none"
    expect(page.locator(".landing-marquee-group:not([aria-hidden]) > li")).to_have_count(6)
    context.close()


def workspace(browser):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    issues = []
    page.on("pageerror", lambda error: issues.append(str(error)))
    for route in ("/signin", "/dashboard", "/projects", "/new-scan", "/scans", "/findings", "/reports", "/settings", "/checks", "/demo"):
        assert page.goto(ORIGIN + route).status == 200, route
        reflows(page)
    assert context.request.get(ORIGIN + "/api/phase8-unknown").status == 404
    account = context.request.post(ORIGIN + "/api/platform/auth/password/register", data={
        "email": f"phase8-{uuid4().hex[:12]}@example.test",
        "password": str(uuid4()) + str(uuid4()),
    })
    assert account.status == 201
    assert page.goto(ORIGIN + "/signin").ok
    page.wait_for_url("**/dashboard")
    org = context.request.post(ORIGIN + "/api/platform/organizations", data={"name": "Phase 8 QA"})
    assert org.status == 201
    project = context.request.post(f"{ORIGIN}/api/platform/organizations/{org.json()['id']}/projects", data={"name": "Phase 8 scope"})
    assert project.status == 201
    project_id = project.json()["id"]
    report_id = project_scan(page, project_id, '<form action="http://example.test/"></form>')

    page.goto(ORIGIN + "/reports")
    expect(page.get_by_role("combobox", name="المشروع", exact=True)).to_be_visible()
    expect(page.get_by_text("اختار مشروعًا لعرض تقاريره.")).to_be_visible()
    page.get_by_role("combobox", name="المشروع", exact=True).select_option(project_id)
    expect(page.get_by_role("link", name="portal.html")).to_be_visible()
    assert parse_qs(urlsplit(page.url).query)["project"] == [project_id]

    page.goto(f"{ORIGIN}/findings?project={project_id}")
    page.get_by_role("combobox", name="الفحص", exact=True).select_option(report_id)
    expect(page.locator(".reports-finding")).to_have_count(1)
    page.get_by_role("link", name="فتح التقرير الكامل").click()
    expect(page.get_by_role("heading", name="تقرير فحص المشروع")).to_be_visible()
    page.get_by_role("link", name="تغطية الفحص").focus()
    page.keyboard.press("Enter")
    expect(page.locator("#report-coverage")).to_be_focused()
    page.get_by_role("button", name="English", exact=True).click()
    expect(page.locator(".reports-workspace")).to_have_attribute("dir", "ltr")
    page.get_by_role("button", name="التبديل إلى العربية").click()
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
    print("Phase 8 browser checks passed for layout, themes, locales, keyboard/motion, auth, wizard, and report scope.")


if __name__ == "__main__":
    main()
