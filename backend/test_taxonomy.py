from fastapi.testclient import TestClient

from . import taxonomy
from .artifact_review import catalog
from .main import app


def test_every_catalog_rule_maps_to_exactly_one_subdomain():
    ids = {rule["id"] for rule in catalog()["rules"]}
    index = taxonomy.rule_index()
    assert set(index) == ids and len(ids) == 114
    assert all(len(places) == 1 for places in index.values())


def test_taxonomy_ids_are_unique_and_references_resolve():
    seen = set()
    for domain, sub in taxonomy.subdomains():
        assert sub["id"] not in seen and sub["id"].startswith(domain["id"] + ".")
        seen.add(sub["id"])
        assert sub["cwe"] and sub["modes"] and sub["problems"] is not None
        assert set(sub["modes"]) <= {"artifact", "capture", "active", "manual"}
        assert all(code in taxonomy.OWASP_2025 for code in sub["owasp_2025"])
        assert all(code in taxonomy.OWASP_API_2023 for code in sub["owasp_api_2023"])
        assert all(code in taxonomy.WSTG for code in sub["wstg"])
        assert all(isinstance(number, int) for number in sub["cwe"])


def test_rule_backed_subdomains_are_observable_without_live_probing():
    for _, sub in taxonomy.subdomains():
        if sub["rules"]:
            assert set(sub["modes"]) & {"artifact", "capture"}, sub["id"]


def test_taxonomy_endpoint_reports_gaps_honestly():
    body = TestClient(app).get("/api/taxonomy").json()
    assert body["summary"]["subdomains_gap"] > 0
    assert body["summary"]["subdomains"] == sum(len(d["subdomains"]) for d in body["domains"])
