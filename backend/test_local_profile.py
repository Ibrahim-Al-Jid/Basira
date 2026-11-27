"""The Windows local profile must turn personal projects on for every service that reads the flag."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def service_block(text, name):
    match = re.search(rf"(?ms)^  {name}:\n(.*?)(?=^  \S|\Z)", text)
    assert match, name
    return match.group(1)


def test_local_profile_enables_personal_projects_for_app_dispatcher_and_worker():
    local = (ROOT / "compose.local.yaml").read_text(encoding="utf-8")
    base = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    for name in ("app", "dispatcher", "worker"):
        assert 'BASIRA_PERSONAL_PROJECTS: "1"' in service_block(local, name)
        assert "*platform" in service_block(base, name)  # these services read the flag from the shared block
