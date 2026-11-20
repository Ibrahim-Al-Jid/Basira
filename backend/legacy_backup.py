"""Create and verify a private SQLite backup before changing legacy session data."""
import argparse
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3


def signature(connection):
    digest = hashlib.sha256()
    count = 0
    for report_id, owner in connection.execute("SELECT id, owner FROM reports ORDER BY id"):
        digest.update(f"{report_id}\x00{owner}\n".encode())
        count += 1
    return count, digest.hexdigest()


def backup(source, destination):
    source = source.resolve(strict=True)
    destination = destination.resolve()
    destination.touch(exist_ok=False)
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as origin, \
            closing(sqlite3.connect(destination)) as replica:
        origin.execute("BEGIN")
        origin.execute("SELECT count(*) FROM reports").fetchone()
        origin.backup(replica)
        if replica.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or signature(origin) != signature(replica):
            raise RuntimeError("Legacy backup verification failed.")
        return signature(replica)[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(f"Verified backup with {backup(args.source, args.destination)} reports.")


if __name__ == "__main__":
    main()
