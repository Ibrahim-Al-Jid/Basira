import io
import json
from zipfile import ZipFile

from .test_platform_identity import invite_member
from .test_platform_runtime import platform  # noqa: F401
from .test_source_intake import artifact, finish


def test_links_require_same_asset_and_project_and_preserve_sources(platform):
    owner, other, ctx = platform
    root = f"/api/platform/projects/{ctx.project_id}"
    origin = "https://evidence.example.test"
    assert owner.put(root + "/policy", json={
        "base_url": origin, "allowed_kinds": ["repository", "openapi"],
    }).is_success
    snapshot = io.BytesIO()
    with ZipFile(snapshot, "w") as archive:
        archive.writestr("index.html", '<form action="http://example.test"></form>')
    zip_body = {**artifact("repository", "site.zip", snapshot.getvalue()), "scope_version": 1}
    document = json.dumps({
        "openapi": "3.0.4", "info": {"title": "Fixture", "version": "1"},
        "paths": {"/status": {"get": {"responses": {"200": {"description": "OK"}}}}},
    }).encode()
    api_body = {**artifact("openapi", "same-name.json", document), "scope_version": 1}
    code, code_origin = finish(owner, ctx, zip_body, "linked-source")
    web, web_origin = finish(owner, ctx, api_body, "linked-web")
    assert code_origin.json()["asset"]["id"] == web_origin.json()["asset"]["id"]
    code_id, web_id = code.json()["id"], web.json()["id"]
    code_path, web_path = root + "/reports/" + code_id, root + "/reports/" + web_id
    [candidate] = owner.get(code_path + "/link-candidates").json()["reports"]
    assert candidate.pop("created_at") <= web.json()["created_at"]
    assert candidate == {"id": web_id, "kind": "openapi", "name": "same-name.json"}

    assert owner.put(root + "/policy", json={
        "base_url": "https://different.example.test", "allowed_kinds": ["repository", "openapi"],
    }).is_success
    different, _ = finish(owner, ctx, {**api_body, "scope_version": 2}, "different-asset")
    assert owner.post(code_path + "/links", json={"report_id": different.json()["id"]}).status_code == 409
    assert other.get(code_path + "/links").status_code == 404
    invite_member(owner, other, ctx.org_id, "viewer")
    recipient = other.get("/api/platform/auth/me").json()["id"]
    assert owner.post(root + "/grants", json={"user_id": recipient}).is_success
    assert other.post(code_path + "/links", json={"report_id": web_id}).status_code == 403
    linked = owner.post(code_path + "/links", json={"report_id": web_id}).json()
    assert len(linked["links"]) == 1
    link = linked["links"][0]
    assert link["report_id"] == web_id and link["finding_count"] == 1
    reverse = owner.post(web_path + "/links", json={"report_id": code_id}).json()["links"]
    assert len(reverse) == 1 and reverse[0]["id"] == link["id"]
    assert other.get(code_path + "/links").json() == {**linked, "can_link": False}
    assert owner.get(code_path).json() == code.json() and owner.get(web_path).json() == web.json()
    assert owner.delete(web_path + "/links/" + link["id"]).status_code == 204
    assert owner.get(code_path + "/links").json()["links"] == []
