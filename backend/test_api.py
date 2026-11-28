from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from . import main


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = self.enterContext(TestClient(main.app))

    def test_unknown_browser_urls_open_the_app_not_a_blank_page(self):
        with TemporaryDirectory() as root:
            dist = Path(root) / "frontend" / "dist"
            dist.mkdir(parents=True)
            (dist / "index.html").write_text("<div id=root></div>")
            with patch.object(main, "ROOT", Path(root)):
                page = self.client.get("/no-such-page", headers={"accept": "text/html"})
                assert page.status_code == 404 and "id=root" in page.text
                assert self.client.get("/projects/abc", headers={"accept": "text/html"}).status_code == 200
                assert self.client.get("/projects/abc/reports/def", headers={"accept": "text/html"}).status_code == 200
                api = self.client.get("/api/no-such-route", headers={"accept": "text/html"})
                assert api.status_code == 404 and api.headers["content-type"].startswith("application/json")

    def test_the_anonymous_lab_and_its_report_store_are_gone(self):
        assert self.client.get("/checks").status_code == 404
        assert len(self.client.get("/api/catalog").json()["rules"]) == 114
        for method, path in (("post", "/api/run"), ("get", "/api/history"), ("get", "/api/reports/abc"),
                             ("get", "/api/reports/abc/download")):
            assert getattr(self.client, method)(path).status_code in {404, 405}, path
        assert self.client.post("/api/run", json={"source": "<p>x</p>"},
                                headers={"Origin": "https://another.test"}).status_code == 403
        paths = self.client.get("/openapi.json").json()["paths"]
        assert not [path for path in paths if path in {"/api/run", "/api/history"} or path.startswith("/api/reports")]
        assert not [path for path in paths if path.endswith("/claim")]


class PageHeaderTests(unittest.TestCase):
    def setUp(self):
        self.client = self.enterContext(TestClient(main.app))

    def shell(self, path):
        return self.client.get(path, headers={"accept": "text/html"})

    def test_app_shell_sets_the_full_content_security_policy(self):
        for path in ("/", "/dashboard", "/no-such-page"):
            page = self.shell(path)
            assert page.headers["content-security-policy"] == main.PAGE_POLICY, path
            assert "script-src 'self'" in main.PAGE_POLICY
            assert "object-src 'none'" in main.PAGE_POLICY
            assert "base-uri 'self'" in main.PAGE_POLICY
            assert page.headers["x-frame-options"] == "DENY"
            assert page.headers["referrer-policy"] == "no-referrer"
            assert page.headers["x-content-type-options"] == "nosniff"
            assert page.headers["cache-control"] == "no-store"

    def test_api_responses_keep_their_own_headers(self):
        response = self.client.get("/api/product")
        assert "content-security-policy" not in response.headers
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "no-store"

    def test_hashed_assets_are_cached_for_a_year(self):
        response = self.client.get("/assets/app-abc12345.js")
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"

    def test_report_html_keeps_its_own_policy(self):
        response = main.page_headers(HTMLResponse("<p>report</p>", headers={
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"}))
        assert response.headers["content-security-policy"] == "default-src 'none'; style-src 'unsafe-inline'"
        assert "frame-ancestors" not in response.headers["content-security-policy"]
