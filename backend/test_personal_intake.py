from base64 import b64decode, urlsafe_b64encode
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import unescape
from io import BytesIO
import json
from pathlib import Path
import re
import runpy
import socket
import ssl
import stat
from threading import Thread
from time import monotonic
from urllib.parse import parse_qs, urlsplit
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import httpx
import pytest
from sqlalchemy import text

from . import github_import, intake_website, personal_github, platform_jobs
from .identity import SESSION_COOKIE
from .artifact_review import InputError
from .platform_db import platform_session
from .test_personal_projects import API, BASE, personal_clients, repository_submission

PAGE = "https://example.test/page"
TOKEN = "ghu_fixture_not_a_real_credential"
COMMIT = "a" * 40
SCOPE = {"scope_version": 0, "acknowledge_scope": True}


def new_project(client):
    project_id = client.post(API + "/projects", json={"name": "Intake fixtures"}).json()["id"]
    return API + "/projects/" + project_id, project_id


def reported(owner, path, project_id, scan):
    assert scan.status_code == 202, scan.text
    with platform_session() as db:
        org_id = db.execute(text("SELECT org_id FROM projects WHERE id=:id"), {"id": project_id}).scalar_one()
    scan_id = scan.json()["id"]
    platform_jobs.execute_scan(org_id, project_id, scan_id)
    report = owner.get(path + "/reports/" + scan_id)
    assert report.status_code == 200, report.text
    provenance = owner.get(path + f"/scans/{scan_id}/provenance")
    assert provenance.status_code == 200
    data = report.json()
    snapshot = provenance.json()["snapshot"]
    execution = data["execution"]
    assert execution["source_sha256"] == snapshot["sha256"]
    assert execution["trace_id"] == scan_id
    assert execution["validated_locations"] == len(data["findings"])
    if snapshot["kind"] == "repository":
        assert execution["inventory_sha256"] == snapshot["profile"]["expanded_text_sha256"]
        assert execution["files_read"] == snapshot["profile"]["text_files"]
    return data, snapshot


def zip_headers(key):
    return {"Idempotency-Key": key, "X-Artifact-Name": "fixture.zip", "Content-Type": "application/zip",
            "X-Scope-Version": "0", "X-Acknowledge-Scope": "true"}


def test_review_memory_only_reuses_scoped_categories_from_the_same_snapshot(personal_clients, monkeypatch):
    monkeypatch.setenv("BASIRA_ALLOW_INLINE_ANALYSIS", "1")
    owner, other = personal_clients
    path, project_id = new_project(owner)
    other_path, other_project_id = new_project(other)

    def archive_for(html):
        output = BytesIO()
        with ZipFile(output, "w") as archive:
            archive.writestr("index.html", html)
        return output.getvalue()

    raw = archive_for('<script src="http://example.invalid/javascript"></script>')
    first = owner.post(path + "/intake/zip", content=raw, headers=zip_headers("memory-first"))
    prior, _ = reported(owner, path, project_id, first)
    review_url = path + "/reports/" + prior["id"] + "/review"
    review = owner.get(review_url).json()["items"][0]
    change = owner.post(review_url, json={
        "fingerprint": review["fingerprint"], "action": "status", "status": "triaged",
        "reason": "Owner note is not agent memory.",
    })
    assert change.status_code == 200, change.text
    repeat = owner.post(path + "/intake/zip", content=raw, headers=zip_headers("memory-repeat"))
    same, _ = reported(owner, path, project_id, repeat)
    assert same["review_context"] == [{
        "fingerprint": review["fingerprint"], "status": "triaged", "prior_scan_id": prior["id"],
    }]
    assert "Owner note" not in json.dumps(same)
    revised = owner.post(path + "/intake/zip", content=archive_for(
        '<script src="http://example.invalid/javascript"></script>\n<p>Different snapshot</p>'),
        headers=zip_headers("memory-revised"))
    different, _ = reported(owner, path, project_id, revised)
    assert "review_context" not in different
    separate = other.post(other_path + "/intake/zip", content=raw, headers=zip_headers("memory-separate"))
    other_report, _ = reported(other, other_path, other_project_id, separate)
    assert "review_context" not in other_report


def test_zip_intake_retries_profile_and_rejections(personal_clients, monkeypatch):
    owner, other = personal_clients
    monkeypatch.setenv("BASIRA_ALLOW_INLINE_ANALYSIS", "1")
    path, project_id = new_project(owner)
    sample = BytesIO(b64decode(repository_submission()["content"]))
    with ZipFile(sample, "a") as archive:
        archive.writestr("dist/output.js", "console.log('excluded build output');")
    raw = sample.getvalue()
    zip_route = path + "/intake/zip"
    headers = zip_headers("zip-fixture-key")
    assert other.post(zip_route, content=raw, headers=headers).status_code == 404
    scan = owner.post(zip_route, content=raw, headers=headers)
    assert owner.post(zip_route, content=raw, headers=headers).json()["id"] == scan.json()["id"]
    assert owner.post(zip_route, content=raw + b" ", headers=headers).status_code == 409
    report, snapshot = reported(owner, path, project_id, scan)
    assert snapshot["sha256"] == sha256(raw).hexdigest()
    profile = report["input_artifact"]["profile"]
    assert profile["mode"] == "zip" and profile["text_files"] == 1
    assert profile["skipped_files"] == 1
    assert any(item["path"] == "dist/output.js" and item["reason"] == "build_artifact"
               for item in report["input_manifest"])
    assert snapshot["profile"] == profile and len(profile["expanded_text_sha256"]) == 64
    assert owner.post(zip_route, content=b"plain", headers=zip_headers("invalid-zip-key")).status_code == 422
    archive = BytesIO()
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as file:
        file.writestr("repeat.txt", b"x" * 500_000)
    assert owner.post(zip_route, content=archive.getvalue(),
                      headers=zip_headers("ratio-limit-key")).status_code == 422
    archive = BytesIO()
    with ZipFile(archive, "w") as file:
        file.writestr("Index.html", "first")
        file.writestr("index.html", "second")
    assert owner.post(zip_route, content=archive.getvalue(),
                      headers=zip_headers("duplicate-name-key")).status_code == 422
    archive = BytesIO()
    with ZipFile(archive, "w") as file:
        file.writestr("index.html", "<html></html>")
        linked = ZipInfo("linked.html")
        linked.create_system = 3
        linked.external_attr = (stat.S_IFLNK | 0o777) << 16
        file.writestr(linked, "index.html")
    assert owner.post(zip_route, content=archive.getvalue(),
                      headers=zip_headers("link-entry-key")).status_code == 422
    assert owner.post(zip_route, content=raw[:-12], headers=zip_headers("truncated-zip-key")).status_code == 422
    monkeypatch.setenv("BASIRA_INTAKE_STORAGE_REQUIRED", "1")
    monkeypatch.delenv("BASIRA_INTAKE_S3_BUCKET", raising=False)
    assert owner.post(zip_route, content=raw, headers=zip_headers("storage-down-key")).status_code == 503


def test_personal_github_oauth_rechecks_selected_repo_and_pins_commit(personal_clients, monkeypatch):
    owner, other = personal_clients
    monkeypatch.setenv("BASIRA_ALLOW_INLINE_ANALYSIS", "1")
    monkeypatch.setenv("BASIRA_GITHUB_CLIENT_ID", "Iv1.Fixture")
    monkeypatch.setenv("BASIRA_GITHUB_CLIENT_SECRET", "fixture-client-secret")
    monkeypatch.setenv("BASIRA_GITHUB_CREDENTIAL_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("BASIRA_GITHUB_CALLBACK_URL", BASE + personal_github.CALLBACK_PATH)
    monkeypatch.setenv("BASIRA_GITHUB_APP_SLUG", "basira-fixture")
    path, project_id = new_project(owner)
    provider = API + "/github"
    assert owner.get(provider + "/setup").json() == {
        "callback_url": BASE + personal_github.CALLBACK_PATH,
        "install_url": "https://github.com/apps/basira-fixture/installations/new",
    }
    raw = b64decode(repository_submission()["content"])
    seen = []
    installation = {"id": 12, "permissions": {"contents": "read", "metadata": "read"},
                    "repository_selection": "selected"}
    repository = {"id": 28, "full_name": "Example/Fixture", "default_branch": "main",
                  "private": True, "permissions": {"pull": True}}
    visible = [repository]
    challenge = None
    exchange_error = None

    def respond(request):
        seen.append((request.method, request.url.path))
        url = request.url.path
        if url.endswith("/access_token"):
            exchange = parse_qs(request.content.decode())
            assert exchange["code"] == ["fixture-code"]
            verifier = exchange["code_verifier"][0]
            assert challenge == urlsafe_b64encode(sha256(verifier.encode()).digest()).decode().rstrip("=")
            if exchange_error:
                return httpx.Response(200, json={"error": exchange_error})
            return httpx.Response(200, json={"access_token": TOKEN, "expires_in": 28_800})
        if request.url.host == "codeload.github.com":
            assert "authorization" not in request.headers
            return httpx.Response(200, stream=httpx.ByteStream(raw))
        if request.method == "DELETE":
            assert request.url.path == "/applications/Iv1.Fixture/token"
            assert json.loads(request.content)["access_token"] == TOKEN
            return httpx.Response(204)
        assert request.headers["authorization"] == "Bearer " + TOKEN
        if url == "/user":
            return httpx.Response(200, json={"id": 77, "login": "fixture-user"})
        if url == "/user/installations":
            return httpx.Response(200, json={"installations": [installation]})
        if url == "/user/installations/12/repositories":
            return httpx.Response(200, json={"repositories": visible})
        if url == "/repos/Example/Fixture/branches/main":
            return httpx.Response(200, json={"commit": {"sha": COMMIT}})
        if url == f"/repos/Example/Fixture/zipball/{COMMIT}":
            return httpx.Response(302, headers={"Location": f"https://codeload.github.com/Example/Fixture/zip/{COMMIT}?signed=fixture"})
        pytest.fail(str(request.url))

    monkeypatch.setattr(github_import, "client", lambda: httpx.Client(transport=httpx.MockTransport(respond)))
    discarded = other.post(provider + "/authorize")
    discarded_state = parse_qs(urlsplit(discarded.json()["url"]).query)["state"][0]
    discarded_proof = other.cookies.get(personal_github.CALLBACK_COOKIE)
    # A second client logs out, while a previously issued cross-site proof still exists.
    with platform_session() as db:
        db.execute(text("UPDATE auth_sessions SET revoked_at = CURRENT_TIMESTAMP WHERE token_digest = :digest"),
                   {"digest": sha256(other.cookies.get(SESSION_COOKIE).encode()).hexdigest()})
    assert other.get(provider + "/callback", params={"state": discarded_state, "code": "fixture-code"},
                     headers={"Cookie": f"{personal_github.CALLBACK_COOKIE}={discarded_proof}"},
                     follow_redirects=False).headers["location"].endswith("failed")
    assert seen == []
    authorize = owner.post(provider + "/authorize")
    cookie = authorize.headers["set-cookie"]
    assert "SameSite=lax" in cookie and "HttpOnly" in cookie
    assert "Path=" + personal_github.CALLBACK_PATH in cookie
    params = parse_qs(urlsplit(authorize.json()["url"]).query)
    challenge, state = params["code_challenge"][0], params["state"][0]
    callback = {"state": state, "code": "fixture-code"}
    proof = owner.cookies.get(personal_github.CALLBACK_COOKIE)
    session = owner.cookies.get(SESSION_COOKIE)
    assert other.get(provider + "/callback", params=callback, follow_redirects=False).headers["location"].endswith("failed")
    assert owner.get(provider + "/callback", params=callback, follow_redirects=False,
                     headers={"Cookie": f"{SESSION_COOKIE}={session}"}).headers["location"].endswith("failed")
    callback_headers = {"Cookie": f"{personal_github.CALLBACK_COOKIE}={proof}"}
    assert owner.get(provider + "/callback", params={**callback, "state": "wrong"}, follow_redirects=False,
                     headers=callback_headers).headers["location"].endswith("failed")
    assert seen == []
    assert owner.get(provider + "/callback", params=callback, follow_redirects=False,
                     headers=callback_headers).headers["location"].endswith("connected")
    assert owner.get(provider + "/callback", params=callback, follow_redirects=False,
                     headers=callback_headers).headers["location"].endswith("failed")
    assert other.get(provider + "/repositories").status_code == 401
    listing = owner.get(provider + "/repositories").json()
    assert listing["account"] == {"login": "fixture-user"}
    assert listing["repositories"][0]["repository_id"] == "28"
    assert listing["repositories"][0]["private"] is True
    body = {**SCOPE, "source": "github", "installation_id": "12", "repository_id": "28", "ref": "main"}
    headers = {"Idempotency-Key": "github-fixture-key"}
    scan = owner.post(path + "/intake", json=body, headers=headers)
    before_retry = list(seen)
    assert owner.post(path + "/intake", json=body, headers=headers).json()["id"] == scan.json()["id"]
    assert seen == before_retry
    report, snapshot = reported(owner, path, project_id, scan)
    assert snapshot["github"]["commit"] == COMMIT
    assert snapshot["profile"]["mode"] == "github"
    assert TOKEN not in json.dumps(report) and "signed=fixture" not in json.dumps(snapshot)
    visible.clear()
    assert owner.post(path + "/intake", json=body, headers={"Idempotency-Key": "revoked-repo-key"}).status_code == 409
    assert owner.delete(provider + "/connection").status_code == 204
    assert not owner.get(provider + "/connection").json()["connected"]
    assert owner.get(path + "/reports/" + scan.json()["id"]).status_code == 200
    exchange_error = "incorrect_client_credentials"
    authorize = owner.post(provider + "/authorize")
    params = parse_qs(urlsplit(authorize.json()["url"]).query)
    challenge = params["code_challenge"][0]
    rejected = owner.get(provider + "/callback", params={"state": params["state"][0], "code": "fixture-code"},
                         follow_redirects=False)
    assert rejected.headers["location"].endswith("github=credentials")
    assert not owner.get(provider + "/connection").json()["connected"]


def test_local_github_manifest_wizard_uses_one_time_state_and_saves_configuration(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "ops" / "configure-local-github.py"
    wizard = runpy.run_path(str(script))["register"]
    received = []
    outcomes = []
    threads = []
    origin = "http://127.0.0.1:8765"
    callback = origin + personal_github.CALLBACK_PATH
    fixture_code = "local-setup-fixture-code"
    path = tmp_path / "vault" / "github-app.json"

    def convert(code):
        received.append(code)
        return "Iv1.Fixture", "basira-fixture", "test-app-config-value"

    def open_wizard(url):
        def exercise():
            with httpx.Client(trust_env=False) as browser:
                page = browser.get(url)
                state_url = unescape(re.search(r'<form method="post" action="([^"]+)"', page.text)[1])
                state = parse_qs(urlsplit(state_url).query)["state"][0]
                manifest_data = json.loads(unescape(re.search(r'name="manifest" value="([^"]+)"', page.text)[1]))
                redirect = manifest_data["redirect_url"]
                rejected = browser.get(redirect, params={"state": "wrong", "code": fixture_code})
                accepted = browser.get(redirect, params={"state": state, "code": fixture_code})
                outcomes.append((page.status_code, manifest_data, rejected.status_code, accepted.text))

        thread = Thread(target=exercise, daemon=True)
        threads.append(thread)
        thread.start()

    monkeypatch.setitem(wizard.__globals__, "convert_registration", convert)
    monkeypatch.setattr(wizard.__globals__["webbrowser"], "open", open_wizard)
    wizard(path, origin, callback)
    threads[0].join(timeout=5)
    code, manifest_data, rejected, done = outcomes[0]
    assert code == 200 and rejected == 400 and received == [fixture_code]
    assert manifest_data["callback_urls"] == [callback] and manifest_data["public"] is False
    assert manifest_data["hook_attributes"]["active"] is False
    assert manifest_data["default_permissions"] == {"contents": "read"}
    assert "https://github.com/apps/basira-fixture/installations/new" in done
    assert "test-app-config-value" not in done
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["callback_url"] == callback and saved["client_id"] == "Iv1.Fixture"
    assert Fernet(saved["credential_key"].encode())


def test_github_installations_require_selected_readonly_scope(monkeypatch):
    installations = [
        {"id": 1, "repository_selection": "selected", "permissions": {"contents": "read", "metadata": "read"}},
        {"id": 2, "repository_selection": "all", "permissions": {"contents": "read", "metadata": "read"}},
        {"id": 3, "repository_selection": "selected", "suspended_at": "2026-01-01T00:00:00Z",
         "permissions": {"contents": "read", "metadata": "read"}},
        {"id": 4, "repository_selection": "selected", "permissions": {"contents": "write", "metadata": "read"}},
        {"id": 5, "repository_selection": "selected", "permissions": {"contents": "read", "issues": "read"}},
    ]
    monkeypatch.setattr(personal_github, "pages", lambda *_args: iter(installations))
    assert list(personal_github.available_installations(None, None)) == [1]


class StaticResponse(BytesIO):
    status = 200

    def getheader(self, name, default=""):
        return "text/html" if name == "Content-Type" else default

    def getheaders(self):
        return [("Set-Cookie", "fixture-id=fixture-secret; HttpOnly; Secure"), ("X-Frame-Options", "DENY")]


def test_website_intake_exact_approval_and_passive_report(personal_clients, monkeypatch):
    owner, other = personal_clients
    monkeypatch.setenv("BASIRA_ALLOW_INLINE_ANALYSIS", "1")
    path, project_id = new_project(owner)
    _, unapproved_project = new_project(other)
    monkeypatch.setenv("BASIRA_APPROVED_WEBSITE_PAGES", json.dumps({project_id: [PAGE]}))
    requests = []

    class FixtureConnection:
        def request(self, method, path, headers):
            requests.append((method, path))
            assert "Cookie" not in headers

        def getresponse(self):
            return StaticResponse(b"<form></form><a href='/other'>Fixture personal data</a>")

    def capture(url):
        return intake_website.capture_response(FixtureConnection(), urlsplit(url), url, monotonic() + 3, "TLSv1.3")

    monkeypatch.setattr(intake_website, "capture", capture)
    body = {**SCOPE, "source": "website", "url": PAGE}
    headers = {"Idempotency-Key": "website-fixture-key"}
    assert other.post(f"{API}/projects/{unapproved_project}/intake", json=body, headers=headers).status_code == 422
    assert owner.post(path + "/intake", json={**body, "url": PAGE + "/outside"}, headers=headers).status_code == 422
    assert owner.post(path + "/intake", json={**body, "acknowledge_scope": False}, headers=headers).status_code == 422
    assert not requests
    scan = owner.post(path + "/intake", json=body, headers=headers)
    report, snapshot = reported(owner, path, project_id, scan)
    assert requests == [("GET", "/page")]
    assert snapshot["profile"]["forms"] == snapshot["profile"]["links_observed"] == 1
    assert snapshot["profile"]["tls_version"] == "TLSv1.3"
    assert "fixture-secret" not in json.dumps(report) and "personal data" not in json.dumps(report)


def test_website_rejects_nonpublic_dns_and_redirect(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_opts: [
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:127.0.0.1", 443, 0, 0)),
    ])
    with pytest.raises(InputError):
        intake_website.validated_address("example.test")

    class RedirectFixture:
        def request(self, method, path, headers):
            assert method == "GET" and path == "/page"

        def getresponse(self):
            return nullcontext(type("Redirect", (), {"status": 302, "getheader": lambda *_: "text/html"})())

    with pytest.raises(InputError):
        intake_website.capture_response(RedirectFixture(), urlsplit(PAGE), PAGE, monotonic() + 3, "TLSv1.3")


def test_website_capture_uses_pinned_socket_with_verified_tls(tmp_path, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    host = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "example.test")])
    clock = datetime.now(UTC)
    cert = (x509.CertificateBuilder().subject_name(host).issuer_name(host).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(clock - timedelta(minutes=5))
            .not_valid_after(clock + timedelta(minutes=5))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("example.test")]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    hits = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append((self.path, self.headers["Host"]))
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<form></form><a href='/other'>Sample</a>")

        def log_message(self, *args):
            pass

    server_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_tls.load_cert_chain(cert_path, key_path)
    client_tls = ssl.create_default_context(cafile=str(cert_path))
    connect = socket.create_connection
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        server.socket = server_tls.wrap_socket(server.socket, server_side=True)

        def fixture_dial(destination, timeout, source):
            assert destination == ("93.184.216.34", 443)
            return connect(server.server_address, timeout, source)

        monkeypatch.setattr(intake_website, "validated_address", lambda host: "93.184.216.34")
        monkeypatch.setattr(intake_website.socket, "create_connection", fixture_dial)
        monkeypatch.setattr(intake_website.ssl, "create_default_context", lambda: client_tls)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            _, profile = intake_website.capture(PAGE)
            assert profile["tls_version"] in {"TLSv1.2", "TLSv1.3"}
            with pytest.raises(InputError):
                intake_website.capture("https://mismatch.test/page")
            assert hits == [("/page", "example.test")]
        finally:
            server.shutdown()
            worker.join()


def test_website_capture_is_limited_to_three_approved_pages_on_same_origin(monkeypatch):
    paths = [PAGE, "https://other.test/outside", "https://example.test/docs",
             "https://example.test/about", "https://example.test/help"]
    monkeypatch.setenv("BASIRA_APPROVED_WEBSITE_PAGES", json.dumps({"project": paths}))
    calls = []

    def capture(url):
        calls.append(url)
        return json.dumps({"log": {"entries": [{"request": {"url": url}}]}}).encode(), {
            "page_sha256": sha256(url.encode()).hexdigest(), "tls_version": "TLSv1.3",
            "forms": 0, "links_observed": 0, "page_bytes": 32,
        }

    monkeypatch.setattr(intake_website, "capture", capture)
    monkeypatch.setattr(intake_website, "sleep", lambda seconds: None)
    raw, facts = intake_website.capture_scope(PAGE, "project")
    assert calls == [paths[0], paths[2], paths[3]]
    assert facts["pages"] == facts["requests"] == 3
    assert len(json.loads(raw)["log"]["entries"]) == 3
