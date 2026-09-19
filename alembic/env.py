"""Alembic ortam dosyası.

`sqlalchemy.url` çalışma zamanında `app.core.config`'ten okunur; `.env`
yönetimi tek noktadan akar.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from alembic import context
from app.core.config import get_settings
from app.db import models  # noqa: F401  (Base.metadata'yı doldurur)
from app.db.base import Base
from app.db.migration_bootstrap import (
    VersionTableOutput,
    bootstrap_version_table,
    write_version_table_prelude,
)
from app.db.session import _normalize_db_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Render/Heroku `postgresql://` → `postgresql+psycopg://` (psycopg v3) normalize.
config.set_main_option(
    "sqlalchemy.url", _normalize_db_url(get_settings().database_url)
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    output = config.output_buffer or sys.stdout
    if make_url(url).get_backend_name() == "postgresql":
        write_version_table_prelude(output)
        output = VersionTableOutput(output)
    context.configure(
        url=url,
        output_buffer=output,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        bootstrap_version_table(connection)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
