"""Quality gate: precision, recall and false-positive rate against a stored baseline.

Detection rate alone rewards noisy checks, so every measured set records all three numbers and a change
fails when recall or precision drops or the false-positive rate rises. Improvements never fail; raise the
baseline in the same change that earns it.

  python -m backend.quality_gate                 check the offline reference corpus (mocked profile)
  python -m backend.quality_gate --network       also check DVWA (downloads the pinned files)
  python -m backend.quality_gate --print         print current measurements as baseline JSON, writes nothing

Sets:
  reference_corpus   the 12-case regression corpus, static adapters, mocked profile. Written together with the
                     checks, so it guards against regressions and proves little about detection.
  dvwa_static        13 vulnerable and 13 fixed DVWA files, static checks only. Independent target, labels by one
                     reader. Unit: a (file, taxonomy subdomain) pair. A pair reported on any file that is not a
                     labeled vulnerability counts as a false positive.
"""
import argparse
import json
import sys
from pathlib import Path

from . import corpus_evaluation, detection_experiment

BASELINE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "quality-baseline.json"
EPSILON = 1e-9
HIGHER_IS_BETTER = ("recall", "precision")
LOWER_IS_BETTER = ("false_positive_rate",)


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def corpus_metrics(result=None):
    row = (result or corpus_evaluation.evaluate(corpus_evaluation.MANIFEST, "mocked", 1))["modes"]["static_adapters"]
    return {"tp": row["tp"], "fp": row["fp"], "fn": row["fn"], "precision": row["precision"], "recall": row["recall"],
            "false_positive_rate": None}


def dvwa_metrics(manifest, found):
    """Scores found = {path: {subdomain, ...}} against the manifest."""
    labeled = {(case["path"], case["subdomain"]) for case in manifest["cases"] if case["vulnerable"]}
    reported = {(path, subdomain) for path, subdomains in found.items() for subdomain in subdomains}
    tp, fp = len(labeled & reported), len(reported - labeled)
    clean = [case for case in manifest["cases"] if not case["vulnerable"]]
    flagged = sum(1 for case in clean if found.get(case["path"]))
    return {"tp": tp, "fp": fp, "fn": len(labeled) - tp, "precision": ratio(tp, tp + fp), "recall": ratio(tp, len(labeled)),
            "false_positive_rate": ratio(flagged, len(clean)), "clean_files": len(clean), "clean_files_flagged": flagged}


def measure_dvwa():
    manifest = detection_experiment.load_manifest(Path(__file__).resolve().parents[1] / detection_experiment.MANIFEST)
    found, _elapsed, _count = detection_experiment.run_static(manifest, detection_experiment.fetch_sources(manifest))
    return dvwa_metrics(manifest, found)


def regressions(name, current, baseline):
    """Human-readable list of drops of current below baseline; empty when the set did not get worse."""
    problems = []
    for metric in HIGHER_IS_BETTER + LOWER_IS_BETTER:
        before, after = baseline.get(metric), current.get(metric)
        if before is None:
            continue
        if after is None:
            if metric in HIGHER_IS_BETTER:
                problems.append(f"{name}: {metric} is undefined now (no findings), baseline {before:.3f}")
            continue
        worse = after < before - EPSILON if metric in HIGHER_IS_BETTER else after > before + EPSILON
        if worse:
            problems.append(f"{name}: {metric} {after:.3f} is worse than baseline {before:.3f}")
    return problems


def load_baseline(path=BASELINE):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check(measurements, baseline):
    problems = []
    for name, current in measurements.items():
        if name not in baseline["sets"]:
            problems.append(f"{name}: no baseline recorded")
        else:
            problems += regressions(name, current, baseline["sets"][name])
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--network", action="store_true", help="also measure DVWA (downloads the pinned files)")
    parser.add_argument("--print", action="store_true", dest="show", help="print measurements, do not compare")
    args = parser.parse_args()
    measurements = {"reference_corpus": corpus_metrics()}
    if args.network:
        measurements["dvwa_static"] = measure_dvwa()
    if args.show:
        print(json.dumps(measurements, indent=2))
        return 0
    problems = check(measurements, load_baseline())
    print(json.dumps(measurements, indent=2))
    for problem in problems:
        print("REGRESSION", problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
