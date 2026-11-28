"""The baseline CLI must keep working: it is how the reference-corpus numbers are reproduced."""
import json

from . import analyzer_baseline
from .corpus_evaluation import MANIFEST


def test_baseline_reproduces_both_modes_with_no_model_calls():
    baseline = analyzer_baseline.tools_baseline(MANIFEST, "mocked", 1)
    assert baseline["contract"] == "basira-tools-baseline-1" and baseline["model_calls"] == 0
    assert set(baseline["modes"]) == {"native_only", "tools_only"} and baseline["registry"]
    assert all(mode["cases"] for mode in baseline["modes"].values())
    json.dumps(baseline)
