"""Write a GitHub App configuration to the existing private local runtime vault."""

from getpass import getpass
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile

from cryptography.fernet import Fernet


def main():
    root = Path(__file__).resolve().parents[1]
    vault = root / "data" / "windows-local" / "provider-vault"
    if not vault.is_dir():
        raise SystemExit("The local Windows runtime vault is unavailable. For Compose use ops/platform.env.example.")
    path = vault / "github-app.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    client_id = input("GitHub App Client ID: ").strip()
    slug = input("GitHub App slug (from github.com/apps/<slug>): ").strip()
    client_secret = getpass("GitHub App Client Secret (hidden): ").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", client_id) or not re.fullmatch(r"[a-z0-9-]{1,100}", slug):
        raise SystemExit("Invalid GitHub App Client ID or slug.")
    if not client_secret:
        raise SystemExit("A GitHub App Client Secret is required.")
    credential_key = previous.get("credential_key") or Fernet.generate_key().decode("ascii")
    settings = {"client_id": client_id, "client_secret": client_secret, "slug": slug,
                "callback_url": "http://127.0.0.1:8765/api/platform/github/callback",
                "credential_key": credential_key}
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=vault, delete=False) as file:
        json.dump(settings, file)
        temporary = Path(file.name)
    temporary.replace(path)
    print("Saved. Reload http://127.0.0.1:8765/settings?tab=github")


if __name__ == "__main__":
    main()
