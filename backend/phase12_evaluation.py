"""Compare the fixed defensive acceptance corpus using offline scanner and provider modes."""
import argparse
import base64
from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
import platform
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx

from . import model_gateway as gateway
from . import source_adapters as adapters
from .artifact_review import RULESET_VERSION, catalog
from .offline_worker import scan_payload
from .phase6_evaluation import percentile
from .phase9_contracts import analyzer_plan

MANIFEST = Path("tests/fixtures/phase12/manifest.json")
FIXTURE_GATEWAY = "https://fixture-gateway.invalid/priority"
CONNECTION = {"model": "fixture/ordering", "generation": "operator"}
IDS = dict(org_id="a" * 32, project_id="b" * 32, scan_id="c" * 32, lease="d" * 32)
SEVERITIES = {"high": 0, "medium": 1, "low": 2}
OSV_DATABASE_SHA256 = "fc59fe15b782dd1ed7db71464d4a70268dac9ee3ab595da28875ad5756896834"
EXPECTED_REJECTION = "ملف JSON غير صالح."


def canon(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def load_manifest(path):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    digest = sha256(canon(manifest).encode("ascii")).hexdigest()
    if digest != path.with_suffix(".sha256").read_text(encoding="ascii").strip():
        raise ValueError("Acceptance manifest does not match the registered SHA-256")
    versions = {tool.id: tool.version for tool in adapters.SOURCE_TOOLS}
    if manifest["ruleset"] != RULESET_VERSION or manifest["tool_versions"] != versions:
        raise ValueError("Registered evaluator pins do not match this code")
    return manifest, digest


def artifact_payload(case, *, external):
    artifact = case["artifact"]
    raw = (artifact if isinstance(artifact, str) else canon(artifact)).encode("utf-8")
    plan = analyzer_plan(case["kind"])
    if not external:
        source_ids = {tool.id for tool in adapters.SOURCE_TOOLS}
        plan = [row for row in plan if row["id"] not in source_ids]
    return {"kind": case["kind"], "name": case["name"],
            "content": base64.b64encode(raw).decode("ascii"),
            "policy": {**case.get("policy", {}), "_analysis_plan": plan, "_ruleset_version": RULESET_VERSION}}


def simulate_adapters(tool, _args, directory, _report, **_options):
    """Use recorded-shape transport fixtures without running the packaged binaries."""
    if tool == adapters.GITLEAKS:
        rows = [{"File": str(path), "StartLine": index, "RuleID": "generic-api-key"}
                for path in (directory / "snapshot").rglob("settings.py")
                for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                if "api_key = " in line]
        return rows, 42 if rows else 0
    rows = []
    for path in directory.rglob("requirements.txt"):
        pins = []
        for line in path.read_text(encoding="utf-8").splitlines():
            name, version = line.split("==")
            records = [{"id": "CVE-2024-56326", "aliases": ["GHSA-q2x7-8rv6-6q7h"]}] if name.casefold() == "jinja2" else []
            pins.append({"package": {"ecosystem": "PyPI", "name": name, "version": version}, "vulnerabilities": records})
        rows.append({"source": {"path": str(path)}, "packages": pins})
    return {"results": rows}, 1 if any(item["vulnerabilities"] for row in rows for item in row["packages"]) else 0


def engine_setup(stack, profile, manifest):
    stack.enter_context(patch.dict(os.environ, {"MARSAD_SOURCE_ADAPTERS": "gitleaks,osv-scanner"}))
    if profile == "mocked":
        path = Path(stack.enter_context(TemporaryDirectory()))
        archive = path / "osv-scalibr/PyPI/all.zip"
        archive.parent.mkdir(parents=True)
        archive.touch()
        (path / "database-date").write_text(manifest["osv_database_date"], encoding="ascii")
        stack.enter_context(patch.dict(os.environ, {"MARSAD_OSV_DB_DIRECTORY": str(path)}))
        stack.enter_context(patch.object(adapters, "run_cli", side_effect=simulate_adapters))
    else:
        if not all((adapters.TOOLS_DIR / tool.id).is_file() for tool in adapters.SOURCE_TOOLS):
            raise ValueError("Bundled mode requires the packaged scanner binaries")
        cache, date = adapters.database()
        if date.isoformat() != manifest["osv_database_date"]:
            raise ValueError("OSV cache date does not match the registered corpus")
        with (cache / "osv-scalibr/PyPI/all.zip").open("rb") as database:
            if file_digest(database, "sha256").hexdigest() != OSV_DATABASE_SHA256:
                raise ValueError("OSV archive does not match the pinned scanner bundle")
        for tool in adapters.SOURCE_TOOLS:
            found = subprocess.run([str(adapters.TOOLS_DIR / tool.id), "--version"], check=True, timeout=5,
                                   capture_output=True, text=True)
            if tool.version not in found.stdout + found.stderr:
                raise ValueError(f"Packaged binary version mismatch: {tool.id}")


def evidence(report):
    return sorted(canon(item) for item in report["findings"])


def digest_findings(report):
    return sha256(canon(evidence(report)).encode("ascii")).hexdigest()


def locations(report):
    return {(item["rule"], item.get("path"), item["line"]) for item in report["findings"]}


def scan(case, external):
    start = perf_counter()
    result = scan_payload(artifact_payload(case, external=external), external=external)
    return result, (perf_counter() - start) * 1000


def fixture_enrichment(report, behavior="valid"):
    report = deepcopy(report)
    report["findings"].sort(key=lambda item: (SEVERITIES[item["severity"]], item["rule"]))
    requests = []

    def intercept(url, *, json, **options):
        if url == FIXTURE_GATEWAY:
            if behavior == "timeout":
                raise httpx.ReadTimeout("Synthetic time-out")
            reply = client.post("/priority", json=json, headers=options["headers"])
            return httpx.Response(reply.status_code, request=httpx.Request("POST", url), content=reply.content)
        if url != gateway.PROVIDER_URL + "/chat/completions":
            raise AssertionError("Unexpected evaluator transport")
        req = httpx.Request("POST", url)
        requests.append(json)
        return provider_response(json, behavior, req)

    with TestClient(gateway.app) as client, ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {"MARSAD_GATEWAY_TOKEN": "phase12-fixture-only"}))
        stack.enter_context(patch.object(gateway, "gateway_config", return_value=(
            FIXTURE_GATEWAY.removesuffix("/priority"), {"Authorization": "Bearer phase12-fixture-only"},
        )))
        stack.enter_context(patch.object(gateway, "operator_enabled", return_value=CONNECTION["model"]))
        stack.enter_context(patch.object(gateway, "start_model_call", return_value=None if behavior == "revoked" else (b"",)))
        stack.enter_context(patch.object(gateway, "openrouter_secret", return_value="fixture-only"))
        stack.enter_context(patch.object(gateway.httpx, "post", side_effect=intercept))
        start = perf_counter()
        gateway.enrich(report, CONNECTION, **IDS)
        elapsed = (perf_counter() - start) * 1000
    return report, elapsed, len(requests)


def provider_response(request, behavior, http_request):
    assert set(request) == {"model", "max_tokens", "provider", "messages"}
    messages = request["messages"]
    assert [message["role"] for message in messages] == ["system", "user"]
    counts = json.loads(messages[1]["content"])
    assert counts and set(counts) <= gateway.IDS and all(type(v) is int and v > 0 for v in counts.values())
    order = sorted(counts) if behavior == "valid" else ["FIXTURE-UNSUPPORTED"]
    return httpx.Response(200, request=http_request, json={
        "choices": [{"message": {"content": canon({"priority": order})}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    })


def score(report, case, *, external):
    observed = locations(report)
    expected = {tuple(row) for row in case["expected"]}
    relevant = expected if external else expected & {row for row in expected if row[0] in gateway.IDS}
    advisory_ids = {value for item in report["findings"] if item.get("advisory")
                    for value in [item["advisory"]["id"], *item["advisory"]["aliases"]]}
    missing_advisories = sorted(set(case.get("expected_advisories", ())) - advisory_ids) if external else []
    metrics = {"tp": len(expected & observed), "fp": len(observed - expected), "fn": len(expected - observed),
               "in_scope_fn": len(relevant - observed), "full_duplicates": len(evidence(report)) - len(set(evidence(report)))}
    return {"score": metrics, "missing": sorted(expected - observed), "unexpected": sorted(observed - expected),
            "missing_advisories": missing_advisories,
            "coverage": dict(Counter(row["status"] for row in report["coverage"])),
            "findings_sha256": digest_findings(report)}


def summarize(rows, durations):
    counts = Counter()
    statuses = Counter()
    for row in rows:
        counts.update(row.get("score", {}))
        statuses[row["status"]] += 1
    tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
    return {**counts, "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None, "statuses": dict(statuses),
            "latency_ms": {"samples": len(durations), "p50": percentile(durations, .50),
                           "p95": percentile(durations, .95)}}


def evaluate(manifest_path, profile, repetitions):
    manifest, digest = load_manifest(manifest_path)
    cases = manifest["cases"]
    rows = {"baseline": [], "static_adapters": [], "fixture_enrichment": []}
    durations = {mode: [] for mode in rows}
    priorities = Counter()
    usage = Counter()
    parity = True
    models_per_scan = 0
    fallback_probe = None
    failures = 0
    with ExitStack() as stack:
        engine_setup(stack, profile, manifest)
        for case in cases:
            for mode in ("baseline", "static_adapters"):
                external = mode == "static_adapters"
                same = set()
                for _ in range(repetitions):
                    payload, elapsed = scan(case, external)
                    report = payload.get("result")
                    durations[mode].append(elapsed)
                    same.add(digest_findings(report) if report else payload.get("error"))
                status = report["status"] if report else "rejected" if same == {EXPECTED_REJECTION} else "failed"
                failures += int(len(same) != 1 or (status == "rejected") != case.get("expect_rejection", False)
                                or status in {"partial", "failed"})
                rows[mode].append({"case": case["id"], "status": status,
                                   **(score(report, case, external=external) if report else {})})
            if report is None:
                rows["fixture_enrichment"].append({"case": case["id"], "status": status})
                continue
            original = evidence(report)
            coverage = report["coverage"]
            reference = case.get("priority_rule")
            if reference:
                priorities["labelled_cases"] += 1
                if report["findings"]:
                    priorities["deterministic_hit"] += min(
                        report["findings"], key=lambda item: (SEVERITIES[item["severity"]], item["rule"])
                    )["rule"] == reference
            for _ in range(repetitions):
                candidate, elapsed, requests = fixture_enrichment(report)
                durations["fixture_enrichment"].append(elapsed)
                models_per_scan = max(models_per_scan, requests)
                usage.update({field: candidate["metrics"][field]
                              for field in ("inputTokens", "outputTokens", "modelCalls")
                              if candidate["metrics"].get(field) is not None})
                usage["fixture_provider_requests"] += requests
                parity &= evidence(candidate) == original and candidate["coverage"] == coverage
            eligible = any(item["rule"] in gateway.IDS for item in report["findings"])
            failures += int((candidate["enrichment"] == "model") != eligible)
            if reference and candidate["findings"]:
                priorities["fixture_hit"] += candidate["findings"][0]["rule"] == reference
            if eligible and fallback_probe is None:
                fallback_probe = report
            rows["fixture_enrichment"].append({"case": case["id"], "status": status,
                "enrichment": candidate["enrichment"], "provider_eligible": eligible,
                **score(candidate, case, external=True)})
        fallback = {}
        for behavior in ("timeout", "malformed", "revoked"):
            report, elapsed, requests = fixture_enrichment(fallback_probe, behavior)
            preserved = evidence(report) == evidence(fallback_probe) and report["coverage"] == fallback_probe["coverage"]
            fallback[behavior] = {"preserved_evidence": preserved, "fallback": report["enrichment"] == "fallback",
                                  "latency_ms": round(elapsed, 3), "requests": requests,
                                  "reported_model_calls": report["metrics"].get("modelCalls")}
    summary = {mode: {**summarize(items, durations[mode]), "cases": items} for mode, items in rows.items()}
    threshold = manifest["thresholds"]
    denominator = priorities["labelled_cases"]
    gain = (priorities["fixture_hit"] - priorities["deterministic_hit"]) / denominator if denominator else None
    gate = {
        "expected_runs": failures <= threshold["maximum_failures"],
        "evidence_parity": parity and all(probe["preserved_evidence"] and probe["fallback"] for probe in fallback.values()),
        "latency": all(summary[mode]["latency_ms"]["p95"] <= threshold[key] for mode, key in (
            ("baseline", "baseline_p95_ms"), ("static_adapters", "static_adapters_p95_ms"),
            ("fixture_enrichment", "fixture_enrichment_overhead_p95_ms"),
        )),
        "static_quality": all((summary["static_adapters"][metric] or 0) >= threshold["minimum_" + metric]
                              for metric in ("precision", "recall"))
            and not any(row.get("missing_advisories") for row in rows["static_adapters"]),
        "duplicates": all(mode.get("full_duplicates", 0) <= threshold["maximum_duplicate_findings"]
                          for mode in summary.values()),
        "priority_gain": gain is not None and gain >= threshold["minimum_priority_accuracy_gain"],
        "request_budget": models_per_scan <= threshold["maximum_model_requests_per_scan"],
    }
    return {"manifest": manifest["version"], "corpus_sha256": digest, "profile": profile,
            "runtime": {"python": platform.python_version(), "platform": platform.system(),
                        "ruleset": RULESET_VERSION, "catalog_rules": len(catalog()["rules"]),
                        "bundle": manifest["tool_versions"], "osv_database_date": manifest["osv_database_date"],
                        "osv_database_sha256": OSV_DATABASE_SHA256 if profile == "bundled" else None},
            "repetitions": repetitions, "thresholds": threshold, "modes": summary, "fallback": fallback,
            "ranking": {**priorities, "top1_accuracy_gain": gain},
            "constraints": {"unexpected_outcomes": failures, "maximum_fixture_model_requests": models_per_scan,
                            "usage_is_synthetic": True, "fixture_usage": dict(usage),
                            "external_provider_requests": 0, "external_provider_cost_usd": None},
            "gates": gate, "automatic_enrichment_approved": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--profile", choices=("bundled", "mocked"), required=True)
    parser.add_argument("--repetitions", type=int, choices=range(1, 6), default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(evaluate(args.manifest, args.profile, args.repetitions), indent=2, ensure_ascii=True) + "\n"
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
