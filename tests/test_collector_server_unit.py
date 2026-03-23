from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import collector.server as collector_server
from agent_debugger_sdk.core.events import (
    AgentTurnEvent,
    BehaviorAlertEvent,
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
from storage import Base, TraceRepository


@pytest.fixture
def collector_repo_factory(tmp_path, monkeypatch):
    db_path = tmp_path / "collector-server.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(setup())
    monkeypatch.setattr(collector_server, "_session_maker", session_maker)

    yield session_maker

    monkeypatch.setattr(collector_server, "_session_maker", None)
    asyncio.run(engine.dispose())


def test_trace_event_ingest_validates_name_and_payload_sizes(monkeypatch):
    monkeypatch.setattr(collector_server, "MAX_NAME_LENGTH", 4)
    monkeypatch.setattr(collector_server, "MAX_DATA_SIZE_BYTES", 8)
    monkeypatch.setattr(collector_server, "MAX_METADATA_SIZE_BYTES", 8)

    with pytest.raises(ValidationError):
        collector_server.TraceEventIngest(session_id="s1", event_type="tool_call", name="too-long")

    with pytest.raises(ValidationError):
        collector_server.TraceEventIngest(
            session_id="s1",
            event_type="tool_call",
            data={"payload": "0123456789"},
        )

    with pytest.raises(ValidationError):
        collector_server.TraceEventIngest(
            session_id="s1",
            event_type="tool_call",
            metadata={"payload": "0123456789"},
        )


def test_trace_event_ingest_accepts_non_json_serializable_payloads_via_fallback(monkeypatch):
    monkeypatch.setattr(collector_server, "MAX_DATA_SIZE_BYTES", 64)
    monkeypatch.setattr(collector_server, "MAX_METADATA_SIZE_BYTES", 64)

    payload = {"set": {1, 2}}
    event = collector_server.TraceEventIngest(
        session_id="s1",
        event_type="tool_call",
        data=payload,
        metadata=payload,
    )

    assert event.data == payload
    assert event.metadata == payload


def test_configure_storage_updates_session_maker():
    marker = object()
    collector_server.configure_storage(marker)
    assert collector_server._session_maker is marker
    collector_server.configure_storage(None)


@pytest.mark.asyncio
async def test_get_tenant_id_uses_local_and_cloud_modes():
    request = SimpleNamespace(headers={})
    db = MagicMock()

    with patch("collector.server.get_config", return_value=SimpleNamespace(mode="local")):
        assert await collector_server._get_tenant_id(request, db) == "local"

    with patch("collector.server.get_config", return_value=SimpleNamespace(mode="cloud")), patch(
        "collector.server.get_tenant_from_api_key", new=AsyncMock(return_value="tenant-cloud")
    ) as get_tenant_from_api_key:
        assert await collector_server._get_tenant_id(request, db) == "tenant-cloud"
        get_tenant_from_api_key.assert_awaited_once_with(request, db)


def test_get_redaction_pipeline_uses_runtime_config():
    with patch(
        "agent_debugger_sdk.config.get_config",
        return_value=SimpleNamespace(redact_prompts=True, max_payload_kb=16),
    ):
        pipeline = collector_server._get_redaction_pipeline()

    assert pipeline.redact_prompts is True
    assert pipeline.redact_pii is False
    assert pipeline.max_payload_kb == 16


@pytest.mark.asyncio
async def test_persist_event_if_configured_is_noop_without_storage(monkeypatch):
    monkeypatch.setattr(collector_server, "_session_maker", None)
    event = TraceEvent(session_id="no-storage", event_type=EventType.ERROR)
    await collector_server._persist_event_if_configured(event)


@pytest.mark.asyncio
async def test_persist_event_if_configured_raises_for_missing_session(collector_repo_factory):
    event = ToolCallEvent(session_id="missing-session", tool_name="search", arguments={})
    pipeline = SimpleNamespace(apply=MagicMock(side_effect=lambda value: value))

    with patch("collector.server._get_redaction_pipeline", return_value=pipeline):
        with pytest.raises(HTTPException) as exc:
            await collector_server._persist_event_if_configured(event, tenant_id="tenant-a")

    assert exc.value.status_code == 404
    assert exc.value.detail == "Session missing-session not found"


@pytest.mark.asyncio
async def test_persist_event_if_configured_persists_to_repository(collector_repo_factory):
    session = Session(id="persisted", agent_name="agent", framework="pytest")
    event = ToolCallEvent(session_id=session.id, tool_name="search", arguments={"q": "Belgrade"})
    pipeline = SimpleNamespace(apply=MagicMock(side_effect=lambda value: value))

    async with collector_repo_factory() as db_session:
        repo = TraceRepository(db_session, tenant_id="tenant-a")
        await repo.create_session(session)

    with patch("collector.server._get_redaction_pipeline", return_value=pipeline):
        await collector_server._persist_event_if_configured(event, tenant_id="tenant-a")

    async with collector_repo_factory() as db_session:
        repo = TraceRepository(db_session, tenant_id="tenant-a")
        events = await repo.list_events(session.id)

    assert [stored_event.tool_name for stored_event in events] == ["search"]
    pipeline.apply.assert_called_once()


def test_parse_event_type_and_timestamp():
    assert collector_server._parse_event_type("tool_call") == EventType.TOOL_CALL
    assert collector_server._parse_timestamp(None) is None
    assert collector_server._parse_timestamp("2026-03-23T10:00:00Z") == datetime(
        2026, 3, 23, 10, 0, tzinfo=timezone.utc
    )

    with pytest.raises(HTTPException) as exc:
        collector_server._parse_event_type("not-real")

    assert exc.value.status_code == 400
    assert "Invalid event_type" in exc.value.detail


@pytest.mark.parametrize(
    ("event_type", "data", "expected_type", "field_assertions"),
    [
        (EventType.TOOL_CALL, {"tool_name": "search", "arguments": {"q": "x"}}, ToolCallEvent, lambda event: event.tool_name == "search"),
        (EventType.TOOL_RESULT, {"tool_name": "search", "result": ["x"], "error": None, "duration_ms": 1.2}, ToolResultEvent, lambda event: event.result == ["x"]),
        (EventType.LLM_REQUEST, {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "tools": [], "settings": {"temperature": 0.1}}, LLMRequestEvent, lambda event: event.model == "gpt-4"),
        (EventType.LLM_RESPONSE, {"model": "gpt-4", "content": "hello", "tool_calls": [], "usage": {"input_tokens": 1, "output_tokens": 1}, "cost_usd": 0.1, "duration_ms": 12.0}, LLMResponseEvent, lambda event: event.content == "hello"),
        (EventType.DECISION, {"reasoning": "tool first", "confidence": 0.8, "evidence": [], "evidence_event_ids": ["e1"], "alternatives": [], "chosen_action": "answer"}, DecisionEvent, lambda event: event.chosen_action == "answer"),
        (EventType.SAFETY_CHECK, {"policy_name": "policy", "outcome": "warn", "risk_level": "medium", "rationale": "careful", "blocked_action": "send", "evidence": []}, SafetyCheckEvent, lambda event: event.outcome == "warn"),
        (EventType.REFUSAL, {"reason": "unsafe", "policy_name": "policy", "risk_level": "high", "blocked_action": "send", "safe_alternative": "summarize"}, RefusalEvent, lambda event: event.safe_alternative == "summarize"),
        (EventType.POLICY_VIOLATION, {"policy_name": "policy", "severity": "high", "violation_type": "prompt", "details": {"a": 1}}, PolicyViolationEvent, lambda event: event.violation_type == "prompt"),
        (EventType.PROMPT_POLICY, {"template_id": "tpl", "policy_parameters": {"mode": "strict"}, "speaker": "system", "state_summary": "clean", "goal": "help"}, PromptPolicyEvent, lambda event: event.template_id == "tpl"),
        (EventType.AGENT_TURN, {"agent_id": "a1", "speaker": "assistant", "turn_index": 2, "goal": "plan", "content": "next"}, AgentTurnEvent, lambda event: event.turn_index == 2),
        (EventType.BEHAVIOR_ALERT, {"alert_type": "drift", "severity": "high", "signal": "looping", "related_event_ids": ["e1"]}, BehaviorAlertEvent, lambda event: event.signal == "looping"),
        (EventType.ERROR, {"error_type": "ValueError", "error_message": "boom", "stack_trace": "trace"}, ErrorEvent, lambda event: event.error_message == "boom"),
        (EventType.CHECKPOINT, {"raw": True}, TraceEvent, lambda event: event.data == {"raw": True}),
    ],
)
def test_build_event_returns_typed_event(event_type, data, expected_type, field_assertions):
    event_data = collector_server.TraceEventIngest(
        session_id="session-1",
        parent_id="parent-1",
        event_type=event_type.value,
        timestamp="2026-03-23T12:00:00Z",
        name="event-name",
        data=data,
        metadata={"source": "test"},
        upstream_event_ids=["up-1"],
    )

    event = collector_server._build_event(event_data, event_type)

    assert isinstance(event, expected_type)
    assert event.session_id == "session-1"
    assert event.parent_id == "parent-1"
    assert event.timestamp == datetime(2026, 3, 23, 12, 0, tzinfo=timezone.utc)
    assert event.metadata == {"source": "test"}
    assert event.upstream_event_ids == ["up-1"]
    assert field_assertions(event)


@pytest.mark.asyncio
async def test_ingest_trace_without_storage_scores_and_publishes(monkeypatch):
    event_data = collector_server.TraceEventIngest(
        session_id="session-1",
        event_type="tool_call",
        data={"tool_name": "search", "arguments": {"q": "Belgrade"}},
    )
    buffer = SimpleNamespace(publish=AsyncMock())
    scorer = SimpleNamespace(score=MagicMock(return_value=0.73))
    persisted: list[tuple[str, float]] = []

    monkeypatch.setattr(collector_server, "_session_maker", None)

    with patch("collector.server.get_event_buffer", return_value=buffer), patch(
        "collector.server.get_importance_scorer", return_value=scorer
    ), patch(
        "collector.server._persist_event_if_configured",
        side_effect=lambda event, tenant_id="local": persisted.append((tenant_id, event.importance)),
    ) as persist:
        response = await collector_server.ingest_trace(event_data, request=SimpleNamespace(headers={}))

    assert response.status == "queued"
    assert persisted == [("local", 0.73)]
    persist.assert_awaited_once()
    buffer.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_ingest_trace_with_storage_resolves_tenant_and_publishes(collector_repo_factory):
    session = Session(id="session-with-storage", agent_name="agent", framework="pytest")
    event_data = collector_server.TraceEventIngest(
        session_id=session.id,
        event_type="tool_result",
        data={"tool_name": "search", "result": ["Belgrade"], "duration_ms": 3.5},
    )
    buffer = SimpleNamespace(publish=AsyncMock())
    scorer = SimpleNamespace(score=MagicMock(return_value=0.4))

    async with collector_repo_factory() as db_session:
        repo = TraceRepository(db_session, tenant_id="tenant-a")
        await repo.create_session(session)

    with patch("collector.server.get_event_buffer", return_value=buffer), patch(
        "collector.server.get_importance_scorer", return_value=scorer
    ), patch("collector.server._get_tenant_id", new=AsyncMock(return_value="tenant-a")):
        response = await collector_server.ingest_trace(event_data, request=SimpleNamespace(headers={}))

    assert response.status == "queued"
    buffer.publish.assert_awaited_once()

    async with collector_repo_factory() as db_session:
        repo = TraceRepository(db_session, tenant_id="tenant-a")
        events = await repo.list_events(session.id)

    assert len(events) == 1
    assert events[0].tool_name == "search"


@pytest.mark.asyncio
async def test_create_session_without_and_with_storage(collector_repo_factory, monkeypatch):
    request = SimpleNamespace(headers={})
    monkeypatch.setattr(collector_server, "_session_maker", None)

    created = await collector_server.create_session(
        collector_server.SessionCreate(agent_name="agent", framework="pytest"),
        request=request,
    )
    assert created.agent_name == "agent"

    monkeypatch.setattr(collector_server, "_session_maker", collector_repo_factory)
    with patch("collector.server._get_tenant_id", new=AsyncMock(return_value="tenant-a")):
        persisted = await collector_server.create_session(
            collector_server.SessionCreate(
                id="persisted-session",
                agent_name="agent",
                framework="pytest",
                config={"mode": "test"},
                tags=["coverage"],
            ),
            request=request,
        )

    assert persisted.id == "persisted-session"

    async with collector_repo_factory() as db_session:
        repo = TraceRepository(db_session, tenant_id="tenant-a")
        stored = await repo.get_session("persisted-session")

    assert stored is not None
    assert stored.config == {"mode": "test"}
    assert stored.tags == ["coverage"]


@pytest.mark.asyncio
async def test_health_check_returns_ok():
    response = await collector_server.health_check()
    assert response.status == "ok"
