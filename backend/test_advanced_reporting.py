import json

from . import platform_jobs as jobs
from .advanced_reporting import compare, sarif
from .contracts import Report
from .test_platform_runtime import artifact, platform, submit  # noqa: F401


def create(client, scope, source, key):
    response = submit(client, scope, artifact(content=source.encode()), key=key)
    assert response.status_code == 202, response.text
    scan = response.json()["id"]
    jobs.execute_scan(scope.org_id, scope.project_id, scan)
    return scan


def test_compare_comments_status_memory_sarif_and_project_scope(platform):
    owner, other, ctx = platform
    path = f"/api/platform/projects/{ctx.project_id}"
    reports = path + "/reports/"
    both = '<script src="http://old.example/app.js"></script><form action="https://example.test"></form>'
    fixed = '<script src="https://new.example/app.js"></script><form action="http://example.test"></form>'
    old_id = create(owner, ctx, both, "compare-1")
    new_id = create(owner, ctx, fixed, "compare-2")
    old, new = reports + old_id, reports + new_id
    response = owner.get(new + "/compare", params={"baseline": old_id}).json()
    assert response["comparable"]
    assert {item["rule"]: item["change"] for item in response["changes"]} == {
        "http-script": "resolved", "http-form": "new",
    }
    assert other.get(new + "/compare", params={"baseline": old_id}).status_code == 404
    current = owner.get(new + "/review").json()
    assert current["can_edit"]
    fingerprint = next(item["fingerprint"] for item in current["items"] if item["rule"] == "http-form")
    comment = {"fingerprint": fingerprint, "action": "comment", "body": "Review queued"}
    assert owner.post(new + "/review", json=comment).json()["comments"][0]["body"] == "Review queued"
    status = {"fingerprint": fingerprint, "action": "status", "status": "triaged", "reason": "Assigned to owner"}
    updated = owner.post(new + "/review", json=status).json()
    assert updated["status"] == "triaged"
    assert updated["history"][0]["previous"] == "open"
    assert owner.post(new + "/review", json=status).status_code == 409
    assert owner.post(old + "/review", json=comment).status_code == 404
    assert other.post(new + "/review", json=comment).status_code == 404
    other_id = other.get("/api/platform/auth/me").json()["id"]
    owner.post(f"/api/platform/organizations/{ctx.org_id}/members", json={"user_id": other_id, "role": "viewer"})
    owner.post(path + "/grants", json={"user_id": other_id})
    assert other.get(new + "/review").json()["can_edit"] is False
    assert other.post(new + "/review", json=comment).status_code == 403

    memory = owner.get(path + "/memory").json()
    assert any(row["fingerprint"] == fingerprint and row["status"] == "triaged" for row in memory["finding"])
    export = owner.get(new + "/download", params={"format": "sarif", "lang": "ar"})
    assert export.status_code == 200
    data = export.json()
    assert data["version"] == "2.1.0"
    first = data["runs"][0]["results"][0]
    assert first["ruleId"] == "http-form"
    assert first["locations"][0]["physicalLocation"] == {
        "artifactLocation": {"uri": "release.html"}, "region": {"startLine": 1},
    }
    assert "example.test" not in export.text
    assert ".sarif" in export.headers["content-disposition"]

    assert owner.put(path + "/policy", json={"allowed_kinds": ["html"]}).is_success
    changed = reports + create(owner, ctx, fixed, "compare-3")
    assert owner.get(changed + "/compare", params={"baseline": new_id}).json()["reason"] == "incompatible_policy"


def test_disappearing_file_or_rule_never_claims_a_fix(platform):
    client, _, ctx = platform
    source = '<script src="http://assets.example/main.js"></script>'
    first = create(client, ctx, source, "coverage-1")
    data = client.get(f"/api/platform/projects/{ctx.project_id}/reports/{first}").json()
    old = Report.model_validate(data)
    data.update(findings=[], input_paths=["different.html"])
    new = Report.model_validate(data)
    result = compare(new, old, {}, {})
    assert result["changes"][0]["change"] == "coverage_changed"
    data["coverage"][0].update(status="error", match_count=0)
    data["input_paths"] = ["release.html"]
    assert compare(Report.model_validate(data), old, {}, {})["changes"][0]["change"] == "coverage_changed"
    data["findings"] = old.model_dump(mode="json")["findings"]
    data["findings"][0]["path"] = "../outside.js"
    assert sarif(Report.model_validate(data), "en")["runs"][0]["results"] == []


def test_extended_lab_records_rules_tools_and_subtasks(platform):
    client, _, _ = platform
    catalog = client.get("/api/catalog").json()
    assert len(catalog["rules"]) == len({rule["id"] for rule in catalog["rules"]}) == 100
    assert all(rule["title_ar"] != rule["id"] for rule in catalog["rules"])
    response = client.post("/api/run", json={
        "profile": "extended", "source": '<form action="https://example.test"><input name="pw" type="password"></form>',
    })
    report = json.loads(response.text.splitlines()[-1])["report"]
    assert report["status"] == "completed"
    assert len(report["coverage"]) == 100
    assert "HTML-17" in {finding["rule"] for finding in report["findings"]}
    assert len(report["task_runs"]) == 14
    assert {task["agent"] for task in report["task_runs"]} == {
        "orchestrator", "planning", "analysis", "validation", "reporting",
    }
