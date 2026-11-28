"""Intake limits (10 MiB archive, 50 MiB unpacked, 1000 entries) and Windows ZIP paths."""
import base64
import io
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

import pytest

from .artifact_review import (InputError, MAX_ARTIFACT, MAX_EXPANDED, MAX_FILES, decode_payload, defensive_review,
                              prepare, zip_texts)

CODE = "def handler(request):\n    return request.args\n"


def build(entries, method=ZIP_DEFLATED):
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", method) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buffer.getvalue()


def test_limits_are_the_documented_ones():
    assert (MAX_ARTIFACT, MAX_EXPANDED, MAX_FILES) == (10 * 1024 * 1024, 50 * 1024 * 1024, 1000)


def test_a_repository_with_a_thousand_files_is_accepted_and_reviewed():
    raw = build([(f"src/m{i}.py", CODE + f"# {i}\n") for i in range(MAX_FILES)])
    assert len(zip_texts(raw)) == MAX_FILES
    report = defensive_review("repository", "big.zip", raw, {"allowed_kinds": ["repository"]})
    assert report["status"] and len(report["input_manifest"]) == MAX_FILES


def test_more_than_a_thousand_entries_is_refused():
    raw = build([(f"src/m{i}.py", CODE) for i in range(MAX_FILES + 1)])
    with pytest.raises(InputError, match="١٠٠٠"):
        zip_texts(raw)


def test_payload_size_boundary():
    assert len(decode_payload(base64.b64encode(b"x" * MAX_ARTIFACT).decode())) == MAX_ARTIFACT
    with pytest.raises(InputError):
        decode_payload(base64.b64encode(b"x" * (MAX_ARTIFACT + 1)).decode())


def test_unpacked_size_over_the_cap_is_refused():
    # Stored entries: no compression ratio to trip first, so the unpacked total is what must stop it.
    raw = build([(f"src/m{i}.py", "x" * 999_000 + f"{i:03d}\n") for i in range(54)], ZIP_STORED)
    assert 54 * 999_004 > MAX_EXPANDED
    with pytest.raises(InputError, match="الحد"):
        zip_texts(raw)


def test_zip_bomb_ratio_is_still_refused_at_the_new_scale():
    raw = build([("src/bomb.py", "a" * 900_000)])
    with pytest.raises(InputError, match="نسبة ضغط"):
        zip_texts(raw)
    raw = build([(f"src/{i}.py", "0" * 600_000 + str(i)) for i in range(40)])
    with pytest.raises(InputError):
        zip_texts(raw)


def test_oversize_single_file_is_still_refused():
    with pytest.raises(InputError):
        zip_texts(build([("src/a.py", "x = 1\n" * 200_000)]))


def test_windows_backslash_paths_are_read_as_folders():
    raw = build([("proj\\", ""), ("proj\\app\\", ""), ("proj\\app\\main.py", CODE), ("proj\\README.txt", "hi")])
    files = zip_texts(raw)
    assert set(files) == {"proj/app/main.py", "proj/README.txt"}


@pytest.mark.parametrize("name", [
    "..\\outside.py", "proj\\..\\..\\outside.py", "\\abs.py", "C:\\x.py", "c:x.py", "proj\\\\x.py", "proj\\.\\x.py",
    "\\\\server\\share\\x.py",
])
def test_windows_style_escapes_are_still_refused(name):
    with pytest.raises(InputError):
        zip_texts(build([(name, CODE)]))


def test_slash_and_backslash_spellings_of_one_path_collide():
    with pytest.raises(InputError, match="مكررة"):
        zip_texts(build([("a/b.py", CODE), ("a\\b.py", CODE)]))


def test_backslash_folder_entry_with_content_is_refused():
    with pytest.raises(InputError):
        zip_texts(build([("proj\\", "not empty"), ("proj\\a.py", CODE)]))


def test_prepare_accepts_a_windows_archive():
    files, *_ = prepare("repository", "w.zip", build([("proj\\a.py", CODE)]))
    assert list(files) == ["proj/a.py"]


def _github_session(size, declared=None):
    import httpx

    commit = "a" * 40
    location = f"https://codeload.github.com/Owner/Repo/zip/{commit}"

    def handler(request):
        if request.url.host == "api.github.com":
            return httpx.Response(302, headers={"Location": location})
        body = b"PK\x03\x04" + b"x" * (size - 4)
        headers = {"Content-Length": str(declared if declared is not None else size)}
        return httpx.Response(200, stream=httpx.ByteStream(body), headers=headers)

    return httpx.Client(transport=httpx.MockTransport(handler)), commit


def test_github_snapshot_download_accepts_the_new_size_and_refuses_beyond():
    import httpx

    from . import github_import as gh

    session, commit = _github_session(6 * 1024 * 1024)
    assert len(gh.download_archive(session, "token", "Owner/Repo", commit)) == 6 * 1024 * 1024
    session, commit = _github_session(1024, declared=MAX_ARTIFACT + 1)
    with pytest.raises(gh.GitHubFailure) as refused:
        gh.download_archive(session, "token", "Owner/Repo", commit)
    assert refused.value.status == 413 and "١٠ ميجابايت" in refused.value.detail
