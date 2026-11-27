"""Browser acceptance against a locally built Marsad with a disposable database."""
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

from browser_release import open_report_section, report_locale

BASE = os.environ.get("MARSAD_TEST_URL", "http://127.0.0.1:8766")
assert urlparse(BASE).hostname == "127.0.0.1"
SOURCE = (
    b'<script src="http://assets.example.test/a.js"></script>\r\n'
    b'<script src="http://assets.example.test/b.js"></script>\r\n'
    b'<form action="http://form.example.test/"></form>'
)


def choose_file(page, name, source):
    page.locator('input[type="file"]').set_input_files({
        "name": name, "mimeType": "text/html", "buffer": source,
    })


def run_review(page):
    page.get_by_label("نطاق الفحص").select_option("baseline")
    page.get_by_role("button", name="تشغيل الفحص").click()
    link = page.get_by_role("link", name="فتح التقرير")
    expect(link).to_be_visible()
    link.focus()
    page.keyboard.press("Enter")


def download(page, link):
    with page.expect_download() as pending:
        link.click()
    return Path(pending.value.path()).read_text(encoding="utf-8")


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(locale="ar-EG", viewport={"width": 1440, "height": 1050})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE + "/reports")
        expect(page.get_by_text("لسه مفيش تقارير محفوظة.")).to_be_visible()
        page.goto(BASE + "/demo")

        choose_file(page, "wrong.txt", SOURCE)
        expect(page.get_by_role("alert")).to_contain_text("امتداد")
        choose_file(page, "huge.html", b" " * 1_000_001)
        expect(page.get_by_role("alert")).to_contain_text("ميجابايت")
        choose_file(page, "review.htm", b"\xff")
        expect(page.get_by_role("alert")).to_contain_text("UTF-8")
        page.evaluate("""() => {
            window.qaRead = FileReader.prototype.readAsArrayBuffer;
            FileReader.prototype.readAsArrayBuffer = function () {};
        }""")
        choose_file(page, "review.htm", SOURCE)
        expect(page.get_by_role("button", name="تشغيل الفحص")).to_be_disabled()
        page.get_by_role("button", name="إلغاء قراءة الملف").click()
        expect(page.get_by_role("button", name="تشغيل الفحص")).to_be_disabled()
        page.evaluate("() => { FileReader.prototype.readAsArrayBuffer = window.qaRead; delete window.qaRead; }")
        choose_file(page, "review.htm", SOURCE)
        expect(page.get_by_text("review.htm", exact=True)).to_be_visible()
        expect(page.get_by_role("alert")).to_have_count(0)
        run_review(page)

        detail_path = urlparse(page.url).path
        assert detail_path.startswith("/reports/")
        page.reload()
        workspace = page.locator(".reports-workspace")
        expect(workspace).to_have_attribute("dir", "rtl")
        expect(page.get_by_text("review.htm", exact=True)).to_be_visible()
        expect(page.get_by_role("link", name="تحميل PDF")).to_be_visible()
        with page.expect_download() as pdf:
            page.get_by_role("link", name="تحميل PDF").click()
        assert pdf.value.suggested_filename.endswith(".pdf")
        assert Path(pdf.value.path()).read_bytes().startswith(b"%PDF-")
        expect(page.locator(".reports-coverage")).to_have_count(0)
        expect(page.locator(".reports-finding")).to_have_count(2)
        evidence_button = page.locator(".reports-finding button").first
        evidence_button.focus()
        page.keyboard.press("Enter")
        evidence = page.get_by_role("dialog")
        expect(evidence.locator(".reports-finding-body li")).to_have_count(2)
        page.keyboard.press("Escape")
        expect(evidence).to_have_count(0)
        expect(evidence_button).to_be_focused()
        open_report_section(page, "coverage")
        expect(page.locator(".reports-coverage")).to_contain_text("غير منطبق")

        report_locale(page, "en")
        expect(workspace).to_have_attribute("dir", "ltr")
        expect(page.locator('a[data-report-section="coverage"]')).to_have_text("Scan coverage")
        open_report_section(page, "findings")
        page.locator('select[name="findingSeverity"]').select_option("medium")
        assert "findingSeverity=medium" in page.url
        page.reload()
        expect(page.locator(".reports-finding")).to_have_count(1)
        open_report_section(page, "export")
        for lang, title, direction in (("ar", "Download Arabic HTML", "rtl"),
                                       ("en", "Download English HTML", "ltr")):
            html = download(page, page.get_by_role("link", name=title))
            assert f'lang="{lang}" dir="{direction}"' in html
            assert html.count("<article>") == 3
            assert "assets.example.test" not in html
        report = json.loads(download(page, page.get_by_role("link", name="Download JSON")))
        assert len(report["findings"]) == 3
        assert report["source"]["name"] == "review.htm"
        assert report["source"]["lines"] == 3
        assert report["enrichment"] == "disabled"

        page.get_by_role("link", name="All reports").click()
        page.get_by_role("searchbox", name="Search reports").fill("does not exist")
        expect(page.get_by_text("No reports match these filters.")).to_be_visible()
        page.get_by_role("searchbox", name="Search reports").fill("review.htm")
        expect(page.get_by_role("link", name="review.htm")).to_have_count(1)
        assert "q=review.htm" in page.url
        page.get_by_role("link", name="review.htm").click()
        expect(page.locator('a[data-report-section="coverage"]')).to_have_text("Scan coverage")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
        report_locale(page, "ar")
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")

        other = browser.new_context(locale="ar-EG").new_page()
        other.goto(BASE + detail_path)
        expect(other.get_by_role("alert")).to_contain_text("غير موجود")

        page.goto(BASE + "/demo")
        page.get_by_role("button", name="لصق HTML").click()
        editor = page.get_by_label("كود HTML", exact=True)
        editor.fill(SOURCE.decode())
        run_review(page)
        open_report_section(page, "export")
        pasted = json.loads(download(page, page.locator('a[href$="?format=json"]')))
        assert pasted["findings"] == report["findings"]
        assert pasted["coverage"] == report["coverage"]

        page.goto(BASE + "/demo")
        page.get_by_role("button", name="لصق HTML").click()
        page.get_by_label("كود HTML", exact=True).fill("<main>outside the scope</main>")
        run_review(page)
        expect(page.get_by_text("ولا قاعدة من قواعد الفحص انطبقت على المصدر ده.")).to_be_visible()
        page.goto(BASE + "/demo")
        page.get_by_role("button", name="لصق HTML").click()
        page.get_by_label("كود HTML", exact=True).fill('<form action="https://example.test/"></form>')
        run_review(page)
        expect(page.get_by_text("القواعد اللي اتنفذت ما رصدتش أدلة مطابقة في المصدر ده.")).to_be_visible()
        assert not errors, errors
        browser.close()
    print("Browser checks passed for file selection, reports, downloads, and session isolation.")


if __name__ == "__main__":
    main()
