import re
from pathlib import Path

from . import guidance
from .artifact_review import catalog, defensive_review
from .contracts import Finding
from .checks.source_code import RULE_IDS

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "source-code"
ARABIC = re.compile(r"[\u0600-\u06ff]")


def test_every_catalog_rule_has_guidance_and_no_entry_is_orphaned():
    ids = {rule["id"] for rule in catalog()["rules"]}
    have = set(guidance.GUIDE) | set(guidance.SOURCE)
    assert ids <= have, sorted(ids - have)
    assert have - ids <= {"API-01", "API-02", "API-03", "SEC-01", "SCA-01"}


def test_every_entry_has_a_fix_and_a_verify_step_in_both_languages_and_no_dash_or_placeholder_left():
    for rule in set(guidance.GUIDE) | set(guidance.SOURCE):
        for language in ("php", "js", "py"):
            item = guidance.guidance_for({"rule": rule, "line": 3, "path": f"app/x.{language}"})
            assert item and all(item[key].strip() for key in ("fix", "fix_ar", "verify", "verify_ar")), rule
            assert ARABIC.search(item["fix_ar"]) and ARABIC.search(item["verify_ar"]), rule
            assert "{where}" not in "".join(item.values()) and "\u2014" not in "".join(item.values()), rule
            Finding(rule=rule, severity="low", line=3, evidence="e", title="t", remediation="r", guidance=item)


def test_source_rules_give_an_example_in_the_language_of_the_file():
    php = guidance.guidance_for({"rule": "SRC-01", "line": 4, "path": "a/q.php"})
    js = guidance.guidance_for({"rule": "SRC-01", "line": 4, "path": "a/q.js"})
    py = guidance.guidance_for({"rule": "SRC-01", "line": 4, "path": "a/q.py"})
    assert "$pdo->prepare" in php["fix"] and "db.query" in js["fix"] and "cursor.execute" in py["fix"]
    assert "a/q.py:4" in py["verify"]
    assert all(guidance.SOURCE[rule][2].keys() == {"php", "js", "py"} for rule in RULE_IDS)


def test_location_comes_from_the_finding_and_an_unknown_rule_gets_none():
    item = guidance.guidance_for({"rule": "APP-02", "line": 7, "path": "config/prod.env"})
    assert "config/prod.env:7" in item["fix"]
    assert "this input" in guidance.guidance_for({"rule": "API-01", "line": 1})["verify"]
    assert guidance.guidance_for({"rule": "ZAP-10020", "line": 1}) is None


def test_scan_findings_carry_guidance_for_their_own_file_and_the_fingerprint_is_unchanged(monkeypatch):
    text = (FIXTURES / "vuln.py").read_text(encoding="utf-8")
    report = defensive_review("repository", "a.zip", _zip({"app/vuln.py": text}), {})
    found = [item for item in report["findings"] if item["rule"].startswith("SRC-")]
    assert found and all(item["guidance"]["verify"].count("app/vuln.py:") == 1 for item in found)
    assert all("cursor.execute" in item["guidance"]["fix"] for item in found if item["rule"] == "SRC-01")
    assert all(len(item["fingerprint"]) == 64 for item in found)
    monkeypatch.setattr(guidance, "attach", lambda findings: findings)
    plain = defensive_review("repository", "a.zip", _zip({"app/vuln.py": text}), {})
    assert [item["fingerprint"] for item in plain["findings"]] == [item["fingerprint"] for item in report["findings"]]
    assert all("guidance" not in item for item in plain["findings"])


def _zip(files):
    import io
    from zipfile import ZipFile
    out = io.BytesIO()
    with ZipFile(out, "w") as bundle:
        for name, body in files.items():
            bundle.writestr(name, body)
    return out.getvalue()
