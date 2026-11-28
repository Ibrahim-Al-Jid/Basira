"""Self-security, part 2: hostile uploads and hostile report content on the export paths. Offline, no live provider."""
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

HOSTILE_FINDING = {"rule": "http-form", "line": 1, "severity": "medium"}


def hostile_report(text):
    from .contracts import Report

    return Report.model_validate({
        "id": "a" * 32, "created_at": "2026-11-18T12:00:00+00:00", "model": "fixture",
        "summary_en": text, "summary_ar": text, "metrics": {"validatedCount": 1, "modelCalls": 0},
        "findings": [{**HOSTILE_FINDING, "evidence": text, "title": text, "title_ar": text,
                      "remediation": text, "remediation_ar": text}]})


def test_hostile_report_text_is_escaped_in_the_html_export():
    from .main import report_html

    markup = "<img src=x onerror=alert(1)>"
    for lang in ("en", "ar"):
        page = report_html(hostile_report(markup).model_dump(mode="json"), lang)
        assert markup not in page and "&lt;img" in page


def test_hostile_report_text_in_the_pdf_export_stays_text_with_no_active_content():
    from .report_pdf import pdf_download, printable

    hostile = ("<script>alert(1)</script> ) /JS (app.alert(1)) /OpenAction /Launch /URI (http://x.test) %%EOF\x00\x1b"
               "\u202e\u2066 " + "A" * 3000 + " \U0001f600")
    for lang in ("en", "ar"):
        answer = pdf_download(hostile_report(hostile), lang)
        assert answer.status_code == 200 and answer.headers["content-type"] == "application/pdf"
        pdf = answer.body
        assert pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF")
        # The hostile words are drawn as glyphs inside compressed streams, never as PDF objects or actions.
        for name in (b"/JavaScript", b"/JS", b"/Launch", b"/URI", b"/AA", b"/EmbeddedFile", b"/SubmitForm"):
            assert name not in pdf
        # The library's own page-zoom entry is the only /OpenAction allowed, and it must be a plain destination.
        assert re.findall(rb"/OpenAction[^\n]*", pdf) == [b"/OpenAction [3 0 R /FitH null]"]
        assert len(pdf) < 2_000_000
    cleaned = printable(hostile)
    assert len(cleaned) <= 450 and "\x00" not in cleaned and "\x1b" not in cleaned and "\u202e" not in cleaned


def test_deployment_config_in_output_folders_is_scanned_but_third_party_folders_stay_skipped():
    manifest = []
    files = zip_texts(build([
        ("app/index.html", PAGE),
        ("build/Dockerfile", b"FROM python:3\nUSER 0\n"),
        ("dist/.env", b"TOKEN=placeholder\n"),
        ("build/docker-compose.yml", b"services: {}\n"),
        ("build/app.js", b"console.log(1)"),
        ("node_modules/pkg/Dockerfile", b"FROM scratch\n"),
        ("vendor/lib/.env", b"A=1\n"),
        (".git/.npmrc", b"x=1\n"),
    ]), manifest=manifest)
    assert set(files) == {"app/index.html", "build/Dockerfile", "dist/.env", "build/docker-compose.yml"}
    status = {row["path"]: (row["status"], row["reason"]) for row in manifest}
    assert status["build/app.js"] == ("skipped", "build_artifact")
    assert status["node_modules/pkg/Dockerfile"] == ("skipped", "build_artifact")
    assert status["vendor/lib/.env"] == ("skipped", "build_artifact")
    assert status[".git/.npmrc"] == ("skipped", "build_artifact")


def test_a_risky_dockerfile_under_build_produces_a_finding():
    raw = build([("app/index.html", PAGE), ("build/Dockerfile", b"FROM python:3\nUSER 0\n")])
    report = defensive_review("repository", "source.zip", raw, {})
    assert "build/Dockerfile" in {row["path"] for row in report["findings"]}
