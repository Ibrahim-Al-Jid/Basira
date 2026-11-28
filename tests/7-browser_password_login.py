"""Exercise real password signup/login, project isolation, and background report access."""
import re
from secrets import token_urlsafe
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

from browser_release import ORIGIN, catalog_rule_count, open_report_section, project_scan


def main():
    email = "acceptance-" + uuid4().hex[:12] + "@example.test"
    password = token_urlsafe(24)
    with sync_playwright() as testing:
        browser = testing.chromium.launch()
        context = browser.new_context(locale="ar-EG", viewport={"width": 390, "height": 844})
        page = context.new_page()
        page.goto(ORIGIN + "/signin")
        page.get_by_role("button", name="إنشاء حساب", exact=True).click()
        page.get_by_label("البريد الإلكتروني", exact=True).fill(email)
        page.locator('[name="first_name"]').fill("إبراهيم")
        page.locator('[name="last_name"]').fill("حمدي")
        page.get_by_label("كلمة المرور", exact=True).fill(password)
        page.get_by_role("button", name="إنشاء الحساب", exact=True).click()
        page.wait_for_url(ORIGIN + "/dashboard")
        expect(page.get_by_text("إبراهيم حمدي", exact=False)).to_be_visible()
        page.goto(ORIGIN + "/projects")
        expect(page.get_by_label("اسم المؤسسة", exact=True)).to_be_visible()

        page.get_by_label("اسم المؤسسة", exact=True).fill("Local account acceptance")
        page.get_by_role("button", name="إنشاء مؤسسة", exact=True).click()
        page.get_by_label("اسم المشروع", exact=True).fill("Password project acceptance")
        page.get_by_role("button", name="إنشاء مشروع", exact=True).click()
        page.wait_for_url(re.compile(r"[?&]project=[a-f0-9]{32}"))
        project = parse_qs(urlsplit(page.url).query)["project"][0]
        report = project_scan(page, project, '<form action="/session"><input name="password" type="password"></form>')
        report_link = f"{ORIGIN}/reports/{report}?project={project}"

        page.goto(report_link)
        open_report_section(page, "coverage")
        expect(page.locator(".reports-coverage tbody tr")).to_have_count(catalog_rule_count(context.request))
        page.goto(ORIGIN + "/settings")
        page.get_by_role("button", name="تسجيل الخروج").click()
        page.wait_for_url(ORIGIN + "/")
        page.goto(ORIGIN + "/signin")
        page.get_by_label("البريد الإلكتروني", exact=True).fill(email)
        forbidden = context.request.get(f"{ORIGIN}/api/platform/projects/{project}/reports/{report}")
        assert forbidden.status == 401
        page.get_by_label("كلمة المرور", exact=True).fill(password)
        page.get_by_role("button", name="تسجيل الدخول", exact=True).click()
        expect(page.get_by_role("link", name="الحساب", exact=True)).to_be_visible()
        page.goto(report_link)
        expect(page.get_by_role("link", name="تحميل PDF")).to_be_visible()
        page.reload()
        open_report_section(page, "coverage")
        expect(page.locator(".reports-coverage tbody tr")).to_have_count(catalog_rule_count(context.request))
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
        browser.close()
    print("Password browser flow passed: signup, scoped project, upload, background scan, logout, login and report reload.")


if __name__ == "__main__":
    main()
