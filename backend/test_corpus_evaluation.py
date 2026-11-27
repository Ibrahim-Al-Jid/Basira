"""Exercise the benchmark contract with local process and provider simulation."""
import pytest

from .corpus_evaluation import MANIFEST, evaluate, load_manifest


def test_manifest_pin_rejects_changed_annotation(tmp_path):
    manifest = tmp_path / MANIFEST.name
    manifest.write_text(MANIFEST.read_text(encoding="utf-8").replace("support-readonly", "edited"),
                        encoding="utf-8")
    manifest.with_suffix(".sha256").write_text(MANIFEST.with_suffix(".sha256").read_text(encoding="ascii"),
                                                encoding="ascii")
    with pytest.raises(ValueError, match="registered SHA-256"):
        load_manifest(manifest)


def test_model_fixture_runner_preserves_static_evidence_and_reports_limits():
    result = evaluate(MANIFEST, "mocked", 1)
    modes = result["modes"]
    assert all(row["statuses"] == {"completed": 11, "rejected": 1} for row in modes.values())
    assert modes["baseline"]["tp"] < modes["static_adapters"]["tp"]
    for static, enriched in zip(modes["static_adapters"]["cases"], modes["fixture_enrichment"]["cases"], strict=True):
        assert static.get("findings_sha256") == enriched.get("findings_sha256")
    assert result["gates"]["evidence_parity"]
    assert result["gates"]["request_budget"]
    assert result["gates"]["static_quality"]
    assert not result["automatic_enrichment_approved"]
    assert result["constraints"]["external_provider_cost_usd"] is None
    assert result["constraints"]["external_provider_requests"] == 0
    fallback = result["fallback"]
    assert fallback["timeout"]["reported_model_calls"] is None
    assert fallback["revoked"]["requests"] == 0
    assert fallback["malformed"]["requests"] == 1
