from .platform_runtime import agent_activity


def step(role, status, second):
    return {"role": role, "status": status, "occurred_at": f"2026-11-27T10:00:0{second}+00:00"}


def test_agent_activity_reports_duration_and_tools_per_finished_stage():
    result = {
        "steps": [step("planning", "start", 1), step("planning", "done", 2), step("analysis", "start", 2)],
        "task_runs": [{"agent": "planning", "tool": "rule-registry"}, {"agent": "planning", "tool": "rule-registry"}],
    }
    assert agent_activity(result) == [("planning", "planning|1000|rule-registry")]


def test_agent_activity_without_steps_is_empty():
    assert agent_activity({}) == []


def test_worker_reports_each_agent_start_in_order():
    import base64
    from .offline_worker import scan_payload
    seen = []
    html = b'<script src="http://assets.test/main.js"></script>'
    payload = {"kind": "html", "name": "a.html", "content": base64.b64encode(html).decode(), "policy": {}}
    result = scan_payload(payload, progress=seen.append)
    assert "result" in result
    assert seen == ["orchestrator", "planning", "analysis", "validation", "reporting"]
