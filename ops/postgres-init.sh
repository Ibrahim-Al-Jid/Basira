#!/bin/sh
set -eu

psql --no-psqlrc -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     --set=app_password="$BASIRA_DB_PASSWORD" --set=dispatch_password="$BASIRA_DISPATCH_PASSWORD" <<'SQL'
CREATE ROLE basira_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD :'app_password';
CREATE ROLE basira_dispatch LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD :'dispatch_password';
GRANT USAGE ON SCHEMA public TO basira_app;
GRANT USAGE ON SCHEMA public TO basira_dispatch;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO basira_app;
SQL
