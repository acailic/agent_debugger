"""Shared fixtures for intelligence test modules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from agent_debugger_sdk.core.events import (
    Checkpoint,
    Session,
    TraceEvent,
)
from collector.intelligence import TraceIntelligence


def make_session_with_events(
    session_id: str,
    events: list[TraceEvent],
    checkpoints: list[Checkpoint],
) -> Session:
    """Factory to create a Session with events for cross-session clustering tests."""
    from agent_debugger_sdk.core.events import EventType

    return Session(
        id=session_id,
        agent_name=f"agent-{session_id}",
        framework="test",
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        status="completed",
        total_tokens=len(events),
        total_cost_usd=0.0,
        tool_calls=sum(1 for e in events if e.event_type == EventType.TOOL_CALL),
        llm_calls=sum(1 for e in events if e.event_type == EventType.LLM_REQUEST),
        errors=sum(1 for e in events if e.event_type == EventType.ERROR),
        config={},
        tags=[],
    )


@pytest.fixture
def make_trace_event():
    """Factory to create TraceEvent instances for tests."""

    def _make_event(
        session_id: str = "session-1",
        event_type="agent_start",
        name: str = "test",
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
        parent_id: str | None = None,
        upstream_event_ids: list[str] | None = None,
        timestamp: datetime | None = None,
        id: str | None = None,
    ) -> TraceEvent:
        from agent_debugger_sdk.core.events import EventType

        kwargs: dict[str, Any] = {}
        kwargs["session_id"] = session_id
        kwargs["event_type"] = EventType(event_type) if isinstance(event_type, str) else event_type
        kwargs["name"] = name
        kwargs["importance"] = importance
        if id is not None:
            kwargs["id"] = id
        if data is not None:
            kwargs["data"] = data
        if metadata is not None:
            kwargs["metadata"] = metadata
        if parent_id is not None:
            kwargs["parent_id"] = parent_id
        if upstream_event_ids is not None:
            kwargs["upstream_event_ids"] = upstream_event_ids
        if timestamp is not None:
            kwargs["timestamp"] = timestamp
        return TraceEvent(**kwargs)

    return _make_event


@pytest.fixture
def intelligence():
    """Create a TraceIntelligence instance for tests."""
    return TraceIntelligence()
