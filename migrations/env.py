import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# 1. TASLAMANYŇ KÖK ÝOLUNY PYTHON PATH-A GOŞÝARYS (app modulyny tapmagy üçin)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Indi Pydantic settings-i arkaýyn import edip bileris
from app.core.config import settings

# This is the Alembic Config object
config = context.config

# 2. PYDANTIC-DEN GELÝÄN URL-I ALEMBIC-E GÖNI MEJBUR EDÝÄRIS
# 'Alembic_URL' uly-kiçi harplaryna üns beriň (klasyňyzda nähili ýazan bolsaňyz)
config.set_main_option("sqlalchemy.url", settings.Alembic_URL)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# target_metadata = MyModel.metadata (Eger model importyňyz bar bolsa şu ýere goşuň)
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine and associate a connection with the context."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()