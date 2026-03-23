import datetime

import pytest
import pytest_asyncio
from agent_debugger_sdk.core.events import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from storage.models import Base
from storage.models import SessionModel
from storage.repository import TraceRepository


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_tenant_id_on_session_model():
    """SessionModel must have a tenant_id column."""
    assert hasattr(SessionModel, "tenant_id")


@pytest.mark.asyncio
async def test_list_sessions_filters_by_tenant(db_session):
    """list_sessions should only return sessions for the given tenant."""
    repo = TraceRepository(db_session, tenant_id="tenant_a")
    session_a = Session(
        id="sess-a", agent_name="agent", framework="test",
        started_at=datetime.datetime.now(datetime.UTC),
        ended_at=None, status="running", total_tokens=0,
        total_cost_usd=0.0, tool_calls=0, llm_calls=0,
        errors=0, config={}, tags=[],
    )
    await repo.create_session(session_a)

    repo_b = TraceRepository(db_session, tenant_id="tenant_b")
    sessions_b = await repo_b.list_sessions()
    assert len(sessions_b) == 0, "Tenant B should not see Tenant A sessions"

    sessions_a = await repo.list_sessions()
    assert len(sessions_a) == 1
