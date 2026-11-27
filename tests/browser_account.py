"""Verify the Account hub, invitations, access, and credential UI on isolated Compose."""
import re
from secrets import token_urlsafe
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

from browser_release import ORIGIN

API = ORIGIN + "/api/platform"
FORBIDDEN_COPY = re.compile(
    "Technical tools|Report migration|Account ID|Demo models|الأدوات التقنية|ترحيل التقارير|معرّف الحساب"
)


def register(context):
    email = f"account-{uuid4().hex[:16]}@example.test"
    response = context.request.post(API + "/auth/password/register", data={
        "email": email, "password": token_urlsafe(28),
        "first_name": "Workspace", "last_name": "Member",
    })
    assert response.status == 201
    return email


def account_layout(page):
    for width in (320, 566, 1280):
        page.set_viewport_size({"width": width, "height": 850})
        for language in ("ar", "en"):
            page.locator(".account-preferences select").first.select_option(language)
            expect(page.locator("html")).to_have_attribute("lang", language)
            expect(page.locator("html")).to_have_attribute("dir", "rtl" if language == "ar" else "ltr")
            assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
            expect(page.locator(".site-account")).to_have_count(1)
            expect(page.locator("header select")).to_have_count(0)
            expect(page.locator("body")).not_to_contain_text(FORBIDDEN_COPY)
    page.get_by_label("Theme").select_option("light")
    page.reload()
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    page.get_by_label("Theme").select_option("dark")
    page.set_viewport_size({"width": 566, "height": 850})
    menu = page.get_by_role("button", name="Open menu")
    menu.focus()
    page.keyboard.press("Enter")
    expect(page.locator(".site-mobile-menu")).to_have_attribute("aria-expanded", "true")
    page.keyboard.press("Escape")
    expect(menu).to_be_focused()
    expect(menu).to_have_attribute("aria-expanded", "false")


def credential_ui(page, org):
    endpoint = f"{API}/organizations/{org}/model-connection"
    key = "sk-or-test-browser-fixture"
    expected_model = "test/fixture"
    connection = None
    current = page.request.get(endpoint)
    assert current.ok and current.json()["available"], current.text()
    assert current.headers["cache-control"] == "no-store"

    def mock(route):
        nonlocal connection
        request = route.request
        if request.method == "PUT":
            body = request.post_data_json
            assert body["model"] == expected_model
            if body.get("api_key") != key:
                route.fulfill(status=422, json={"detail": "Fixture validation rejected"})
                return
            connection = {"id": "openrouter-default", "provider": "openrouter", "model": expected_model,
                          "source": "organization", "verified_at": "2026-11-21T12:00:00Z"}
        elif request.method == "DELETE":
            connection = None
        route.fulfill(json={"available": True, "connection": connection})

    page.route(endpoint, mock)
    page.reload()
    page.get_by_label("OpenRouter model ID").fill(expected_model)
    secret = page.get_by_label("OpenRouter API key")
    expect(secret).to_have_attribute("type", "password")
    secret.fill(key)
    page.get_by_role("button", name="Verify and save").click()
    expect(page.get_by_text("Connection verified and saved.")).to_be_visible()
    expect(page.locator('input[name="api_key"]')).to_have_count(0)
    page.get_by_role("button", name="Rotate key").click()
    page.get_by_label("New API key").fill("rejected-browser-fixture")
    page.get_by_role("button", name="Verify and save").click()
    expect(page.get_by_label("New API key")).to_have_value("")
    expect(page.get_by_text(expected_model, exact=True)).to_be_visible()
    assert key not in page.evaluate("JSON.stringify([localStorage,sessionStorage])")
    assert key not in page.content()
    page.get_by_role("button", name="Remove connection").click()
    page.get_by_role("button", name="Confirm removal").click()
    expect(page.get_by_text("Connection removed.")).to_be_visible()
    page.unroute(endpoint, mock)


def main():
    with sync_playwright() as testing:
        browser = testing.chromium.launch()
        owner = browser.new_context(locale="en-US")
        member = browser.new_context(locale="en-US")
        register(owner)
        register(member)
        org = owner.request.post(API + "/organizations", data={"name": "Account team"}).json()["id"]
        org_api = f"{API}/organizations/{org}"
        project = owner.request.post(org_api + "/projects", data={"name": "Account project"}).json()["id"]
        project_api = f"{API}/projects/{project}"
        page = owner.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(ORIGIN + "/settings")
        account_layout(page)
        credential_ui(page, org)
        for path in ("/checks", "/checks/"):
            assert owner.request.get(ORIGIN + path).status == 404
        assert len(owner.request.get(ORIGIN + "/api/catalog").json()["rules"]) == 100

        project_link = f"{ORIGIN}/projects?project={project}"
        page.goto(project_link)
        expect(page.get_by_role("link", name="New scan", exact=True)).to_have_count(1)
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_have_count(0)
        page.get_by_role("link", name="Access", exact=True).click()
        page.get_by_label("Invitation role").select_option("viewer")
        page.get_by_role("button", name="Create invitation").click()
        url = page.get_by_label("Invitation link").input_value()
        assert urlsplit(url).fragment.startswith("invite=")
        guest = member.new_page()
        guest.goto(url)
        guest.get_by_role("button", name="Accept invitation").click()
        expect(guest.get_by_text("You joined", exact=False)).to_be_visible()
        assert not urlsplit(guest.url).fragment
        expect(guest.get_by_role("heading", name="Model connection")).to_have_count(0)
        assert member.request.get(org_api + "/model-connection").status == 403
        assert member.request.get(project_api + "/scan-profile").status == 404

        page.reload()
        picker = page.locator('select[name="member"]')
        picker.select_option(label="Workspace Member · Viewer")
        page.get_by_role("button", name="Add to project").click()
        expect(page.get_by_text("Member added to the project.")).to_be_visible()
        assert member.request.get(project_api + "/scan-profile").status == 200
        page.get_by_role("button", name="Revoke project access").click()
        expect(page.get_by_text("Project access revoked.")).to_be_visible()
        assert member.request.get(project_api + "/scan-profile").status == 404
        page.get_by_role("button", name="Create invitation").click()
        page.get_by_role("button", name="Revoke invitation").click()
        expect(page.get_by_text("Invitation revoked.")).to_be_visible()

        page.get_by_role("link", name="Account", exact=True).click()
        page.get_by_role("button", name="Sign out", exact=True).click()
        expect(page.get_by_role("button", name="Sign out", exact=True)).to_have_count(0)
        assert owner.request.get(project_api + "/scan-profile").status == 401
        assert not errors, errors
        browser.close()
    print("Account browser flow passed for account, layouts, credential UI, invitations, access and logout.")


if __name__ == "__main__":
    main()
