"""Defensive adapter fixtures and malformed-tool-output regression coverage."""
import base64
import json
import os
from pathlib import Path
import subprocess

import pytest

from . import source_adapters as adapters
from .artifact_review import RULESET_VERSION, catalog
from .contracts import Report
from .offline_worker import scan_payload
from .phase9_contracts import analyzer_plan


SYNTHETIC_GITHUB = "gh" "p_" + "A1b2C3d4E5F6G7h8i9JkLmNoPqRstUvW0123"
SYNTHETIC_STRIPE = "sk" "_test_" + "A1b2C3d4E5F6G7h8i9JkLmNo"
POSITIVE = {
    ".gitleaks.toml": "[[allowlists]]\npaths = ['.*']\n",
    "app/demo.py": f'token = "{SYNTHETIC_GITHUB}"  # gitleaks:allow\n'
                   f'stripe_key = "{SYNTHETIC_STRIPE}"\n',
    "pinned/requirements.txt": "# Source snapshot\nJinja2==3.1.4\n",
}
NEGATIVE = {"app/demo.py": 'token = "use-a-secret-provider"\n', "pinned/requirements.txt": "packaging==26.2\n"}
NEW_RULES = {adapters.GITLEAKS_RULE, adapters.PYPI_RULE}


def scan(files, *, external=True):
    raw = json.dumps({"files": files}).encode()
    result = scan_payload({
        "kind": "config", "name": "snapshot.json", "content": base64.b64encode(raw).decode(),
        "policy": {"_analysis_plan": analyzer_plan("config"), "_ruleset_version": RULESET_VERSION},
    }, external=external)
    assert "result" in result, result
    return result["result"]


def projected_report(data):
    return Report.model_validate({
        **data, "id": "source-fixture", "created_at": "2026-11-21T00:00:00Z", "model": None,
        "schema_version": 2, "input_artifact": {"kind": "config", "name": "snapshot.json", "bytes": 100},
    })


def test_gitleaks_fixture_merges_builtin_observation_and_keeps_provenance(monkeypatch):
    monkeypatch.setenv("MARSAD_SOURCE_ADAPTERS", "gitleaks")

    def cli(tool, args, directory, report, **options):
        assert tool is adapters.GITLEAKS
        assert "--ignore-gitleaks-allow" in args
        assert "--redact=100" in args
        assert options["timeout"] <= 8
        path = next((directory / "snapshot").rglob("demo.py"))
        match = {"File": str(path), "StartLine": 1, "RuleID": "github-pat", "Secret": SYNTHETIC_GITHUB}
        return [match, match, {**match, "RuleID": "stripe-access-token", "StartLine": 2, "Secret": SYNTHETIC_STRIPE}], 42

    monkeypatch.setattr(adapters, "run_cli", cli)
    data = scan(POSITIVE)
    assert len(catalog()["rules"]) == 100
    assert len(data["findings"]) == 2
    merged = next(item for item in data["findings"] if item["rule"] == "APP-02")
    assert {item["tool"] for item in merged["origins"]} == {"deployment-config", "gitleaks"}
    assert (merged["path"], merged["line"]) == ("app/demo.py", 1)
    assert {item["rule"]: item["match_count"] for item in data["coverage"] if item["match_count"]} == {
        "APP-02": 1, adapters.GITLEAKS_RULE: 1,
    }
    assert data["metrics"]["findingsCount"] == data["metrics"]["validatedCount"] == 2
    from .advanced_reporting import sarif
    report = projected_report(data)
    payload = sarif(report, "en")
    assert {point["ruleId"] for point in payload["runs"][0]["results"]} == {"APP-02", adapters.GITLEAKS_RULE}
    assert all(point["partialFingerprints"] for point in payload["runs"][0]["results"])
    for value in (SYNTHETIC_GITHUB, SYNTHETIC_STRIPE):
        assert value not in report.model_dump_json()
        assert value not in json.dumps(payload)


def test_osv_aliases_merge_and_partial_input_retains_results(monkeypatch, tmp_path):
    monkeypatch.setenv("MARSAD_SOURCE_ADAPTERS", "osv-scanner")
    monkeypatch.setenv("MARSAD_OSV_DB_DIRECTORY", str(tmp_path))
    cache = tmp_path / "osv-scalibr" / "PyPI" / "all.zip"
    cache.parent.mkdir(parents=True)
    cache.touch()
    (tmp_path / "database-date").write_text("2026-11-21", encoding="ascii")

    def cli(tool, args, directory, report, **options):
        assert tool is adapters.OSV and "--offline" in args and "--no-resolve" in args
        path = Path(args[args.index("--lockfile") + 1])
        assert set(path.read_text().splitlines()) == {"jinja2==3.1.4"}
        return {"results": [{"source": {"path": str(path)}, "packages": [{
            "package": {"ecosystem": "PyPI", "name": "jinja2", "version": "3.1.4"},
            "vulnerabilities": [{"id": "CVE-2024-56326", "aliases": ["GHSA-TEST-ALIA-S001"]},
                                {"id": "GHSA-TEST-ALIA-S001", "aliases": ["PYSEC-2024-22"]}],
        }]}]}, 1

    monkeypatch.setattr(adapters, "run_cli", cli)
    data = scan({"requirements.txt": "# lock\nJinja2==3.1.4\nJinja2==3.1.4\n-r ../outside.txt\n"})
    assert data["status"] == "partial"
    [advisory] = data["findings"]
    assert (advisory["path"], advisory["line"]) == ("requirements.txt", 2)
    assert advisory["advisory"] == {"id": "CVE-2024-56326", "aliases": ["GHSA-TEST-ALIA-S001", "PYSEC-2024-22"],
                                    "ecosystem": "PyPI", "package": "Jinja2", "version": "3.1.4",
                                    "database_date": "2026-11-21"}
    [coverage] = [item for item in data["coverage"] if item["rule"] == adapters.PYPI_RULE]
    assert (coverage["status"], coverage["match_count"], coverage["reason"]) == ("error", 1, "unsupported_dependency_pin")


@pytest.mark.parametrize("failure,reason", [
    (subprocess.TimeoutExpired(["tool"], 1), "adapter_timeout"),
    (adapters.AdapterError("adapter_output_limit"), "adapter_output_limit"),
    (ValueError("private exception content"), "adapter_invalid_output"),
])
def test_adapter_failure_keeps_local_findings(monkeypatch, failure, reason):
    monkeypatch.setenv("MARSAD_SOURCE_ADAPTERS", "gitleaks")
    def cli(*args, **kwargs):
        raise failure
    monkeypatch.setattr(adapters, "run_cli", cli)
    report = scan(POSITIVE)
    assert report["status"] == "partial" and report["findings"][0]["rule"] == "APP-02"
    [failed] = [run for run in report["task_runs"] if run["tool"] == "gitleaks"]
    assert failed["status"] == "error" and failed["reason"] == reason
    no_external = scan(POSITIVE, external=False)
    assert no_external["status"] == "partial"
    assert all("private exception" not in json.dumps(row) for row in report["task_runs"])


def test_unavailable_osv_database_is_partial(monkeypatch, tmp_path):
    monkeypatch.setenv("MARSAD_SOURCE_ADAPTERS", "osv-scanner")
    monkeypatch.setenv("MARSAD_OSV_DB_DIRECTORY", str(tmp_path))
    report = scan(POSITIVE)
    [osv] = [run for run in report["task_runs"] if run["tool"] == "osv-scanner"]
    assert report["status"] == "partial" and osv["reason"] == "database_unavailable"


@pytest.mark.skipif(os.environ.get("MARSAD_REAL_ADAPTERS") != "1", reason="requires pinned tools and a read-only OSV snapshot")
def test_actual_tools_offline_against_fixed_positive_and_negative(monkeypatch):
    monkeypatch.setenv("MARSAD_SOURCE_ADAPTERS", "gitleaks,osv-scanner")
    positive = scan(POSITIVE)
    assert positive["status"] == "completed", [run for run in positive["task_runs"] if run["tool"] in {
        "gitleaks", "osv-scanner",
    }]
    actual = {item["rule"]: item for item in positive["findings"]}
    assert {"APP-02", adapters.GITLEAKS_RULE, adapters.PYPI_RULE} <= actual.keys()
    assert {item["tool"] for item in actual["APP-02"]["origins"]} == {"deployment-config", "gitleaks"}
    assert (actual[adapters.GITLEAKS_RULE]["path"], actual[adapters.GITLEAKS_RULE]["line"]) == ("app/demo.py", 2)
    assert any("CVE-2024-56326" in [item["advisory"]["id"], *item["advisory"]["aliases"]]
               and (item["path"], item["line"]) == ("pinned/requirements.txt", 2)
               for item in positive["findings"] if item["rule"] == adapters.PYPI_RULE)
    negative = scan(NEGATIVE)
    assert negative["status"] == "completed", [run for run in negative["task_runs"] if run["tool"] in {
        "gitleaks", "osv-scanner",
    }]
    assert not (NEW_RULES & {item["rule"] for item in negative["findings"]})
