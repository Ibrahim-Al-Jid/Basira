"""The local start scripts must turn personal projects and password sign-up on through .env.local.

compose.local.yaml is gone: compose.yaml forwards these flags from .env.local to every
service that reads them, and the start scripts write them on every run.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ("BASIRA_PERSONAL_PROJECTS", "BASIRA_PASSWORD_AUTH_ENABLED", "BASIRA_PASSWORD_SELF_SIGNUP")


def service_block(text, name):
    match = re.search(rf"(?ms)^  {name}:\n(.*?)(?=^  \S|\Z)", text)
    assert match, name
    return match.group(1)


def test_start_scripts_write_the_local_flags_and_use_no_override_file():
    for script in ("ops/start-local.sh", "ops/start-local.ps1"):
        text = (ROOT / script).read_text(encoding="utf-8")
        for flag in FLAGS:
            assert flag in text, (script, flag)
        assert "compose.local.yaml" not in text, script
    assert not (ROOT / "compose.local.yaml").exists()


def test_compose_forwards_personal_projects_to_app_dispatcher_and_worker():
    base = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "BASIRA_PERSONAL_PROJECTS: ${BASIRA_PERSONAL_PROJECTS:-0}" in base
    for name in ("app", "dispatcher", "worker"):
        assert "*platform" in service_block(base, name)  # the shared block carries the flag
    app = service_block(base, "app")
    assert "BASIRA_PASSWORD_AUTH_ENABLED: ${BASIRA_PASSWORD_AUTH_ENABLED:-0}" in app
    assert "BASIRA_PASSWORD_SELF_SIGNUP: ${BASIRA_PASSWORD_SELF_SIGNUP:-0}" in app
