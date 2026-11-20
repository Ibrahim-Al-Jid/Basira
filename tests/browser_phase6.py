"""Browser release checks using a test account or fixture session on isolated Compose."""
import json
import os
from pathlib import Path
from secrets import token_urlsafe
import sys
from urllib.parse import urlparse
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

ORIGIN = os.environ.get("MARSAD_TEST_PLATFORM_URL", "http://127.0.0.1:8776")
assert urlparse(ORIGIN).hostname == "127.0.0.1"


def download(page, link):
    with page.expect_download() as pending:
        link.click()
    return json.loads(Path(pending.value.path()).read_text(encoding="utf-8"))


def project_scan(page, project, text):
    page.goto(f"{ORIGIN}/projects?project={project}")
    page.locator('input[type="file"][name="file"]').set_input_files({
        "name": "portal.html", "mimeType": "text/html", "buffer": text.encode(),
    })
    page.get_by_role("button", name="إرسال الفحص").click()
    link = page.get_by_role("link", name="فتح التقرير")
    expect(link).to_be_visible(timeout=30_000)
    page.reload()
    expect(link).to_be_visible(timeout=30_000)
    link.click()
    expect(page.get_by_role("heading", name="تقرير فحص المشروع")).to_be_visible()
    return urlparse(page.url).path.split("/")[-1]


def lab_check(browser):
    tab = browser.new_context(viewport={"width": 390, "height": 844}).new_page()
    tab.goto(ORIGIN)
    expect(tab.get_by_label("نطاق الفحص")).to_have_value("extended")
    tab.locator('input[type="file"]').set_input_files({
        "name": "extended.html", "mimeType": "text/html",
        "buffer": b'<form action="/session"><input name="pass" type="password"></form>',
    })
    tab.get_by_role("button", name="تشغيل الفحص").click()
    tab.get_by_role("link", name="فتح التقرير").click()
    expect(tab.locator(".reports-coverage > li")).to_have_count(100)
    expect(tab.locator(".reports-finding summary").filter(has_text="HTML-17")).to_be_visible()
    expect(tab.get_by_role("heading", name="سجل تشغيل الأدوات")).to_be_visible()
    assert tab.get_by_role("link", name="تحميل SARIF").count() == 0


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        lab_check(browser)
        if "--local-only" in sys.argv:
            print("The anonymous lab defaults to extended mode and reports all 100 coverage statuses.")
            browser.close()
            return
        context = browser.new_context(viewport={"width": 390, "height": 844})
        user = context.request
        if "--password-account" in sys.argv:
            account = user.post(ORIGIN + "/api/platform/auth/password/register", data={
                "email": f"release-{uuid4().hex[:12]}@example.test",
                "password": token_urlsafe(24),
            })
            assert account.status == 201
        else:
            token = os.environ["MARSAD_TEST_SESSION"]
            context.add_cookies([{"name": "marsad_platform_session", "value": token, "url": ORIGIN}])
        org = user.post(ORIGIN + "/api/platform/organizations", data={"name": "Release acceptance"})
        assert org.status == 201
        response = user.post(f"{ORIGIN}/api/platform/organizations/{org.json()['id']}/projects",
                             data={"name": "Browser comparison"})
        assert response.status == 201
        project = response.json()["id"]
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(ORIGIN + "/checks")
        expect(page.locator(".catalog-rules > li")).to_have_count(100)
        page.get_by_role("searchbox").fill("HTML-17")
        expect(page.locator(".catalog-rules > li")).to_have_count(1)
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")

        first = project_scan(page, project, '<script src="http://assets.example.test/site.js"></script>'
                                           '<form action="https://portal.example.test/"></form>')
        current_source = ('<script src="https://assets.example.test/site.js"></script>'
                          '<form action="http://portal.example.test/"></form>')
        current = project_scan(page, project, current_source)
        page.get_by_label("التقرير المرجعي").select_option(first)
        expect(page.get_by_text("الفحصين قابلين للمقارنة.")).to_be_visible()
        expect(page.locator('[data-review-state="resolved"]')).to_have_count(1)
        expect(page.locator('[data-review-state="new"]')).to_have_count(1)
        assert "baseline=" + first in page.url

        review = page.locator(".reports-review-item").first
        review.locator("summary").focus()
        page.keyboard.press("Enter")
        review.locator('textarea[name="body"]').fill("Acceptance review comment")
        review.get_by_role("button", name="إضافة تعليق").click()
        expect(review.get_by_text("Acceptance review comment")).to_be_visible()
        review.locator('select[name="status"]').select_option("triaged")
        review.locator('textarea[name="reason"]').fill("Assigned during acceptance")
        review.get_by_role("button", name="تحديث الحالة").click()
        expect(review.get_by_text("Assigned during acceptance")).to_be_visible()

        page.get_by_role("button", name="English").click()
        expect(page.locator(".reports-workspace")).to_have_attribute("dir", "ltr")
        expect(page.get_by_role("heading", name="Tool execution")).to_be_visible()
        expect(page.get_by_text("These scans are comparable.")).to_be_visible()
        report = download(page, page.get_by_role("link", name="Download SARIF"))
        assert report["version"] == "2.1.0"
        assert report["runs"][0]["results"][0]["ruleId"] == "http-form"
        schema = os.environ.get("MARSAD_TEST_SARIF_SCHEMA")
        if schema:
            from jsonschema.validators import validator_for
            specification = json.loads(Path(schema).read_text(encoding="utf-8"))
            validator_for(specification)(specification).validate(report)
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
        other = browser.new_context().new_page()
        other.goto(page.url)
        expect(other.get_by_role("alert")).to_be_visible()

        page.get_by_role("button", name="العربية").click()
        changed = user.put(f"{ORIGIN}/api/platform/projects/{project}/policy", data={"allowed_kinds": ["html"]})
        assert changed.ok
        project_scan(page, project, current_source)
        page.get_by_label("التقرير المرجعي").select_option(current)
        expect(page.get_by_text("سياسة الفحص اتغيّرت. اختار تقرير بنفس إصدار السياسة.")).to_be_visible()
        assert errors == [], errors
        browser.close()
    print("Release browser acceptance passed: catalog, upload, recovery, diff, reviews, SARIF, AR/EN, and access.")


if __name__ == "__main__":
    main()
