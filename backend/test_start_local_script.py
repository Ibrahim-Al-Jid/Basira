"""start-local.ps1 edits lines of .env.local, so every line it touches must exist in the example file."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
KEYS = ("BASIRA_GITHUB_CLIENT_ID", "BASIRA_GITHUB_APP_SLUG", "BASIRA_GITHUB_CLIENT_SECRET",
        "BASIRA_GITHUB_CREDENTIAL_KEY", "BASIRA_GITHUB_CALLBACK_URL")


def test_script_and_example_agree_on_github_lines():
    script = (ROOT / "ops" / "start-local.ps1").read_text(encoding="utf-8")
    example = (ROOT / "ops" / "platform.env.example").read_text(encoding="utf-8")
    for key in KEYS:
        assert key in script
        assert re.search(rf"(?m)^{key}=", example)
    assert "Initialize-GitHubSettings $settings" in script
    assert "Test-CredentialKey" in script
