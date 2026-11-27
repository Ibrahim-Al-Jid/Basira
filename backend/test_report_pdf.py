"""Verify PDF uses the same ownership and locale contract as other report formats."""
import json

from fastapi.testclient import TestClient

from . import main, platform_jobs
from .test_platform_runtime import platform, submit  # noqa: F401


def check_pdf(response, lang):
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"] == f'attachment; filename="basira-report-{lang}.pdf"'
    assert response.content.startswith(b"%PDF-")
    assert response.content.rstrip().endswith(b"%%EOF")


def test_project_pdf_follows_report_ownership(platform):
    owner, stranger, ctx = platform
    submission = submit(owner, ctx)
    assert submission.status_code == 202
    report_id = submission.json()["id"]
    platform_jobs.execute_scan(ctx.org_id, ctx.project_id, report_id)
    download = f"/api/platform/projects/{ctx.project_id}/reports/{report_id}/download?format=pdf"
    for lang in ("ar", "en"):
        check_pdf(owner.get(download + "&lang=" + lang), lang)
    assert stranger.get(download).status_code == 404


def test_anonymous_pdf_requires_the_owning_session(tmp_path, monkeypatch):
    monkeypatch.setenv("BASIRA_DB_PATH", str(tmp_path / "reports.sqlite3"))
    with TestClient(main.app) as owner, TestClient(main.app) as stranger:
        response = owner.post("/api/run", json={"source": '<form action="http://example.test/">Sample</form>'})
        assert response.status_code == 200
        completed = json.loads(response.text.splitlines()[-1])
        assert completed["type"] == "complete"
        report_id = completed["report"]["id"]
        path = f"/api/reports/{report_id}/download?format=pdf&lang=ar"
        check_pdf(owner.get(path), "ar")
        assert stranger.get(path).status_code == 404
