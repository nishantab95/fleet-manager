from __future__ import annotations

import os
from collections.abc import Iterator
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import engine_from_config, pool

from fleet_api.db import models  # noqa: F401
from fleet_api.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Keep the checked-in Alembic default useful for local development, while
# allowing CI and isolated test databases to select their URL explicitly.
environment_database_url = os.getenv("FLEET_TEST_DATABASE_URL") or os.getenv("FLEET_DATABASE_URL")
if environment_database_url:
    config.set_main_option("sqlalchemy.url", environment_database_url)

target_metadata = Base.metadata


class _EmptyOfflineResult:
    """Empty result used only while rendering a fresh-database SQL script.

    Historical revisions 0011, 0014, and 0016 inspect rows so their online
    migrations can preserve existing data. A base-to-head offline script has
    no pre-existing business rows, so those reads deterministically return an
    empty result without changing the deployed revision files.
    """

    def __iter__(self) -> Iterator[Any]:
        return iter(())

    def mappings(self) -> _EmptyOfflineResult:
        return self

    def scalar_one(self) -> int:
        return 0


class _EmptyDatabaseOfflineBind:
    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        if str(statement).lstrip().upper().startswith("SELECT"):
            return _EmptyOfflineResult()
        return self._delegate.execute(statement, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    migration_context = context.get_context()
    assert migration_context.impl.connection is not None
    migration_context.impl.connection = _EmptyDatabaseOfflineBind(migration_context.impl.connection)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": 2},
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
