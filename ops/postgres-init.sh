#!/bin/sh
set -eu

psql --no-psqlrc -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     --set=app_password="$MARSAD_DB_PASSWORD" --set=dispatch_password="$MARSAD_DISPATCH_PASSWORD" <<'SQL'
CREATE ROLE marsad_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD :'app_password';
CREATE ROLE marsad_dispatch LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD :'dispatch_password';
GRANT USAGE ON SCHEMA public TO marsad_app;
GRANT USAGE ON SCHEMA public TO marsad_dispatch;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO marsad_app;
SQL
