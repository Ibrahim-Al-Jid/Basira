import pytest

from .analysis_mode import ModeUnavailable, resolve_mode


def test_flag_model_and_repository_input_are_all_needed_for_the_agent_path(monkeypatch):
    monkeypatch.setenv("BASIRA_AGENT_LOOP", "1")
    assert resolve_mode("agents", has_model=True) == {
        "analysis_mode": "agents", "mode_effective": "agents", "fallback_reason": None}
    assert resolve_mode(None, has_model=True)["mode_effective"] == "hybrid"
    for options in ({"has_model": False}, {"has_model": True, "kind": "html"}):
        assert resolve_mode("hybrid", **options) == {
            "analysis_mode": "hybrid", "mode_effective": "rules", "fallback_reason": "agent_path_unavailable"}
        with pytest.raises(ModeUnavailable):
            resolve_mode("agents", **options)
    assert resolve_mode("rules", has_model=True)["mode_effective"] == "rules"


def test_flag_off_means_rules_and_agents_is_refused(monkeypatch):
    monkeypatch.delenv("BASIRA_AGENT_LOOP", raising=False)
    assert resolve_mode("hybrid", has_model=True)["fallback_reason"] == "agent_path_unavailable"
    with pytest.raises(ModeUnavailable):
        resolve_mode("agents", has_model=True)
    assert resolve_mode("rules")["fallback_reason"] is None
