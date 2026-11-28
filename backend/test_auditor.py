from .auditor import REASONS, audit_candidates

FILES = {"app.py": "import os\nos.system('ping ' + host)\n\n", "web/a.js": "eval(req.body.x)\n"}
RULES = {"SRC-02", "SRC-03"}


def run(candidate, rules=RULES, files=FILES):
    accepted, rejected = audit_candidates([candidate], files, rules)
    return accepted, rejected


def test_a_candidate_with_a_real_location_and_quote_is_accepted():
    good = {"path": "app.py", "line": 2, "quote": "os.system('ping ' + host)", "rule": "SRC-02"}
    accepted, rejected = run(good)
    assert accepted == [good] and rejected == []
    spaced = {"path": "web/a.js", "line": 1, "quote": "eval(req.body.x)\n", "rule": "SRC-03"}
    assert run(spaced)[0] == [spaced]
    padded = {"path": "app.py", "line": 2, "quote": "os.system('ping '   +   host)", "rule": "SRC-02"}
    assert run(padded)[0] == [padded]


def test_every_way_a_model_can_be_wrong_gets_a_fixed_reason_code():
    cases = {
        "unknown_path": {"path": "nope.py", "line": 1, "quote": "import os", "rule": "SRC-02"},
        "line_out_of_range": {"path": "app.py", "line": 99, "quote": "import os", "rule": "SRC-02"},
        "quote_missing": {"path": "app.py", "line": 1, "quote": "", "rule": "SRC-02"},
        "quote_not_at_location": {"path": "app.py", "line": 1, "quote": "os.system('ping ' + host)", "rule": "SRC-02"},
        "unknown_rule": {"path": "app.py", "line": 2, "quote": "os.system('ping ' + host)", "rule": "MADE-UP"},
        "bad_shape": {"path": "app.py", "line": "2", "quote": "import os", "rule": "SRC-02"},
    }
    for reason, candidate in cases.items():
        assert run(candidate)[1] == [{"index": 0, "reason": reason}], reason
    assert run("not a dict")[1] == [{"index": 0, "reason": "bad_shape"}]
    assert run({"path": "app.py", "line": True, "quote": "import os"})[1][0]["reason"] == "bad_shape"
    assert set(cases) | {"duplicate"} == set(REASONS)


def test_duplicates_and_blank_lines_are_rejected_and_order_is_kept():
    good = {"path": "app.py", "line": 2, "quote": "os.system('ping ' + host)", "rule": "SRC-02"}
    blank = {"path": "app.py", "line": 3, "quote": "anything at all", "rule": "SRC-02"}
    accepted, rejected = audit_candidates([good, dict(good), blank], FILES, RULES)
    assert accepted == [good]
    assert rejected == [{"index": 1, "reason": "duplicate"}, {"index": 2, "reason": "quote_not_at_location"}]


def test_rule_check_is_optional_and_quotes_are_bounded():
    free = {"path": "app.py", "line": 2, "quote": "os.system('ping ' + host)"}
    assert audit_candidates([free], FILES)[0] == [free]
    long = {"path": "app.py", "line": 2, "quote": "x" * 301}
    assert audit_candidates([long], FILES)[1] == [{"index": 0, "reason": "quote_missing"}]
