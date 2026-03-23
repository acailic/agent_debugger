from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent_debugger_sdk.core.events import (
    AgentTurnEvent,
    BehaviorAlertEvent,
    Checkpoint,
    DecisionEvent,
    ErrorEvent,
    EventType,
    LLMRequestEvent,
    LLMResponseEvent,
    PolicyViolationEvent,
    PromptPolicyEvent,
    RefusalEvent,
    SafetyCheckEvent,
    Session,
    ToolCallEvent,
    ToolResultEvent,
    TraceEvent,
)
from storage.models import Base, CheckpointModel, SessionModel
from storage.repository import TraceRepository


def _make_session(session_id: str = "session-1") -> Session:
    return Session(
        id=session_id,
        agent_name="agent",
        framework="pytest",
        started_at=datetime(2026, 3, 23, 10, 0, tzinfo=UTC),
        config={"mode": "test"},
        tags=["coverage"],
    )


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_session_crud_and_count_paths(db_session):
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    session = _make_session()

    created = await repo.create_session(session)
    assert created.id == session.id
    assert await repo.count_sessions() == 1

    fetched = await repo.get_session(session.id)
    assert fetched is not None
    assert fetched.agent_name == "agent"

    no_change = await repo.update_session(session.id, not_a_field="ignored")
    assert no_change is not None
    assert no_change.id == session.id

    updated = await repo.update_session(
        session.id,
        status="completed",
        total_tokens=42,
        tool_calls=2,
        llm_calls=3,
        errors=1,
        tags=["updated"],
    )
    assert updated is not None
    assert updated.status == "completed"
    assert updated.total_tokens == 42
    assert updated.tags == ["updated"]

    assert await repo.update_session("missing", status="completed") is None
    assert await repo.delete_session("missing") is False
    assert await repo.delete_session(session.id) is True
    assert await repo.get_session(session.id) is None
    assert await repo.count_sessions() == 0


@pytest.mark.asyncio
async def test_event_and_checkpoint_queries_respect_tenant_and_filters(db_session):
    repo_a = TraceRepository(db_session, tenant_id="tenant-a")
    repo_b = TraceRepository(db_session, tenant_id="tenant-b")
    session_a = _make_session("session-a")
    session_b = _make_session("session-b")
    await repo_a.create_session(session_a)
    await repo_b.create_session(session_b)

    first = ToolCallEvent(
        id="event-1",
        session_id=session_a.id,
        timestamp=datetime(2026, 3, 23, 10, 1, tzinfo=UTC),
        name="search-start",
        tool_name="search",
        arguments={"q": "Belgrade"},
        metadata={"origin": "test"},
        upstream_event_ids=["root"],
    )
    second = ErrorEvent(
        id="event-2",
        session_id=session_a.id,
        timestamp=datetime(2026, 3, 23, 10, 2, tzinfo=UTC),
        name="tool-failure",
        error_type="RuntimeError",
        error_message="Belgrade failed",
    )
    foreign = ToolCallEvent(
        id="event-foreign",
        session_id=session_b.id,
        timestamp=datetime(2026, 3, 23, 10, 3, tzinfo=UTC),
        name="foreign",
        tool_name="lookup",
        arguments={"q": "foreign"},
    )

    added = await repo_a.add_event(first)
    assert isinstance(added, ToolCallEvent)
    batch = await repo_a.add_events_batch([second])
    assert len(batch) == 1
    await repo_b.add_event(foreign)

    assert await repo_a.get_event("missing") is None
    fetched = await repo_a.get_event(first.id)
    assert isinstance(fetched, ToolCallEvent)
    assert fetched.tool_name == "search"
    assert fetched.metadata["origin"] == "test"
    assert fetched.upstream_event_ids == ["root"]
    assert await repo_b.get_event(first.id) is None

    listed = await repo_a.list_events(session_a.id, limit=1, offset=1)
    assert len(listed) == 1
    assert listed[0].id == second.id

    tree = await repo_a.get_event_tree(session_a.id)
    assert [event.id for event in tree] == [first.id, second.id]

    checkpoint_high = Checkpoint(
        id="cp-high",
        session_id=session_a.id,
        event_id=first.id,
        sequence=1,
        timestamp=datetime(2026, 3, 23, 10, 1, tzinfo=UTC),
        importance=0.95,
        state={"step": 1},
    )
    checkpoint_low = Checkpoint(
        id="cp-low",
        session_id=session_a.id,
        event_id=second.id,
        sequence=2,
        timestamp=datetime(2026, 3, 23, 10, 2, tzinfo=UTC),
        importance=0.2,
        state={"step": 2},
    )
    created_checkpoint = await repo_a.create_checkpoint(checkpoint_high)
    assert created_checkpoint.id == "cp-high"
    await repo_a.create_checkpoint(checkpoint_low)

    assert await repo_a.get_checkpoint("missing") is None
    fetched_checkpoint = await repo_a.get_checkpoint("cp-high")
    assert fetched_checkpoint is not None
    assert fetched_checkpoint.sequence == 1
    assert await repo_b.get_checkpoint("cp-high") is None

    checkpoints = await repo_a.list_checkpoints(session_a.id)
    assert [checkpoint.id for checkpoint in checkpoints] == ["cp-high", "cp-low"]

    high_importance = await repo_a.get_high_importance_checkpoints(session_a.id, limit=10)
    assert [checkpoint.id for checkpoint in high_importance] == ["cp-high"]

    search_by_name = await repo_a.search_events("search")
    assert [event.id for event in search_by_name] == [first.id]

    search_by_payload = await repo_a.search_events("Belgrade", session_id=session_a.id, event_type="error", limit=10)
    assert [event.id for event in search_by_payload] == [second.id]


@pytest.mark.parametrize(
    ("event", "expected_type", "field_name", "field_value"),
    [
        (
            ToolCallEvent(session_id="session-1", tool_name="search", arguments={"q": "x"}, upstream_event_ids=["u1"]),
            ToolCallEvent,
            "tool_name",
            "search",
        ),
        (
            ToolResultEvent(session_id="session-1", tool_name="search", result=["hit"], error=None, duration_ms=1.2),
            ToolResultEvent,
            "result",
            ["hit"],
        ),
        (
            LLMRequestEvent(
                session_id="session-1",
                model="gpt-4",
                messages=[{"role": "user", "content": "hi"}],
                tools=[{"name": "search"}],
                settings={"temperature": 0.2},
            ),
            LLMRequestEvent,
            "model",
            "gpt-4",
        ),
        (
            LLMResponseEvent(
                session_id="session-1",
                model="gpt-4",
                content="hello",
                tool_calls=[],
                usage={"input_tokens": 1, "output_tokens": 2},
                cost_usd=0.01,
                duration_ms=12.5,
            ),
            LLMResponseEvent,
            "content",
            "hello",
        ),
        (
            DecisionEvent(
                session_id="session-1",
                reasoning="pick tool",
                confidence=0.8,
                evidence=[],
                evidence_event_ids=["e1"],
                alternatives=[],
                chosen_action="answer",
            ),
            DecisionEvent,
            "chosen_action",
            "answer",
        ),
        (
            SafetyCheckEvent(
                session_id="session-1",
                policy_name="policy",
                outcome="warn",
                risk_level="medium",
                rationale="careful",
                blocked_action="send",
                evidence=[],
            ),
            SafetyCheckEvent,
            "outcome",
            "warn",
        ),
        (
            RefusalEvent(
                session_id="session-1",
                reason="unsafe",
                policy_name="policy",
                risk_level="high",
                blocked_action="send",
                safe_alternative="summarize",
            ),
            RefusalEvent,
            "safe_alternative",
            "summarize",
        ),
        (
            PolicyViolationEvent(
                session_id="session-1",
                policy_name="policy",
                severity="high",
                violation_type="prompt",
                details={"kind": "pii"},
            ),
            PolicyViolationEvent,
            "violation_type",
            "prompt",
        ),
        (
            PromptPolicyEvent(
                session_id="session-1",
                template_id="tpl",
                policy_parameters={"mode": "strict"},
                speaker="system",
                state_summary="clean",
                goal="help",
            ),
            PromptPolicyEvent,
            "template_id",
            "tpl",
        ),
        (
            AgentTurnEvent(
                session_id="session-1",
                agent_id="agent-1",
                speaker="assistant",
                turn_index=2,
                goal="plan",
                content="next step",
            ),
            AgentTurnEvent,
            "turn_index",
            2,
        ),
        (
            BehaviorAlertEvent(
                session_id="session-1",
                alert_type="drift",
                severity="high",
                signal="looping",
                related_event_ids=["e1"],
            ),
            BehaviorAlertEvent,
            "signal",
            "looping",
        ),
        (
            ErrorEvent(
                session_id="session-1",
                error_type="ValueError",
                error_message="boom",
                stack_trace="trace",
            ),
            ErrorEvent,
            "error_message",
            "boom",
        ),
        (
            TraceEvent(
                session_id="session-1",
                event_type=EventType.CHECKPOINT,
                data={"raw": True},
                metadata={"origin": "raw"},
                upstream_event_ids=["root"],
            ),
            TraceEvent,
            "data",
            {"raw": True},
        ),
    ],
)
def test_event_model_round_trip(event, expected_type, field_name, field_value):
    repo = TraceRepository(MagicMock(), tenant_id="tenant-a")
    orm_event = repo._event_to_orm(event)
    round_tripped = repo._orm_to_event(orm_event)

    assert isinstance(round_tripped, expected_type)
    assert getattr(round_tripped, field_name) == field_value
    assert round_tripped.upstream_event_ids == event.upstream_event_ids
    if expected_type is not TraceEvent:
        assert "upstream_event_ids" in round_tripped.metadata


def test_session_and_checkpoint_orm_converters():
    repo = TraceRepository(MagicMock(), tenant_id="tenant-a")
    session = _make_session("session-convert")
    checkpoint = Checkpoint(
        id="checkpoint-convert",
        session_id="session-convert",
        event_id="event-1",
        sequence=7,
        state={"done": True},
        memory={"notes": "ok"},
        timestamp=datetime(2026, 3, 23, 11, 0, tzinfo=UTC),
        importance=0.9,
    )

    db_session_model = SessionModel(
        id=session.id,
        tenant_id="tenant-a",
        agent_name=session.agent_name,
        framework=session.framework,
        started_at=session.started_at,
        ended_at=session.ended_at,
        status=session.status,
        total_tokens=session.total_tokens,
        total_cost_usd=session.total_cost_usd,
        tool_calls=session.tool_calls,
        llm_calls=session.llm_calls,
        errors=session.errors,
        config=session.config,
        tags=session.tags,
    )
    db_checkpoint_model = CheckpointModel(
        id=checkpoint.id,
        tenant_id="tenant-a",
        session_id=checkpoint.session_id,
        event_id=checkpoint.event_id,
        sequence=checkpoint.sequence,
        state=checkpoint.state,
        memory=checkpoint.memory,
        timestamp=checkpoint.timestamp,
        importance=checkpoint.importance,
    )

    restored_session = repo._orm_to_session(db_session_model)
    restored_checkpoint = repo._orm_to_checkpoint(db_checkpoint_model)

    assert restored_session.id == session.id
    assert restored_session.config == {"mode": "test"}
    assert restored_checkpoint.id == checkpoint.id
    assert restored_checkpoint.sequence == 7
