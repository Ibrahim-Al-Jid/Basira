from pathlib import Path
import importlib.util
import os
import re

ROOT = Path(__file__).resolve().parents[1]


def markdown_files():
    return [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md"), *(ROOT / "work").glob("*.md")]


def test_relative_markdown_links_resolve():
    broken = []
    for file in markdown_files():
        for target in re.findall(r"\]\(([^)\s]+)\)", file.read_text(encoding="utf-8")):
            if re.match(r"[a-z]+:|#", target):
                continue
            path = target.split("#")[0]
            if path and not os.path.exists(file.parent / path):
                broken.append((str(file.relative_to(ROOT)), target))
    assert not broken, broken


def test_generated_taxonomy_doc_is_current():
    spec = importlib.util.spec_from_file_location("build_taxonomy_docs", ROOT / "ops" / "build-taxonomy-docs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.OUT.read_text(encoding="utf-8") == module.render()


def test_no_new_phase_notes_outside_archive():
    stray = [p.name for p in (ROOT / "docs").glob("PHASE*.md")]
    assert not stray, stray
