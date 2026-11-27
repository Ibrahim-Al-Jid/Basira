"""Self-security, part 2: hostile uploads and hostile report content on the export paths. Offline, no live provider."""
import base64
import io
import json
import re
import struct
import zipfile
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

import pytest

from . import artifact_review as review
from .artifact_review import InputError, defensive_review, zip_texts

PAGE = b'<script src="http://one.example.test/a"></script>'


def build(entries, method=ZIP_DEFLATED):
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", method) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buffer.getvalue()


@pytest.mark.parametrize("name", [
    "../evil.html", "a/../../evil.html", "/etc/passwd.html", "a//b.html", "./a.html", "a/./b.html",
    "a\\..\\b.html", "C:\\x.html", "c:evil.html", "a/b\x00.html", "a/b\n.html", "a/\x7f.html", "x" * 241 + ".html",
])
def test_zip_entry_names_that_escape_or_confuse_paths_are_rejected(name):
    with pytest.raises(InputError):
        zip_texts(build([(name, PAGE)]))


def test_case_and_unicode_lookalike_duplicates_are_rejected():
    for first, second in (("a.html", "A.HTML"), ("ﬁle.html", "file.html"), ("a.html", "a.html")):
        with pytest.raises(InputError):
            zip_texts(build([(first, PAGE), (second, PAGE)]))


def test_symlink_special_encrypted_and_exotic_compression_entries_are_rejected():
    link = ZipInfo("link.html")
    link.external_attr = 0o120777 << 16
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(link, "/etc/passwd")
    with pytest.raises(InputError):
        zip_texts(buffer.getvalue())

    raw = bytearray(build([("a.html", PAGE)]))
    for signature in (b"PK\x03\x04", b"PK\x01\x02"):  # set the "encrypted" flag in local and central headers
        offset = raw.find(signature)
        flag = offset + (6 if signature == b"PK\x03\x04" else 8)
        raw[flag] |= 1
    with pytest.raises(InputError):
        zip_texts(bytes(raw))

    buffer = io.BytesIO()
    with ZipFile(buffer, "w", zipfile.ZIP_BZIP2) as archive:
        archive.writestr("a.html", PAGE)
    with pytest.raises(InputError):
        zip_texts(buffer.getvalue())


def test_nested_archives_are_rejected_by_name_and_by_content():
    inner = build([("x.html", PAGE)])
    with pytest.raises(InputError):
        zip_texts(build([("inner.zip", inner), ("a.html", PAGE)]))
    with pytest.raises(InputError):
        zip_texts(build([("disguised.html", inner)]))
    with pytest.raises(InputError):
        zip_texts(build([("disguised.js", b"\x1f\x8b\x08\x00" + b"0" * 20)]))


def test_compression_bomb_and_expansion_limits_hold():
    with pytest.raises(InputError):  # 900 KB of zeros compresses past 200:1
        zip_texts(build([("bomb.html", b"0" * 900_000)]))
    with pytest.raises(InputError):  # one file over the per-file limit
        zip_texts(build([("big.html", b"<p>" + b"x" * 1_000_001)], ZIP_STORED))
    parts = [(f"f{i}.html", b"<p>" + b"%d" % i * 900_000) for i in range(9)]  # 9 stored files of 900 KB: each fits, the total does not
    with pytest.raises(InputError):
        zip_texts(build(parts, ZIP_STORED))
    with pytest.raises(InputError):
        zip_texts(build([(f"f{i}.html", PAGE) for i in range(review.MAX_FILES + 1)]))
    assert zip_texts(build([(f"f{i}.html", PAGE) for i in range(review.MAX_FILES)]))


def test_a_declared_size_that_lies_is_rejected():
    raw = bytearray(build([("a.html", PAGE)], ZIP_STORED))
    central = raw.rfind(b"PK\x01\x02")
    struct.pack_into("<I", raw, central + 24, len(PAGE) + 5)  # uncompressed size in the central directory
    with pytest.raises(InputError):
        zip_texts(bytes(raw))


def test_binary_and_non_utf8_text_is_rejected_and_unsupported_files_are_only_listed():
    with pytest.raises(InputError):
        zip_texts(build([("a.html", b"<p>\x00</p>")]))
    with pytest.raises(InputError):
        zip_texts(build([("a.html", b"\xff\xfe\xfa<p>")]))
    manifest = []
    zip_texts(build([("a.html", PAGE), ("logo.png", b"\x89PNG"), ("node_modules/x.js", b"1")]), manifest=manifest)
    assert {row["path"]: row["status"] for row in manifest} == {"a.html": "included", "logo.png": "skipped", "node_modules/x.js": "skipped"}


@pytest.mark.parametrize("kind,raw", [
    ("zap", b"[" * 5000 + b"]" * 5000), ("zap", b'{"a": 1, "a": 2}'), ("zap", b'{"a": NaN}'), ("zap", b"[]"),
    ("zap", b"\xff\xfe{}"), ("openapi", b'{"openapi": "3.0.0", "openapi": "3.1.0"}'), ("har", b"x" * 2_000_001),
])
def test_hostile_json_documents_are_rejected_with_a_bounded_error(kind, raw):
    with pytest.raises(InputError):
        review.prepare(kind, "doc.json", raw)


def test_empty_and_oversized_uploads_are_rejected_before_parsing():
    for raw in (b"", b"x" * (review.MAX_ARTIFACT + 1)):
        with pytest.raises(InputError):
            review.prepare("repository", "a.zip", raw)


def test_secrets_in_file_names_are_redacted_in_the_manifest_and_reports():
    token = "ghp_" + "A" * 36
    manifest = []
    zip_texts(build([(f"{token}.html", PAGE)]), manifest=manifest)
    assert token not in json.dumps(manifest) and "[redacted]" in manifest[0]["path"]


# ---- export paths ----

def test_hostile_report_text_is_escaped_in_the_html_export_and_headers_are_fixed(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from . import main

    markup = "<img src=x onerror=alert(1)>"
    monkeypatch.setenv("BASIRA_DB_PATH", str(tmp_path / "t.sqlite3"))

    async def graph(source, model, key, emit, previous=None):
        return {"summary_en": markup, "summary_ar": markup, "metrics": {"validatedCount": 1, "modelCalls": 0}, "findings": [{
            "rule": "http-form", "line": 1, "evidence": markup, "severity": "medium", "title": markup, "title_ar": markup,
            "remediation": markup, "remediation_ar": markup}]}

    monkeypatch.setattr(main, "run_graph", graph)
    with TestClient(main.app) as client:
        events = [json.loads(line) for line in client.post("/api/run", json={"source": "<p>x</p>"}).text.splitlines()]
        report_id = events[-1]["report"]["id"]
        for lang in ("en", "ar"):
            page = client.get(f"/api/reports/{report_id}/download?lang={lang}")
            assert markup not in page.text and "&lt;img" in page.text
            assert page.headers["content-security-policy"] == "default-src 'none'; style-src 'unsafe-inline'"
            assert page.headers["content-disposition"] == f'attachment; filename="basira-{report_id}-{lang}.html"'
        for hostile in ("x%0d%0aInjected:%20a", "%22%3Bfilename%3D%22evil"):
            answer = client.get(f"/api/reports/{hostile}/download")
            assert answer.status_code == 404 and "content-disposition" not in answer.headers and "injected" not in answer.headers


def test_hostile_report_text_in_the_pdf_export_stays_text_with_no_active_content(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from . import main
    from .report_pdf import printable

    hostile = ("<script>alert(1)</script> ) /JS (app.alert(1)) /OpenAction /Launch /URI (http://x.test) %%EOF\x00\x1b"
               "\u202e\u2066 " + "A" * 3000 + " \U0001f600")
    monkeypatch.setenv("BASIRA_DB_PATH", str(tmp_path / "t.sqlite3"))

    async def graph(source, model, key, emit, previous=None):
        return {"summary_en": hostile, "summary_ar": hostile, "metrics": {"validatedCount": 1, "modelCalls": 0}, "findings": [{
            "rule": "http-form", "line": 1, "evidence": hostile, "severity": "medium", "title": hostile, "title_ar": hostile,
            "remediation": hostile, "remediation_ar": hostile}]}

    monkeypatch.setattr(main, "run_graph", graph)
    with TestClient(main.app) as client:
        events = [json.loads(line) for line in client.post("/api/run", json={"source": "<p>x</p>"}).text.splitlines()]
        report_id = events[-1]["report"]["id"]
        for lang in ("en", "ar"):
            answer = client.get(f"/api/reports/{report_id}/download?format=pdf&lang={lang}")
            assert answer.status_code == 200 and answer.headers["content-type"] == "application/pdf"
            pdf = answer.content
            assert pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF")
            # The hostile words are drawn as glyphs inside compressed streams, never as PDF objects or actions.
            for name in (b"/JavaScript", b"/JS", b"/Launch", b"/URI", b"/AA", b"/EmbeddedFile", b"/SubmitForm"):
                assert name not in pdf
            # The library's own page-zoom entry is the only /OpenAction allowed, and it must be a plain destination.
            assert re.findall(rb"/OpenAction[^\n]*", pdf) == [b"/OpenAction [3 0 R /FitH null]"]
            assert len(pdf) < 2_000_000
    cleaned = printable(hostile)
    assert len(cleaned) <= 450 and "\x00" not in cleaned and "\x1b" not in cleaned and "\u202e" not in cleaned
