"""Deterministic map of a submitted project (the Scout's output). No model, no network, no file bodies.

The map holds paths, counts and short route strings only, so it is safe to store and to hand to a model."""
import re
from pathlib import PurePosixPath

from .checks.source_code import OTHER_CODE_SUFFIXES, language

MAX_ITEMS = 200
LANGUAGE_NAMES = {"php": "php", "js": "javascript", "py": "python"}
MANIFESTS = frozenset({
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "requirements.txt", "pyproject.toml",
    "poetry.lock", "pipfile", "pipfile.lock", "composer.json", "composer.lock", "gemfile", "gemfile.lock",
    "go.mod", "go.sum", "cargo.toml", "cargo.lock", "pom.xml", "build.gradle",
})
CONFIG_PREFIXES = ("dockerfile", ".env", "docker-compose", "compose.", ".npmrc")
CONFIG_NAMES = frozenset({"nginx.conf", ".htaccess", "web.config", "php.ini", "settings.py", "application.properties"})
ENTRY_NAMES = frozenset({
    "main.py", "app.py", "wsgi.py", "asgi.py", "manage.py", "server.js", "app.js", "index.js", "index.php",
    "main.go", "main.rs",
})
PY_ROUTE = re.compile(r"@\w+\.(get|post|put|patch|delete|route)\(\s*['\"]([^'\"]{1,120})['\"]")
JS_ROUTE = re.compile(r"\b(?:app|router|server)\.(get|post|put|patch|delete|all)\(\s*['\"`]([^'\"`]{1,120})['\"`]")
BOUNDARIES = (
    ("database", re.compile(r"\b(?:sqlite3|psycopg2?|pymysql|mysqli_|PDO\(|sequelize|mongoose|sqlalchemy)\b", re.I)),
    ("file_upload", re.compile(r"\$_FILES|multipart|UploadFile|multer|request\.files", re.I)),
    ("outbound_http", re.compile(r"\b(?:requests\.(?:get|post)|httpx\.|urllib\.request|fetch\(|axios\.|curl_init|file_get_contents\(\s*\$)", re.I)),
    ("process_exec", re.compile(r"\b(?:subprocess\.|os\.system|child_process|shell_exec|exec\(|passthru\()", re.I)),
    ("auth", re.compile(r"\b(?:jwt|session_start|login_required|passport|bcrypt|password_hash)\b", re.I)),
)


def project_map(files, digest):
    """files: path -> text, as produced by the intake. Returns the same map for the same input."""
    languages, entry_points, routes, config_files, manifests, boundaries = {}, [], [], [], [], []
    for path in sorted(files):
        name = PurePosixPath(path).name.lower()
        lang = language(path)
        suffix = PurePosixPath(path).suffix.lower()
        if lang:
            languages[LANGUAGE_NAMES[lang]] = languages.get(LANGUAGE_NAMES[lang], 0) + 1
        elif suffix in OTHER_CODE_SUFFIXES:
            languages[suffix[1:]] = languages.get(suffix[1:], 0) + 1
        if name in MANIFESTS:
            manifests.append(path)
        if name in CONFIG_NAMES or name.startswith(CONFIG_PREFIXES):
            config_files.append(path)
        if name in ENTRY_NAMES:
            entry_points.append(path)
        text = files[path] or ""
        if lang in ("py", "js"):
            for method, route in (PY_ROUTE if lang == "py" else JS_ROUTE).findall(text):
                routes.append({"method": method.upper(), "path": route, "file": path})
        if lang or suffix in OTHER_CODE_SUFFIXES:
            for kind, pattern in BOUNDARIES:
                if pattern.search(text):
                    boundaries.append({"kind": kind, "file": path})
    return {
        "digest": digest, "languages": dict(sorted(languages.items())),
        "entry_points": entry_points[:MAX_ITEMS], "routes": routes[:MAX_ITEMS],
        "config_files": config_files[:MAX_ITEMS], "manifests": manifests[:MAX_ITEMS],
        "boundaries": boundaries[:MAX_ITEMS],
    }
