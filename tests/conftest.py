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
from agent_debugger_sdk.core.events import EventType, TraceEvent


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


# =============================================================================
# Shared Test Factories
# =============================================================================

@pytest.fixture
def make_event():
    """Factory fixture to create TraceEvent instances for tests."""
    def _make_event(
        session_id: str = "s1",
        name: str = "test",
        event_type: EventType = EventType.TOOL_CALL,
        data: dict | None = None,
        metadata: dict | None = None,
        importance: float = 0.5,
        parent_id: str | None = None,
        upstream_event_ids: list | None = None,
    ) -> TraceEvent:
        return TraceEvent(
            session_id=session_id,
            parent_id=parent_id,
            event_type=event_type,
            name=name,
            data=data or {},
            metadata=metadata or {},
            importance=importance,
            upstream_event_ids=upstream_event_ids or [],
        )
    return _make_event


@pytest.fixture
def make_llm_event():
    """Factory fixture to create LLM response events for tests."""
    def _make_llm_event(
        content: str,
        session_id: str = "s1",
        model: str = "gpt-4",
        metadata: dict | None = None,
    ) -> TraceEvent:
        return TraceEvent(
            session_id=session_id,
            parent_id=None,
            event_type=EventType.LLM_RESPONSE,
            name="llm_response",
            importance=0.5,
            upstream_event_ids=[],
            data={"content": content, "model": model},
            metadata=metadata or {},
        )
    return _make_llm_event


# =============================================================================
# API Test Client
# =============================================================================

@pytest.fixture
async def api_client():
    """Async test client for FastAPI app."""
    from httpx import ASGITransport, AsyncClient

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
