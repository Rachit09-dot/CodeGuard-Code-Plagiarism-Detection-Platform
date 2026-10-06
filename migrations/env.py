"""Alembic environment — connects to the database configured via DATABASE_URL.

Usage
-----
# Create a new migration after changing models:
  alembic revision --autogenerate -m "description"

# Apply all pending migrations:
  alembic upgrade head

# Downgrade one step:
  alembic downgrade -1

# Show current revision:
  alembic current
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# Alembic config
# ---------------------------------------------------------------------------

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from DATABASE_URL env var so we never hard-code
# credentials in alembic.ini.
_database_url = os.getenv("DATABASE_URL", "sqlite:///./plagiarism.db")
config.set_main_option("sqlalchemy.url", _database_url)

# Import the project's declarative Base so autogenerate can diff models.
from backend.models import Base  # noqa: E402

target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection needed)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (live DB connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
