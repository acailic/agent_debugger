"""Tests for similar failures API behavior."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import ErrorEvent, Session, SessionStatus
from api.exceptions import NotFoundError
from api.session_routes import get_similar_failures
from storage.repository import TraceRepository


def _make_session(session_id: str, agent_name: str, fix_note: str | None = None) -> Session:
    return Session(
        id=session_id,
        agent_name=agent_name,
        framework="pytest",
        started_at=datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc),
        status=SessionStatus.ERROR,
        config={"mode": "test"},
        tags=["coverage"],
        fix_note=fix_note,
    )


def _make_error(session_id: str, event_id: str, error_type: str, error_message: str) -> ErrorEvent:
    return ErrorEvent(
        id=event_id,
        session_id=session_id,
        timestamp=datetime(2026, 4, 3, 10, 1, tzinfo=timezone.utc),
        name="error",
        error_type=error_type,
        error_message=error_message,
    )


@pytest.mark.asyncio
async def test_similar_failures_requires_event_to_belong_to_session(db_session):
    repo = TraceRepository(db_session, tenant_id="local")

    source_session = _make_session("session-source", "agent-source")
    other_session = _make_session("session-other", "agent-other")
    await repo.create_session(source_session)
    await repo.create_session(other_session)
    await repo.add_event(_make_error("session-source", "event-source", "RuntimeError", "timeout while calling tool"))
    other_event = await repo.add_event(
        _make_error("session-other", "event-other", "RuntimeError", "timeout while calling tool")
    )
    await repo.commit()

    with pytest.raises(NotFoundError):
        await get_similar_failures(
            session_id="session-source",
            failure_event_id=other_event.id,
            limit=5,
            repo=repo,
        )


@pytest.mark.asyncio
async def test_similar_failures_returns_best_historical_match_per_session(db_session):
    repo = TraceRepository(db_session, tenant_id="local")

    source_session = _make_session("session-source", "agent-source")
    match_session = _make_session("session-match", "agent-match", fix_note="increase retry budget")
    second_match_session = _make_session("session-match-2", "agent-match-2")
    non_match_session = _make_session("session-other", "agent-other")

    await repo.create_session(source_session)
    await repo.create_session(match_session)
    await repo.create_session(second_match_session)
    await repo.create_session(non_match_session)

    await repo.add_event(
        _make_error("session-source", "event-source", "RuntimeError", "search timeout after 30 seconds")
    )
    await repo.add_event(
        _make_error("session-match", "event-match-strong", "RuntimeError", "search timeout after 30 seconds")
    )
    await repo.add_event(
        _make_error("session-match", "event-match-weak", "RuntimeError", "generic runtime issue")
    )
    await repo.add_event(
        _make_error("session-match-2", "event-match-2", "RuntimeError", "search timeout after 10 seconds")
    )
    await repo.add_event(
        _make_error("session-other", "event-other", "ValueError", "bad input provided")
    )
    await repo.commit()

    response = await get_similar_failures(
        session_id="session-source",
        failure_event_id="event-source",
        limit=5,
        repo=repo,
    )

    assert response.total == 2
    assert [item.session_id for item in response.similar_failures] == [
        "session-match",
        "session-match-2",
    ]
    assert response.similar_failures[0].fix_note == "increase retry budget"
    assert response.similar_failures[0].similarity >= response.similar_failures[1].similarity
