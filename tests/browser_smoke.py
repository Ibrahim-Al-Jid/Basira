"""Visit every main page in English and Arabic: no script errors, no horizontal overflow, bare report links resolve."""

from io import BytesIO
import os
import time
from secrets import token_urlsafe
from urllib.parse import urlsplit
from uuid import uuid4
from zipfile import ZipFile

from playwright.sync_api import sync_playwright


def main():
    origin = os.environ["BASIRA_QA_ORIGIN"].rstrip("/")
    parsed = urlsplit(origin)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port in (None, 8765):
        raise ValueError("Use a disposable loopback instance on its own port.")
    archive = BytesIO()
    with ZipFile(archive, "w") as file:
        file.writestr("index.html", "<!doctype html><html><title>Smoke</title><form action='x'><input name='q'></form></html>")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=os.environ.get("BASIRA_BROWSER_CHANNEL") or None)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append("script error: " + str(error)[:160]))
        page.on("console", lambda message: errors.append("console: " + message.text[:160]) if message.type == "error" else None)
        failed = []
        page.on("response", lambda response: failed.append(f"{response.status} {response.url[len(origin):][:80]}") if response.status >= 400 else None)
        context.request.post(origin + "/api/platform/auth/password/register", data={
            "email": f"smoke-{uuid4().hex[:10]}@example.test", "password": token_urlsafe(24),
            "first_name": "Smoke", "last_name": "Tester"}).json()
        project = context.request.post(origin + "/api/platform/projects", data={"name": "Smoke"}).json()["id"]
        version = context.request.get(f"{origin}/api/platform/projects/{project}/scan-profile").json().get("scope_version", 0)
        scan = context.request.post(f"{origin}/api/platform/projects/{project}/intake/zip", data=archive.getvalue(), headers={
            "Content-Type": "application/zip", "X-Artifact-Name": "smoke.zip", "X-Scope-Version": str(version),
            "X-Acknowledge-Scope": "true", "Idempotency-Key": "smoke-" + uuid4().hex}).json()["id"]
        for _ in range(90):
            state = context.request.get(f"{origin}/api/platform/projects/{project}/scans/{scan}").json().get("state")
            if state in ("completed", "failed"):
                break
            time.sleep(1)
        assert state == "completed", f"scan ended as {state}"
        paths = ["/projects", f"/projects/{project}", f"/reports?project={project}", f"/reports/{scan}?project={project}",
                 "/dashboard", "/scans", f"/new-scan?project={project}", "/settings", f"/projects/{project}/scans/{scan}"]
        for language in ("en", "ar"):
            page.goto(origin + "/")
            page.evaluate(f"localStorage.setItem('basira-language', '{language}')")
            for path in paths:
                page.goto(origin + path)
                page.wait_for_load_state("networkidle")
                overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                assert overflow <= 0, f"horizontal overflow {overflow}px on {path} ({language})"
                try:
                    page.wait_for_selector("main h1", timeout=8000)
                except Exception:
                    raise AssertionError(f"no heading on {path} ({language}); url {page.url}; text {page.inner_text('body')[:200]!r}")
            page.goto(f"{origin}/reports/{scan}")
            page.wait_for_url(f"{origin}/reports/{scan}?project={project}")
        assert not errors, (errors[:5], failed[:5])
        page.goto(origin + "/definitely-not-a-page")
        page.wait_for_load_state("networkidle")
        assert page.locator("h1").count() > 0
        browser.close()
    print("Smoke test passed: 9 pages in English and Arabic, bare report link resolved, no script errors.")


if __name__ == "__main__":
    main()
