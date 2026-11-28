import json
import os
from pathlib import Path
import time
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from . import main


class ApiTests(unittest.TestCase):
    def setUp(self):
        tmp = self.enterContext(TemporaryDirectory())
        self.db = Path(tmp) / "test.sqlite3"
        self.enterContext(patch.dict(os.environ, {"BASIRA_DB_PATH": str(self.db)}))
        self.client = self.enterContext(TestClient(main.app))
        self.key = "test-key-fictional"
        self.run = {"source": "<p>demo</p>"}

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

    def test_removed_user_routes_and_raw_credential_rejection(self):
        assert self.client.get("/checks").status_code == 404
        assert self.client.get("/checks/").status_code == 404
        assert len(self.client.get("/api/catalog").json()["rules"]) == 114
        removed = self.client.post("/api/models", json={"key": self.key})
        assert removed.status_code in {404, 405}
        rejected = self.client.post("/api/run", json={**self.run, "key": self.key, "model": "vendor/demo"})
        assert rejected.status_code == 422
        assert self.key not in removed.text + rejected.text
        assert rejected.headers["cache-control"] == "no-store"
        foreign = self.client.post("/api/run", json=self.run, headers={"Origin": "https://another.test"})
        assert foreign.status_code == 403

    def test_stream_persistence_downloads_and_isolation(self):
        calls = []
        async def graph(source, model, key, emit, previous=None):
            calls.append(previous)
            await emit({"node":"orchestrator","status":"start","parents":[],"detail":"Ready"})
            return {"summary_en":"One finding.", "summary_ar":"ملاحظة واحدة.",
                    "metrics":{"validatedCount":1,"modelCalls":5}, "findings":[{
                        "rule":"http-form","line":5,"evidence":"<form action='http://…'>","severity":"medium",
                        "title":"Form submits over HTTP","title_ar":"إرسال البيانات عبر HTTP",
                        "remediation":"Use HTTPS.","remediation_ar":"استخدم اتصالًا مشفرًا."}]}
        with patch.object(main, "run_graph", graph):
            first = self.client.post("/api/run", json=self.run)
            self.assertEqual(first.status_code, 200)
            self.assertIn("HttpOnly",first.headers["set-cookie"])
            events = [json.loads(line) for line in first.text.splitlines()]
            self.assertEqual([e["type"] for e in events],["step","complete"])
            report = events[-1]["report"]
            self.client.post("/api/run", json=self.run)
        self.assertEqual(calls, [None, None])
        self.assertNotIn(self.key.encode(), self.db.read_bytes())
        self.assertNotIn(self.run["source"].encode(), self.db.read_bytes())
        url = "/api/reports/" + report["id"]
        self.assertEqual(self.client.get(url).json(), report)
        self.assertEqual(len(self.client.get("/api/history").json()["reports"]), 2)
        for lang, text in [("en","Use HTTPS."), ("ar","استخدم اتصالًا مشفرًا.")]:
            file = self.client.get(url + "/download?lang=" + lang)
            self.assertIn("attachment", file.headers["content-disposition"])
            self.assertIn(text,file.text)
            self.assertIn("&lt;form",file.text)
        with TestClient(main.app) as other:
            self.assertEqual(other.get("/api/history").json(), {"reports":[]})
            self.assertEqual(other.get(url).status_code, 404)
            self.assertEqual(other.get(url + "/download").status_code, 404)

    def test_graph_failure_is_not_saved_or_reflected(self):
        with patch.object(main, "run_graph", side_effect=ValueError(self.key)):
            response = self.client.post("/api/run",json=self.run)
        self.assertEqual(json.loads(response.text)["type"], "error")
        self.assertNotIn(self.key, response.text)
        self.assertEqual(self.client.get("/api/history").json(), {"reports":[]})

    def test_local_source_contract_coverage_exports_and_isolation(self):
        source = '<script src="http://one.example/a.js"></script>\r\n' \
                 '<script src="http://two.example/b.js"></script>\r'
        filename = '<b>مصدر</b>.html'.replace("/", "")
        payload = {"source": source, "source_info": {"kind": "file", "name": filename, "lines": 1}}
        response = self.client.post("/api/run", json=payload)
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual(response.status_code, 200)
        report = events[-1]["report"]
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["enrichment"], "disabled")
        self.assertEqual(report["summary_source"], "system")
        self.assertEqual(report["model"], None)
        self.assertEqual(report["source"], {
            "kind": "file", "name": filename, "bytes": len(source.encode()), "lines": 3, "encoding": "utf-8",
        })
        self.assertEqual([f["line"] for f in report["findings"]], [1, 2])
        self.assertTrue(all(f["domain"] == "html" for f in report["findings"]))
        self.assertTrue(all(step["scan_id"] == report["id"] and step["occurred_at"] for step in events[:-1]))
        self.assertIn("not_applicable", [row["status"] for row in report["coverage"]])
        summary = self.client.get("/api/history").json()["reports"][0]
        self.assertEqual((summary["finding_count"], summary["unique_count"]), (2, 1))
        url = "/api/reports/" + report["id"]
        self.assertEqual(self.client.get(url).json(), report)
        exported = self.client.get(url + "/download?format=json")
        self.assertEqual(exported.json(), report)
        self.assertIn(".json", exported.headers["content-disposition"])
        for lang, direction in (("ar", "rtl"), ("en", "ltr")):
            page = self.client.get(url + f"/download?lang={lang}")
            self.assertIn(f'lang="{lang}" dir="{direction}"', page.text)
            self.assertIn("&lt;b&gt;مصدر", page.text)
            self.assertNotIn("one.example", page.text)
        with TestClient(main.app) as other:
            self.assertEqual(other.get(url + "/download?format=json").status_code, 404)
        self.assertNotIn("one.example".encode(), self.db.read_bytes())

    def test_invalid_source_inputs(self):
        for payload in [
            {"source": "<p>\x00</p>"},
            {"source": "<p>" + "x" * 250_000 + "</p>"},
            {"source": "<p>hello</p>", "source_info": {"kind": "file", "name": "../file.html"}},
            {"source": "<p>hello</p>", "source_info": {"kind": "file", "name": "file.exe"}},
            {"source": "<p>hello</p>", "model": "provider/example"},
        ]:
            with self.subTest(fields=list(payload)):
                response = self.client.post("/api/run", json=payload)
                self.assertEqual(response.status_code, 422)

    def test_legacy_report_keeps_id_and_marks_unavailable_metadata(self):
        self.client.get("/api/history")
        owner = main.owner_key(self.client.cookies.get(main.COOKIE))
        report_id = "a" * 32
        legacy = {"id": report_id, "created_at": "2026-11-18T12:00:00+00:00", "model": "test/legacy",
                  "findings": [], "summary_ar": "قديم", "summary_en": "Legacy", "metrics": {}}
        with main.database() as db:
            db.execute("INSERT INTO reports VALUES (?,?,?,?,?,?)",
                       (report_id, owner, legacy["created_at"], legacy["model"], 0, json.dumps(legacy)))
        url = "/api/reports/" + report_id
        result = self.client.get(url).json()
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["summary_en"], "Legacy")
        self.assertIsNone(result["source"])
        self.assertIsNone(result["coverage"])
        self.assertIsNone(result["enrichment"])
        self.assertIn("Unavailable", self.client.get(url + "/download").text)
        self.assertEqual(self.client.get("/api/history").json()["reports"][0]["id"], report_id)
        with main.database() as db:
            self.assertEqual(db.execute("SELECT id FROM report_index").fetchone()["id"], report_id)

    def test_openapi_describes_versioned_report_and_stream_events(self):
        schema = self.client.get("/openapi.json").json()
        content = schema["paths"]["/api/run"]["post"]["responses"]["200"]["content"]
        media = content["application/x-ndjson"]
        self.assertEqual(media["schema"], {"type": "string"})
        events = media["x-itemSchema"]
        self.assertNotIn("type", events)
        self.assertEqual(events["discriminator"]["propertyName"], "type")
        self.assertEqual(set(events["discriminator"]["mapping"]), {"step", "complete", "error"})
        detail = schema["paths"]["/api/reports/{report_id}"]["get"]["responses"]["200"]
        self.assertEqual(detail["content"]["application/json"]["schema"]["$ref"], "#/components/schemas/Report")


class SessionTableTests(unittest.TestCase):
    def setUp(self):
        tmp = self.enterContext(TemporaryDirectory())
        self.db = Path(tmp) / "sessions.sqlite3"
        self.enterContext(patch.dict(os.environ, {"BASIRA_DB_PATH": str(self.db)}))
        self.client = self.enterContext(TestClient(main.app))

    def rows(self):
        with main.database() as db:
            return db.execute("SELECT owner, expires_at FROM sessions").fetchall()

    def test_page_views_do_not_create_sessions(self):
        for _ in range(5):
            assert self.client.get("/", headers={"accept": "text/html"}).status_code == 200
        assert self.rows() == []

    def test_minting_a_session_removes_expired_rows(self):
        with main.database() as db:
            db.execute("INSERT INTO sessions(owner, expires_at) VALUES('expired', 1)")
            db.execute("INSERT INTO sessions(owner, expires_at) VALUES('live', ?)", (int(time.time()) + 600,))
        self.client.get("/api/history")
        owners = {row["owner"] for row in self.rows()}
        assert "expired" not in owners and "live" in owners
        assert len(owners) == 2
class PageHeaderTests(unittest.TestCase):
    def setUp(self):
        tmp = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"BASIRA_DB_PATH": str(Path(tmp) / "headers.sqlite3")}))
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
        response = main.page_headers(main.HTMLResponse("<p>report</p>", headers={
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"}))
        assert response.headers["content-security-policy"] == "default-src 'none'; style-src 'unsafe-inline'"
        assert "frame-ancestors" not in response.headers["content-security-policy"]
