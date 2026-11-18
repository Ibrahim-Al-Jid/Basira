"""Exercise the real SDK, graph, HTTP routes and storage with offline provider HTTP."""
import json

import httpx
import httpx2
from fastapi.testclient import TestClient

from backend.graph import SAMPLE
from backend.main import app
from backend.test_graph import FakeModel


def test_review_with_openrouter_wire_protocol(monkeypatch, tmp_path):
    monkeypatch.setenv("MARSAD_DB_PATH", str(tmp_path / "review.db"))
    model_id = "test/sample:free"
    provider = FakeModel()
    received = []

    async def transport(self, req):
        assert req.url.host == "openrouter.ai"
        assert req.headers["Authorization"] == "Bearer test-wire-token"
        received.append(req.url.path)
        if req.url.path.endswith("/key"):
            body = {"data": {"label": "test"}}
        elif req.url.path.endswith("/models/user"):
            body = {"data": [{"id": model_id, "pricing": {"prompt": "0", "completion": "0"}}]}
        else:
            assert req.url.path == "/api/v1/chat/completions"
            payload = json.loads(req.content)
            assert payload["model"] == model_id
            messages = [(message["role"], message["content"]) for message in payload["messages"]]
            reply = await provider.ainvoke(messages)
            body = {"id": "test", "model": model_id, "object": "chat.completion", "created": 1,
                    "choices": [{"index": 0, "finish_reason": "stop",
                                 "message": {"role": "assistant", "content": reply.content}}]}
        response_type = httpx2.Response if isinstance(req, httpx2.Request) else httpx.Response
        return response_type(200, json=body)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", transport)
    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", transport)
    with TestClient(app) as session:
        res = session.post("/api/run", json={"source": SAMPLE, "model": model_id, "key": "test-wire-token"})
        events = [json.loads(line) for line in res.text.splitlines()]
        assert res.is_success and events[-1]["type"] == "complete", events[-1]
        report = events[-1]["report"]
        assert report["metrics"]["benchmark"]["passed"]
        assert received.count("/api/v1/chat/completions") == report["metrics"]["modelCalls"] == 6
        for lang in ("ar", "en"):
            download = session.get(f'/api/reports/{report["id"]}/download', params={"lang": lang})
            assert download.is_success
            assert report["summary_" + lang] in download.text
            assert all(finding["rule"] in download.text for finding in report["findings"])
