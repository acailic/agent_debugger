"""Config-driven database engine factory."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./data/agent_debugger.db"


def get_database_url() -> str:
    return os.environ.get("AGENT_DEBUGGER_DB_URL", DEFAULT_SQLITE_URL)


def create_db_engine(url: str | None = None, **kwargs) -> AsyncEngine:
    db_url = url or get_database_url()
    defaults = {"echo": False}
    if "sqlite" in db_url:
        defaults["connect_args"] = {"check_same_thread": False}
    defaults.update(kwargs)
    return create_async_engine(db_url, **defaults)


def create_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _create_alembic_config(db_url: str) -> AlembicConfig:
    project_root = _project_root()
    config = AlembicConfig(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "storage" / "migrations"))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


def _run_migrations(db_url: str) -> None:
    command.upgrade(_create_alembic_config(db_url), "head")


def _repair_legacy_sqlite_schema(connection) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    repaired_legacy = False
    session_columns = set()
    if "sessions" in tables:
        session_columns = {column["name"] for column in inspector.get_columns("sessions")}
        if "replay_value" not in session_columns:
            connection.execute(text("ALTER TABLE sessions ADD COLUMN replay_value FLOAT NOT NULL DEFAULT 0.0"))
            repaired_legacy = True
            session_columns.add("replay_value")

        if "fix_note" not in session_columns:
            connection.execute(text("ALTER TABLE sessions ADD COLUMN fix_note TEXT"))
            repaired_legacy = True
            session_columns.add("fix_note")

        session_indexes = {index["name"] for index in inspector.get_indexes("sessions")}
        if "ix_sessions_replay_value" not in session_indexes:
            connection.execute(text("CREATE INDEX ix_sessions_replay_value ON sessions (replay_value)"))
            repaired_legacy = True

    legacy_tables = {"sessions", "events", "checkpoints"}
    if "alembic_version" not in tables and legacy_tables.issubset(tables):
        connection.execute(
            text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        )
        connection.execute(text("DELETE FROM alembic_version"))
        # Determine the correct stamp version based on which columns already exist.
        # If the schema was created via Base.metadata.create_all, all columns from
        # the latest models are present and we must stamp at the latest migration
        # to prevent Alembic from trying to re-add existing columns.
        if "fix_note" in session_columns:
            stamp_version = "004_add_session_fix_note"
        elif "retention_tier" in session_columns:
            stamp_version = "003_add_research_features"
        else:
            stamp_version = "002_add_session_replay_value"
        connection.execute(text(f"INSERT INTO alembic_version (version_num) VALUES ('{stamp_version}')"))
        repaired_legacy = True

    return repaired_legacy


async def prepare_database(engine: AsyncEngine, url: str | None = None) -> None:
    """Ensure the configured database schema is ready for the current code."""
    from storage import Base

    db_url = url or get_database_url()

    if "sqlite" in db_url and ":memory:" in db_url:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return

    if "sqlite" in db_url:
        async with engine.begin() as conn:
            repaired_legacy = await conn.run_sync(_repair_legacy_sqlite_schema)
        if repaired_legacy:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return

    await asyncio.to_thread(_run_migrations, db_url)

    # Keep create_all as a backstop for newly added tables while Alembic handles
    # column and index evolution for existing local databases.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
