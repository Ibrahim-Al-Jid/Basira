"""Exercise the release in a disposable Compose project and seed a schema-v1 report."""
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

from browser_release import ORIGIN, open_report_section
from browser_account import API, FORBIDDEN_COPY, register

QA_PROJECT = "basira12-qa"
LEGACY_FIXTURE = '''
import json
import secrets
import time
from uuid import uuid4
from backend.main import COOKIE, database, owner_key

token = secrets.token_urlsafe(32)
report_id = uuid4().hex
data = {
    "id": report_id, "created_at": "2025-01-10T14:23:00+00:00", "model": None,
    "summary_en": "One preserved observation.", "summary_ar": "ملاحظة واحدة محفوظة.",
    "metrics": {"checksRun": 1, "findingsCount": 1, "validatedCount": 1},
    "findings": [{
        "rule": "http-form", "line": 5, "severity": "medium", "path": "legacy.html",
        "title": "Form submits over HTTP", "title_ar": "نموذج يرسل البيانات عبر HTTP",
        "evidence": "Form submission uses HTTP.",
        "remediation": "Use HTTPS.", "remediation_ar": "استخدم HTTPS.",
    }],
}
with database() as db:
    owner = owner_key(token)
    db.execute("INSERT INTO sessions (owner, expires_at) VALUES (?,?)", (owner, int(time.time()) + 900))
    db.execute("INSERT INTO reports (id,owner,created_at,model,finding_count,report_json) VALUES (?,?,?,?,?,?)",
               (report_id, owner, data["created_at"], "", 1, json.dumps(data)))
print(json.dumps({"cookie": COOKIE, "token": token, "report_id": report_id}))
'''


def seed_legacy():
    parsed = urlsplit(ORIGIN)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port != 8776:
        raise RuntimeError("Fixture seeding requires the isolated HTTP origin on port 8776.")
    container = os.environ.get("BASIRA_QA_CONTAINER", "")
    if container != f"{QA_PROJECT}-app-1":
        raise RuntimeError("Set BASIRA_QA_CONTAINER to the disposable app.")
    docker = ["docker", "--context", os.environ.get("BASIRA_TEST_DOCKER_CONTEXT", "desktop-linux")]
    labels = json.loads(subprocess.check_output(
        [*docker, "inspect", "--format", "{{json .Config.Labels}}", container], text=True
    ))
    if labels.get("com.docker.compose.project") != QA_PROJECT or labels.get("com.docker.compose.service") != "app":
        raise RuntimeError("Container labels do not identify the expected test service.")
    port = subprocess.check_output([*docker, "port", container, "8000/tcp"], text=True)
    if "127.0.0.1:8776" not in port.splitlines():
        raise RuntimeError("The QA service does not expose the expected isolated port.")
    # Pass the fixture as bytes to preserve UTF-8 in Windows terminals. Never print the session token.
    output = subprocess.check_output([*docker, "exec", "-i", container, "python", "-"],
                                     input=LEGACY_FIXTURE.encode("utf-8"))
    return json.loads(output)


def assert_no_overflow(page):
    assert page.evaluate("document.documentElement.scrollWidth === innerWidth"), page.url


def legacy_report(browser, fixture, artifacts):
    context = browser.new_context(locale="en-US")
    context.add_cookies([{
        "name": fixture["cookie"], "value": fixture["token"], "url": ORIGIN,
        "httpOnly": True, "sameSite": "Strict",
    }])
    report_id = fixture["report_id"]
    endpoint = f"{ORIGIN}/api/reports/{report_id}"
    report = context.request.get(endpoint).json()
    assert report["schema_version"] == 1
    assert report["coverage"] is None
    assert [(item["rule"], item["line"]) for item in report["findings"]] == [("http-form", 5)]
    assert report["metrics"]["findingsCount"] == 1

    page = context.new_page()
    for language, direction in (("ar", "rtl"), ("en", "ltr")):
        page.goto(f"{ORIGIN}/reports/{report_id}?lang={language}")
        workspace = page.locator(".reports-workspace")
        expect(workspace).to_have_attribute("dir", direction)
        findings = workspace.locator(".reports-overview-stats dd")
        expect(findings.nth(0)).to_have_text(re.compile("^[1١]$"))
        expect(findings.nth(1)).to_have_text(re.compile("^[1١]$"))
        expect(page.locator('[data-rule="http-form"]')).to_have_count(1)
        for width in (320, 566, 1280):
            page.set_viewport_size({"width": width, "height": 850})
            assert_no_overflow(page)
        open_report_section(page, "coverage")
        expect(page.locator(".reports-coverage tbody tr")).to_have_count(0)
        link = page.get_by_role("link", name="تحميل PDF" if language == "ar" else "Download PDF", exact=True)
        with page.expect_download() as pending:
            link.click()
        completed = pending.value
        assert completed.suggested_filename.endswith(f"-{language}.pdf")
        assert Path(completed.path()).read_bytes().startswith(b"%PDF-")
        if artifacts:
            completed.save_as(artifacts / f"legacy-report-{language}.pdf")
    if artifacts:
        (artifacts / "legacy-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    stranger = browser.new_context()
    try:
        assert stranger.request.get(endpoint).status == 404
        assert stranger.request.get(endpoint + "/download?format=pdf").status == 404
    finally:
        context.close()
        stranger.close()


def authenticated_workspace(browser):
    context = browser.new_context(locale="en-US")
    request = context.request
    register(context)
    organization = request.post(API + "/organizations", data={"name": "Release layout fixtures"})
    assert organization.status == 201
    organization_id = organization.json()["id"]
    created = request.post(API + f"/organizations/{organization_id}/projects", data={"name": "Release workspace"})
    assert created.status == 201
    project = created.json()["id"]
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    layout = page.locator("html")
    for language in ("ar", "en"):
        page.goto(ORIGIN + "/settings")
        page.locator(".account-preferences select").first.select_option(language)
        expect(layout).to_have_attribute("lang", language)
        for width in (320, 566, 1280):
            page.set_viewport_size({"width": width, "height": 850})
            for route in ("/settings", "/dashboard", f"/projects?project={project}", f"/new-scan?project={project}"):
                page.goto(ORIGIN + route)
                expect(page.locator(".site-account")).to_have_count(1)
                expect(page.locator("main h1")).to_have_count(1)
                expect(page.locator("body")).not_to_contain_text(FORBIDDEN_COPY)
                expect(layout).to_have_attribute("dir", "rtl" if language == "ar" else "ltr")
                expect(page.locator("header a[href='/checks']")).to_have_count(0)
                scans = page.get_by_role("link", name="فحص جديد" if language == "ar" else "New scan", exact=True)
                assert scans.count() <= 1, page.url
                assert_no_overflow(page)
    page.goto(ORIGIN + "/settings")
    page.get_by_label("Theme").select_option("light")
    page.reload()
    expect(layout).to_have_attribute("data-theme", "light")
    page.set_viewport_size({"width": 320, "height": 850})
    menu = page.get_by_role("button", name="Open menu")
    menu.focus()
    page.keyboard.press("Enter")
    expect(page.locator(".site-mobile-menu")).to_have_attribute("aria-expanded", "true")
    page.keyboard.press("Escape")
    expect(menu).to_be_focused()
    expect(page.locator(".site-mobile-menu")).to_have_attribute("aria-expanded", "false")

    fake_key = "raw-credential-fixture"
    removed = request.post(ORIGIN + "/api/models", data={"key": fake_key})
    rejected = request.post(ORIGIN + "/api/run", data={"source": "<p>Fixture</p>", "key": fake_key, "model": "fixture/demo"})
    assert removed.status in {404, 405} and rejected.status == 422
    assert fake_key not in removed.text() + rejected.text()
    assert rejected.headers["cache-control"] == "no-store"

    page.goto(f"{ORIGIN}/new-scan?project={project}")
    page.get_by_role("button", name="Continue to source").click()
    page.locator('input[name="kind"][value="github"]').check()
    expect(page.get_by_text("This project needs an authorized GitHub connection.", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Review scan")).to_be_disabled()
    page.locator('input[name="kind"][value="repository"]').check()
    expect(page.locator('input[type="file"][accept=".zip"]')).to_be_visible()

    page.get_by_role("link", name="Account", exact=True).click()
    page.get_by_role("button", name="Sign out", exact=True).click()
    expect(page.get_by_role("button", name="Sign out", exact=True)).to_have_count(0)
    assert request.get(API + f"/projects/{project}/scan-profile").status == 401
    assert not errors, errors
    context.close()


def model_priority(browser):
    context = browser.new_context(locale="en-US")
    context.route(re.compile(r"/api/"), lambda route: route.fulfill(status=401, json={}))
    page = context.new_page()
    report_id = "1" * 32
    rules = ("http-form", "insecure-script")
    findings = [
        {"rule": rule, "line": index + 1, "severity": severity, "path": "fixture.html", "title": title,
         "evidence": "Saved evidence.", "remediation": "Review the configuration."}
        for index, (rule, severity, title) in enumerate(
            zip(rules, ("high", "low"), ("Fixture form", "Fixture script"))
        )
    ]
    payload = {
        "id": report_id, "created_at": "2025-01-10T14:23:00+00:00", "status": "completed",
        "summary_en": "Two observations.", "summary_ar": "ملاحظتان.",
        "metrics": {"findingsCount": 2}, "findings": findings, "coverage": [],
        "priority": list(reversed(rules)), "enrichment": "model",
    }
    page.route(f"{ORIGIN}/api/reports/{report_id}", lambda route: route.fulfill(json=payload))
    url = f"{ORIGIN}/reports/{report_id}?lang=en"
    page.goto(url)
    order = page.locator(".reports-finding-row")
    expect(order.nth(0)).to_have_attribute("data-rule", rules[1])
    expect(order.nth(1)).to_have_attribute("data-rule", rules[0])
    expect(page.get_by_text("Order suggested by the model", exact=True)).to_be_visible()

    payload["enrichment"] = "fallback"
    page.reload()
    expect(order.nth(0)).to_have_attribute("data-rule", rules[0])
    expect(order.nth(1)).to_have_attribute("data-rule", rules[1])
    expect(page.get_by_text("Order suggested by the model", exact=True)).to_have_count(0)
    context.close()


def main():
    fixture = seed_legacy()
    directory = os.environ.get("BASIRA_TEST_ARTIFACT_DIR")
    artifacts = Path(directory) if directory else None
    if artifacts:
        artifacts.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as testing:
        browser = testing.chromium.launch()
        legacy_report(browser, fixture, artifacts)
        authenticated_workspace(browser)
        if os.environ.get("BASIRA_QA_CHECK_RANKING") == "1":
            model_priority(browser)
            print("Accepted UI model ranking and deterministic fallback verified with a local fixture.")
        browser.close()
    print("Verified schema-v1 PDF/JSON, AR/EN responsive routes, keyboard, GitHub fallback, and credential boundaries.")


if __name__ == "__main__":
    main()
