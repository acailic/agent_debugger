"""Alembic environment configuration."""

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Add parent directory to path to enable imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from storage.models import Base

config = context.config
# Guard on existence, not just non-None: when the server runs from an
# installed wheel, storage/engine.py points config_file_name at
# <site-packages>/alembic.ini, which the wheel does not ship (it overrides
# script_location and sqlalchemy.url explicitly). fileConfig raises
# FileNotFoundError on a missing file, so without this guard the installed
# server crashes during lifespan migrations.
if config.config_file_name is not None and os.path.exists(config.config_file_name):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def get_url() -> str:
    return os.environ.get(
        "AGENT_DEBUGGER_DB_URL",
        config.get_main_option("sqlalchemy.url", "sqlite+aiosqlite:///./data/agent_debugger.db"),
    )


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(get_url())
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
