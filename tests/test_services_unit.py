"""Unit tests for api/services.py persist functions with injected dependencies.

These tests use the new optional parameters to inject fakes and in-memory
databases, avoiding the need for the full app_context or MagicMock patching.
"""

from __future__ import annotations

import pytest

from agent_debugger_sdk.core.events import Checkpoint, EventType, SessionStatus, TraceEvent
from tests.helpers.fakes import FakeRedactionPipeline, FakeTraceIntelligence


def _make_event(session_id: str = "s1", **kwargs) -> TraceEvent:
    return TraceEvent(
        session_id=session_id,
        event_type=EventType.TOOL_CALL,
        name="tool_call",
        **kwargs,
    )


def _make_session(session_id: str = "s1", **kwargs) -> TraceEvent:
    """Return a Session object."""
    from agent_debugger_sdk.core.events import Session

    return Session(
        id=session_id,
        agent_name="test_agent",
        framework="custom",
        status=SessionStatus.RUNNING,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_persist_event_saves_to_injected_db(db_session_maker):
    """persist_event with injected session_maker should save the event."""
    from api.services import persist_event, persist_session_start

    # Events require a parent session row (tenant isolation join)
    session = _make_session(session_id="persist-test")
    await persist_session_start(session, session_maker=db_session_maker)

    event = _make_event(session_id="persist-test")
    await persist_event(event, session_maker=db_session_maker, redaction_pipeline=FakeRedactionPipeline())

    from storage import TraceRepository

    async with db_session_maker() as db:
        repo = TraceRepository(db)
        events = await repo.get_event_tree("persist-test")
    assert len(events) == 1
    assert events[0].name == "tool_call"


@pytest.mark.asyncio
async def test_persist_event_applies_redaction(db_session_maker):
    """persist_event should call the injected redaction pipeline."""
    from api.services import persist_event

    pipeline = FakeRedactionPipeline()
    event = _make_event(session_id="redact-test")
    await persist_event(event, session_maker=db_session_maker, redaction_pipeline=pipeline)

    assert len(pipeline.apply_calls) == 1
    assert pipeline.apply_calls[0].session_id == "redact-test"


@pytest.mark.asyncio
async def test_persist_checkpoint_saves_to_injected_db(db_session_maker):
    """persist_checkpoint with injected session_maker should save the checkpoint."""
    from api.services import persist_checkpoint, persist_session_start

    # Create parent session first (tenant isolation)
    session = _make_session(session_id="cp-test")
    await persist_session_start(session, session_maker=db_session_maker)

    cp = Checkpoint(
        session_id="cp-test",
        event_id="e1",
        sequence=1,
    )
    await persist_checkpoint(cp, session_maker=db_session_maker)

    from storage import TraceRepository

    async with db_session_maker() as db:
        repo = TraceRepository(db)
        checkpoints = await repo.list_checkpoints("cp-test")
    assert len(checkpoints) == 1
    assert checkpoints[0].sequence == 1


@pytest.mark.asyncio
async def test_persist_session_start_creates_session(db_session_maker):
    """persist_session_start with injected session_maker should create the session."""
    from api.services import persist_session_start

    session = _make_session(session_id="new-session")
    await persist_session_start(session, session_maker=db_session_maker)

    from storage import TraceRepository

    async with db_session_maker() as db:
        repo = TraceRepository(db)
        result = await repo.get_session("new-session")
    assert result is not None
    assert result.agent_name == "test_agent"


@pytest.mark.asyncio
async def test_persist_session_start_idempotent(db_session_maker):
    """persist_session_start should not fail if session already exists."""
    from api.services import persist_session_start

    session = _make_session(session_id="dup-session")
    await persist_session_start(session, session_maker=db_session_maker)
    await persist_session_start(session, session_maker=db_session_maker)  # second call


@pytest.mark.asyncio
async def test_analyze_session_uses_injected_intelligence(db_session_maker):
    """analyze_session should delegate to the injected intelligence."""
    from api.services import analyze_session

    # Seed an event first
    event = _make_event(session_id="analyze-test")
    from api.services import persist_event

    await persist_event(event, session_maker=db_session_maker, redaction_pipeline=FakeRedactionPipeline())

    fake_intel = FakeTraceIntelligence(replay_value=0.42)
    from storage import TraceRepository

    async with db_session_maker() as session:
        repo = TraceRepository(session)
        _, _, analysis, replay_value = await analyze_session(repo, "analyze-test", intelligence=fake_intel)

    assert replay_value == 0.42
    assert len(fake_intel.analyze_session_calls) == 1


@pytest.mark.asyncio
async def test_build_live_summary_uses_injected_intelligence(db_session_maker):
    """build_live_summary should delegate to the injected intelligence."""
    from api.services import build_live_summary

    fake_intel = FakeTraceIntelligence()
    from storage import TraceRepository

    async with db_session_maker() as session:
        repo = TraceRepository(session)
        summary = await build_live_summary(repo, "any-session", intelligence=fake_intel)

    assert summary["event_count"] == 0
    assert len(fake_intel.build_live_summary_calls) == 1
