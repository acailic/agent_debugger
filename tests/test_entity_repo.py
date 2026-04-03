"""Tests for entity repository and API integration."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from storage.entities import EntityType
from storage.repositories.entity_repo import EntityRepository


@pytest.mark.asyncio
async def test_entity_repo_extract_from_session(db_session):
    repo = EntityRepository(db_session, tenant_id="tenant-a")

    # Create a test session with events
    from storage.repository import TraceRepository

    trace_repo = TraceRepository(db_session, tenant_id="tenant-a")
    from agent_debugger_sdk.core.events import ErrorEvent, Session, ToolCallEvent

    session = Session(
        id="session-1",
        agent_name="test-agent",
        framework="pytest",
        started_at=datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc),
        config={},
        tags=[],
    )
    await trace_repo.create_session(session)

    # Add tool call events
    await trace_repo.add_event(
        ToolCallEvent(
            id="event-1",
            session_id=session.id,
            timestamp=datetime(2026, 4, 3, 10, 1, tzinfo=timezone.utc),
            name="search-call",
            tool_name="search",
            arguments={"q": "test"},
            upstream_event_ids=[],
        )
    )
    await trace_repo.add_event(
        ToolCallEvent(
            id="event-2",
            session_id=session.id,
            timestamp=datetime(2026, 4, 3, 10, 2, tzinfo=timezone.utc),
            name="lookup-call",
            tool_name="lookup",
            arguments={"key": "value"},
            upstream_event_ids=[],
        )
    )

    # Add error event
    await trace_repo.add_event(
        ErrorEvent(
            id="event-3",
            session_id=session.id,
            timestamp=datetime(2026, 4, 3, 10, 3, tzinfo=timezone.utc),
            name="error",
            error_type="RuntimeError",
            error_message="test error",
        )
    )

    entities = await repo.extract_entities_from_session(session.id)

    assert f"{EntityType.TOOL_NAME}:search" in entities
    assert f"{EntityType.TOOL_NAME}:lookup" in entities
    assert f"{EntityType.ERROR_TYPE}:RuntimeError" in entities

    search_entity = entities[f"{EntityType.TOOL_NAME}:search"]
    assert search_entity.count == 1
    assert search_entity.value == "search"


@pytest.mark.asyncio
async def test_entity_repo_get_top_tools(db_session):
    repo = EntityRepository(db_session, tenant_id="tenant-a")

    from storage.repository import TraceRepository

    trace_repo = TraceRepository(db_session, tenant_id="tenant-a")
    from agent_debugger_sdk.core.events import Session, ToolCallEvent

    session = Session(
        id="session-1",
        agent_name="test-agent",
        framework="pytest",
        started_at=datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc),
        config={},
        tags=[],
    )
    await trace_repo.create_session(session)

    # Add multiple tool calls with same tool
    for i in range(5):
        await trace_repo.add_event(
            ToolCallEvent(
                id=f"event-{i}",
                session_id=session.id,
                timestamp=datetime(2026, 4, 3, 10, i, tzinfo=timezone.utc),
                name=f"search-{i}",
                tool_name="search",
                arguments={"q": f"query{i}"},
                upstream_event_ids=[],
            )
        )

    # Add calls to different tools
    await trace_repo.add_event(
        ToolCallEvent(
            id="event-lookup",
            session_id=session.id,
            timestamp=datetime(2026, 4, 3, 10, 10, tzinfo=timezone.utc),
            name="lookup",
            tool_name="lookup",
            arguments={},
            upstream_event_ids=[],
        )
    )

    top_tools = await repo.get_top_tools(limit=5, sort_by="count")

    assert len(top_tools) >= 2
    assert top_tools[0]["value"] == "search"
    assert top_tools[0]["count"] == 5


@pytest.mark.asyncio
async def test_entity_repo_get_top_errors(db_session):
    repo = EntityRepository(db_session, tenant_id="tenant-a")

    from storage.repository import TraceRepository

    trace_repo = TraceRepository(db_session, tenant_id="tenant-a")
    from agent_debugger_sdk.core.events import ErrorEvent, Session

    session = Session(
        id="session-1",
        agent_name="test-agent",
        framework="pytest",
        started_at=datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc),
        config={},
        tags=[],
    )
    await trace_repo.create_session(session)

    # Add multiple errors
    await trace_repo.add_event(
        ErrorEvent(
            id="error-1",
            session_id=session.id,
            timestamp=datetime(2026, 4, 3, 10, 1, tzinfo=timezone.utc),
            name="error-1",
            error_type="RuntimeError",
            error_message="error 1",
        )
    )
    await trace_repo.add_event(
        ErrorEvent(
            id="error-2",
            session_id=session.id,
            timestamp=datetime(2026, 4, 3, 10, 2, tzinfo=timezone.utc),
            name="error-2",
            error_type="ValueError",
            error_message="error 2",
        )
    )
    await trace_repo.add_event(
        ErrorEvent(
            id="error-3",
            session_id=session.id,
            timestamp=datetime(2026, 4, 3, 10, 3, tzinfo=timezone.utc),
            name="error-3",
            error_type="RuntimeError",
            error_message="error 3",
        )
    )

    top_errors = await repo.get_top_errors(limit=10, sort_by="count")

    assert len(top_errors) >= 2
    runtime_error = next((e for e in top_errors if e["value"] == "RuntimeError"), None)
    assert runtime_error is not None
    assert runtime_error["count"] == 2


@pytest.mark.asyncio
async def test_entity_repo_get_entity_summary(db_session):
    repo = EntityRepository(db_session, tenant_id="tenant-a")

    from storage.repository import TraceRepository

    trace_repo = TraceRepository(db_session, tenant_id="tenant-a")
    from agent_debugger_sdk.core.events import ErrorEvent, LLMRequestEvent, Session, ToolCallEvent

    session = Session(
        id="session-1",
        agent_name="test-agent",
        framework="pytest",
        started_at=datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc),
        config={},
        tags=[],
    )
    await trace_repo.create_session(session)

    await trace_repo.add_event(
        ToolCallEvent(
            id="tool-1",
            session_id=session.id,
            timestamp=datetime(2026, 4, 3, 10, 1, tzinfo=timezone.utc),
            name="tool",
            tool_name="search",
            arguments={},
            upstream_event_ids=[],
        )
    )
    await trace_repo.add_event(
        ErrorEvent(
            id="error-1",
            session_id=session.id,
            timestamp=datetime(2026, 4, 3, 10, 2, tzinfo=timezone.utc),
            name="error",
            error_type="RuntimeError",
            error_message="error",
        )
    )
    await trace_repo.add_event(
        LLMRequestEvent(
            id="llm-1",
            session_id=session.id,
            timestamp=datetime(2026, 4, 3, 10, 3, tzinfo=timezone.utc),
            name="llm",
            model="gpt-4",
            messages=[],
            tools=[],
            settings={},
        )
    )

    summary = await repo.get_entity_summary()

    assert summary.get(EntityType.TOOL_NAME, 0) >= 1
    assert summary.get(EntityType.ERROR_TYPE, 0) >= 1
    assert summary.get(EntityType.MODEL, 0) >= 1


@pytest.mark.asyncio
async def test_entity_repo_tenant_isolation(db_session):
    repo_a = EntityRepository(db_session, tenant_id="tenant-a")
    repo_b = EntityRepository(db_session, tenant_id="tenant-b")

    from storage.repository import TraceRepository

    trace_repo_a = TraceRepository(db_session, tenant_id="tenant-a")
    trace_repo_b = TraceRepository(db_session, tenant_id="tenant-b")
    from agent_debugger_sdk.core.events import Session, ToolCallEvent

    session_a = Session(
        id="session-a",
        agent_name="agent-a",
        framework="pytest",
        started_at=datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc),
        config={},
        tags=[],
    )
    await trace_repo_a.create_session(session_a)

    session_b = Session(
        id="session-b",
        agent_name="agent-b",
        framework="pytest",
        started_at=datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc),
        config={},
        tags=[],
    )
    await trace_repo_b.create_session(session_b)

    # Add tool to tenant A
    await trace_repo_a.add_event(
        ToolCallEvent(
            id="tool-a",
            session_id=session_a.id,
            timestamp=datetime(2026, 4, 3, 10, 1, tzinfo=timezone.utc),
            name="tool-a",
            tool_name="search_a",
            arguments={},
            upstream_event_ids=[],
        )
    )

    # Add tool to tenant B
    await trace_repo_b.add_event(
        ToolCallEvent(
            id="tool-b",
            session_id=session_b.id,
            timestamp=datetime(2026, 4, 3, 10, 1, tzinfo=timezone.utc),
            name="tool-b",
            tool_name="search_b",
            arguments={},
            upstream_event_ids=[],
        )
    )

    entities_a = await repo_a.get_top_tools(limit=10)
    entities_b = await repo_b.get_top_tools(limit=10)

    # Tenant A should only see search_a
    assert any(e["value"] == "search_a" for e in entities_a)
    assert not any(e["value"] == "search_b" for e in entities_a)

    # Tenant B should only see search_b
    assert any(e["value"] == "search_b" for e in entities_b)
    assert not any(e["value"] == "search_a" for e in entities_b)
