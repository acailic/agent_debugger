import os
import sqlite3
from unittest.mock import patch

import pytest


def test_default_engine_is_sqlite():
    """Without env var, engine should be SQLite."""
    from storage.engine import get_database_url

    with patch.dict(os.environ, {}, clear=True):
        url = get_database_url()
        assert "sqlite" in url


def test_env_var_overrides_engine():
    """AGENT_DEBUGGER_DB_URL should override default."""
    from storage.engine import get_database_url

    with patch.dict(os.environ, {"AGENT_DEBUGGER_DB_URL": "postgresql+asyncpg://localhost/debugger"}):
        url = get_database_url()
        assert "postgresql" in url


def test_create_engine_returns_async_engine():
    """create_engine should return an AsyncEngine."""
    from storage.engine import create_db_engine

    engine = create_db_engine("sqlite+aiosqlite:///:memory:")
    assert engine is not None


@pytest.mark.asyncio
async def test_prepare_database_migrates_existing_sqlite_file(tmp_path):
    """Existing local SQLite databases should be upgraded before use."""
    from storage.engine import create_db_engine, prepare_database

    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE sessions (
            id VARCHAR(36) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL,
            agent_name VARCHAR(255) NOT NULL,
            framework VARCHAR(100) NOT NULL,
            started_at DATETIME NOT NULL,
            ended_at DATETIME,
            status VARCHAR(32) NOT NULL,
            total_tokens INTEGER NOT NULL,
            total_cost_usd FLOAT NOT NULL,
            tool_calls INTEGER NOT NULL,
            llm_calls INTEGER NOT NULL,
            errors INTEGER NOT NULL,
            config JSON NOT NULL,
            tags JSON NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE events (
            id VARCHAR(36) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL,
            session_id VARCHAR(36),
            parent_id VARCHAR(36),
            event_type VARCHAR(32),
            timestamp DATETIME,
            name VARCHAR(255),
            data JSON,
            event_metadata JSON,
            importance FLOAT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE checkpoints (
            id VARCHAR(36) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL,
            session_id VARCHAR(36),
            event_id VARCHAR(36),
            sequence INTEGER,
            state JSON,
            memory JSON,
            timestamp DATETIME,
            importance FLOAT
        )
        """
    )
    conn.commit()
    conn.close()

    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_db_engine(db_url)
    try:
        await prepare_database(engine, db_url)
    finally:
        await engine.dispose()

    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    finally:
        conn.close()

    assert "replay_value" in columns
