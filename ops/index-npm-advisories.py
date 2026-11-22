"""Build the package index for a checksum-pinned official OSV npm archive."""

import argparse
import json
from pathlib import Path
import re
import sqlite3
from zipfile import ZipFile
import zlib


def build_index(archive, output):
    if output.exists():
        raise ValueError("Build the index at a new path")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive) as feed, sqlite3.connect(output) as db:
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA synchronous=OFF")
        db.executescript("""
            CREATE TABLE advisories (id TEXT PRIMARY KEY, compressed BLOB NOT NULL) WITHOUT ROWID;
            CREATE TABLE packages (
                name TEXT NOT NULL, advisory_id TEXT NOT NULL,
                PRIMARY KEY (name, advisory_id)
            ) WITHOUT ROWID;
            PRAGMA user_version=1;
        """)
        for item in feed.infolist():
            if item.is_dir():
                continue
            if item.file_size > 2_000_000 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,79}\.json", item.filename):
                raise ValueError("Unexpected member in the pinned OSV archive")
            raw = feed.read(item)
            advisory = json.loads(raw)
            identifier = advisory["id"]
            if item.filename != identifier + ".json":
                raise ValueError("Unexpected advisory identity in the pinned OSV archive")
            packages = {entry["package"]["name"] for entry in advisory.get("affected", [])
                        if entry.get("package", {}).get("ecosystem") == "npm"}
            if not packages:
                continue
            db.execute("INSERT INTO advisories VALUES (?, ?)", (identifier, zlib.compress(raw, level=3)))
            db.executemany("INSERT INTO packages VALUES (?, ?)", [(name, identifier) for name in sorted(packages)])
        if not db.execute("SELECT 1 FROM packages LIMIT 1").fetchone():
            raise ValueError("The pinned OSV archive has no npm records")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    build_index(arguments.archive, arguments.output)
