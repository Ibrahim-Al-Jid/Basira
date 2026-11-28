import json

from .project_map import MAX_ITEMS, project_map

DIGEST = "a" * 64
FILES = {
    "app.py": "from flask import Flask\napp = Flask(__name__)\n@app.get('/users/<id>')\ndef u(id): pass\n@app.post('/login')\ndef l(): pass\nimport sqlite3\n",
    "web/server.js": "const app = require('express')();\napp.get('/health', h);\nconst cp = require('child_process');\n",
    "index.php": "<?php $f = $_FILES['a']; ?>",
    "requirements.txt": "flask\n",
    "build/Dockerfile": "FROM python:3\n",
    ".env.production": "A=1\n",
    "main.go": "package main",
    "README.md": "secret-looking text that must not appear in the map",
}


def test_map_lists_languages_routes_config_manifests_and_boundaries():
    result = project_map(FILES, DIGEST)
    assert result["digest"] == DIGEST
    assert result["languages"] == {"go": 1, "javascript": 1, "php": 1, "python": 1}
    assert {"method": "GET", "path": "/users/<id>", "file": "app.py"} in result["routes"]
    assert {"method": "POST", "path": "/login", "file": "app.py"} in result["routes"]
    assert {"method": "GET", "path": "/health", "file": "web/server.js"} in result["routes"]
    assert result["manifests"] == ["requirements.txt"]
    assert result["config_files"] == [".env.production", "build/Dockerfile"]
    assert set(result["entry_points"]) == {"app.py", "index.php", "main.go", "web/server.js"}
    kinds = {(row["kind"], row["file"]) for row in result["boundaries"]}
    assert {("database", "app.py"), ("process_exec", "web/server.js"), ("file_upload", "index.php")} <= kinds


def test_map_is_deterministic_and_holds_no_file_bodies():
    first = project_map(FILES, DIGEST)
    assert first == project_map(dict(reversed(list(FILES.items()))), DIGEST)
    assert "must not appear" not in json.dumps(first)
    assert "from flask" not in json.dumps(first)


def test_map_is_bounded_and_handles_empty_input():
    assert project_map({}, DIGEST)["languages"] == {}
    many = {f"r{n}.py": "@app.get('/a')\ndef f(): pass\n" for n in range(MAX_ITEMS + 50)}
    result = project_map(many, DIGEST)
    assert len(result["routes"]) == MAX_ITEMS and result["languages"] == {"python": MAX_ITEMS + 50}
