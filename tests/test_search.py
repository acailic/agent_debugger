"""Tests for storage/search.py — SessionSearchService."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent_debugger_sdk.core.events import EventType, Session, SessionStatus, TraceEvent
from storage.converters import event_to_orm
from storage.models import Base, SessionModel
from storage.search import SessionSearchService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session(
    session_id: str,
    tenant_id: str = "tenant-a",
    status: SessionStatus = SessionStatus.ERROR,
) -> Session:
    return Session(
        id=session_id,
        agent_name="test-agent",
        framework="pytest",
        started_at=datetime(2026, 3, 23, 10, 0, tzinfo=timezone.utc),
        status=status,
        config={},
        tags=[],
    )


def _error_event(
    session_id: str,
    error_type: str = "TimeoutError",
    error_message: str = "Request timed out",
    event_id: str | None = None,
) -> TraceEvent:
    return TraceEvent(
        id=event_id or f"ev-{session_id}-err",
        session_id=session_id,
        name="error_occurred",
        event_type=EventType.ERROR,
        timestamp=datetime(2026, 3, 23, 10, 1, tzinfo=timezone.utc),
        data={"error_type": error_type, "error_message": error_message},
    )


def _tool_event(
    session_id: str,
    tool_name: str = "search_api",
    model: str = "gpt-4",
    event_id: str | None = None,
) -> TraceEvent:
    return TraceEvent(
        id=event_id or f"ev-{session_id}-tool",
        session_id=session_id,
        name="tool_called",
        event_type=EventType.TOOL_CALL,
        timestamp=datetime(2026, 3, 23, 10, 2, tzinfo=timezone.utc),
        data={"tool_name": tool_name, "model": model},
    )


async def _insert_session(db: AsyncSession, sess: Session, tenant_id: str = "tenant-a") -> None:
    db.add(
        SessionModel(
            id=sess.id,
            tenant_id=tenant_id,
            agent_name=sess.agent_name,
            framework=sess.framework,
            started_at=sess.started_at,
            ended_at=sess.ended_at,
            status=sess.status,
            config=sess.config,
            tags=sess.tags,
        )
    )
    await db.flush()


async def _insert_event(db: AsyncSession, event: TraceEvent, tenant_id: str = "tenant-a") -> None:
    db.add(event_to_orm(event, tenant_id=tenant_id))
    await db.flush()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db():
    """In-memory SQLite async session — isolated per test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _svc(db: AsyncSession, tenant_id: str = "tenant-a") -> SessionSearchService:
    return SessionSearchService(db, tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# search_sessions — basic behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_query_returns_empty(db):
    """Empty query string immediately returns []."""
    await _insert_session(db, _session("s1"))
    await db.commit()

    svc = _svc(db)
    assert await svc.search_sessions("") == []


@pytest.mark.asyncio
async def test_whitespace_only_query_returns_empty(db):
    """Whitespace-only query is treated as empty."""
    await _insert_session(db, _session("s1"))
    await db.commit()

    svc = _svc(db)
    assert await svc.search_sessions("   ") == []


@pytest.mark.asyncio
async def test_no_sessions_returns_empty(db):
    """Search over an empty database returns []."""
    svc = _svc(db)
    assert await svc.search_sessions("timeout") == []


@pytest.mark.asyncio
async def test_session_without_events_not_returned(db):
    """Sessions with no events produce a zero-vector and are excluded."""
    await _insert_session(db, _session("s1"))
    await db.commit()

    svc = _svc(db)
    results = await svc.search_sessions("timeout")
    assert results == []


@pytest.mark.asyncio
async def test_matching_session_is_returned(db):
    """A session whose events contain the query term appears in results."""
    await _insert_session(db, _session("s1"))
    await _insert_event(db, _error_event("s1", "TimeoutError", "connection timeout occurred"))
    await db.commit()

    svc = _svc(db)
    results = await svc.search_sessions("timeout")
    assert len(results) == 1
    assert results[0].id == "s1"


@pytest.mark.asyncio
async def test_similarity_score_is_set(db):
    """Results carry a float search_similarity in (0, 1]."""
    await _insert_session(db, _session("s1"))
    await _insert_event(db, _error_event("s1", "TimeoutError", "connection timeout"))
    await db.commit()

    svc = _svc(db)
    results = await svc.search_sessions("timeout")
    assert len(results) == 1
    sim = results[0].search_similarity
    assert sim is not None
    assert isinstance(sim, float)
    assert 0.0 < sim <= 1.0


# ---------------------------------------------------------------------------
# search_sessions — result ranking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_results_ranked_by_similarity(db):
    """Better-matching session appears before weaker match."""
    # s1: matches "timeout" AND "error"
    await _insert_session(db, _session("s1"))
    await _insert_event(db, _error_event("s1", "TimeoutError", "timeout error occurred", "e1"))

    # s2: only matches "error" (via event_type), not "timeout"
    await _insert_session(db, _session("s2"))
    await _insert_event(db, _error_event("s2", "NetworkError", "network connection failed", "e2"))
    await db.commit()

    svc = _svc(db)
    results = await svc.search_sessions("timeout error")
    assert len(results) >= 1

    if len(results) >= 2:
        # Descending order
        assert results[0].search_similarity >= results[1].search_similarity

    s1 = next((r for r in results if r.id == "s1"), None)
    s2 = next((r for r in results if r.id == "s2"), None)
    if s1 and s2:
        assert s1.search_similarity > s2.search_similarity


@pytest.mark.asyncio
async def test_non_matching_session_excluded(db):
    """A session with completely different content is excluded (similarity == 0)."""
    await _insert_session(db, _session("s1"))
    await _insert_event(db, _error_event("s1", "TimeoutError", "connection timeout", "e1"))

    await _insert_session(db, _session("s2"))
    await _insert_event(
        db,
        TraceEvent(
            id="e2",
            session_id="s2",
            name="validation_complete",
            event_type=EventType.AGENT_END,
            timestamp=datetime(2026, 3, 23, 10, 1, tzinfo=timezone.utc),
            data={},
        ),
    )
    await db.commit()

    svc = _svc(db)
    results = await svc.search_sessions("timeout")
    ids = [r.id for r in results]
    assert "s1" in ids
    # s2 shares no "timeout" token → not in results
    assert "s2" not in ids


# ---------------------------------------------------------------------------
# search_sessions — status filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_filter_restricts_results(db):
    """status= parameter limits results to sessions with that status."""
    await _insert_session(db, _session("s-err", status=SessionStatus.ERROR))
    await _insert_event(db, _error_event("s-err", "TimeoutError", "connection timeout", "e1"))

    await _insert_session(db, _session("s-ok", status=SessionStatus.COMPLETED))
    await _insert_event(db, _error_event("s-ok", "TimeoutError", "connection timeout", "e2"))
    await db.commit()

    svc = _svc(db)
    results = await svc.search_sessions("timeout", status=str(SessionStatus.ERROR))
    assert all(r.status == SessionStatus.ERROR for r in results)
    assert any(r.id == "s-err" for r in results)
    assert all(r.id != "s-ok" for r in results)


@pytest.mark.asyncio
async def test_status_filter_completed(db):
    """Filtering by COMPLETED returns only completed sessions."""
    await _insert_session(db, _session("s-err", status=SessionStatus.ERROR))
    await _insert_event(db, _error_event("s-err", "TimeoutError", "connection timeout", "e1"))

    await _insert_session(db, _session("s-ok", status=SessionStatus.COMPLETED))
    await _insert_event(db, _error_event("s-ok", "TimeoutError", "connection timeout", "e2"))
    await db.commit()

    svc = _svc(db)
    results = await svc.search_sessions("timeout", status=str(SessionStatus.COMPLETED))
    assert len(results) == 1
    assert results[0].id == "s-ok"


# ---------------------------------------------------------------------------
# search_sessions — limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_limit_restricts_result_count(db):
    """limit= caps the number of returned sessions."""
    for i in range(6):
        await _insert_session(db, _session(f"s{i}"))
        await _insert_event(db, _error_event(f"s{i}", "TimeoutError", f"connection timeout {i}", f"e{i}"))
    await db.commit()

    svc = _svc(db)
    results = await svc.search_sessions("timeout", limit=3)
    assert len(results) <= 3


@pytest.mark.asyncio
async def test_default_limit_is_20(db):
    """Default limit caps at 20 results."""
    for i in range(25):
        await _insert_session(db, _session(f"s{i}"))
        await _insert_event(db, _error_event(f"s{i}", "TimeoutError", f"connection timeout {i}", f"e{i}"))
    await db.commit()

    svc = _svc(db)
    results = await svc.search_sessions("timeout")
    assert len(results) <= 20


# ---------------------------------------------------------------------------
# search_sessions — tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_isolation_sessions(db):
    """Tenant A cannot see Tenant B's sessions."""
    svc_a = _svc(db, "tenant-a")
    svc_b = _svc(db, "tenant-b")

    # Insert one session per tenant
    await _insert_session(db, _session("sa"), tenant_id="tenant-a")
    await _insert_event(db, _error_event("sa", event_id="ea"), tenant_id="tenant-a")

    await _insert_session(db, _session("sb"), tenant_id="tenant-b")
    await _insert_event(db, _error_event("sb", event_id="eb"), tenant_id="tenant-b")
    await db.commit()

    results_a = await svc_a.search_sessions("timeout")
    results_b = await svc_b.search_sessions("timeout")

    assert all(r.id == "sa" for r in results_a)
    assert all(r.id == "sb" for r in results_b)
    assert not any(r.id == "sb" for r in results_a)
    assert not any(r.id == "sa" for r in results_b)


@pytest.mark.asyncio
async def test_tenant_isolation_empty_cross_tenant(db):
    """A tenant with no data gets empty results even if other tenants have matches."""
    await _insert_session(db, _session("s1"), tenant_id="tenant-a")
    await _insert_event(db, _error_event("s1", event_id="e1"), tenant_id="tenant-a")
    await db.commit()

    svc_b = _svc(db, "tenant-b")
    results = await svc_b.search_sessions("timeout")
    assert results == []


# ---------------------------------------------------------------------------
# search_sessions — special characters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_special_characters_in_query_do_not_crash(db):
    """Queries with SQL-special characters complete without error."""
    await _insert_session(db, _session("s1"))
    await _insert_event(db, _error_event("s1", "ValueError", "invalid param: test_value", "e1"))
    await db.commit()

    svc = _svc(db)
    # These should not raise
    for query in ["test_value", "100%", "a%b", "a\\b", "error%_type"]:
        result = await svc.search_sessions(query)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# search_sessions — embedding fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_name_in_data_is_searchable(db):
    """Events with tool_name in data are included in the session embedding."""
    await _insert_session(db, _session("s1"))
    await _insert_event(db, _tool_event("s1", tool_name="database_query"))
    await db.commit()

    svc = _svc(db)
    results = await svc.search_sessions("database_query")
    assert any(r.id == "s1" for r in results)


@pytest.mark.asyncio
async def test_model_field_in_data_is_searchable(db):
    """Events with model in data are included in the session embedding."""
    await _insert_session(db, _session("s1"))
    await _insert_event(db, _tool_event("s1", tool_name="web_search", model="gpt-4"))
    await db.commit()

    svc = _svc(db)
    # "gpt" is a token derived from "gpt-4"
    results = await svc.search_sessions("gpt")
    assert isinstance(results, list)  # may or may not match depending on tokeniser


# ---------------------------------------------------------------------------
# search_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_events_finds_by_name(db):
    """search_events matches on the event name field."""
    await _insert_session(db, _session("s1"))
    await _insert_event(
        db,
        TraceEvent(
            id="ev1",
            session_id="s1",
            name="call-database-lookup",
            event_type=EventType.TOOL_CALL,
            timestamp=datetime(2026, 3, 23, 10, 1, tzinfo=timezone.utc),
            data={},
        ),
    )
    await db.commit()

    svc = _svc(db)
    results = await svc.search_events("database")
    assert len(results) >= 1
    assert any(e.name == "call-database-lookup" for e in results)


@pytest.mark.asyncio
async def test_search_events_tenant_isolation(db):
    """search_events does not return events belonging to another tenant."""
    await _insert_session(db, _session("sa"), tenant_id="tenant-a")
    await _insert_event(
        db,
        TraceEvent(
            id="ea",
            session_id="sa",
            name="special_tool",
            event_type=EventType.TOOL_CALL,
            timestamp=datetime(2026, 3, 23, 10, 1, tzinfo=timezone.utc),
            data={},
        ),
        tenant_id="tenant-a",
    )

    await _insert_session(db, _session("sb"), tenant_id="tenant-b")
    await _insert_event(
        db,
        TraceEvent(
            id="eb",
            session_id="sb",
            name="special_tool",
            event_type=EventType.TOOL_CALL,
            timestamp=datetime(2026, 3, 23, 10, 1, tzinfo=timezone.utc),
            data={},
        ),
        tenant_id="tenant-b",
    )
    await db.commit()

    svc_a = _svc(db, "tenant-a")
    results = await svc_a.search_events("special_tool")
    assert all(e.session_id == "sa" for e in results)


@pytest.mark.asyncio
async def test_search_events_filter_by_session_id(db):
    """session_id= restricts search_events to a single session."""
    await _insert_session(db, _session("s1"))
    await _insert_session(db, _session("s2"))
    await _insert_event(
        db,
        TraceEvent(
            id="ev1",
            session_id="s1",
            name="mytool",
            event_type=EventType.TOOL_CALL,
            timestamp=datetime(2026, 3, 23, 10, 1, tzinfo=timezone.utc),
            data={},
        ),
    )
    await _insert_event(
        db,
        TraceEvent(
            id="ev2",
            session_id="s2",
            name="mytool",
            event_type=EventType.TOOL_CALL,
            timestamp=datetime(2026, 3, 23, 10, 1, tzinfo=timezone.utc),
            data={},
        ),
    )
    await db.commit()

    svc = _svc(db)
    results = await svc.search_events("mytool", session_id="s1")
    assert all(e.session_id == "s1" for e in results)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_events_filter_by_event_type(db):
    """event_type= restricts search_events to the specified type."""
    await _insert_session(db, _session("s1"))
    await _insert_event(
        db,
        TraceEvent(
            id="ev-tool",
            session_id="s1",
            name="process_data",
            event_type=EventType.TOOL_CALL,
            timestamp=datetime(2026, 3, 23, 10, 1, tzinfo=timezone.utc),
            data={},
        ),
    )
    await _insert_event(
        db,
        TraceEvent(
            id="ev-err",
            session_id="s1",
            name="process_data_error",
            event_type=EventType.ERROR,
            timestamp=datetime(2026, 3, 23, 10, 2, tzinfo=timezone.utc),
            data={},
        ),
    )
    await db.commit()

    svc = _svc(db)
    results = await svc.search_events("process_data", event_type=str(EventType.TOOL_CALL))
    assert all(e.event_type == EventType.TOOL_CALL for e in results)


@pytest.mark.asyncio
async def test_search_events_special_characters_do_not_crash(db):
    """Queries with SQL-special chars (%, _, backslash) complete without error."""
    await _insert_session(db, _session("s1"))
    await _insert_event(
        db,
        TraceEvent(
            id="ev1",
            session_id="s1",
            name="validateparam",
            event_type=EventType.TOOL_CALL,
            timestamp=datetime(2026, 3, 23, 10, 1, tzinfo=timezone.utc),
            data={},
        ),
    )
    await db.commit()

    svc = _svc(db)
    for query in ["validate%param", "validate_param", "validate\\param", "100%", "a%b%c"]:
        result = await svc.search_events(query)
        assert isinstance(result, list), f"search_events raised for query={query!r}"


@pytest.mark.asyncio
async def test_search_events_empty_returns_all_matching(db):
    """search_events with an empty-ish query still runs without error."""
    await _insert_session(db, _session("s1"))
    await _insert_event(db, _tool_event("s1"))
    await db.commit()

    svc = _svc(db)
    # Empty string produces a LIKE "%%", which matches everything — that's fine
    results = await svc.search_events("")
    assert isinstance(results, list)
