"""Provision the optional gateway login and advance the platform schema."""
import os
import re
from subprocess import run

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

GATEWAY_ROLE = "basira_model_gateway"


def database():
    url = make_url(os.environ["BASIRA_PLATFORM_MIGRATION_URL"])
    return psycopg.connect(url.set(drivername="postgresql").render_as_string(hide_password=False))


def provision(password):
    if not re.fullmatch(r"[0-9A-Za-z]{24,128}", password):
        raise SystemExit("BASIRA_MODEL_DB_PASSWORD must have 24–128 ASCII alphanumeric characters.")
    with database() as db:
        db.execute("SELECT pg_advisory_xact_lock(38571462)")
        exists = db.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (GATEWAY_ROLE,)).fetchone()
        action = sql.SQL("ALTER ROLE" if exists else "CREATE ROLE")
        db.execute(sql.SQL("{} {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD {}")
                   .format(action, sql.Identifier(GATEWAY_ROLE), sql.Literal(password)))


password = os.environ.get("BASIRA_MODEL_DB_PASSWORD", "")
if password:
    provision(password)
run(["alembic", "upgrade", "head"], check=True)
if password:
    with database() as db:
        role = sql.Identifier(GATEWAY_ROLE)
        db.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
        db.execute(sql.SQL(
            "GRANT EXECUTE ON FUNCTION public.basira_model_credential(text,text), "
            "public.basira_start_model_call(text,text,text,text,text,text), "
            "public.basira_start_account_model_call(text,text,text,text,text,text) TO {}"
        ).format(role))
