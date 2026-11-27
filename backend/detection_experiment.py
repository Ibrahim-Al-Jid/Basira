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
import json
from hashlib import sha256
from pathlib import Path
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", choices=["static"], default="static")
    args = parser.parse_args()
    manifest = load_manifest()
    sources = fetch_sources(manifest)
    found, elapsed, total = run_static(manifest, sources)
    result = {"config": args.config, "target": manifest["target"], "commit": manifest["commit"],
              "seconds": round(elapsed, 3), "findings_total": total, **score(manifest, found)}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
