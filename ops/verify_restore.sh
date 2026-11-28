#!/usr/bin/env sh
# Back up a Basira database, restore it into a scratch database, and prove nothing was lost.
#
# The security posture is part of the data here: row level security flags, policies, the definer
# functions and the application role's grants all have to survive a dump and a restore, not just the
# rows. A restore that silently drops a policy is a restore that hands one tenant another tenant's
# rows, and nothing in the application would notice.
#
# Usage (all three URLs are libpq connection strings). The file is checked in without the
# executable bit, so run it through sh:
#   BASIRA_RESTORE_SOURCE_URL=postgresql://.../basira \
#   BASIRA_RESTORE_ADMIN_URL=postgresql://.../postgres \
#   BASIRA_RESTORE_TARGET_URL=postgresql://.../basira_restore_check \
#   sh ops/verify_restore.sh
#
# The scratch database is dropped and recreated, so point TARGET at a database nobody else uses.
# Set PG_DUMP and PG_RESTORE when the default binaries do not match the server major version.
set -eu

SOURCE_URL=${BASIRA_RESTORE_SOURCE_URL:?set BASIRA_RESTORE_SOURCE_URL}
ADMIN_URL=${BASIRA_RESTORE_ADMIN_URL:?set BASIRA_RESTORE_ADMIN_URL}
TARGET_URL=${BASIRA_RESTORE_TARGET_URL:?set BASIRA_RESTORE_TARGET_URL}
SCRATCH_DB=${BASIRA_RESTORE_SCRATCH_DB:-basira_restore_check}
PG_DUMP=${PG_DUMP:-pg_dump}
PG_RESTORE=${PG_RESTORE:-pg_restore}

DUMP=$(mktemp "${TMPDIR:-/tmp}/basira-restore-XXXXXX.dump")
trap 'rm -f "$DUMP"' EXIT

# One row of counts: tables, policies, functions, tables with row level security, and the migration.
SHAPE="SELECT (SELECT count(*) FROM pg_tables WHERE schemaname = 'public')
            || '/' || (SELECT count(*) FROM pg_policies WHERE schemaname = 'public')
            || '/' || (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                       WHERE n.nspname = 'public')
            || '/' || (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                       WHERE n.nspname = 'public' AND c.relrowsecurity)
            || '/' || (SELECT version_num FROM alembic_version)"

# The application role's reach, which a restore can quietly widen back to the default grants.
POSTURE="SELECT has_table_privilege('basira_app', 'users', 'DELETE')
             || '/' || has_table_privilege('basira_app', 'password_attempt_limits', 'SELECT')
             || '/' || has_function_privilege('basira_app', 'public.basira_login_identity(text,text)', 'EXECUTE')
             || '/' || (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                        WHERE n.nspname = 'public' AND p.prosecdef
                          AND has_function_privilege('public', p.oid, 'EXECUTE'))"

echo "dumping $SOURCE_URL"
"$PG_DUMP" "$SOURCE_URL" -Fc -f "$DUMP"

echo "restoring into $SCRATCH_DB"
psql "$ADMIN_URL" -q -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $SCRATCH_DB"
psql "$ADMIN_URL" -q -v ON_ERROR_STOP=1 -c "CREATE DATABASE $SCRATCH_DB"
"$PG_RESTORE" -d "$TARGET_URL" "$DUMP"

fail=0
for probe in SHAPE POSTURE; do
    if [ "$probe" = "SHAPE" ]; then statement=$SHAPE; else statement=$POSTURE; fi
    source_value=$(psql "$SOURCE_URL" -Atc "$statement")
    target_value=$(psql "$TARGET_URL" -Atc "$statement")
    if [ "$source_value" = "$target_value" ]; then
        echo "$probe matches: $source_value"
    else
        echo "$probe differs: source $source_value, restored $target_value" >&2
        fail=1
    fi
done

if [ "$fail" -ne 0 ]; then
    echo "restore check failed" >&2
    exit 1
fi
echo "restore check passed"
