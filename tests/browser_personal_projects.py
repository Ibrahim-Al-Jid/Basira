"""Exercise personal projects in a disposable personal-project environment."""

from io import BytesIO
import os
from secrets import token_urlsafe
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
from zipfile import ZipFile

from playwright.sync_api import expect, sync_playwright


def signup(page, origin, language):
    address = f"personal-{uuid4().hex[:12]}@example.test"
    password = token_urlsafe(24)
    page.goto(origin + "/signin")
    page.get_by_role("button", name="Create an account" if language == "en" else "إنشاء حساب", exact=True).click()
    page.locator('[name="first_name"]').fill("Example")
    page.locator('[name="last_name"]').fill("Tester")
    page.locator('[name="email"]').fill(address)
    page.locator('[name="password"]').fill(password)
    page.get_by_role("button", name="Create account" if language == "en" else "إنشاء الحساب", exact=True).click()
    page.wait_for_url(origin + "/projects")
    return address, password


def project_zip():
    archive = BytesIO()
    with ZipFile(archive, "w") as file:
        file.writestr("index.html", "<!doctype html><html><title>Personal project fixture</title><p>Sample</p></html>")
    return {"name": "project.zip", "mimeType": "application/zip", "buffer": archive.getvalue()}


def main():
    origin = os.environ["BASIRA_QA_ORIGIN"].rstrip("/")
    parsed = urlsplit(origin)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port in (None, 8765):
        raise ValueError("Use a disposable loopback instance on its own port.")
    with sync_playwright() as playwright:
        channel = os.environ.get("BASIRA_BROWSER_CHANNEL")
        browser = playwright.chromium.launch(channel=channel)
        owner = browser.new_context(locale="en-US")
        other = browser.new_context(locale="ar-EG", viewport={"width": 390, "height": 844})
        assert owner.request.get(origin + "/api/product").json() == {"personal_projects": True}
        page = owner.new_page()
        address, password = signup(page, origin, "en")
        header = page.get_by_role("banner")
        expect(page.get_by_text("Create organization")).to_have_count(0)
        header.get_by_role("link", name="Projects", exact=True).click()
        page.get_by_role("main").get_by_role("link", name="New project", exact=True).click()
        page.get_by_label("Project name").fill("Personal QA project")
        page.get_by_role("button", name="Create project", exact=True).click()
        expect(page.get_by_role("heading", name="Personal QA project", exact=True)).to_be_visible()
        project_id = parse_qs(urlsplit(page.url).query)["project"][0]
        project_api = origin + "/api/platform/projects/" + project_id
        project_navigation = page.get_by_role("navigation", name="Project sections")
        expect(project_navigation.get_by_role("link", name="Settings", exact=True)).to_be_visible()
        expect(project_navigation.get_by_role("link", name="Scan History")).to_have_count(0)
        expect(project_navigation.get_by_role("link", name="Scans", exact=True)).to_be_visible()
        page.get_by_role("main").get_by_role("link", name="New scan", exact=True).click()
        # The project is already chosen, so the flow opens on the source step.
        expect(page.locator('input[name="kind"]')).to_have_count(3)
        expect(page.get_by_role("radio", name="GitHub", exact=False)).to_be_enabled()
        website = page.get_by_role("radio", name="Website URL", exact=False)
        expect(website).to_be_enabled()
        website.check()
        expect(page.get_by_label("Approved page URL")).to_be_visible()
        page.get_by_role("radio", name="Project source", exact=False).check()
        page.locator('input[type="file"]').set_input_files(project_zip())  # choosing a file opens the review step
        page.get_by_role("checkbox", name="I have permission to review this file").check()
        page.get_by_role("button", name="Submit scan").click()
        page.wait_for_url("**/projects/*/scans/*")
        scan_id = urlsplit(page.url).path.rsplit("/", 1)[-1]
        expect(page.get_by_role("link", name="Open report", exact=True)).to_be_visible(timeout=50_000)
        page.get_by_role("link", name="Open report", exact=True).click()
        decision = page.locator(".reports-decision")
        expect(decision).to_be_visible(timeout=20_000)  # decision-first block is the first thing on the report
        expect(decision).to_contain_text("This does not mean the project is clean")
        export = owner.request.get(f"{project_api}/reports/{scan_id}/download?format=pdf&lang=ar")
        assert export.ok and export.body().startswith(b"%PDF")

        mobile = other.new_page()
        signup(mobile, origin, "ar")
        expect(mobile.locator("html")).to_have_attribute("dir", "rtl")
        menu = mobile.get_by_role("button", name="قائمة الحساب", exact=True)
        menu.focus()
        menu.press("Enter")
        mobile_menu_item = mobile.get_by_role("menuitem", name="الإعدادات", exact=True)
        expect(mobile_menu_item).to_be_visible()
        mobile_menu_item.focus()
        mobile_menu_item.press("Escape")
        expect(menu).to_be_focused()
        expect(menu).to_have_attribute("aria-expanded", "false")
        expect(mobile.get_by_text("Personal QA project", exact=True)).to_have_count(0)
        for path in ("", "/scans", f"/scans/{scan_id}", f"/reports/{scan_id}/download?format=pdf"):
            assert other.request.get(project_api + path).status == 404
        assert other.request.patch(project_api, data={"name": "Cross-account update"}).status == 404

        header.get_by_role("link", name="Projects", exact=True).click()
        page.get_by_role("main").get_by_role("link", name="Personal QA project").first.click()
        page.get_by_role("link", name="Settings", exact=True).click()
        page.get_by_label("Project name").fill("Renamed personal QA")
        page.get_by_role("button", name="Save name").click()
        expect(page.get_by_role("heading", name="Renamed personal QA", exact=True)).to_be_visible()
        page.get_by_role("button", name="Account menu").click()
        page.get_by_role("menuitem", name="GitHub connection").click()
        expect(page.get_by_text("The server needs a GitHub App configuration.", exact=False)).to_be_visible()
        page.route("**/api/platform/github/connection", lambda route: route.fulfill(
            json={"connect_available": True, "connected": True}))
        page.route("**/api/platform/github/repositories", lambda route: route.fulfill(json={
            "account": {"login": "fixture-user"},
            "repositories": [
                {"installation_id": "12", "repository_id": "28",
                 "repository": "Example/Fixture", "default_branch": "main", "private": True},
                {"installation_id": "12", "repository_id": "29",
                 "repository": "Example/Other", "default_branch": "dev", "private": False},
            ],
        }))
        page.reload()
        expect(page.get_by_text("Connected", exact=True)).to_be_visible()
        expect(page.get_by_text("@fixture-user", exact=True)).to_be_visible()
        expect(page.get_by_text("Example/Fixture", exact=True)).to_be_visible()
        expect(page.get_by_text("Private", exact=True)).to_be_visible()
        page.get_by_role("searchbox", name="Find a repository").fill("Other")
        expect(page.get_by_text("Example/Fixture", exact=True)).to_have_count(0)
        expect(page.get_by_text("Example/Other", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Refresh repositories")).to_be_enabled()
        page.unroute_all()
        assert owner.request.get(origin + "/demo").status == 404
        page.get_by_role("button", name="Account menu").click()
        page.get_by_role("menuitem", name="Sign out").click()
        page.wait_for_url(origin + "/")
        page.goto(origin + "/signin")
        page.locator('[name="email"]').fill(address)
        page.locator('[name="password"]').fill(password)
        page.get_by_role("button", name="Sign in", exact=True).click()
        page.wait_for_url(origin + "/projects")
        page.get_by_role("main").get_by_role("link", name="Renamed personal QA").first.click()
        page.get_by_role("link", name="Settings", exact=True).click()
        page.get_by_role("button", name="Delete project", exact=True).click()
        page.get_by_role("checkbox", name="Hide the project", exact=False).check()
        page.get_by_role("button", name="Confirm project deletion", exact=True).click()
        page.wait_for_url(origin + "/projects")
        assert owner.request.get(project_api).status == 404
        assert owner.request.get(f"{project_api}/reports/{scan_id}").status == 404
        browser.close()
    print("Personal projects browser acceptance passed in English and Arabic.")


if __name__ == "__main__":
    main()
