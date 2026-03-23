"""Pytest fixtures for test isolation."""
import asyncio
import os
import tempfile

import pytest

from agent_debugger_sdk import config as cfg_mod


@pytest.fixture(autouse=True)
def reset_global_config():
    """Reset global SDK config before and after each test to ensure isolation."""
    original_config = cfg_mod._global_config
    cfg_mod._global_config = None
    yield
    cfg_mod._global_config = original_config


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment before any tests run."""
    # Use a temporary file-based database for tests
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_agent_debugger.db")
    os.environ["AGENT_DEBUGGER_DB_URL"] = f"sqlite+aiosqlite:///{db_path}"
    yield
    # Cleanup
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
async def setup_test_db():
    """Ensure database tables exist for each test."""
    from storage import Base
    from storage.engine import create_db_engine

    engine = create_db_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
