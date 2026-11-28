"""Lints on the migration graph that need no database.

`alembic_version.version_num` is `varchar(32)`, so a revision id longer than that fails the upgrade
*after* the migration's own DDL has run: the version row cannot be written, and the whole transaction
rolls back with a string-truncation error that names the UPDATE rather than the migration. The length
is a hard limit, not a style choice, so it is checked here instead of in review.

The graph checks catch the other ways a migration file can look fine and still break `upgrade head`:
two files claiming the same id, a `down_revision` that names nothing, or a second head that makes
"head" ambiguous.
"""

import ast
from pathlib import Path

VERSIONS = Path(__file__).with_name("migrations") / "versions"
MAX_REVISION_ID = 32


def _value(node):
    """The literal a `revision`/`down_revision` assignment holds, or None when it is not literal."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Tuple):
        return tuple(_value(element) for element in node.elts)
    return None


def revisions(directory=VERSIONS):
    """Map file name to (revision, down_revision) for every migration in `directory`."""
    found = {}
    for path in sorted(directory.glob("*.py")):
        values = {}
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign):
                targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets = [node.target.id]
            else:
                continue
            for name in targets:
                if name in ("revision", "down_revision"):
                    values[name] = _value(node.value)
        if "revision" in values:
            found[path.name] = (values["revision"], values.get("down_revision"))
    return found


def test_migration_files_are_found():
    assert revisions(), f"no migration files under {VERSIONS}"


def test_revision_ids_fit_alembic_version():
    too_long = {name: revision for name, (revision, _) in revisions().items()
                if len(revision) > MAX_REVISION_ID}
    assert not too_long, (
        f"alembic_version.version_num is varchar({MAX_REVISION_ID}), so these ids cannot be written "
        f"and the upgrade rolls back after its DDL runs: {too_long}")


def test_revision_ids_are_unique():
    seen = {}
    for name, (revision, _) in revisions().items():
        assert revision not in seen, f"{name} and {seen[revision]} both claim revision {revision}"
        seen[revision] = name


def test_every_down_revision_exists():
    found = revisions()
    ids = {revision for revision, _ in found.values()}
    for name, (_, parent) in found.items():
        if parent is None:
            continue
        parents = parent if isinstance(parent, tuple) else (parent,)
        for one in parents:
            assert one in ids, f"{name} has down_revision {one!r}, which is not a revision in this directory"


def test_there_is_exactly_one_head():
    found = revisions()
    parents = set()
    for _, parent in found.values():
        if parent is None:
            continue
        parents.update(parent if isinstance(parent, tuple) else (parent,))
    heads = sorted(revision for revision, _ in found.values() if revision not in parents)
    assert len(heads) == 1, f"upgrade head is ambiguous with more than one head: {heads}"


def test_a_long_id_is_reported(tmp_path):
    (tmp_path / "platform_example_0001.py").write_text(
        'revision = "platform_a_revision_id_that_is_way_too_long_0001"\n'
        'down_revision = None\n', encoding="utf-8")
    too_long = {name: revision for name, (revision, _) in revisions(tmp_path).items()
                if len(revision) > MAX_REVISION_ID}
    assert too_long, "the length check did not see an id longer than the column"
