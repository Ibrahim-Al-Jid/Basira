import asyncio
import json
from types import SimpleNamespace
import unittest

from backend.graph import GraphError, SAMPLE, run_graph


class FakeModel:
    def __init__(self, layout="split", *, fail=False, detect=True):
        self.layout = layout
        self.fail = fail
        self.detect = detect
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
            answer = {"confirmed": sorted(set(data["nominated"]) & data["local_matches"].keys())}
        elif role == "reporting":
            answer = {"summary_en": "Review completed.", "summary_ar": "اكتملت المراجعة."}
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
        self.assertEqual(model.max_active, 2)
        self.assertEqual(result["metrics"]["benchmark"], dict(expected=3, matched=3, unexpected=0, passed=True))
        validation = next(i for i, e in enumerate(events) if e["node"] == "validation")
        finished = {e["node"] for e in events[:validation] if e["status"] == "done"}
        self.assertEqual(events[validation]["parents"], ["analysis:scripts", "analysis:forms"])
        self.assertTrue(set(events[validation]["parents"]) <= finished)
        self.assertEqual([e["node"] for e in events if e["status"] == "done"].count("validation"), 1)
        self.assertEqual(model.calls[0][1]["memory"], {"prior_findings_count": 2})
        self.assertIn("summary_ar", result)
        self.assertIn("summary_en", result)

    async def test_model_decisions_change_route_and_report(self):
        result, events, _ = await self.review(layout="combined", detect=False)
        self.assertIn("analysis:document", [e["node"] for e in events])
        self.assertEqual(result["metrics"]["modelCalls"], 5)
        self.assertFalse(result["metrics"]["benchmark"]["passed"])
        self.assertEqual(result["findings"], [])

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
        self.assertTrue(any(e["node"] == "analysis:document" for e in events))

    async def test_model_and_input_failures(self):
        with self.assertRaisesRegex(GraphError, "OpenRouter call failed in orchestrator"):
            await self.review(fail=True)
        with self.assertRaisesRegex(GraphError, "unsupported route"):
            await self.review(layout="invalid")
        with self.assertRaisesRegex(GraphError, "HTML element"):
            await self.review("https://example.test")
