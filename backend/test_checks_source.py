import io
from pathlib import Path
from zipfile import ZipFile

from .artifact_review import RULESET_VERSION, catalog, defensive_review
from .checks import source_code
from .taxonomy import rule_index

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "source-code"


def run(name, text=None, path=None):
    text = (FIXTURES / name).read_text(encoding="utf-8") if text is None else text
    results = source_code.check({path or name: text}, None, {}, [])
    return {rule: sorted({hit["line"] for hit in hits}) for rule, hits in results.items() if hits}


def test_python_vulnerable_fixture_hits_every_expected_rule():
    found = run("vuln.py")
    assert set(found) == {f"SRC-{n:02d}" for n in (1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14)}
    assert found["SRC-01"] == [11, 12]
    assert found["SRC-11"] == [36, 37]


def test_javascript_vulnerable_fixture_hits_every_expected_rule():
    found = run("vuln.js")
    assert set(found) == {f"SRC-{n:02d}" for n in (1, 2, 3, 4, 5, 6, 8, 9, 10, 13, 14)}
    assert {8, 11} <= set(found["SRC-01"])


def test_php_vulnerable_fixture_hits_every_expected_rule():
    found = run("vuln.php")
    assert set(found) == {f"SRC-{n:02d}" for n in (3, 4, 5, 6, 10, 11, 14)}


def test_fixed_versions_raise_nothing():
    for name in ("safe.py", "safe.js", "safe.php"):
        assert run(name) == {}, name


def test_dvwa_style_php_sources_and_guards():
    sql = "<?php\n$id = $_GET['id'];\n$q = \"SELECT * FROM u WHERE id = '$id'\";\nmysqli_query($link, $q);\n"
    assert run("a.php", sql) == {"SRC-01": [4]}
    fixed = "<?php\n$id = $_GET['id'];\nif (is_numeric($id)) { $id = intval($id);\n$q = \"SELECT * FROM u WHERE id = '$id'\";\nmysqli_query($link, $q); }\n"
    assert run("a.php", fixed) == {}
    escaped = "<?php\n$u = mysqli_real_escape_string($l, $_POST['u']);\n$q = \"SELECT 1 FROM x WHERE u = '$u'\";\nmysqli_query($l, $q);\n"
    assert run("a.php", escaped) == {}
    xss = "<?php\n$html .= '<p>Hello ' . $_GET['name'] . '</p>';\n"
    assert run("a.php", xss) == {"SRC-04": [2]}
    # SQL escaping does not make HTML output safe
    mixed = "<?php\n$u = mysqli_real_escape_string($l, $_POST['u']);\necho \"<b>$u</b>\";\n"
    assert run("a.php", mixed) == {"SRC-04": [3]}


def test_php_csrf_needs_a_write_and_no_token():
    write = "<?php\n$p = $_GET['p'];\n$p = md5($p);\n$q = \"UPDATE users SET password = '$p'\";\nmysqli_query($l, $q);\n"
    assert run("a.php", write) == {"SRC-08": [5]}
    assert run("a.php", write.replace("$p = md5", "checkToken($_REQUEST['user_token']);\n$p = md5")) == {}


def test_comments_and_single_quoted_strings_do_not_count():
    text = "<?php\n// echo $_GET['x'];\n$a = 'SELECT $_GET';\necho 'hi';\n"
    assert run("a.php", text) == {}


def test_not_applicable_without_supported_files_and_fixtures_are_skipped():
    results = source_code.check({"README.md": "hello"}, None, {}, [])
    assert set(results) == set(source_code.RULE_IDS) and all(value is None for value in results.values())
    results = source_code.check({"tests/fixtures/x.php": "<?php eval($_GET['a']);"}, None, {}, [])
    assert all(value is None for value in results.values())


def test_broken_or_huge_files_do_not_crash():
    assert run("bad.py", "def (:\n") == {}
    assert run("big.js", "var a = '" + "x" * 5000 + "';\n") == {}


def test_end_to_end_zip_has_source_findings_mapped_to_the_taxonomy():
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("app/vuln.php", (FIXTURES / "vuln.php").read_text())
        archive.writestr("app/safe.php", (FIXTURES / "safe.php").read_text())
    report = defensive_review("repository", "snapshot.zip", buffer.getvalue(), {"allowed_kinds": ["repository"]})
    source = [item for item in report["findings"] if item["rule"].startswith("SRC-")]
    assert source and {item["path"] for item in source} == {"app/vuln.php"}
    assert all(item["domain"] == "source" for item in source)
    index = rule_index()
    assert all(index[item["rule"]] for item in source)
    assert {row["rule"] for row in report["coverage"] if row["rule"].startswith("SRC-")} == set(source_code.RULE_IDS)


def test_catalog_lists_the_source_tool_and_version():
    data = catalog()
    assert data["version"] == RULESET_VERSION == "basira-static-3"
    tool = next(item for item in data["tools"] if item["id"] == "source-code")
    assert tool["rules"] == list(source_code.RULE_IDS)


def test_search_code_tool_rejects_backtracking_patterns_and_still_searches():
    import time
    from .detection_agents import search_lines
    started = time.monotonic()
    assert search_lines("a" * 34 + "!\n", "(a+)+$") == "pattern rejected"
    assert search_lines("x", "(a*)*b") == "pattern rejected"
    assert search_lines("x", "(a)\\1") == "pattern rejected"
    assert time.monotonic() - started < 1
    assert search_lines("one\ntwo $_GET\nthree", r"\$_GET") == "2: two $_GET"
    assert search_lines("x", "[") == "invalid pattern"
