"""Register a private GitHub App from the local operator's browser."""

import argparse
from getpass import getpass
from hmac import compare_digest
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
from secrets import token_hex, token_urlsafe
from tempfile import NamedTemporaryFile
from time import monotonic
from urllib.parse import parse_qs, urlencode, urlsplit
import webbrowser

from cryptography.fernet import Fernet
import httpx

PROJECT_URL = "https://github.com/Ibrahim-Al-Jid/Basira"
GITHUB_REGISTRATION = "https://github.com/settings/apps/new"


def save_config(path, callback, client_id, slug, client_secret):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", client_id) or not re.fullmatch(r"[a-z0-9-]{1,100}", slug):
        raise SystemExit("Invalid GitHub App Client ID or slug.")
    if not client_secret or len(client_secret) > 512:
        raise SystemExit("A valid GitHub App Client Secret is required.")
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    credential_key = previous.get("credential_key") or Fernet.generate_key().decode("ascii")
    settings = {"client_id": client_id, "client_secret": client_secret, "slug": slug,
                "callback_url": callback, "credential_key": credential_key}
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
        json.dump(settings, file)
        temporary = Path(file.name)
    temporary.replace(path)


def manifest(callback, registration_callback):
    return {
        "name": "Basira Repository Review " + token_hex(4),
        "url": PROJECT_URL,
        "public": False,
        "hook_attributes": {"url": PROJECT_URL, "active": False},
        "redirect_url": registration_callback,
        "callback_urls": [callback],
        "default_permissions": {"contents": "read"},
        "request_oauth_on_install": False,
    }


def convert_registration(code):
    endpoint = f"https://api.github.com/app-manifests/{code}/conversions"
    with httpx.Client(timeout=15, trust_env=False) as client:
        response = client.post(endpoint, headers={
            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10",
        })
        response.raise_for_status()
        data = response.json()
    permissions = data["permissions"]
    if (data.get("public") is True or not isinstance(permissions, dict)
            or permissions.get("contents") != "read"
            or any(key not in {"contents", "metadata"} or value != "read" for key, value in permissions.items())):
        raise ValueError("Unexpected GitHub permissions")
    fields = data["client_id"], data["slug"], data["client_secret"]
    if not all(isinstance(field, str) for field in fields):
        raise ValueError("Invalid GitHub registration")
    return fields


def register(path, origin, callback):
    start_path = "/start/" + token_urlsafe(24)
    state = token_urlsafe(32)
    registered = False

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(3)
            super().setup()

        def log_message(self, *_args):
            pass

        def reply(self, status, body):
            data = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                    '<title>Basira GitHub setup</title><main>' + body + '</main></html>').encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; form-action https://github.com; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            nonlocal registered
            target = urlsplit(self.path)
            if self.headers.get("Host") != authority:
                self.reply(404, "<p>This setup link is unavailable.</p>")
                return
            if target.path == start_path:
                action = escape(GITHUB_REGISTRATION + "?" + urlencode({"state": state}), quote=True)
                payload = escape(json.dumps(application), quote=True)
                self.reply(200, '<h1>Set up GitHub for Basira</h1><p>Create a private app with read access to selected repositories.</p>'
                                f'<form method="post" action="{action}"><input type="hidden" name="manifest" value="{payload}">'
                                '<button>Create on GitHub</button></form>')
                return
            fields = parse_qs(target.query)
            code = fields.get("code", [""])[0]
            received_state = fields.get("state", [""])[0]
            if (target.path != "/complete" or registered or not received_state.isascii()
                    or not compare_digest(received_state, state) or not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", code)):
                self.reply(400, "<p>Invalid setup callback. Open the setup link again.</p>")
                return
            try:
                client_id, slug, secret = convert_registration(code)
                save_config(path, callback, client_id, slug, secret)
            except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError, SystemExit):
                self.reply(502, "<p>GitHub setup could not be saved. Check the app settings on GitHub or use manual setup.</p>")
                return
            registered = True
            self.reply(200, f'<h1>GitHub App saved</h1><p><a href="https://github.com/apps/{slug}/installations/new" '
                            'target="_blank" rel="noreferrer">Install on selected repositories</a></p>'
                            f'<p><a href="{origin}/settings?tab=github">Return to Basira and connect GitHub</a></p>')

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        authority = f"127.0.0.1:{server.server_port}"
        application = manifest(callback, f"http://{authority}/complete")
        setup_url = f"http://{authority}{start_path}"
        print(f"Open this one-time setup link: {setup_url}", flush=True)
        webbrowser.open(setup_url)
        server.timeout = 1
        deadline = monotonic() + 600
        while not registered and monotonic() < deadline:
            server.handle_request()
    if not registered:
        raise SystemExit("GitHub setup expired. Run the command again.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765, help="local Basira web port")
    parser.add_argument("--manual", action="store_true", help="configure an existing GitHub App")
    parser.add_argument("--client-id", help="existing GitHub App Client ID")
    parser.add_argument("--slug", help="existing GitHub App slug")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("--port must be between 1024 and 65535")
    if not args.manual and (args.client_id or args.slug):
        parser.error("--client-id and --slug require --manual")
    root = Path(__file__).resolve().parents[1]
    path = root / "data" / "windows-local" / "provider-vault" / "github-app.json"
    origin = f"http://127.0.0.1:{args.port}"
    callback = origin + "/api/platform/github/callback"
    if args.manual:
        client_id = args.client_id or input("GitHub App Client ID: ").strip()
        slug = args.slug or input("GitHub App slug (from github.com/apps/<slug>): ").strip()
        secret = getpass("GitHub App Client Secret (hidden): ").strip()
        save_config(path, callback, client_id, slug, secret)
    elif path.is_file():
        raise SystemExit(f"GitHub App already configured. Open {origin}/settings?tab=github")
    else:
        register(path, origin, callback)
    print(f"Saved. Open {origin}/settings?tab=github")


if __name__ == "__main__":
    main()
