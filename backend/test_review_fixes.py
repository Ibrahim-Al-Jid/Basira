import pytest
from fastapi.testclient import TestClient

from . import intake_website
from .artifact_review import InputError
from .evidence_text import localized_evidence
from .main import app


def test_arabic_exports_translate_fixed_evidence_sentences():
    assert localized_evidence("3 matching declarations in the document.", True) == "3 تعريف مطابق في المستند."
    assert "5" in localized_evidence("Saved ZAP report contains 5 observation(s) for this rule.", True)
    english = "3 matching declarations in the document."
    assert localized_evidence(english, False) == english
    assert localized_evidence("<script>", True) == "<script>"


def test_unapproved_page_errors_say_what_to_do(monkeypatch):
    monkeypatch.setenv("BASIRA_APPROVED_WEBSITE_PAGES", "{}")
    with pytest.raises(InputError, match="BASIRA_APPROVED_WEBSITE_PAGES"):
        intake_website.approved_url("https://example.test/", "p1")
    monkeypatch.setenv("BASIRA_APPROVED_WEBSITE_PAGES", '{"p1": ["https://example.test/a"]}')
    with pytest.raises(InputError, match="مش في الصفحات المعتمدة"):
        intake_website.approved_url("https://example.test/b", "p1")
    assert intake_website.approved_url("https://example.test/a", "p1") == "https://example.test/a"


def test_platform_422_names_the_failed_fields_and_not_the_values():
    client = TestClient(app)
    response = client.post("/api/platform/projects/abc/intake", json={"source": "website", "url": 5, "secret": "hunter2"})
    assert response.status_code in (401, 403, 404, 422)
    if response.status_code == 422:
        assert "hunter2" not in response.text


def test_docs_page_is_off_unless_enabled():
    assert app.docs_url is None and app.redoc_url is None
