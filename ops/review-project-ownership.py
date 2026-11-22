"""List quarantined ownership records or apply an independently approved assignment."""

import argparse
import json
import os
import re

from sqlalchemy import create_engine, text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project")
    parser.add_argument("--owner")
    parser.add_argument("--decision-ref", help="Reference to the approved internal ownership decision")
    args = parser.parse_args()
    assignment = any((args.project, args.owner, args.decision_ref))
    if assignment and (
        not all(re.fullmatch(r"[a-f0-9]{32}", value or "") for value in (args.project, args.owner))
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/#-]{0,159}", args.decision_ref or "")
    ):
        parser.error("Supply valid --project, --owner and --decision-ref together.")
    url = os.environ.get("MARSAD_PLATFORM_MIGRATION_URL")
    if not url:
        parser.error("Set MARSAD_PLATFORM_MIGRATION_URL to the intended administrator connection.")
    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.begin() as db:
            if not assignment:
                reviews = db.execute(text("""
                    SELECT project_id, reason FROM project_ownership_reviews
                    WHERE resolved_at IS NULL ORDER BY project_id
                """)).mappings()
                print(json.dumps([dict(row) for row in reviews]))
                return
            params = {"project": args.project, "owner": args.owner, "reference": args.decision_ref}
            updated = db.execute(text("""
                UPDATE projects SET owner_user_id = :owner
                WHERE id = :project AND owner_user_id IS NULL AND deleted_at IS NULL
                  AND EXISTS (SELECT 1 FROM users WHERE id = :owner AND disabled_at IS NULL)
                  AND EXISTS (
                      SELECT 1 FROM project_ownership_reviews
                      WHERE project_id = :project AND resolved_at IS NULL
                  )
            """), params)
            if updated.rowcount != 1:
                raise SystemExit("Ownership already resolved, project unavailable, or account not enabled.")
            reviewed = db.execute(text("""
                UPDATE project_ownership_reviews
                SET resolved_at = CURRENT_TIMESTAMP, resolution_ref = :reference
                WHERE project_id = :project AND resolved_at IS NULL
            """), params)
            if reviewed.rowcount != 1:
                raise SystemExit("Ownership review changed during the assignment.")
        print("Ownership assigned. Historical records were preserved.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
