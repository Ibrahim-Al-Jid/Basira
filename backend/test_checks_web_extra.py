"""Offline positive, clear and unavailable cases for every extra HTML/HAR rule."""
import base64

from .checks import web_extra


POLICY = {
    "base_url": "https://site.example",
    "disallow_external_pings": True,
    "restrict_connection_hints": True,
    "require_explicit_samesite": True,
    "session_cookie_names": ["session"],
    "session_cookie_host_only": True,
    "cors_credential_origins": ["https://trusted.example"],
    "require_cross_origin_isolation": True,
    "corp_paths": ["/protected"],
    "clear_site_data_logout_paths": ["/logout"],
    "untrusted_download_paths": ["/uploads/shared"],
    "redact_server_versions": True,
    "service_worker_scopes": {"/app/service-worker.js": "/app/"},
    "expected_json_paths": ["/api/data"],
    "har_headers_complete": True,
}
SRI = "sha256-" + base64.b64encode(bytes(32)).decode("ascii")


def html(text, policy=POLICY):
    return web_extra.check({"sample.html": text}, None, policy, [])


def har_entry(path, headers, *, transport="https", status=200, mime="text/html", origin=None):
    return {
        "request": {"method": "GET", "url": f"{transport}://site.example{path}?s=private-query",
                    "headers": [{"name": "Origin", "value": origin}] if origin else []},
        "response": {"status": status, "headers": [{"name": name, "value": value} for name, value in headers],
                     "content": {"mimeType": mime}},
    }


def har(*entries, policy=POLICY):
    return web_extra.check({}, {"log": {"entries": list(entries)}}, policy, [])


def test_all_html_extra_rules_find_real_declarations_and_do_not_echo_source():
    findings = html(f"""
        <head><base href="https://private-base.example"></head>
        <script src="https://private-cdn.example/asset.js" integrity="{SRI}"></script>
        <a href="https://private-target.example" target="_blank" rel="opener"
            ping="https://private-tracker.example/path">Open</a>
        <iframe src="https://site.example/account" sandbox="allow-same-origin allow-scripts"></iframe>
        <video poster="http://private-media.example/image"></video>
        <form id="login"></form>
        <input type="password" name="private-name" value="private-password" form="login">
        <link rel="preconnect" href="https://private-network.example">
        <iframe src="https://private-frame.example" allow="camera 'src'; geolocation 'none'"></iframe>
    """)
    assert all(findings[rule] for rule in web_extra.HTML_IDS)
    assert all(findings[rule] is None for rule in web_extra.WEB_IDS)
    assert all(hit["title_ar"] and hit["remediation_ar"] for rule in web_extra.HTML_IDS for hit in findings[rule])
    assert "private-" not in repr(findings)


def test_all_html_extra_rules_distinguish_clear_and_inapplicable_inputs():
    safe = html(f"""
        <head><base href="/app/"></head>
        <script type="module" src="https://module.example/a.js" integrity="{SRI}"></script>
        <link rel="stylesheet" href="https://cdn.example/style.css" crossorigin integrity="{SRI}">
        <a href="https://partner.example" target="_blank" rel="opener noopener" ping="/audit">Open</a>
        <iframe srcdoc="<p>Details</p>" sandbox="allow-scripts"></iframe>
        <img src="https://media.example/picture.jpg">
        <form method="post"><input type="password" name="password"></form>
        <link rel="dns-prefetch" href="/helpers">
        <iframe src="https://frame.example" allow="camera 'none'; microphone 'self'"></iframe>
    """)
    assert all(safe[rule] == [] for rule in web_extra.HTML_IDS)
    none = html("<template><input type=password value=ignored></template><p>Normal text</p>")
    assert all(none[rule] is None for rule in web_extra.HTML_IDS)
    assert html(f'<script src="https://cdn.example/x.js" integrity="{SRI}"></script>', {})["HTML-11"] is None


def test_all_har_extra_rules_find_bad_configuration_with_redacted_facts():
    variant_1, variant_2 = "https://other.example", "https://trusted.example"
    cache = ("Cache-Control", "public")
    base = har_entry("/", [
        ("Set-Cookie", "session=private-cookie; Domain=site.example"),
        ("Permissions-Policy", "camera=*, geolocation=()"),
        ("Server", "private-software/1.2.3"),
    ])
    observed = har(
        base,
        har_entry("/cors", [cache, ("Access-Control-Allow-Origin", variant_1),
                             ("Access-Control-Allow-Credentials", "true")], origin=variant_1),
        har_entry("/cors", [cache, ("Access-Control-Allow-Origin", variant_2),
                             ("Access-Control-Allow-Credentials", "true")], origin=variant_2),
        har_entry("/protected", [("Cross-Origin-Resource-Policy", "cross-origin")]),
        har_entry("/logout", []), har_entry("/uploads/shared", [("Content-Disposition", "inline")]),
        har_entry("/login", [("WWW-Authenticate", 'Digest realm="private-digest, text", Basic realm="private"')],
                  transport="http", status=401),
        har_entry("/redirect", [("Location", "http://site.example/private-redirect")], status=302),
        har_entry("/app/service-worker.js", [("Service-Worker-Allowed", "/")]),
        har_entry("/api/data", [("Content-Type", "text/html")]),
    )
    assert all(observed[rule] for rule in web_extra.WEB_IDS), observed
    assert all(observed[rule] is None for rule in web_extra.HTML_IDS)
    assert len(observed["WEB-14"]) == 2
    assert "private-" not in repr(observed)
    assert "other.example" not in repr(observed)


def test_all_har_extra_rules_distinguish_clear_from_unavailable():
    isolation = [("Cross-Origin-Opener-Policy", "same-origin"), ("Cross-Origin-Embedder-Policy", "credentialless")]
    allowed_2 = "https://second-trusted.example"
    policy = {**POLICY, "cors_credential_origins": ["https://trusted.example", allowed_2]}
    variants = [
        har_entry("/cors", isolation + [("Cache-Control", "public"), ("Vary", "Origin, Accept-Encoding"),
                                       ("Access-Control-Allow-Origin", origin), ("Access-Control-Allow-Credentials", "true")],
                  origin=origin)
        for origin in policy["cors_credential_origins"]
    ]
    safe = har(
        har_entry("/", isolation + [("Set-Cookie", "session=private; SameSite=Lax; Secure"),
                                    ("Server", "server"), ("Permissions-Policy", "camera=(), geolocation=(self)")]),
        *variants,
        har_entry("/protected", isolation + [("Cross-Origin-Resource-Policy", "same-origin")]),
        har_entry("/logout", isolation + [("Clear-Site-Data", '"cache", "cookies"')]),
        har_entry("/uploads/shared", [("Content-Disposition", 'attachment; filename="private.txt"')], mime="text/plain"),
        har_entry("/login", isolation + [("WWW-Authenticate", 'Basic realm="private"')], status=401),
        har_entry("/redirect", [("Location", "/secure")], status=302),
        har_entry("/app/service-worker.js", [], mime="text/javascript"),
        har_entry("/api/data", [("Content-Type", "application/problem+json; charset=utf-8")], mime="application/problem+json"),
        policy=policy,
    )
    assert all(safe[rule] == [] for rule in web_extra.WEB_IDS), safe
    empty = har(policy=policy)
    assert all(empty[rule] is None for rule in web_extra.WEB_IDS)
    partial = har(har_entry("/logout", []), har_entry("/uploads/shared", []), har_entry("/api/data", []),
                  policy={**policy, "har_headers_complete": False})
    assert all(partial[rule] is None or partial[rule].reason == "har_headers_incomplete"
               for rule in web_extra.WEB_IDS)
    assert any(partial[rule] is not None for rule in web_extra.WEB_IDS)


def test_cors_requires_distinct_cacheable_origin_evidence():
    origin = "https://private-origin.example"
    one = har_entry("/cors", [("Cache-Control", "public"), ("Access-Control-Allow-Origin", origin)], origin=origin)
    request_only = har_entry("/cors", [("Cache-Control", "public"), ("Access-Control-Allow-Origin", origin)],
                             origin="https://mismatched.example")
    withheld = har_entry("/cors", [("Cache-Control", "no-store"),
                                    ("Access-Control-Allow-Origin", "https://trusted.example")],
                         origin="https://trusted.example")
    assert har(one, request_only, withheld)["WEB-14"] is None
    wildcard = har_entry("/cors", [
        ("Access-Control-Allow-Origin", "*"), ("Access-Control-Allow-Credentials", "true"),
    ])
    assert har(wildcard)["WEB-13"] == []


def test_structured_policy_parameters_and_bodyless_routes():
    scoped = har(har_entry("/", [
        ("Cross-Origin-Opener-Policy", 'same-origin; report-to="coop"'),
        ("Cross-Origin-Embedder-Policy", 'require-corp; report-to="coep"'),
        ("Permissions-Policy", "camera=(*);report-to=policy, microphone=(self)"),
    ]))
    assert scoped["WEB-15"] == scoped["WEB-16"] == []
    assert scoped["WEB-18"]
    bodyless = har(har_entry("/api/data", [], status=204), har_entry("/uploads/shared", [], status=205))
    assert bodyless["WEB-20"] is bodyless["WEB-25"] is None
    malformed = har(har_entry("/", [("Permissions-Policy", 'camera=(*")')]))
    assert malformed["WEB-18"] is None
