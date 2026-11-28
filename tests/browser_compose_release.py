"""Exercise the release in a disposable Compose project."""

from playwright.sync_api import expect, sync_playwright

from browser_release import ORIGIN
from browser_account import API, FORBIDDEN_COPY, register


def assert_no_overflow(page):
    assert page.evaluate("document.documentElement.scrollWidth === innerWidth"), page.url


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
                # The shell renders one persistent main-navigation entry; the
                # workspace may add one contextual primary action inside main.
                label = "فحص جديد" if language == "ar" else "New scan"
                nav = page.locator(".overview-nav")
                expect(nav.get_by_role("link", name=label, exact=True)).to_have_count(1)
                assert page.get_by_role("main").get_by_role("link", name=label, exact=True).count() <= 1, page.url
                assert_no_overflow(page)
    page.goto(ORIGIN + "/settings")
    page.get_by_label("Theme").select_option("light")
    page.reload()
    expect(layout).to_have_attribute("data-theme", "light")
    page.set_viewport_size({"width": 320, "height": 850})
    # Keyboard path through the header's only dialog: open with Enter, the
    # search field is there, Escape closes. Focus placement on open/close is a
    # known frontend follow-up, so it is deliberately not asserted here.
    search = page.get_by_role("button", name="Search projects and reports", exact=False)
    search.focus()
    page.keyboard.press("Enter")
    dialog = page.get_by_role("dialog", name="Search workspace", exact=True)
    expect(dialog).to_be_visible()
    expect(dialog.get_by_role("searchbox")).to_be_visible()
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)

    fake_key = "raw-credential-fixture"
    removed = request.post(ORIGIN + "/api/models", data={"key": fake_key})
    rejected = request.post(ORIGIN + "/api/run", data={"source": "<p>Fixture</p>", "key": fake_key, "model": "fixture/demo"})
    assert removed.status in {404, 405} and rejected.status in {404, 405}
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


def main():
    with sync_playwright() as testing:
        browser = testing.chromium.launch()
        authenticated_workspace(browser)
        browser.close()
    print("Verified AR/EN responsive routes, keyboard, GitHub fallback, and credential boundaries.")


if __name__ == "__main__":
    main()
