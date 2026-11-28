"""Positive, clear and unavailable examples for offline web and npm rules."""

import base64
import json

from .checks import dependencies, web


SRI = "sha256-" + base64.b64encode(bytes(32)).decode("ascii")
BASE_POLICY = {"base_url": "https://site.example", "har_headers_complete": True,
               "require_csp": True, "require_frame_protection": True,
               "private_paths": ["/account"], "session_cookie_names": ["session"]}


def html_check(html, policy=BASE_POLICY):
    return web.check({"index.html": html}, None, policy, [])


def har_entry(headers, *, body="<html><head></head><body></body></html>",
              url="https://site.example/account?token=private-query", status=200):
    content = {"mimeType": "text/html"}
    if body is not None:
        content.update(text=body, size=len(body.encode("utf-8")))
    return {"request": {"url": url}, "response": {
        "status": status, "content": content,
        "headers": [{"name": name, "value": value} for name, value in headers],
    }}


def har_check(*entries, policy=BASE_POLICY):
    return web.check({}, {"log": {"entries": list(entries)}}, policy, [])


def test_all_html_rules_observe_redacted_local_evidence():
    results = html_check("""
      <link rel="stylesheet" href="https://cdn.jsdelivr.net/private.css?token=private-key">
      <script src="/script.js" integrity="sha256-bogus"></script>
      <form id="purchase"></form>
      <button form="purchase" formaction="http://shop.example/?token=private-key">Order</button>
      <iframe src="http://frames.example/private"></iframe>
      <link rel="alternate stylesheet" href="http://assets.example/file.css">
      <meta http-equiv="refresh" content="0; URL='http://shop.example/private'">
    """)
    assert all(results[rule] for rule in web.HTML_IDS)
    assert all(results[rule] is None for rule in web.WEB_IDS)
    assert results["HTML-10"][0]["assessment"] == "review_required"
    assert results["HTML-06"][0]["line"] == 5
    assert "private" not in repr(results)


def test_all_html_rules_distinguish_clear_and_not_applicable():
    results = html_check(f"""
      <link rel="stylesheet" href="//cdn.jsdelivr.net/file.css" integrity="{SRI}">
      <form><button type="submit" formaction="https://site.example">Send</button></form>
      <iframe src="https://frames.example" sandbox></iframe>
      <meta http-equiv="refresh" content="0; url=https://site.example">
    """)
    assert all(results[rule] == [] for rule in web.HTML_IDS)
    unrelated = html_check("""
      <template>
        <iframe src="http://frames.example"></iframe>
        <link rel="stylesheet" href="http://cdn.jsdelivr.net/file.css">
      </template>
      <input type="button" formaction="http://example.test">
      <iframe srcdoc="<p>inline frame</p>" src="http://example.test">
    """)
    assert all(unrelated[rule] is None for rule in web.HTML_IDS)
    no_origin = html_check('<iframe src="http://example.test"></iframe>', {})
    assert no_origin["HTML-07"] is None and no_origin["HTML-10"] is None


def test_all_web_rules_observe_only_safe_capture_facts():
    headers = [
        ("Content-Security-Policy-Report-Only", "script-src 'none'"),
        ("Referrer-Policy", "origin, unsafe-url"),
        ("Cache-Control", 'x-extension="private-control", s-maxage=12'),
        ("Set-Cookie", "session=private-cookie; Path=/; SameSite=Lax"),
    ]
    permissive = har_entry([("Content-Security-Policy", "script-src 'unsafe-inline' 'unsafe-eval';")])
    results = har_check(har_entry(headers), permissive)
    assert all(results[rule] for rule in web.WEB_IDS)
    assert all(results[rule] is None for rule in web.HTML_IDS)
    assert len(results["WEB-03"]) == 1
    assert results["WEB-10"][0]["evidence"].startswith("HAR response #1")
    for private in ("private-cookie", "private-query", "private-control", "site.example"):
        assert private not in repr(results)


def test_safe_web_configuration_csp_intersection_and_header_precedence():
    headers = [
        ("Strict-Transport-Security", "max-age=3600; includeSubDomains"),
        ("Content-Security-Policy", "script-src 'unsafe-inline' 'unsafe-eval';frame-ancestors 'self'"),
        ("Content-Security-Policy", "default-src 'self';"),
        ("X-Content-Type-Options", "NoSniff"),
        ("Referrer-Policy", "unsafe-url, strict-origin"),
        ("Cache-Control", 'public, no-store, x-extension="unrelated, quoted"'),
        ("Set-Cookie", "session=sensitive; Secure; HttpOnly"),
    ]
    safe = har_check(har_entry(headers))
    assert all(safe[rule] == [] for rule in web.WEB_IDS)
    meta = "<html><head><meta http-equiv='content-security-policy' content=\"script-src 'nonce-YWJj' 'unsafe-inline'\"></head></html>"
    via_meta = har_check(har_entry([], body=meta))
    assert via_meta["WEB-02"] == [] and via_meta["WEB-03"] == []
    override = har_check(har_entry([
        ("Content-Security-Policy", "script-src 'none'; script-src-attr 'unsafe-inline'; frame-ancestors *"),
        ("X-Frame-Options", "DENY"),
    ]))
    assert override["WEB-03"] and len(override["WEB-03"]) == 1
    assert "script-src-attr" in override["WEB-03"][0]["evidence"]
    assert override["WEB-05"]


def test_incomplete_capture_never_claims_missing_headers_or_meta():
    policy = dict(BASE_POLICY, har_headers_complete=False)
    unmeasured = har_check(har_entry([], body=None), policy=policy)
    gated = {"WEB-01", "WEB-02", "WEB-05", "WEB-06", "WEB-07", "WEB-08"}
    assert all(unmeasured[rule].reason == "har_headers_incomplete" for rule in gated)
    assert all(unmeasured[rule] is None for rule in set(web.WEB_IDS) - gated)
    incomplete_body = har_entry([], body="<html>")
    incomplete_body["response"]["content"]["size"] = 500
    assert har_check(incomplete_body)["WEB-02"].reason == "response_content_unreadable"
    external = har_entry([], url="https://third-party.example")
    assert all(har_check(external)[rule] is None for rule in web.WEB_IDS)


def json_file(value):
    return json.dumps(value, indent=2)


def local_advisory(identifier, name, affected):
    return {"id": identifier, "modified": "2026-11-20T07:00:00Z",
            "affected": [{"package": {"ecosystem": "npm", "name": name}, **affected}]}


def lock_file(direct_version, rows, *, workspaces=None):
    root = {"dependencies": {"demo-direct": direct_version}}
    if workspaces:
        root["workspaces"] = workspaces
    return {"lockfileVersion": 3, "packages": {"": root, **rows}}


def package(name, version, *, host="registry.npmjs.org", integrity="sha512-valid-placeholder"):
    return {"version": version, "integrity": integrity,
            "resolved": f"https://{host}/{name}/-/{name}-{version}.tgz"}


def test_all_dependency_rules_observe_pins_and_enforce_direct_precedence():
    rows = {
        "node_modules/demo-direct": package("demo-direct", "1.0.0", integrity=None),
        "node_modules/parent/node_modules/demo-direct": package("demo-direct", "1.0.0"),
        "node_modules/demo-child": package("demo-child", "1.0.1", host="other-registry.test"),
    }
    files = {
        "package.json": json_file({"dependencies": {
            "demo-direct": "^2.0.0",
            "demo-tarball": "http://demo.test/package.tgz?key=private-npm",
            "demo-git": "github:demo/project#main",
        }}),
        "package-lock.json": json_file(lock_file("^1.0.0", rows)),
        "fresh/package.json": json_file({"name": "fresh", "packageManager": "npm@11.0.0"}),
    }
    local = [
        local_advisory("TEST-2026-1", "demo-direct", {"versions": ["1.0.0"]}),
        local_advisory("TEST-2026-2", "demo-child", {"ranges": [
            {"type": "SEMVER", "events": [{"introduced": "1.0.0"}, {"fixed": "1.0.2"}]},
        ]}),
    ]
    policy = {"registry_allowlist": ["registry.npmjs.org"], "application": True, "repository_complete": True}
    results = dependencies.check(files, None, policy, local)
    assert all(results[rule] for rule in dependencies.IDS)
    assert len(results["DEP-01"]) == len(results["DEP-02"]) == 1
    assert "demo-direct@1.0.0" in results["DEP-01"][0]["evidence"]
    assert "demo-child@1.0.1" in results["DEP-02"][0]["evidence"]
    assert results["DEP-03"][0]["path"] == "fresh/package.json"
    assert "private-npm" not in repr(results)


def test_all_dependency_rules_clear_for_supported_safe_inputs():
    spec = {"demo-direct": "^2.0.0", "demo-git": "github:demo/project#" + ("a" * 40)}
    lock = lock_file("^2.0.0", {
        "node_modules/demo-direct": package("demo-direct", "2.0.0"),
        "node_modules/demo-child": package("demo-child", "1.0.2"),
    }, workspaces=["packages/*"])
    lock["packages"][""]["dependencies"] = spec
    files = {
        "package.json": json_file({"dependencies": spec, "workspaces": ["packages/*"]}),
        "package-lock.json": json_file(lock),
        "packages/demo/package.json": json_file({"name": "demo-workspace"}),
    }
    local = [
        local_advisory("TEST-2026-1", "demo-direct", {"versions": ["1.0.0"]}),
        local_advisory("TEST-2026-2", "demo-child", {"ranges": [
            {"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": "1.0.2"}]},
        ]}),
    ]
    policy = {"registry_allowlist": ["registry.npmjs.org"], "application": True, "repository_complete": True}
    results = dependencies.check(files, None, policy, local)
    assert all(results[rule] == [] for rule in dependencies.IDS)
    assert all(result is None for result in dependencies.check({"README.md": "Demo"}, None, {}, []).values())


def test_unsupported_advisories_and_absence_evidence_do_not_claim_coverage():
    files = {"package.json": json_file({"name": "demo", "packageManager": "pnpm@10.0.0"}),
             "package-lock.json": json_file({"lockfileVersion": 1, "dependencies": {}})}
    policy = {"application": True, "repository_complete": True}
    local = [local_advisory("TEST-2026-1", "demo", {"ranges": [
        {"type": "ECOSYSTEM", "events": [{"introduced": "0"}]},
    ]})]
    results = dependencies.check(files, None, policy, local)
    assert results["DEP-01"] is results["DEP-02"] is results["DEP-03"] is results["DEP-08"] is None
