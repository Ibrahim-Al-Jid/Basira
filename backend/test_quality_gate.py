"""The regression gate: precision, recall and false-positive rate may not get worse than the stored baseline."""
import os

import pytest

from . import quality_gate as gate

BASE = {"precision": 0.9, "recall": 0.9, "false_positive_rate": 0.1}


def test_a_drop_in_any_metric_is_a_regression_and_an_improvement_is_not():
    assert gate.regressions("s", dict(BASE), BASE) == []
    assert gate.regressions("s", {"precision": 1.0, "recall": 1.0, "false_positive_rate": 0.0}, BASE) == []
    for worse in ({**BASE, "recall": 0.8}, {**BASE, "precision": 0.8}, {**BASE, "false_positive_rate": 0.2}):
        [problem] = gate.regressions("s", worse, BASE)
        assert "worse than baseline" in problem


def test_no_findings_where_the_baseline_had_precision_is_a_regression_but_the_reverse_is_not():
    assert gate.regressions("s", {**BASE, "precision": None}, BASE)
    assert gate.regressions("s", {"precision": 0.5, "recall": 0.1, "false_positive_rate": None}, {"precision": None, "recall": 0.0, "false_positive_rate": None}) == []


def test_unmeasured_set_fails_instead_of_passing_silently():
    assert gate.check({"new_set": dict(BASE)}, {"sets": {}}) == ["new_set: no baseline recorded"]


def test_dvwa_scoring_counts_pairs_and_clean_files():
    manifest = {"cases": [
        {"path": "a/low.php", "vulnerable": True, "subdomain": "D04.1"},
        {"path": "b/low.php", "vulnerable": True, "subdomain": "D05.1"},
        {"path": "a/impossible.php", "vulnerable": False}, {"path": "b/impossible.php", "vulnerable": False}]}
    found = {"a/low.php": {"D04.1", "D08.1"}, "a/impossible.php": {"D04.1"}}
    result = gate.dvwa_metrics(manifest, found)
    assert (result["tp"], result["fp"], result["fn"]) == (1, 2, 1)
    assert result["precision"] == pytest.approx(1 / 3) and result["recall"] == 0.5
    assert result["false_positive_rate"] == 0.5
    assert gate.dvwa_metrics(manifest, {})["precision"] is None


def test_offline_reference_corpus_does_not_regress_against_the_baseline():
    baseline = gate.load_baseline()
    assert gate.check({"reference_corpus": gate.corpus_metrics()}, baseline) == []


@pytest.mark.skipif(os.environ.get("BASIRA_EVAL_NETWORK") != "1", reason="downloads the pinned DVWA files")
def test_dvwa_static_does_not_regress_against_the_baseline():
    assert gate.check({"dvwa_static": gate.measure_dvwa()}, gate.load_baseline()) == []
