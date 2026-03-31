"""Pytest fixtures for test isolation."""

import os
import tempfile

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Each xdist worker gets its own DB file to avoid SQLite lock contention.
_worker_id = os.environ.get("PYTEST_XDIST_WORKER_ID", "master")
_temp_dir = tempfile.mkdtemp()
_test_db_path = os.path.join(_temp_dir, f"test_agent_debugger_{_worker_id}.db")
os.environ["AGENT_DEBUGGER_DB_URL"] = f"sqlite+aiosqlite:///{_test_db_path}"

from agent_debugger_sdk import config as cfg_mod
from agent_debugger_sdk.core.events import Checkpoint, EventType, Session, SessionStatus, TraceEvent
from storage import Base


def pytest_configure(config):
    """Configure pytest before test collection."""
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


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Ensure database tables exist for tests."""
    import asyncio

    from api import app_context
    from storage import Base
    from storage.engine import create_db_engine

    async def _setup():
        # Reset app context globals so each xdist worker uses its own engine
        app_context.engine = None
        app_context.async_session_maker = None
        engine = create_db_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        app_context.init_app_context()

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


@pytest.fixture
def make_session():
    """Factory fixture to create Session instances for tests."""

    def _make(
        session_id: str = "s1",
        agent_name: str = "test_agent",
        framework: str = "custom",
        status: str = "running",
        total_tokens: int = 0,
        total_cost_usd: float = 0.0,
        **overrides,
    ) -> Session:
        return Session(
            id=session_id,
            agent_name=agent_name,
            framework=framework,
            status=SessionStatus(status),
            total_tokens=total_tokens,
            total_cost_usd=total_cost_usd,
            **overrides,
        )

    return _make


@pytest.fixture
def make_checkpoint():
    """Factory fixture to create Checkpoint instances for tests."""

    def _make(
        session_id: str = "s1",
        event_id: str = "e1",
        sequence: int = 1,
        **overrides,
    ) -> Checkpoint:
        return Checkpoint(
            session_id=session_id,
            event_id=event_id,
            sequence=sequence,
            **overrides,
        )

    return _make


@pytest.fixture
def make_decision_event():
    """Factory fixture to create decision events for tests."""

    def _make(
        session_id: str = "s1",
        reasoning: str = "test reasoning",
        confidence: float = 0.85,
        chosen_action: str = "test_action",
        id: str | None = None,
        event_id: str | None = None,  # Alias for id for backward compatibility
        **overrides,
    ) -> TraceEvent:
        # Use event_id as fallback if id not provided
        event_id_value = id or event_id
        if event_id_value:
            overrides["id"] = event_id_value

        # Build kwargs with defaults that can be overridden
        data_overrides = overrides.pop("data", {})
        kwargs = {
            "session_id": session_id,
            "parent_id": overrides.pop("parent_id", None),
            "event_type": EventType.DECISION,
            "name": overrides.pop("name", "decision"),
            "importance": overrides.pop("importance", 0.5),
            "upstream_event_ids": overrides.pop("upstream_event_ids", []),
            "data": {
                "reasoning": reasoning,
                "confidence": confidence,
                "chosen_action": chosen_action,
                "evidence": [],
                **data_overrides,
            },
        }
        kwargs.update(overrides)

        return TraceEvent(**kwargs)

    return _make


@pytest.fixture
def make_error_event():
    """Factory fixture to create error events for tests."""

    def _make(
        session_id: str = "s1",
        error_message: str = "test error",
        error_type: str = "RuntimeError",
        id: str | None = None,
        event_id: str | None = None,  # Alias for id for backward compatibility
        message: str | None = None,  # Alias for error_message for backward compatibility
        **overrides,
    ) -> TraceEvent:
        # Use event_id as fallback if id not provided
        event_id_value = id or event_id
        if event_id_value:
            overrides["id"] = event_id_value

        # Use message as fallback for error_message
        if message is not None:
            error_message = message

        # Build kwargs with defaults that can be overridden
        # Move certain overrides into data dict
        data_overrides = overrides.pop("data", {})
        for key in ["message", "error_message", "error_type"]:
            if key in overrides:
                data_overrides[key] = overrides.pop(key)

        kwargs = {
            "session_id": session_id,
            "parent_id": overrides.pop("parent_id", None),
            "event_type": EventType.ERROR,
            "name": overrides.pop("name", "error"),
            "importance": overrides.pop("importance", 0.8),
            "upstream_event_ids": overrides.pop("upstream_event_ids", []),
            "data": {
                "error_message": error_message,
                "error_type": error_type,
                **data_overrides,
            },
        }
        kwargs.update(overrides)

        return TraceEvent(**kwargs)

    return _make


@pytest.fixture
def reset_event_buffer():
    """Reset the global event buffer after each test."""
    from collector import buffer as buf_mod

    original = buf_mod._event_buffer
    buf_mod._event_buffer = None
    yield
    buf_mod._event_buffer = original


# =============================================================================
# In-memory database fixtures
# =============================================================================


@pytest.fixture
async def db_session_maker():
    """Provide an isolated session maker for tests.

    Uses a temp file so that separate connections share the same database.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()
    os.unlink(db_path)


@pytest_asyncio.fixture
async def db_session():
    """Provide an in-memory SQLite session for tests.

    Creates a fresh database for each test function.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


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
