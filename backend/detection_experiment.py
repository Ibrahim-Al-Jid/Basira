"""Detection-rate experiment on fixed, independently authored targets.

Configurations (same targets, same scoring):
  static   Marsad's deterministic checks only (no model).
Model-backed configurations are added in the same file once a model run is recorded.
A labeled vulnerability counts as found when a finding on its file maps, through the
taxonomy, to the labeled subdomain. Findings on clean files, and findings on a vulnerable
file that map elsewhere, are reported separately as false positives and extras.
"""
import argparse
import io
import os
import json
from hashlib import sha256
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from urllib.request import urlopen
from zipfile import ZipFile

from .artifact_review import defensive_review
from .taxonomy import rule_index

MANIFEST = Path("tests/fixtures/detection-targets/manifest.json")
RAW = "https://raw.githubusercontent.com/digininja/DVWA/{commit}/{path}"


def load_manifest(path=MANIFEST):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fetch_sources(manifest):
    """Download each pinned file and verify its digest; nothing is cached in the repo."""
    sources = {}
    for case in manifest["cases"]:
        with urlopen(RAW.format(commit=manifest["commit"], path=case["path"]), timeout=30) as response:
            body = response.read()
        if sha256(body).hexdigest() != case["sha256"]:
            raise ValueError(f"Digest mismatch for {case['path']}")
        sources[case["id"]] = body.decode("utf-8")
    return sources


def run_static(manifest, sources):
    """Scan all target files as one ZIP through the real repository path."""
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        for case in manifest["cases"]:
            archive.writestr(case["path"], sources[case["id"]])
    started = perf_counter()
    report = defensive_review("repository", "targets.zip", buffer.getvalue(), {"allowed_kinds": ["repository"]})
    elapsed = perf_counter() - started
    index = rule_index()
    found = {}
    for finding in report["findings"]:
        found.setdefault(finding["path"], set()).update(index.get(finding["rule"], []))
    return found, elapsed, len(report["findings"])


def score(manifest, found):
    vulnerable = [case for case in manifest["cases"] if case["vulnerable"]]
    clean = [case for case in manifest["cases"] if not case["vulnerable"]]
    hits = [case["id"] for case in vulnerable if case["subdomain"] in found.get(case["path"], set())]
    false_positives = [case["id"] for case in clean if found.get(case["path"])]
    return {"vulnerable": len(vulnerable), "found": len(hits), "detection_rate": len(hits) / len(vulnerable),
            "clean_files": len(clean), "clean_files_flagged": len(false_positives), "hits": hits}


def run_model_config(config, manifest, sources, log_path, cache_path, budget=int(os.environ.get("DET_BUDGET", "10")), workers=int(os.environ.get("DET_WORKERS", "5"))):
    from .detection_agents import Client, run_single, run_team
    client = Client(log_path)

    cache = json.loads(Path(cache_path).read_text()) if Path(cache_path).exists() else {}
    deadline = perf_counter() + budget

    def one(case):
        if case["path"] in cache or perf_counter() > deadline:
            return case["path"], cache.get(case["path"])
        source = sources[case["id"]]
        if config == "single":
            labels = run_single(client, source)
        elif config == "team":
            labels = run_team(client, source)
        else:
            def hook(case=case, source=source):
                report = defensive_review("repository", "f.zip", _zip({case["path"]: source}), {"allowed_kinds": ["repository"]})
                return json.dumps(sorted({item["rule"] for item in report["findings"]})) or "[]"
            labels = run_team(client, source, tools_enabled=True, static_hook=hook)
        cache[case["path"]] = sorted(labels)
        Path(cache_path).write_text(json.dumps(cache))
        return case["path"], sorted(labels)

    started = perf_counter()
    with ThreadPoolExecutor(workers) as pool:
        found = dict(pool.map(one, manifest["cases"]))
    pending = [path for path, value in found.items() if value is None]
    if pending:
        raise SystemExit(f"{len(pending)} of {len(found)} cases still pending; run the same command again to resume")
    return {path: set(value) for path, value in found.items()}, perf_counter() - started, client.calls


def _zip(files):
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", choices=["static", "single", "team", "team-tools"], default="static")
    parser.add_argument("--cache", default="/tmp/detection-cache.json")
    parser.add_argument("--log", default="/tmp/detection-requests.jsonl")
    args = parser.parse_args()
    manifest = load_manifest()
    sources = fetch_sources(manifest)
    if args.config == "static":
        found, elapsed, calls = run_static(manifest, sources)
    else:
        found, elapsed, calls = run_model_config(args.config, manifest, sources, args.log, args.cache)
    result = {"config": args.config, "target": manifest["target"], "commit": manifest["commit"],
              "seconds": round(elapsed, 3), "requests_or_findings": calls, **score(manifest, found)}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
