import os
from unittest.mock import patch


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
