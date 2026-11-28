#!/bin/sh
# Provision the roles a deployment runs as.
#
# Safe to run again: an existing role is left alone, so a redeploy or a second environment sharing a
# cluster does not abort before the grants below are applied. Without this, the first CREATE ROLE
# fails, set -e stops the script, and the schema usage and default privileges are never granted.
set -eu

psql --no-psqlrc -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     --set=app_password="$BASIRA_DB_PASSWORD" --set=dispatch_password="$BASIRA_DISPATCH_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE basira_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_app')
\gexec

SELECT format('CREATE ROLE basira_dispatch LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %L', :'dispatch_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'basira_dispatch')
\gexec

GRANT USAGE ON SCHEMA public TO basira_app;
GRANT USAGE ON SCHEMA public TO basira_dispatch;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO basira_app;
SQL
