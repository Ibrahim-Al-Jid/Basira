"""Exercise the offline Demo HTTP routes, graph, and report storage."""
import json

import httpx
from fastapi.testclient import TestClient

from backend.graph import SAMPLE
from backend.main import app


def test_review_with_offline_demo_protocol(monkeypatch, tmp_path):
    monkeypatch.setenv("MARSAD_DB_PATH", str(tmp_path / "review.db"))

    async def deny_egress(self, request):
        raise AssertionError(f"Unexpected Demo request to {request.url.host}")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", deny_egress)
    with TestClient(app) as session:
        res = session.post("/api/run", json={"source": SAMPLE})
        events = [json.loads(line) for line in res.text.splitlines()]
        assert res.is_success and events[-1]["type"] == "complete", events[-1]
        report = events[-1]["report"]
        assert report["metrics"]["benchmark"]["passed"]
        assert report["metrics"]["modelCalls"] == 0
        assert report["enrichment"] == "disabled"
        for lang in ("ar", "en"):
            download = session.get(f'/api/reports/{report["id"]}/download', params={"lang": lang})
            assert download.is_success
            assert report["summary_" + lang] in download.text
            assert all(finding["rule"] in download.text for finding in report["findings"])
