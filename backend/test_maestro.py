import json

import pytest

from .hunter_loop import FLAG, Budget
from .maestro import (HUNTER_MIN_STEPS, ORDER, TOKEN_CEILING, Ledger, default_plan, hunter_budget, parse_plan,
                      plan_run)

MAP = {"digest": "a" * 64, "languages": {"python": 3}, "entry_points": ["app.py"], "routes": []}


@pytest.fixture(autouse=True)
def flag(monkeypatch):
    monkeypatch.setenv(FLAG, "1")


def reply(payload, **extra):
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return {"content": content, "usage": {"input": 10, "output": 5}, **extra}


def model_of(answer, seen=None):
    def model(messages, tools):
        if seen is not None:
            seen.append((messages, tools))
        if isinstance(answer, Exception):
            raise answer
        return answer
    return model


def test_default_plan_is_the_full_pipeline_with_todays_hunter_budget():
    plan = default_plan("hybrid")
    assert plan.stages == ORDER and plan.hunter_steps == Budget().max_steps
    assert default_plan("agents").token_ceiling == TOKEN_CEILING["agents"] > TOKEN_CEILING["hybrid"]


def test_flag_off_never_calls_the_model_and_returns_the_default(monkeypatch):
    monkeypatch.delenv(FLAG)
    result = plan_run(model_of(AssertionError("model called")), "hybrid", MAP, 3)
    assert (result.status, result.plan, result.steps) == ("disabled", default_plan("hybrid"), 0)


def test_the_model_can_narrow_the_plan():
    seen = []
    answer = reply({"stages": ["hunter", "auditor"], "hunter_steps": 3})
    result = plan_run(model_of(answer, seen), "hybrid", MAP, 3)
    assert result.status == "ok" and result.plan.stages == ("hunter", "auditor") and result.plan.hunter_steps == 3
    assert (result.steps, result.tokens_in, result.tokens_out) == (1, 10, 5)
    messages, tools = seen[0]
    assert tools == [] and '"files": 3' in messages[1]["content"] and "app.py" not in messages[1]["content"]


@pytest.mark.parametrize("bad", [
    "not json", "[]", {"stages": ["hunter", "auditor"]}, {"hunter_steps": 3},
    {"stages": ["scout", "hunter", "auditor", "scribe", "shell"], "hunter_steps": 3},
    {"stages": ["hunter", "scribe"], "hunter_steps": 3},
    {"stages": ["auditor", "hunter"], "hunter_steps": 3},
    {"stages": ["scout", "hunter", "hunter", "auditor"], "hunter_steps": 3},
    {"stages": ["hunter", "auditor"], "hunter_steps": 9},
    {"stages": ["hunter", "auditor"], "hunter_steps": HUNTER_MIN_STEPS - 1},
    {"stages": ["hunter", "auditor"], "hunter_steps": True},
    {"stages": ["hunter", "auditor"], "hunter_steps": "3"},
    {"stages": ["hunter", "auditor"], "hunter_steps": 3, "tools": ["network"]},
    {"stages": ["hunter", "auditor"], "hunter_steps": 3, "token_ceiling": 10**9},
    {"stages": [1, 2], "hunter_steps": 3},
])
def test_an_answer_that_widens_or_breaks_the_plan_gives_the_default(bad):
    result = plan_run(model_of(reply(bad)), "agents", MAP, 3)
    assert (result.status, result.plan) == ("invalid_output", default_plan("agents"))


def test_a_tool_call_is_invalid():
    answer = reply({"stages": ["hunter", "auditor"], "hunter_steps": 3}, tool_calls=[{"name": "x", "arguments": {}}])
    assert plan_run(model_of(answer), "hybrid", MAP, 3).status == "invalid_output"


def test_failures_and_budgets_keep_the_default_and_a_fixed_status():
    default = default_plan("hybrid")
    for answer, status in ((RuntimeError("secret"), "model_error"), ({"content": "{}"}, "model_error")):
        result = plan_run(model_of(answer), "hybrid", MAP, 3)
        assert (result.status, result.plan) == (status, default)
    good = reply({"stages": ["hunter", "auditor"], "hunter_steps": 3})
    assert plan_run(model_of(good), "hybrid", MAP, 3, budget_tokens=10).status == "budget_tokens"
    ticks = iter([0.0, 99.0])
    late = plan_run(model_of(good), "hybrid", MAP, 3, budget_seconds=1, clock=lambda: next(ticks))
    assert (late.status, late.plan) == ("budget_time", default)


def test_parse_plan_accepts_the_default_itself():
    plan = parse_plan(json.dumps({"stages": list(ORDER), "hunter_steps": Budget().max_steps}), "hybrid")
    assert plan == default_plan("hybrid")


def test_ledger_tracks_spend_and_bounds_the_hunter():
    ledger = Ledger(100)
    ledger.charge(30, 20)
    ledger.charge(-5, "7")
    assert (ledger.spent, ledger.remaining, ledger.exhausted) == (57, 43, False)
    plan = default_plan("hybrid")
    assert hunter_budget(plan, ledger).max_tokens == 43 and hunter_budget(plan).max_tokens == Budget().max_tokens
    ledger.charge(100, 0)
    assert ledger.exhausted and ledger.remaining == 0 and hunter_budget(plan, ledger).max_tokens == 0
    narrowed = parse_plan(json.dumps({"stages": ["hunter", "auditor"], "hunter_steps": 2}), "hybrid")
    assert hunter_budget(narrowed).max_steps == 2
