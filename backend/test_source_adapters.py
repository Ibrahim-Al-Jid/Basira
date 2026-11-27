"""Defensive adapter fixtures and malformed-tool-output regression coverage."""
import base64
import json
import os
from pathlib import Path
import runpy
import subprocess
from dataclasses import replace
from zipfile import ZipFile

import pytest

from . import source_adapters as adapters
from .artifact_review import RULESET_VERSION, catalog
from .contracts import Report
from .offline_worker import scan_payload
from .scan_contracts import analyzer_plan


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
    monkeypatch.setenv("BASIRA_SOURCE_ADAPTERS", "gitleaks")

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
    assert len(catalog()["rules"]) == 114
    assert len(data["findings"]) == 2
    merged = next(item for item in data["findings"] if item["rule"] == "APP-02")
    assert {item["tool"] for item in merged["origins"]} == {"deployment-config", "gitleaks"}
    assert (merged["path"], merged["line"]) == ("app/demo.py", 1)
    assert {item["rule"]: item["match_count"] for item in data["coverage"] if item["match_count"]} == {
        "APP-02": 1, adapters.GITLEAKS_RULE: 1,
    }
    assert data["metrics"]["findingsCount"] == data["metrics"]["validatedCount"] == 2
    report = projected_report(data)
    for value in (SYNTHETIC_GITHUB, SYNTHETIC_STRIPE):
        assert value not in report.model_dump_json()


def test_osv_aliases_merge_and_partial_input_retains_results(monkeypatch, tmp_path):
    monkeypatch.setenv("BASIRA_SOURCE_ADAPTERS", "osv-scanner")
    monkeypatch.setenv("BASIRA_OSV_DB_DIRECTORY", str(tmp_path))
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
    monkeypatch.setenv("BASIRA_SOURCE_ADAPTERS", "gitleaks")
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
    monkeypatch.setenv("BASIRA_SOURCE_ADAPTERS", "osv-scanner")
    monkeypatch.setenv("BASIRA_OSV_DB_DIRECTORY", str(tmp_path))
    report = scan(POSITIVE)
    [osv] = [run for run in report["task_runs"] if run["tool"] == "osv-scanner"]
    assert report["status"] == "partial" and osv["reason"] == "database_unavailable"


@pytest.mark.parametrize("lockfile_version", [2, 3])
def test_osv_npm_scans_sanitized_lockfile_and_preserves_evidence_line(monkeypatch, tmp_path, lockfile_version):
    monkeypatch.setenv("BASIRA_SOURCE_ADAPTERS", "osv-scanner")
    monkeypatch.setenv("BASIRA_OSV_DB_DIRECTORY", str(tmp_path))
    build_index = runpy.run_path(str(Path(__file__).parent.parent / "ops/index-npm-advisories.py"))["build_index"]
    with ZipFile(tmp_path / "official-fixture.zip", "w") as archive:
        for identifier, names in {
            "GHSA-FIXT-URES-0001": ("@demo/example", "related"),
            "GHSA-FIXT-URES-0002": ("unrelated",),
            "GHSA-FIXT-URES-0003": ("@demo/example",),
        }.items():
            archive.writestr(identifier + ".json", json.dumps({
                "id": identifier, "affected": [{"package": {"ecosystem": "npm", "name": name},
                                                 "versions": ["1.2.3", "9.9.9"]} for name in names],
            }))
    build_index(tmp_path / "official-fixture.zip", tmp_path / "npm-advisories.sqlite3")
    (tmp_path / "npm-database-date").write_text("2026-11-22", encoding="ascii")
    lock = json.dumps({
        "lockfileVersion": lockfile_version,
        "packages": {
            "": {"name": "separate-root", "version": "1.0.0"},
            "node_modules/@demo/example": {
                "version": "1.2.3", "resolved": "https://registry.npmjs.org/@demo/example/-/example-1.2.3.tgz",
                "install": "discard this field", "integrity": "discard this too",
            },
            "node_modules/example/node_modules/@demo/example": {"version": "1.2.3"},
            "node_modules/local": {"link": True, "resolved": "../other"},
            "node_modules/internal": {"version": "2.0.0", "resolved": "https://example.invalid/internal.tgz"},
        },
        "dependencies": {"legacy": {"version": "0.0.0"}},
    }, indent=2)
    expected_line = next(index for index, line in enumerate(lock.splitlines(), 1)
                         if '"node_modules/@demo/example":' in line)

    def cli(tool, args, _directory, _report, **options):
        assert tool is adapters.OSV and "--offline" in args and "--no-resolve" in args
        path = Path(args[args.index("--lockfile") + 1])
        clean = json.loads(path.read_text(encoding="ascii"))
        assert clean == {"lockfileVersion": 3, "packages": {"node_modules/@demo/example": {"version": "1.2.3"}}}
        with ZipFile(Path(options["env"]["OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY"]) / "osv-scalibr/npm/all.zip") as archive:
            assert archive.namelist() == ["GHSA-FIXT-URES-0001.json", "GHSA-FIXT-URES-0003.json"]
            assert "9.9.9" in archive.read("GHSA-FIXT-URES-0001.json").decode()
        return {"results": [{"source": {"path": str(path)}, "packages": [{
            "package": {"ecosystem": "npm", "name": "@demo/example", "version": "1.2.3"},
            "vulnerabilities": [{"id": "GHSA-FIXT-URES-0001"}],
        }]}]}, 1

    monkeypatch.setattr(adapters, "run_cli", cli)
    report = projected_report(scan({"frontend/package-lock.json": lock}))
    [finding] = report.findings
    assert (finding.path, finding.line) == ("frontend/package-lock.json", expected_line)
    assert finding.advisory.ecosystem == "npm" and finding.advisory.database_date.isoformat() == "2026-11-22"
    assert report.status == "partial"
    monkeypatch.setattr(adapters, "MAX_NPM_ADVISORIES", 1)
    overflow = adapters.review_source(adapters.OSV, {"frontend/package-lock.json": lock})
    assert (overflow.status, overflow.reason, overflow.observations) == ("error", "adapter_output_limit", [])


def test_duplicate_npm_json_keys_remain_partial_and_never_run_cli(monkeypatch):
    monkeypatch.setattr(adapters, "run_cli", lambda *_args, **_kwargs: pytest.fail("Invalid lockfile reached OSV"))
    lock = '{"lockfileVersion":3,"packages":{"node_modules/example":{"version":"1.0.0","version":"2.0.0"}}}'
    assert adapters.review_source(adapters.OSV, {"package-lock.json": lock}).reason == "unsupported_dependency_pin"


def test_missing_npm_database_retains_pypi_results(monkeypatch, tmp_path):
    monkeypatch.setenv("BASIRA_OSV_DB_DIRECTORY", str(tmp_path))
    cache = tmp_path / "osv-scalibr" / "PyPI" / "all.zip"
    cache.parent.mkdir(parents=True)
    cache.touch()
    (tmp_path / "database-date").write_text("2026-11-21", encoding="ascii")

    def cli(_tool, args, _directory, _report, **_options):
        assert args.count("--lockfile") == 1
        path = Path(args[args.index("--lockfile") + 1])
        assert path.name == "requirements.txt"
        return {"results": [{"source": {"path": str(path)}, "packages": [{
            "package": {"ecosystem": "PyPI", "name": "demo", "version": "1.0.0"},
            "vulnerabilities": [{"id": "GHSA-FIXT-URES-0002"}],
        }]}]}, 1

    monkeypatch.setattr(adapters, "run_cli", cli)
    result = adapters.review_source(adapters.OSV, {
        "requirements.txt": "demo==1.0.0\n",
        "package-lock.json": '{"lockfileVersion":3,"packages":{"node_modules/demo":{"version":"1.0.0"}}}',
    })
    assert (result.status, result.reason) == ("error", "database_unavailable")
    assert result.observations[0]["advisory"]["ecosystem"] == "PyPI"


def test_adapter_broker_rejects_equal_copies_and_excess_runtime(tmp_path):
    copied = replace(adapters.GITLEAKS)
    assert adapters.review_source(copied, {}).reason == "adapter_not_registered"
    with pytest.raises(adapters.AdapterError, match="adapter_not_registered"):
        adapters.run_cli(copied, [], tmp_path, tmp_path / "report.json", timeout=1, success={0})
    with pytest.raises(adapters.AdapterError, match="adapter_budget_exceeded"):
        adapters.run_cli(adapters.GITLEAKS, [], tmp_path, tmp_path / "report.json", timeout=9, success={0})


def test_adapter_broker_refuses_installed_unpinned_version(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "TOOLS_DIR", tmp_path)
    executable = tmp_path / "gitleaks"
    executable.touch()

    def preflight(command, **options):
        assert command == [str(executable), "--version"]
        assert options["timeout"] <= 3
        return subprocess.CompletedProcess(command, 0, stdout=b"gitleaks version 8.30.1-rc1\n")

    monkeypatch.setattr(adapters.subprocess, "run", preflight)
    report = tmp_path / "gitleaks.json"
    with pytest.raises(adapters.AdapterError, match="adapter_version_mismatch"):
        adapters.run_cli(adapters.GITLEAKS, adapters.gitleaks_command(tmp_path, report), tmp_path, report,
                         timeout=8, success={0, 42})


def test_adapter_broker_rejects_unreviewed_flags_and_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters.subprocess, "run", lambda *_a, **_k: pytest.fail("Unapproved command reached process runner"))
    report = tmp_path / "osv.json"
    lock = str(tmp_path / "package-lock.json")
    offline = adapters.osv_command(tmp_path, report, [lock])
    assert adapters.approved_cli(adapters.OSV, offline, tmp_path, report)
    cases = [
        (adapters.OSV, [flag for flag in offline if flag != "--offline"], report, None),
        (adapters.OSV, [*offline, "--download-offline-databases"], report, None),
        (adapters.OSV, adapters.osv_command(tmp_path, report, [str(tmp_path.parent / "package-lock.json")]), report, None),
        (adapters.OSV, offline, report, {"HTTPS_PROXY": "http://example.invalid"}),
    ]
    leaks_report = tmp_path / "gitleaks.json"
    redacted = adapters.gitleaks_command(tmp_path, leaks_report)
    cases.append((adapters.GITLEAKS, [arg for arg in redacted if arg != "--redact=100"], leaks_report, None))
    for tool, argv, output, env in cases:
        with pytest.raises(adapters.AdapterError, match="adapter_execution_denied"):
            adapters.run_cli(tool, argv, tmp_path, output, timeout=1, success={0}, env=env)


@pytest.mark.skipif(os.environ.get("BASIRA_REAL_ADAPTERS") != "1", reason="requires pinned tools and a read-only OSV snapshot")
def test_actual_tools_offline_against_fixed_positive_and_negative(monkeypatch):
    monkeypatch.setenv("BASIRA_SOURCE_ADAPTERS", "gitleaks,osv-scanner")
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
