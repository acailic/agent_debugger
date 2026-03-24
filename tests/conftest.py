"""Pytest fixtures for test isolation."""
import asyncio
import os
import tempfile

import pytest

# Set environment variables BEFORE any imports that might use them
_temp_dir = tempfile.mkdtemp()
_test_db_path = os.path.join(_temp_dir, "test_agent_debugger.db")
os.environ["AGENT_DEBUGGER_DB_URL"] = f"sqlite+aiosqlite:///{_test_db_path}"

from agent_debugger_sdk import config as cfg_mod


def pytest_configure(config):
    """Configure pytest before test collection."""
    # Ensure environment is set up before any test collection
    os.environ["AGENT_DEBUGGER_DB_URL"] = f"sqlite+aiosqlite:///{_test_db_path}"


def pytest_unconfigure(config):
    """Cleanup after all tests."""
    import shutil
    shutil.rmtree(_temp_dir, ignore_errors=True)


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
def setup_test_db():
    """Ensure database tables exist for tests."""
    import asyncio

    from api import app_context
    from storage import Base
    from storage.engine import create_db_engine

    async def _setup():
        engine = create_db_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        app_context.init_app_context()

    # Run async setup synchronously for session-scoped fixture
    asyncio.run(_setup())
    yield
