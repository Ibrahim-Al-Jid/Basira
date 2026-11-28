"""Take a PostgreSQL backup of the platform database and check that the archive is readable.

The runbook in docs/PLATFORM.md describes the full procedure (freeze writes, dump, restore into an
empty database, compare counts). This script is the repeatable part of it: it produces a
`pg_dump -Fc` archive named after the current UTC time and verifies the archive with
`pg_restore --list`, so a corrupt dump fails here instead of at restore time.

Usage:
    BASIRA_PLATFORM_MIGRATION_URL=postgresql://postgres@host/basira python ops/backup-platform.py
    python ops/backup-platform.py --url postgresql://postgres@host/basira --output-dir backups

Requires the `pg_dump` and `pg_restore` binaries (the PostgreSQL client package).
"""

import argparse
import datetime
import os
import subprocess
import sys


def database_dsn(url):
    # pg_dump takes a plain postgresql:// DSN; the app config may carry a SQLAlchemy driver suffix.
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=os.environ.get("BASIRA_PLATFORM_MIGRATION_URL"),
                        help="database DSN (default: BASIRA_PLATFORM_MIGRATION_URL)")
    parser.add_argument("--output-dir", default="backups", help="directory for the archive")
    args = parser.parse_args()
    if not args.url:
        parser.error("no database URL: pass --url or set BASIRA_PLATFORM_MIGRATION_URL")

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    os.makedirs(args.output_dir, exist_ok=True)
    archive = os.path.join(args.output_dir, f"basira-{stamp}.dump")

    dsn = database_dsn(args.url)
    try:
        subprocess.run(["pg_dump", "--format=custom", "--file", archive, dsn], check=True)
    except subprocess.CalledProcessError:
        # Do not leave a partial archive behind: it would look like a valid backup.
        if os.path.exists(archive):
            os.remove(archive)
        raise
    # A dump that pg_restore cannot list would also fail at restore time.
    listing = subprocess.run(["pg_restore", "--list", archive], check=True,
                             capture_output=True, text=True)
    entries = sum(1 for line in listing.stdout.splitlines() if line and not line.startswith(";"))
    size = os.path.getsize(archive)
    print(f"{archive}: {size} bytes, {entries} entries; verified with pg_restore --list")
    if entries == 0:
        sys.exit("backup archive is empty")


if __name__ == "__main__":
    main()
