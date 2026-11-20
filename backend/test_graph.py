import asyncio
import json
from types import SimpleNamespace
import unittest

from backend.graph import GraphError, SAMPLE, run_graph


class FakeModel:
    def __init__(self, layout="split", *, fail=False, detect=True, incomplete=False, summary=None):
        self.layout = layout
        self.fail = fail
        self.detect = detect
        self.incomplete = incomplete
        self.summary = summary
        self.calls = []
        self.active = 0
        self.max_active = 0

    async def ainvoke(self, messages):
        role = messages[0][1].split()[3]
        data = json.loads(messages[1][1])
        self.calls.append((role, data))
        if self.fail:
            raise RuntimeError("private error body")
        if role == "orchestrator":
            answer = {"layout": self.layout}
        elif role == "planning":
            answer = {"groups": data["groups"]}
        elif role == "analysis":
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.008)
            self.active -= 1
            rules = set()
            for p in data["profiles"]:
                if p["explicit_http"]:
                    rules.add("http-script" if p["group"] == "scripts" else "http-form")
                if p["group"] == "scripts" and p["recognized_cdn"] and not p["integrity_present"]:
                    rules.add("cdn-integrity")
            answer = {"rules": sorted(rules) if self.detect else []}
        elif role == "validation":
            confirmed = sorted(set(data["nominated"]) & data["local_matches"].keys())
            answer = {"confirmed": confirmed[:-1] if self.incomplete else confirmed}
        elif role == "reporting":
            if self.summary is not None:
                return SimpleNamespace(content=self.summary)
            answer = {"priority": [item["rule"] for item in data["findings"]]}
        else:
            raise AssertionError(role)
        return SimpleNamespace(content=json.dumps(answer))


class GraphTests(unittest.IsolatedAsyncioTestCase):
    async def review(self, source=SAMPLE, **options):
        model = FakeModel(**options)
        events = []

        async def emit(event):
            events.append(event)

        result = await run_graph(source, "example/model:free", "private-key", emit,
                                 {"findingsCount": 2, "source": "secret_memory"}, _llm=model)
        return result, events, model

    async def test_sample_parallel_join_and_one_call_per_task(self):
        result, events, model = await self.review()
        self.assertEqual(result["metrics"]["modelCalls"], 6)
        self.assertEqual(result["enrichment"], "model")
        self.assertEqual(result["summary_source"], "model")
        self.assertTrue(all(item["status"] == "matched" for item in result["coverage"]))
        self.assertEqual(model.max_active, 2)
        self.assertEqual(result["metrics"]["benchmark"], dict(expected=3, matched=3, unexpected=0, passed=True))
        validation = next(i for i, e in enumerate(events) if e["node"] == "validation")
        finished = {e["node"] for e in events[:validation] if e["status"] == "done"}
        self.assertEqual(events[validation]["parents"], ["analysis:scripts", "analysis:forms"])
        self.assertTrue(set(events[validation]["parents"]) <= finished)
        self.assertEqual([e["node"] for e in events if e["status"] == "done"].count("validation"), 1)
        self.assertEqual(next(e["source"] for e in events if e["node"] == "validation" and e["status"] == "done"), "system")
        self.assertEqual(model.calls[0][1]["memory"], {"prior_findings_count": 2})
        self.assertIn("summary_ar", result)
        self.assertIn("summary_en", result)

    async def test_model_can_route_but_cannot_suppress_local_evidence(self):
        result, events, _ = await self.review(layout="combined", detect=False, incomplete=True)
        self.assertIn("analysis:document", [e["node"] for e in events])
        self.assertEqual(result["metrics"]["modelCalls"], 5)
        self.assertTrue(result["metrics"]["benchmark"]["passed"])
        self.assertEqual(len(result["findings"]), 3)
        self.assertEqual(result["enrichment"], "fallback")
        self.assertEqual(next(e["source"] for e in events if e["node"] == "analysis:document" and e["status"] == "done"), "system")

    async def test_does_not_forward_raw_source_or_store_unsafe_evidence(self):
        source = '<form action="http://example.test/?token=secret_input" title="private note">'
        result, _, model = await self.review(source)
        for value in ["secret_input", "example.test", "private note", "secret_memory", "private-key"]:
            self.assertNotIn(value, repr(model.calls))
            self.assertNotIn(value, repr(result))
        self.assertEqual(result["findings"][0]["line"], 1)
        self.assertIsNone(result["metrics"]["benchmark"])

    async def test_ignores_inert_content_and_processes_empty_scope(self):
        result, events, _ = await self.review('<textarea><form action="http://test"></textarea>')
        self.assertEqual(result["findings"], [])
        self.assertTrue(all(item["status"] == "not_applicable" for item in result["coverage"]))
        self.assertTrue(any(e["node"] == "analysis:document" for e in events))

    async def test_provider_failure_and_no_provider_keep_same_evidence(self):
        failed, events, model = await self.review(fail=True)
        local = await run_graph(SAMPLE, None, None, self.ignore_event)
        self.assertEqual(failed["findings"], local["findings"])
        self.assertEqual(failed["coverage"], local["coverage"])
        self.assertEqual(failed["summary_en"], local["summary_en"])
        self.assertEqual(failed["summary_ar"], local["summary_ar"])
        self.assertTrue(failed["metrics"]["benchmark"]["passed"])
        self.assertEqual(failed["enrichment"], "fallback")
        self.assertEqual(failed["summary_source"], "system")
        self.assertEqual(failed["metrics"]["modelCalls"], len(model.calls))
        self.assertNotIn("private error body", repr(events))
        self.assertEqual(local["enrichment"], "disabled")
        self.assertEqual(local["metrics"]["modelCalls"], 0)

    async def test_clean_and_out_of_scope_checks_are_distinct(self):
        source = '<script src="https://example.test/main.js"></script><form action="/signup"></form>'
        result = await run_graph(source, None, None, self.ignore_event)
        self.assertEqual(result["findings"], [])
        actual = {item["rule"]: item["status"] for item in result["coverage"]}
        self.assertEqual(actual, {"http-script": "clear", "http-form": "clear", "cdn-integrity": "not_applicable"})
        self.assertEqual(result["metrics"]["checksRun"], 2)

    async def test_invalid_priorities_cannot_override_report_facts(self):
        for summary in ("not JSON", json.dumps({"summary_en": "No issues; private-key", "summary_ar": "مراجعة"}),
                        json.dumps({"priority": ["unknown"]})):
            with self.subTest(summary=summary):
                result, _, _ = await self.review(summary=summary)
                self.assertEqual(result["enrichment"], "fallback")
                self.assertEqual(result["summary_source"], "system")
                self.assertTrue(result["metrics"]["benchmark"]["passed"])
                self.assertNotIn("private-key", repr(result))
                self.assertIn("3 issue types at 3 matching locations", result["summary_en"])

    async def test_invalid_model_route_falls_back_and_invalid_input_is_rejected(self):
        result, _, _ = await self.review(layout="invalid")
        self.assertEqual(result["enrichment"], "fallback")
        with self.assertRaisesRegex(GraphError, "HTML element"):
            await self.review("https://example.test")

    async def ignore_event(self, _event):
        pass
