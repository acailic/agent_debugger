"""Tests for storage/search.py — SessionSearchService."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent_debugger_sdk.core.events import EventType, Session, SessionStatus, TraceEvent
from storage.models import Base
from storage.repository import TraceRepository
from storage.search import SessionSearchService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session(
    session_id: str,
    status: SessionStatus = SessionStatus.ERROR,
    agent_name: str = "agent",
) -> Session:
    return Session(
        id=session_id,
        agent_name=agent_name,
        framework="pytest",
        started_at=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        status=status,
        config={},
        tags=[],
    )


def _error_event(
    session_id: str,
    event_id: str,
    error_type: str = "TimeoutError",
    error_message: str = "connection timed out",
) -> TraceEvent:
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        name="error_occurred",
        event_type=EventType.ERROR,
        timestamp=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
        data={"error_type": error_type, "error_message": error_message},
    )


def _tool_event(
    session_id: str,
    event_id: str,
    tool_name: str = "search_api",
    model: str = "gpt-4",
) -> TraceEvent:
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        name="tool_called",
        event_type=EventType.TOOL_CALL,
        timestamp=datetime(2026, 1, 1, 0, 2, tzinfo=timezone.utc),
        data={"tool_name": tool_name, "model": model},
    )


def _llm_event(
    session_id: str,
    event_id: str,
    name: str = "generate",
) -> TraceEvent:
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        name=name,
        event_type=EventType.LLM_REQUEST,
        timestamp=datetime(2026, 1, 1, 0, 3, tzinfo=timezone.utc),
        data={},
    )


@pytest_asyncio.fixture
async def db():
    """In-memory SQLite async session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


def _svc(db_session: AsyncSession, tenant_id: str = "tenant-a") -> SessionSearchService:
    return SessionSearchService(db_session, tenant_id)


async def _seed(db_session: AsyncSession, tenant_id: str, sessions_and_events: list) -> None:
    repo = TraceRepository(db_session, tenant_id=tenant_id)
    for item in sessions_and_events:
        if isinstance(item, Session):
            await repo.create_session(item)
        elif isinstance(item, TraceEvent):
            await repo.add_event(item)
    await repo.commit()


# ===========================================================================
# TestSearchSessions
# ===========================================================================


class TestSearchSessions:
    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self, db):
        """Empty query string returns [] without hitting the DB."""
        svc = _svc(db)
        assert await svc.search_sessions("") == []

    @pytest.mark.asyncio
    async def test_whitespace_query_returns_empty(self, db):
        """Whitespace-only query returns []."""
        svc = _svc(db)
        assert await svc.search_sessions("   ") == []

    @pytest.mark.asyncio
    async def test_stopwords_only_query_returns_empty(self, db):
        """Query made only of stopwords produces no vector and returns []."""
        await _seed(
            db,
            "tenant-a",
            [_session("s1"), _error_event("s1", "e1", "TimeoutError", "request failed")],
        )
        svc = _svc(db)
        # "the is a" → all stopwords → text_to_vector returns {} → early return
        result = await svc.search_sessions("the is a")
        assert result == []

    @pytest.mark.asyncio
    async def test_no_sessions_returns_empty(self, db):
        """No data in DB → search returns []."""
        result = await _svc(db).search_sessions("timeout")
        assert result == []

    @pytest.mark.asyncio
    async def test_finds_session_by_error_type(self, db):
        await _seed(
            db,
            "tenant-a",
            [_session("s1"), _error_event("s1", "e1", "TimeoutError", "connection timeout occurred")],
        )
        results = await _svc(db).search_sessions("timeout")
        assert any(s.id == "s1" for s in results)

    @pytest.mark.asyncio
    async def test_finds_session_by_error_message(self, db):
        await _seed(
            db,
            "tenant-a",
            [_session("s1"), _error_event("s1", "e1", "ValueError", "invalid schema validation")],
        )
        results = await _svc(db).search_sessions("schema validation")
        assert any(s.id == "s1" for s in results)

    @pytest.mark.asyncio
    async def test_finds_session_by_tool_name(self, db):
        await _seed(
            db,
            "tenant-a",
            [_session("s1"), _tool_event("s1", "e1", tool_name="database_query")],
        )
        results = await _svc(db).search_sessions("database_query")
        assert any(s.id == "s1" for s in results)

    @pytest.mark.asyncio
    async def test_finds_session_by_model(self, db):
        await _seed(
            db,
            "tenant-a",
            [_session("s1"), _tool_event("s1", "e1", model="claude-opus")],
        )
        results = await _svc(db).search_sessions("claude opus")
        assert any(s.id == "s1" for s in results)

    @pytest.mark.asyncio
    async def test_search_similarity_attached(self, db):
        """Every result must carry a search_similarity float."""
        await _seed(
            db,
            "tenant-a",
            [_session("s1"), _error_event("s1", "e1", "TimeoutError", "connection timeout")],
        )
        results = await _svc(db).search_sessions("timeout")
        assert results
        for s in results:
            assert isinstance(s.search_similarity, float)
            assert 0.0 < s.search_similarity <= 1.0

    @pytest.mark.asyncio
    async def test_results_ranked_by_similarity(self, db):
        """Session with more matching terms should rank above partial match."""
        await _seed(
            db,
            "tenant-a",
            [
                _session("s1"),
                _error_event("s1", "e1", "TimeoutError", "connection timeout error occurred"),
                _session("s2"),
                _error_event("s2", "e2", "NetworkError", "network failure"),
            ],
        )
        results = await _svc(db).search_sessions("timeout error")
        assert results
        # Results should be sorted descending by similarity
        scores = [s.search_similarity for s in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_sessions_without_events_excluded(self, db):
        """Sessions with no events have empty embedding → sim=0 → excluded."""
        await _seed(db, "tenant-a", [_session("s1")])
        results = await _svc(db).search_sessions("timeout")
        assert results == []

    @pytest.mark.asyncio
    async def test_status_filter(self, db):
        """status parameter restricts results to matching session status."""
        await _seed(
            db,
            "tenant-a",
            [
                _session("s-error", status=SessionStatus.ERROR),
                _error_event("s-error", "e1", "TimeoutError", "timeout error"),
                _session("s-done", status=SessionStatus.COMPLETED),
                _error_event("s-done", "e2", "TimeoutError", "timeout error"),
            ],
        )
        svc = _svc(db)
        error_results = await svc.search_sessions("timeout", status=str(SessionStatus.ERROR))
        assert all(s.status == SessionStatus.ERROR for s in error_results)
        assert any(s.id == "s-error" for s in error_results)
        assert not any(s.id == "s-done" for s in error_results)

    @pytest.mark.asyncio
    async def test_limit_parameter(self, db):
        """limit parameter caps result count."""
        items: list = []
        for i in range(6):
            items.append(_session(f"s{i}"))
            items.append(_error_event(f"s{i}", f"e{i}", "TimeoutError", f"timeout error {i}"))
        await _seed(db, "tenant-a", items)

        results = await _svc(db).search_sessions("timeout", limit=3)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, db):
        """Each tenant only sees its own sessions."""
        await _seed(
            db,
            "tenant-a",
            [_session("sa"), _error_event("sa", "ea", "TimeoutError", "connection timeout")],
        )
        await _seed(
            db,
            "tenant-b",
            [_session("sb"), _error_event("sb", "eb", "TimeoutError", "connection timeout")],
        )

        results_a = await _svc(db, "tenant-a").search_sessions("timeout")
        results_b = await _svc(db, "tenant-b").search_sessions("timeout")

        ids_a = {s.id for s in results_a}
        ids_b = {s.id for s in results_b}

        assert "sa" in ids_a
        assert "sb" not in ids_a
        assert "sb" in ids_b
        assert "sa" not in ids_b

    @pytest.mark.asyncio
    async def test_tenant_a_cannot_see_tenant_b_even_with_matching_query(self, db):
        """Cross-tenant leakage must not occur even for identical queries."""
        await _seed(
            db,
            "tenant-x",
            [_session("sx"), _error_event("sx", "ex", "ValueError", "input validation failed")],
        )
        # tenant-y has no sessions
        results = await _svc(db, "tenant-y").search_sessions("validation")
        assert results == []

    @pytest.mark.asyncio
    async def test_special_characters_in_query(self, db):
        """Queries with special chars must not raise and should return a list."""
        await _seed(
            db,
            "tenant-a",
            [_session("s1"), _error_event("s1", "e1", "ValueError", "invalid input")],
        )
        svc = _svc(db)
        assert isinstance(await svc.search_sessions("value%error"), list)
        assert isinstance(await svc.search_sessions("input_error"), list)
        assert isinstance(await svc.search_sessions("error\\n"), list)


# ===========================================================================
# TestSearchEvents
# ===========================================================================


class TestSearchEvents:
    @pytest.mark.asyncio
    async def test_finds_event_by_name(self, db):
        await _seed(
            db,
            "tenant-a",
            [_session("s1"), _llm_event("s1", "e1", name="generate_response")],
        )
        results = await _svc(db).search_events("generate_response")
        assert any(e.id == "e1" for e in results)

    @pytest.mark.asyncio
    async def test_finds_event_by_event_type(self, db):
        await _seed(
            db,
            "tenant-a",
            [_session("s1"), _tool_event("s1", "e1")],
        )
        results = await _svc(db).search_events("tool_call")
        assert any(e.id == "e1" for e in results)

    @pytest.mark.asyncio
    async def test_finds_event_by_data_content(self, db):
        """search_events searches inside JSON data blobs."""
        await _seed(
            db,
            "tenant-a",
            [_session("s1"), _tool_event("s1", "e1", tool_name="unique_tool_xyz")],
        )
        results = await _svc(db).search_events("unique_tool_xyz")
        assert any(e.id == "e1" for e in results)

    @pytest.mark.asyncio
    async def test_no_matching_events_returns_empty(self, db):
        await _seed(
            db,
            "tenant-a",
            [_session("s1"), _llm_event("s1", "e1")],
        )
        results = await _svc(db).search_events("zzznomatch_xyzzy")
        assert results == []

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, db):
        """Events from other tenants must not appear."""
        await _seed(
            db,
            "tenant-a",
            [_session("sa"), _llm_event("sa", "ea", name="exclusive_event_alpha")],
        )
        await _seed(
            db,
            "tenant-b",
            [_session("sb"), _llm_event("sb", "eb", name="exclusive_event_beta")],
        )
        results_a = await _svc(db, "tenant-a").search_events("exclusive_event")
        ids_a = {e.id for e in results_a}
        assert "ea" in ids_a
        assert "eb" not in ids_a

    @pytest.mark.asyncio
    async def test_session_id_filter(self, db):
        """session_id filter restricts results to that session."""
        await _seed(
            db,
            "tenant-a",
            [
                _session("s1"),
                _llm_event("s1", "e1", name="generate"),
                _session("s2"),
                _llm_event("s2", "e2", name="generate"),
            ],
        )
        results = await _svc(db).search_events("generate", session_id="s1")
        event_ids = {e.id for e in results}
        assert "e1" in event_ids
        assert "e2" not in event_ids

    @pytest.mark.asyncio
    async def test_event_type_filter(self, db):
        """event_type kwarg restricts to matching type only."""
        await _seed(
            db,
            "tenant-a",
            [
                _session("s1"),
                _llm_event("s1", "e-llm"),
                _tool_event("s1", "e-tool"),
            ],
        )
        results = await _svc(db).search_events("generate", event_type=EventType.LLM_REQUEST.value)
        event_ids = {e.id for e in results}
        assert "e-llm" in event_ids
        assert "e-tool" not in event_ids

    @pytest.mark.asyncio
    async def test_limit_parameter(self, db):
        items: list = [_session("s1")]
        for i in range(10):
            items.append(_llm_event("s1", f"e{i}", name=f"generate_{i}"))
        await _seed(db, "tenant-a", items)

        results = await _svc(db).search_events("generate", limit=4)
        assert len(results) <= 4

    @pytest.mark.asyncio
    async def test_percent_wildcard_escaped(self, db):
        """% in query should be treated as literal, not SQL wildcard."""
        await _seed(
            db,
            "tenant-a",
            [_session("s1"), _llm_event("s1", "e1", name="no_match_event")],
        )
        # Should not crash and should not match unintended events
        results = await _svc(db).search_events("100%complete")
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_underscore_wildcard_escaped(self, db):
        """_ in query should be treated as literal, not SQL single-char wildcard."""
        await _seed(
            db,
            "tenant-a",
            [
                _session("s1"),
                _llm_event("s1", "e1", name="test_name"),
                _llm_event("s1", "e2", name="testXname"),
            ],
        )
        results = await _svc(db).search_events("test_name")
        event_ids = {e.id for e in results}
        # test_name (literal underscore) should match e1, NOT e2 (testXname)
        assert "e1" in event_ids
        assert "e2" not in event_ids

    @pytest.mark.asyncio
    async def test_backslash_escaped(self, db):
        """Backslash in query should not cause SQL errors."""
        await _seed(
            db,
            "tenant-a",
            [_session("s1"), _llm_event("s1", "e1")],
        )
        results = await _svc(db).search_events("path\\to\\file")
        assert isinstance(results, list)
