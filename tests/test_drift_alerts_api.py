"""Integration tests for drift and alert API endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import api.main as api_main
from agent_debugger_sdk.core.context import configure_event_pipeline
from agent_debugger_sdk.core.events import EventType
from api import app_context
from api import services as api_services
from collector.buffer import get_event_buffer
from collector.server import SessionCreate, configure_storage, create_session
from storage import Base, TraceRepository
from storage.models import AnomalyAlertModel


def _get_route_endpoint(path: str, method: str):
    """Get a route endpoint by path and method."""
    for route in api_main.app.routes:
        if isinstance(route, APIRoute) and route.path == path and method.upper() in route.methods:
            return route.endpoint
    raise AssertionError(f"Route {method} {path} not found")


def _create_mock_request():
    """Create a mock Request object for testing."""

    class MockRequest:
        def __init__(self):
            self.headers = {}
            self.method = "POST"
            self.url = "http://test"
            self.query_params = {}
            self.path_params = {}
            self.body = b""

        async def body(self):
            return b""

    return MockRequest()


@pytest.fixture
def drift_repo_factory(tmp_path, monkeypatch):
    """Create a test repository for drift/alert tests."""
    db_path = tmp_path / "drift-alerts.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    monkeypatch.setattr(app_context, "engine", engine)
    monkeypatch.setattr(app_context, "async_session_maker", session_maker)

    buffer = get_event_buffer()
    buffer._events.clear()
    buffer._queues.clear()
    buffer._session_activity.clear()

    async def setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(setup())

    configure_storage(session_maker)
    configure_event_pipeline(
        buffer,
        persist_event=api_services.persist_event,
        persist_checkpoint=api_services.persist_checkpoint,
        persist_session_start=api_services.persist_session_start,
        persist_session_update=api_services.persist_session_update,
    )

    yield session_maker

    configure_event_pipeline(None)
    asyncio.run(engine.dispose())


async def _create_session_with_events(
    session_maker,
    agent_name: str,
    started_at: datetime,
    events_data: list[dict],
) -> str:
    """Helper to create a session with events."""
    import uuid

    from agent_debugger_sdk.core.events import TraceEvent

    mock_request = _create_mock_request()
    session = await create_session(
        SessionCreate(agent_name=agent_name, framework="pytest", tags=["test"]),
        mock_request,
    )

    # Manually set started_at for time-based testing
    # Ensure timezone-aware datetime
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    from sqlalchemy import select

    from storage.models import SessionModel

    async with session_maker() as db_session:
        stmt = select(SessionModel).where(SessionModel.id == session.id)
        result = await db_session.execute(stmt)
        s = result.scalar_one()
        s.started_at = started_at
        await db_session.commit()

        # Add events directly to repository for deterministic testing
        repo = TraceRepository(db_session)
        for event_data in events_data:
            # Use base TraceEvent with data in the data field (not as typed fields)
            # This ensures baseline computation can access the data
            data_payload = event_data.get("data", {})
            event = TraceEvent(
                id=str(uuid.uuid4()),
                session_id=session.id,
                event_type=event_data["event_type"],
                timestamp=datetime.now(timezone.utc),
                name=event_data["name"],
                data=data_payload,
                metadata={},
                importance=0.5,
                parent_id=None,
            )
            await repo.add_event(event)
        await db_session.commit()

    return session.id


async def _create_anomaly_alert(
    session_maker,
    session_id: str,
    alert_type: str = "test_alert",
    severity: float = 0.8,
    signal: str = "Test signal",
) -> str:
    """Helper to create an anomaly alert."""
    import uuid

    async with session_maker() as db_session:
        alert = AnomalyAlertModel(
            id=f"alert-{alert_type}-{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            alert_type=alert_type,
            severity=severity,
            signal=signal,
            event_ids=["event-1"],
            detection_source="test",
            detection_config={"threshold": 0.5},
        )
        db_session.add(alert)
        await db_session.commit()
        return alert.id


# ==============================================================================
# GET /api/agents/{agent_name}/baseline
# ==============================================================================


def test_baseline_returns_metrics_when_sessions_exist(drift_repo_factory):
    """Test baseline endpoint returns metrics when sessions exist."""
    baseline_endpoint = _get_route_endpoint("/api/agents/{agent_name}/baseline", "GET")

    async def run():
        # Create sessions with events
        now = datetime.now(timezone.utc)
        await _create_session_with_events(
            drift_repo_factory,
            agent_name="test-agent",
            started_at=now - timedelta(days=1),
            events_data=[
                {
                    "event_type": EventType.DECISION,
                    "name": "decision-1",
                    "data": {"confidence": 0.9, "reasoning": "test"},
                },
                {
                    "event_type": EventType.TOOL_RESULT,
                    "name": "tool-1",
                    "data": {"duration_ms": 100, "error": None},
                },
            ],
        )

        async with drift_repo_factory() as session:
            repo = TraceRepository(session)
            return await baseline_endpoint(agent_name="test-agent", repo=repo)

    result = asyncio.run(run())

    assert result["agent_name"] == "test-agent"
    assert result["session_count"] == 1
    assert "avg_decision_confidence" in result
    assert result["avg_decision_confidence"] == 0.9
    assert "error" not in result


def test_baseline_returns_error_when_no_sessions_found(drift_repo_factory):
    """Test baseline endpoint returns error when no sessions found for agent."""
    baseline_endpoint = _get_route_endpoint("/api/agents/{agent_name}/baseline", "GET")

    async def run():
        async with drift_repo_factory() as session:
            repo = TraceRepository(session)
            return await baseline_endpoint(agent_name="nonexistent-agent", repo=repo)

    result = asyncio.run(run())

    assert result["agent_name"] == "nonexistent-agent"
    assert result["session_count"] == 0
    assert "error" in result
    assert result["error"] == "No sessions found"


# ==============================================================================
# GET /api/agents/{agent_name}/drift
# ==============================================================================


def test_drift_returns_alerts_comparing_baseline_vs_recent(drift_repo_factory):
    """Test drift endpoint returns alerts comparing baseline (7d) vs recent (24h)."""
    drift_endpoint = _get_route_endpoint("/api/agents/{agent_name}/drift", "GET")

    async def run():
        now = datetime.now(timezone.utc)

        # Create baseline sessions (older than 24h)
        for i in range(3):
            await _create_session_with_events(
                drift_repo_factory,
                agent_name="drift-agent",
                started_at=now - timedelta(days=3),
                events_data=[
                    {
                        "event_type": EventType.DECISION,
                        "name": f"decision-{i}",
                        "data": {"confidence": 0.8},
                    },
                ],
            )

        # Create recent session with different behavior
        await _create_session_with_events(
            drift_repo_factory,
            agent_name="drift-agent",
            started_at=now - timedelta(hours=1),
            events_data=[
                {
                    "event_type": EventType.DECISION,
                    "name": "recent-decision",
                    "data": {"confidence": 0.3},  # Lower confidence
                },
            ],
        )

        async with drift_repo_factory() as session:
            repo = TraceRepository(session)
            return await drift_endpoint(agent_name="drift-agent", repo=repo)

    result = asyncio.run(run())

    assert result["agent_name"] == "drift-agent"
    assert "baseline" in result
    assert "current" in result
    assert "alerts" in result
    # Check baseline session count from the baseline dict
    assert result["baseline"]["session_count"] == 3
    assert result["current"]["session_count"] == 1


def test_drift_returns_error_when_no_sessions_found(drift_repo_factory):
    """Test drift endpoint returns error when no sessions found."""
    drift_endpoint = _get_route_endpoint("/api/agents/{agent_name}/drift", "GET")

    async def run():
        async with drift_repo_factory() as session:
            repo = TraceRepository(session)
            return await drift_endpoint(agent_name="nonexistent-agent", repo=repo)

    result = asyncio.run(run())

    assert result["agent_name"] == "nonexistent-agent"
    assert result["alerts"] == []
    assert "error" in result
    assert result["error"] == "No sessions found"


def test_drift_returns_message_when_insufficient_baseline_sessions(drift_repo_factory):
    """Test drift endpoint returns message when insufficient baseline sessions (< 1)."""
    drift_endpoint = _get_route_endpoint("/api/agents/{agent_name}/drift", "GET")

    async def run():
        now = datetime.now(timezone.utc)

        # Create only recent sessions (no baseline sessions older than 24h)
        for i in range(3):
            await _create_session_with_events(
                drift_repo_factory,
                agent_name="insufficient-agent",
                started_at=now - timedelta(hours=1),
                events_data=[
                    {
                        "event_type": EventType.DECISION,
                        "name": f"decision-{i}",
                        "data": {"confidence": 0.8},
                    },
                ],
            )

        async with drift_repo_factory() as session:
            repo = TraceRepository(session)
            return await drift_endpoint(agent_name="insufficient-agent", repo=repo)

    result = asyncio.run(run())

    assert result["agent_name"] == "insufficient-agent"
    assert result["alerts"] == []
    assert result["baseline_session_count"] == 0
    assert result["recent_session_count"] == 3
    assert "message" in result
    assert "Need at least 1 baseline session" in result["message"]


# ==============================================================================
# GET /api/sessions/{session_id}/alerts
# ==============================================================================


def test_session_alerts_returns_empty_list_for_session_with_no_alerts(drift_repo_factory):
    """Test session alerts endpoint returns empty list for session with no alerts."""
    alerts_endpoint = _get_route_endpoint("/api/sessions/{session_id}/alerts", "GET")

    async def run():
        # Create session without alerts
        session_id = await _create_session_with_events(
            drift_repo_factory,
            agent_name="no-alerts-agent",
            started_at=datetime.now(timezone.utc),
            events_data=[
                {
                    "event_type": EventType.DECISION,
                    "name": "decision-1",
                    "data": {"confidence": 0.9},
                },
            ],
        )

        async with drift_repo_factory() as session:
            repo = TraceRepository(session)
            return await alerts_endpoint(session_id=session_id, limit=50, repo=repo)

    result = asyncio.run(run())

    assert result.session_id is not None
    assert result.alerts == []
    assert result.total == 0


def test_session_alerts_returns_alerts_when_exist(drift_repo_factory):
    """Test session alerts endpoint returns alerts when they exist."""
    alerts_endpoint = _get_route_endpoint("/api/sessions/{session_id}/alerts", "GET")

    async def run():
        # Create session
        session_id = await _create_session_with_events(
            drift_repo_factory,
            agent_name="alerts-agent",
            started_at=datetime.now(timezone.utc),
            events_data=[
                {
                    "event_type": EventType.DECISION,
                    "name": "decision-1",
                    "data": {"confidence": 0.9},
                },
            ],
        )

        # Create anomaly alerts
        await _create_anomaly_alert(
            drift_repo_factory,
            session_id,
            alert_type="tool_loop",
            severity=0.9,
            signal="Tool loop detected",
        )
        await _create_anomaly_alert(
            drift_repo_factory,
            session_id,
            alert_type="high_error_rate",
            severity=0.7,
            signal="High error rate detected",
        )

        async with drift_repo_factory() as session:
            repo = TraceRepository(session)
            result = await alerts_endpoint(session_id=session_id, limit=50, repo=repo)
            return result, session_id

    result, session_id = asyncio.run(run())

    assert result.session_id == session_id
    assert result.total == 2
    assert len(result.alerts) == 2
    assert any(a.alert_type == "tool_loop" for a in result.alerts)
    assert any(a.alert_type == "high_error_rate" for a in result.alerts)


def test_session_alerts_returns_404_for_invalid_session_id(drift_repo_factory):
    """Test session alerts endpoint returns 404 for invalid session_id."""
    from fastapi import HTTPException

    alerts_endpoint = _get_route_endpoint("/api/sessions/{session_id}/alerts", "GET")

    async def run():
        async with drift_repo_factory() as session:
            repo = TraceRepository(session)
            try:
                await alerts_endpoint(session_id="invalid-session-id", limit=50, repo=repo)
                return False  # Should have raised
            except HTTPException as e:
                return e.status_code

    status_code = asyncio.run(run())
    assert status_code == 404


# ==============================================================================
# GET /api/alerts/{alert_id}
# ==============================================================================


def test_get_alert_returns_404_for_nonexistent_alert_id(drift_repo_factory):
    """Test get alert endpoint returns 404 for non-existent alert_id."""
    from fastapi import HTTPException

    alert_endpoint = _get_route_endpoint("/api/alerts/{alert_id}", "GET")

    async def run():
        async with drift_repo_factory() as session:
            repo = TraceRepository(session)
            try:
                await alert_endpoint(alert_id="nonexistent-alert-id", repo=repo)
                return False  # Should have raised
            except HTTPException as e:
                return e.status_code

    status_code = asyncio.run(run())
    assert status_code == 404


def test_get_alert_returns_alert_when_exists(drift_repo_factory):
    """Test get alert endpoint returns alert when it exists."""
    alert_endpoint = _get_route_endpoint("/api/alerts/{alert_id}", "GET")

    async def run():
        # Create session and alert
        session_id = await _create_session_with_events(
            drift_repo_factory,
            agent_name="get-alert-agent",
            started_at=datetime.now(timezone.utc),
            events_data=[
                {
                    "event_type": EventType.DECISION,
                    "name": "decision-1",
                    "data": {"confidence": 0.9},
                },
            ],
        )

        alert_id = await _create_anomaly_alert(
            drift_repo_factory,
            session_id,
            alert_type="test_alert",
            severity=0.85,
            signal="Test alert signal",
        )

        async with drift_repo_factory() as session:
            repo = TraceRepository(session)
            return await alert_endpoint(alert_id=alert_id, repo=repo)

    result = asyncio.run(run())

    assert result.id is not None
    assert result.alert_type == "test_alert"
    assert result.severity == 0.85
    assert result.signal == "Test alert signal"
    assert result.detection_source == "test"
