"""Reproduce the deterministic analyzer baseline on the registered acceptance corpus."""

import argparse
from collections import Counter
from contextlib import ExitStack
import json
from pathlib import Path

from .corpus_evaluation import (
    EXPECTED_REJECTION, MANIFEST, OSV_DATABASE_SHA256, canon, engine_setup, load_manifest,
    scan, score, summarize,
)
from .synthetic_evaluation import percentile
from .scan_contracts import analyzer_manifests


def tools_baseline(path, profile, repetitions):
    manifest, digest = load_manifest(path)
    modes = {}
    with ExitStack() as stack:
        engine_setup(stack, profile, manifest)
        for mode, external in (("native_only", False), ("tools_only", True)):
            rows, durations = [], []
            tool_times = {}
            tool_states = {}
            for case in manifest["cases"]:
                fingerprints = set()
                for _ in range(repetitions):
                    result, elapsed = scan(case, external)
                    durations.append(elapsed)
                    report = result.get("result")
                    if not report:
                        valid = case.get("expect_rejection") and result.get("error") == EXPECTED_REJECTION
                        if not valid:
                            raise ValueError(f"Unexpected analyzer outcome for case {case['id']}")
                        row = {"case": case["id"], "status": "rejected"}
                    else:
                        if report["metrics"]["modelCalls"] != 0 or report["enrichment"] != "disabled":
                            raise ValueError("Model enrichment must be disabled in the analyzer baseline")
                        if case.get("expect_rejection") or report["status"] != "completed":
                            raise ValueError(f"Incomplete analyzer outcome for case {case['id']}")
                        row = {"case": case["id"], "status": report["status"], **score(report, case, external=external)}
                        for task in report["task_runs"]:
                            if task["agent"] == "analysis":
                                tool_times.setdefault(task["tool"], []).append(task["duration_ms"])
                                tool_states.setdefault(task["tool"], Counter())[task["status"]] += 1
                    fingerprints.add(canon(row))
                if len(fingerprints) != 1:
                    raise ValueError(f"Analyzer output changed between runs for case {case['id']}")
                rows.append(row)
            modes[mode] = {
                **summarize(rows, durations), "cases": rows,
                "tools": {tool: {"samples": len(timings), "p95_ms": percentile(timings, .95),
                                  "statuses": dict(tool_states[tool])}
                          for tool, timings in sorted(tool_times.items())},
            }
        registry = [tool.model_dump(mode="json") for tool in analyzer_manifests()]
    return {
        "contract": "basira-tools-baseline-1", "corpus": manifest["version"], "corpus_sha256": digest,
        "profile": profile, "repetitions": repetitions, "model_calls": 0,
        "pypi_snapshot_sha256": OSV_DATABASE_SHA256 if profile == "bundled" else None,
        "registry": registry, "modes": modes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--profile", choices=("bundled", "mocked"), required=True)
    parser.add_argument("--repetitions", type=int, choices=range(1, 6), default=3)
    args = parser.parse_args()
    print(json.dumps(tools_baseline(args.manifest, args.profile, args.repetitions), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
