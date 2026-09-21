import os
from logging.config import fileConfig

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


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
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
