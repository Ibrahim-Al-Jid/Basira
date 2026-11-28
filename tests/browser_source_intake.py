"""Exercise local file intake, project routing, and reports on an isolated Compose stack."""
import io
import json
from secrets import token_urlsafe
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from playwright.sync_api import expect, sync_playwright

from browser_release import ORIGIN, open_report_section


def submit(page, project, kind, name, content, target=None):
    page.goto(f"{ORIGIN}/new-scan?project={project}")
    page.get_by_role("button", name="Continue to source").click()
    page.locator(f'input[name="kind"][value="{kind}"]').check()
    page.locator('input[type="file"]').set_input_files({
        "name": name, "mimeType": "application/octet-stream", "buffer": content,
    })
    if target:
        page.get_by_label("Website address", exact=False).fill(target)
    page.get_by_role("button", name="Review scan").click()
    page.get_by_label("I have permission to review this file").check()
    page.get_by_role("button", name="Submit scan").click()
    link = page.get_by_role("link", name="Open report", exact=True)
    expect(link).to_be_visible(timeout=60_000)
    link.click()
    return page.url.split("/reports/")[1].split("?")[0]


def main():
    api = ORIGIN + "/api/platform"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        ctx = browser.new_context(locale="en-US", viewport={"width": 566, "height": 850})
        response = ctx.request.post(api + "/auth/password/register", data={
            "email": f"intake-{uuid4().hex[:10]}@example.test", "password": token_urlsafe(24),
            "first_name": "Source", "last_name": "Reviewer",
        })
        assert response.status == 201, response.text()
        team = ctx.request.post(api + "/organizations", data={"name": "Intake QA"}).json()["id"]
        project = ctx.request.post(f"{api}/organizations/{team}/projects", data={"name": "Artifact sources"}).json()["id"]
        page = ctx.new_page()
        page.goto(ORIGIN + "/dashboard")
        expect(page.get_by_text("Source Reviewer", exact=False)).to_be_visible()
        expect(page.locator("main").get_by_role("link", name="New scan", exact=True)).to_have_count(1)
        expect(page.locator("main a[href='/projects'], main a[href='/scans'], main a[href='/reports']")).to_have_count(0)
        page.goto(f"{ORIGIN}/projects?project={project}")
        page.locator(".site-brand").click()
        page.wait_for_url("**/dashboard")
        expect(page.locator("main details")).to_have_count(0)

        target = "https://evidence.example.test"
        assert ctx.request.put(f"{api}/projects/{project}/policy", data={
            "base_url": target, "allowed_kinds": ["repository", "html", "har", "openapi", "config", "zap"],
        }).ok
        sample = io.BytesIO()
        with ZipFile(sample, "w", ZIP_DEFLATED) as folder:
            folder.writestr("frontend/index.html", '<form action="http://example.test"></form>')
            folder.writestr("frontend/style.css", ".card { color: black; }")
            folder.writestr("frontend/icon.png", bytes([0, 1, 2]))
            folder.writestr("docker/Dockerfile", "FROM python:3\nUSER 0\n")
        code_id = submit(page, project, "repository", "source.zip", sample.getvalue())
        report_path = f"{api}/projects/{project}/reports/{code_id}"
        report = ctx.request.get(report_path).json()
        assert {row["path"] for row in report["findings"]} >= {"frontend/index.html", "docker/Dockerfile"}
        manifest = {item["path"]: item["status"] for item in report["input_manifest"]}
        assert manifest["frontend/style.css"] == "included" and manifest["frontend/icon.png"] == "skipped"
        open_report_section(page, "coverage")
        expect(page.get_by_role("row", name="frontend/style.css Included in scan")).to_be_visible()
        assert ctx.request.get(report_path + "/download?format=pdf").body().startswith(b"%PDF")

        har = {"log": {"entries": [{"request": {"url": target, "method": "GET", "headers": []},
                                   "response": {"status": 200, "headers": [], "content": {"mimeType": "text/html"}}}]}}
        report_id = submit(page, project, "har", "capture.har", json.dumps(har).encode(), target)
        trace = ctx.request.get(f"{api}/projects/{project}/scans/{report_id}/provenance").json()
        assert trace["asset"]["reference"] == target and trace["asset"]["source"] == "scan_reference"

        specification = {"openapi": "3.1.1", "info": {"title": "Example", "version": "1"},
                         "paths": {"/status": {"get": {"responses": {"200": {"description": "OK"}}}}}}
        report_id = submit(page, project, "openapi", "service.json", json.dumps(specification).encode(), target)
        report_path = f"{api}/projects/{project}/reports/{report_id}"
        assert ctx.request.get(report_path).json()["api_inventory"]["operations"] == 1
        open_report_section(page, "technical")
        expect(page.get_by_role("heading", name="API contract")).to_be_visible()
        expect(page.get_by_text("3.1.1", exact=True)).to_be_visible()
        zap = {"site": [{"@name": target, "alerts": [
            {"pluginid": "10021", "instances": [{"uri": target + "/status?test=ignored"}]},
        ]}]}
        zap_id = submit(page, project, "zap", "saved-zap.json", json.dumps(zap).encode())
        root = f"{api}/projects/{project}/reports/{zap_id}"
        imported = ctx.request.get(root).json()
        assert imported["imported_evidence"]["accepted_alerts"] == 1
        assert imported["findings"][0]["origins"][0]["tool"] == "zap-passive-report"
        assert imported["metrics"]["checksRun"] == 0
        open_report_section(page, "links")
        page.get_by_role("combobox", name="Matching report").select_option(code_id)
        page.get_by_role("button", name="Link report").click()
        expect(page.get_by_role("link", name="source.zip")).to_be_visible()
        assert ctx.request.get(root + "/links").json()["links"][0]["report_id"] == code_id
        page.get_by_role("button", name="Remove link to source.zip").click()
        expect(page.get_by_role("link", name="source.zip")).to_have_count(0)
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
        expect(page.locator("main details")).to_have_count(0)
        browser.close()
    print("Workspace, brand navigation, ZIP/CSS, HAR, OpenAPI, ZAP, linked evidence, and PDF browser checks passed.")


if __name__ == "__main__":
    main()
