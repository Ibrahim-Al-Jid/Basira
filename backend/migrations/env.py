"""Migrate the project platform explicitly with Alembic."""

import os

from alembic import context

from backend import advanced_reporting  # noqa: F401 - register project and review tables
from backend import password_auth  # noqa: F401 - register local credential tables
from backend.platform_db import Base, database_engine, platform_database_url


def migration_url():
    return os.environ.get("MARSAD_PLATFORM_MIGRATION_URL") or platform_database_url()


def run_migrations():
    url = migration_url()
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=Base.metadata, literal_binds=True,
                          dialect_opts={"paramstyle": "named"})
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = database_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
