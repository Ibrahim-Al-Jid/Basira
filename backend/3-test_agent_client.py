import json

import httpx
import pytest

from backend import agent_client
from backend.hunter_loop import hunt

IDENTITY = {"connection": "openrouter-default", "model": "m/free", "org_id": "a" * 32, "project_id": "b" * 32,
            "scan_id": "c" * 32, "lease": "d" * 32, "generation": "e" * 32}
FILES = {"app.py": "import os\nos.system(input())\n"}
MAP = {"digest": "x"}


def scripted(answers, sent):
    def post(url, json=None, **kwargs):
        sent.append((url, json, kwargs))
        return httpx.Response(200, json=answers.pop(0), request=httpx.Request("POST", url))
    return post


def answer(text):
    return {"content": text, "usage": {"input": 10, "output": 5}}


def test_loop_runs_through_the_gateway_and_never_sends_a_key(monkeypatch):
    monkeypatch.setenv("BASIRA_AGENT_LOOP", "1")
    sent = []
    post = scripted([
        answer(json.dumps({"tool_calls": [{"name": "search_code", "arguments": {"path": "app.py", "pattern": "system"}}]})),
        answer(json.dumps({"candidates": [{"path": "app.py", "line": 2, "quote": "os.system(input())"}]})),
    ], sent)
    model = agent_client.gateway_model("http://gw", {"Authorization": "Bearer t"}, IDENTITY, post=post)
    result = hunt(model, FILES, MAP, mode="agents")
    assert result.status == "ok" and result.steps == 2 and result.tokens_in == 20
    assert [item[0] for item in sent] == ["http://gw/chat"] * 2
    assert all(item[1]["scan_id"] == IDENTITY["scan_id"] and "key" not in json.dumps(item[1]).lower() for item in sent)
    roles = [m["role"] for m in sent[1][1]["messages"]]
    assert "tool" not in roles and roles[0] == "system"
    assert "search_code" in sent[0][1]["messages"][0]["content"] and "run_rules" not in sent[0][1]["messages"][0]["content"]


def test_gateway_refusal_ends_the_loop_with_model_error(monkeypatch):
    monkeypatch.setenv("BASIRA_AGENT_LOOP", "1")
    def post(url, **kwargs):
        return httpx.Response(409, json={"detail": "x"}, request=httpx.Request("POST", url))
    model = agent_client.gateway_model("http://gw", {}, IDENTITY, post=post)
    assert hunt(model, FILES, MAP, mode="agents").status == "model_error"


@pytest.mark.parametrize("body", [{"content": 5, "usage": {"input": 1, "output": 1}}, {"content": "{}"}, {}])
def test_malformed_gateway_answers_are_model_errors(monkeypatch, body):
    monkeypatch.setenv("BASIRA_AGENT_LOOP", "1")
    model = agent_client.gateway_model("http://gw", {}, IDENTITY, post=scripted([body], []))
    assert hunt(model, FILES, MAP, mode="agents").status == "model_error"
