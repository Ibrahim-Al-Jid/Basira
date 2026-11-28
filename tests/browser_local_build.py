"""Browser acceptance for the documented local bootstrap with a disposable database.

The suite drives the platform path a brand-new local user takes after
ops/start-local.sh answers: sign up, create a personal project, run a real
source scan, and read and export the report. It replaces the retired
anonymous-lab flow (/demo, /api/run, sqlite) that #160 removed.
"""
from io import BytesIO
import json
import os
from pathlib import Path
from secrets import token_urlsafe
from urllib.parse import parse_qs, urlsplit, urlparse
from uuid import uuid4
from zipfile import ZipFile

from playwright.sync_api import expect, sync_playwright

from browser_release import open_report_section, report_locale

BASE = os.environ.get("BASIRA_TEST_URL", "http://127.0.0.1:8766")
assert urlparse(BASE).hostname == "127.0.0.1"
SOURCE = (
    b'<script src="http://assets.example.test/a.js"></script>\r\n'
    b'<script src="http://assets.example.test/b.js"></script>\r\n'
    b'<form action="http://form.example.test/"></form>'
)


def source_zip():
    # Personal projects take a source archive; the single document inside is review.htm.
    archive = BytesIO()
    with ZipFile(archive, "w") as folder:
        folder.writestr("review.htm", SOURCE)
    return {"name": "source.zip", "mimeType": "application/zip", "buffer": archive.getvalue()}


def signup(page):
    address = f"local-{uuid4().hex[:12]}@example.test"
    page.goto(BASE + "/signin")
    page.get_by_role("button", name="Create an account", exact=True).click()
    page.locator('[name="first_name"]').fill("Local")
    page.locator('[name="last_name"]').fill("Builder")
    page.locator('[name="email"]').fill(address)
    page.locator('[name="password"]').fill(token_urlsafe(24))
    page.get_by_role("button", name="Create account", exact=True).click()
    page.wait_for_url(BASE + "/projects")


def first_scan(page):
    page.get_by_role("navigation", name="Workspace navigation").get_by_role(
        "link", name="Projects", exact=True).click()
    page.get_by_role("main").get_by_role("link", name="New project", exact=True).click()
    page.get_by_label("Project name").fill("Local build QA")
    page.get_by_role("button", name="Create project", exact=True).click()
    expect(page.get_by_role("heading", name="Local build QA", exact=True)).to_be_visible()
    project_id = parse_qs(urlsplit(page.url).query)["project"][0]
    page.get_by_role("main").get_by_role("link", name="New scan", exact=True).click()
    # The project is already chosen, so the flow opens on the source step.
    page.get_by_role("radio", name="Project source", exact=False).check()
    # A malformed archive passes the client checks and is rejected by the
    # server on submit; the review shows why (personal_intake.py).
    page.locator('input[type="file"]').set_input_files({
        "name": "bad.zip", "mimeType": "application/zip", "buffer": b"this is not a zip archive",
    })
    page.get_by_role("checkbox", name="I have permission to review this file").check()
    page.get_by_role("button", name="Submit scan").click()
    expect(page.get_by_role("alert")).to_contain_text("The file must be a valid ZIP.")
    page.get_by_role("button", name="Back").click()
    page.locator('input[type="file"]').set_input_files(source_zip())  # choosing a file opens the review step
    page.get_by_role("button", name="Submit scan").click()
    page.wait_for_url("**/projects/*/scans/*")
    scan_id = urlsplit(page.url).path.rsplit("/", 1)[-1]
    link = page.get_by_role("link", name="Open report", exact=True)
    expect(link).to_be_visible(timeout=50_000)
    page.reload()
    expect(link).to_be_visible(timeout=50_000)  # the scan survives a reload
    link.click()
    return project_id, scan_id


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(locale="en-US", viewport={"width": 1440, "height": 1050})
        request = context.request
        # The bootstrap wrote the local profile flags: personal projects on.
        assert request.get(BASE + "/api/product").json() == {"personal_projects": True}
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        signup(page)
        project_id, scan_id = first_scan(page)
        project_api = f"{BASE}/api/platform/projects/{project_id}"

        expect(page.locator(".reports-decision")).to_be_visible(timeout=20_000)
        expect(page.locator(".reports-decision")).to_contain_text("This does not mean the project is clean")
        open_report_section(page, "findings")
        expect(page.locator('.reports-finding-row[data-rule="http-script"]')).to_be_visible()
        expect(page.locator('.reports-finding-row[data-rule="http-form"]')).to_be_visible()

        # The severity filter survives a reload through the URL.
        page.locator('select[name="findingSeverity"]').select_option("medium")
        assert "findingSeverity=medium" in page.url
        page.reload()
        expect(page.locator('.reports-finding-row[data-rule="http-form"]')).to_be_visible()
        expect(page.locator('.reports-finding-row[data-rule="http-script"]')).to_have_count(0)
        page.locator('select[name="findingSeverity"]').select_option("")

        # Exports from the page and the API, in both languages.
        open_report_section(page, "export")
        with page.expect_download() as pending:
            page.get_by_role("link", name="Download PDF", exact=True).click()
        assert pending.value.suggested_filename.endswith(".pdf")
        assert Path(pending.value.path()).read_bytes().startswith(b"%PDF-")
        for lang, direction in (("ar", "rtl"), ("en", "ltr")):
            response = request.get(f"{project_api}/reports/{scan_id}/download?format=pdf&lang={lang}")
            assert response.ok and response.body().startswith(b"%PDF")
            html = request.get(f"{project_api}/reports/{scan_id}/download?format=html&lang={lang}").text()
            assert f'lang="{lang}" dir="{direction}"' in html
            assert "assets.example.test" not in html  # exports never embed remote sources
        report = request.get(f"{project_api}/reports/{scan_id}/download?format=json").json()
        rules = {finding["rule"] for finding in report["findings"]}
        assert {"http-script", "http-form"} <= rules
        expected = [finding for finding in report["findings"] if finding["rule"] in ("http-script", "http-form")]
        assert {finding["path"] for finding in expected} == {"review.htm"}

        # The report switches direction with the locale and fits a phone.
        workspace = page.locator(".reports-workspace")
        expect(workspace).to_have_attribute("dir", "ltr")
        report_locale(page, "ar")
        expect(workspace).to_have_attribute("dir", "rtl")
        open_report_section(page, "findings")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
        report_locale(page, "en")
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")

        # Another visitor cannot see the report, over the page or the API.
        other = browser.new_context(locale="en-US")
        other_page = other.new_page()
        other_page.goto(page.url)
        expect(other_page.get_by_text("Sign in to see this project report.")).to_be_visible()
        assert other.request.get(f"{project_api}/reports/{scan_id}").status in (401, 404)
        assert other.request.get(f"{project_api}/reports/{scan_id}/download?format=pdf").status in (401, 404)
        other.close()

        assert not errors, errors
        browser.close()
    print("Local-build browser acceptance passed: signup, first scan, report, exports, locale, and isolation.")


if __name__ == "__main__":
    main()
