import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
import httpx

from . import main


class ApiTests(unittest.TestCase):
    def setUp(self):
        tmp = self.enterContext(TemporaryDirectory())
        self.db = Path(tmp) / "test.sqlite3"
        self.enterContext(patch.dict(os.environ, {"MARSAD_DB_PATH": str(self.db)}))
        self.client = self.enterContext(TestClient(main.app))
        self.key = "test-key-fictional"
        self.models = [{"id": "vendor/demo", "free": True, "name": "Demo"}]
        self.run = {"key": self.key, "model": "vendor/demo", "source": "<p>demo</p>"}

    def test_live_catalog_protocol_and_prices(self):
        urls = []
        def router(request):
            urls.append(request.url.path)
            self.assertEqual(request.headers["authorization"], "Bearer " + self.key)
            if request.url.path.endswith("/key"):
                return httpx.Response(200, json={"data":{"limit_remaining":0}})
            prices = [{"prompt":"0","completion":"0"}, {"prompt":"0","completion":"0","request":"0.01"},
                      {"prompt":"0"}, {"prompt":"-1","completion":"-1"}, {"prompt":"0","completion":"0","internal_reasoning":"0.01"}]
            return httpx.Response(200, json={"data":[{"id":f"v/{i}", "pricing":p} for i,p in enumerate(prices)]})
        client_cls = httpx.AsyncClient
        with patch.object(main.httpx, "AsyncClient",
                          side_effect=lambda **kw: client_cls(**kw, transport=httpx.MockTransport(router))):
            result = self.client.post("/api/models", json={"key":self.key})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(urls, ["/api/v1/key", "/api/v1/models/user"])
        self.assertEqual([x["free"] for x in result.json()["models"]], [True,False,False,False,False])
        self.assertNotIn(self.key, result.text)

    def test_provider_auth_errors_do_not_reflect_key(self):
        client_cls = httpx.AsyncClient
        mock = httpx.MockTransport(lambda req: httpx.Response(401, text=self.key))
        with patch.object(main.httpx, "AsyncClient", side_effect=lambda **kw: client_cls(**kw, transport=mock)):
            res = self.client.post("/api/models", json={"key": self.key})
        self.assertEqual(res.status_code, 401)
        self.assertNotIn(self.key, res.text)
        self.assertEqual(res.headers["cache-control"], "no-store")

    def test_price_change_unavailable_model_and_invalid_inputs(self):
        with patch.object(main, "catalog", return_value=[{**self.models[0],"free":False}]):
            res = self.client.post("/api/run", json=self.run)
            self.assertEqual(res.status_code, 409)
            self.assertEqual(self.client.post("/api/run", json={**self.run, "model":"gone"}).status_code, 422)
        res = self.client.post("/api/run", json={"key": self.key})
        self.assertEqual(res.status_code, 422)
        self.assertNotIn(self.key, res.text)
        self.assertEqual(self.client.post("/api/run", json=self.run, headers={"Origin":"https://another.test"}).status_code,403)

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
        with patch.object(main, "catalog", return_value=self.models), patch.object(main, "run_graph", graph):
            first = self.client.post("/api/run", json=self.run)
            self.assertEqual(first.status_code, 200)
            self.assertIn("HttpOnly",first.headers["set-cookie"])
            events = [json.loads(line) for line in first.text.splitlines()]
            self.assertEqual([e["type"] for e in events],["step","complete"])
            report = events[-1]["report"]
            self.client.post("/api/run", json=self.run)
        self.assertEqual(calls,[None,{"findingsCount":1}])
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
        with patch.object(main,"catalog",return_value=self.models), patch.object(main,"run_graph",side_effect=ValueError(self.key)):
            response = self.client.post("/api/run",json=self.run)
        self.assertEqual(json.loads(response.text)["type"], "error")
        self.assertNotIn(self.key, response.text)
        self.assertEqual(self.client.get("/api/history").json(), {"reports":[]})

    def test_local_source_contract_coverage_exports_and_isolation(self):
        source = '<script src="http://one.example/a.js"></script>\r\n' \
                 '<script src="http://two.example/b.js"></script>\r'
        filename = '<b>مصدر</b>.html'.replace("/", "")
        payload = {"source": source, "source_info": {"kind": "file", "name": filename, "lines": 1}}
        with patch.object(main, "catalog") as catalog:
            response = self.client.post("/api/run", json=payload)
        catalog.assert_not_called()
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

    def test_invalid_source_inputs_and_provider_fallback(self):
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
        with patch.object(main, "catalog", side_effect=HTTPException(502, "Unavailable")):
            response = self.client.post("/api/run", json=self.run)
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual(events[-1]["report"]["enrichment"], "fallback")
        self.assertEqual(events[-1]["report"]["metrics"]["modelCalls"], 0)
        self.assertEqual(events[-1]["report"]["findings"], [])

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
