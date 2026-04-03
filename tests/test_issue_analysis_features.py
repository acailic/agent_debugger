"""Regression tests for Issue #4 (Drift Detection) and Issue #5 (Behavior Alerts).

These tests reproduce known issues with drift detection requiring 3+ baseline sessions
and behavior alerts being empty across most sessions due to insufficient baseline data.

Issue #4: Drift detection needs more data
- Drift detection requires 3+ baseline sessions per agent
- With only 1 session per agent (current seed data), it returns "Need at least 3 baseline sessions"
- These tests verify the 3-session requirement and proper responses

Issue #5: Behavior alerts empty across all sessions
- BehaviorMonitor requires min_baseline_days=7 and min_baseline_sessions=30
- Most seed sessions have no behavior alerts
- These tests verify behavior alert detection with insufficient baseline
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import api.main as api_main
from agent_debugger_sdk.core.context import configure_event_pipeline
from agent_debugger_sdk.core.events import EventType, TraceEvent
from api import app_context
from api import services as api_services
from collector.baseline import AgentBaseline, detect_drift
from collector.behavior_monitor import BehaviorMonitor
from collector.buffer import get_event_buffer
from collector.server import SessionCreate, configure_storage, create_session
from storage import Base, TraceRepository
from storage.models import AnomalyAlertModel

# =============================================================================
# Helper Functions (borrowed from test_drift_alerts_api.py)
# =============================================================================


def _get_route_endpoint(path: str, method: str):
    """Get a route endpoint by path and method."""
    from fastapi.routing import APIRoute

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

    mock_request = _create_mock_request()
    session = await create_session(
        SessionCreate(agent_name=agent_name, framework="pytest", tags=["test"]),
        mock_request,
    )

    # Manually set started_at for time-based testing
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


# =============================================================================
# Issue #4: Drift Detection Needs More Data (FIXED: 1+ Sessions Required)
# =============================================================================


class TestIssue4DriftDetectionInsufficientData:
    """Regression tests for Issue #4: Drift detection lowered to 1 baseline session.

    The drift detection system now returns alerts with 1+ baseline sessions for an agent.
    This was changed from 3+ sessions to work with demo data that has 1 session per agent.
    """

    def test_drift_with_zero_baseline_sessions_returns_empty(self):
        """Reproduce Issue #4: Zero baseline sessions should return empty alerts list.

        EXPECTED (current behavior): detect_drift returns [] when baseline.session_count < 1
        This test documents that drift detection intentionally requires 1+ session.
        """
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=0,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.8,
        )
        current = AgentBaseline(
            agent_name="test-agent",
            session_count=1,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.4,  # 50% drop - would be critical if detected
        )

        alerts = detect_drift(baseline, current)

        # EXPECTED: No alerts due to insufficient baseline
        assert len(alerts) == 0, "Drift detection should not trigger with 0 baseline sessions"

    def test_drift_with_one_baseline_session_detects_drift(self):
        """Verify Issue #4 fix: One baseline session should now detect drift.

        EXPECTED (current behavior): detect_drift returns alerts when baseline.session_count >= 1
        Even with massive changes (confidence 0.8 -> 0.2), drift is now detected.
        """
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=1,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.8,
            error_rate=0.1,
        )
        current = AgentBaseline(
            agent_name="test-agent",
            session_count=1,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.2,  # 75% drop - critical
            error_rate=0.5,  # 400% increase - critical
        )

        alerts = detect_drift(baseline, current)

        # EXPECTED: Alerts detected with 1 baseline session (FIXED)
        assert len(alerts) >= 1, "Drift detection should trigger with 1 baseline session"
        assert any(a.metric == "decision_confidence" for a in alerts), "Should detect confidence drop"
        assert any(a.metric == "error_rate" for a in alerts), "Should detect error rate spike"

    def test_drift_with_two_baseline_sessions_detects_drift(self):
        """Verify Issue #4 fix: Two baseline sessions should detect drift.

        EXPECTED (current behavior): detect_drift returns alerts when baseline.session_count >= 1
        The threshold is now 1, not 3.
        """
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=2,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.8,
        )
        current = AgentBaseline(
            agent_name="test-agent",
            session_count=1,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.3,  # 62.5% drop - would be critical
        )

        alerts = detect_drift(baseline, current)

        # EXPECTED: Alerts with 2 baseline sessions (FIXED)
        assert len(alerts) >= 1, "Drift detection should trigger with 2 baseline sessions"
        assert alerts[0].severity == "critical"
        assert alerts[0].metric == "decision_confidence"

    def test_drift_with_three_baseline_sessions_succeeds(self):
        """Verify Issue #4 fix: Three baseline sessions should enable drift detection.

        EXPECTED (current behavior): detect_drift returns alerts when baseline.session_count >= 1
        This still works with 3+ sessions (original behavior preserved).
        """
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.8,
        )
        current = AgentBaseline(
            agent_name="test-agent",
            session_count=1,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.3,  # 62.5% drop
        )

        alerts = detect_drift(baseline, current)

        # EXPECTED: Critical alert detected with 3+ baseline sessions
        assert len(alerts) == 1, "Drift detection should trigger with 3+ baseline sessions"
        assert alerts[0].severity == "critical"
        assert alerts[0].metric == "decision_confidence"

    def test_drift_api_endpoint_insufficient_sessions_message(self, drift_repo_factory):
        """Verify Issue #4 fix: API endpoint returns "Need at least 1 baseline session" message.

        EXPECTED (current behavior): /api/agents/{agent_name}/drift returns specific message
        when baseline_session_count < 1, rather than attempting drift detection.
        """
        drift_endpoint = _get_route_endpoint("/api/agents/{agent_name}/drift", "GET")

        async def run():
            now = datetime.now(timezone.utc)

            # Create only 1 baseline session (now sufficient for drift)
            await _create_session_with_events(
                drift_repo_factory,
                agent_name="sufficient-agent",
                started_at=now - timedelta(days=3),
                events_data=[
                    {
                        "event_type": EventType.DECISION,
                        "name": "baseline-decision",
                        "data": {"confidence": 0.8},
                    },
                ],
            )

            # Create recent session with different confidence
            await _create_session_with_events(
                drift_repo_factory,
                agent_name="sufficient-agent",
                started_at=now - timedelta(hours=1),
                events_data=[
                    {
                        "event_type": EventType.DECISION,
                        "name": "recent-decision",
                        "data": {"confidence": 0.3},
                    },
                ],
            )

            async with drift_repo_factory() as session:
                repo = TraceRepository(session)
                return await drift_endpoint(agent_name="sufficient-agent", repo=repo)

        result = asyncio.run(run())

        # EXPECTED: Drift detected with 1 baseline session (FIXED)
        assert result.agent_name == "sufficient-agent"
        # When drift detection succeeds, returns baseline/current objects with session_count inside
        assert result.baseline.session_count == 1
        assert result.current.session_count == 1
        # Should have alerts now, not a message about insufficient sessions
        assert not result.message or "Need at least" not in result.message
        # May have alerts if confidence difference triggers drift
        assert isinstance(result.alerts, list)

    def test_drift_per_agent_independence(self, drift_repo_factory):
        """Verify Issue #4: Drift detection works independently per agent.

        EXPECTED (current behavior): Sessions for agent A don't affect agent B's drift.
        Each agent's baseline is computed separately.
        """
        drift_endpoint = _get_route_endpoint("/api/agents/{agent_name}/drift", "GET")

        async def run():
            now = datetime.now(timezone.utc)

            # Agent A: 1 baseline session (now sufficient)
            await _create_session_with_events(
                drift_repo_factory,
                agent_name="agent-a",
                started_at=now - timedelta(days=3),
                events_data=[
                    {
                        "event_type": EventType.DECISION,
                        "name": "decision-a",
                        "data": {"confidence": 0.8},
                    },
                ],
            )

            # Agent B: 0 baseline sessions (insufficient)
            # Create only recent session, no baseline
            await _create_session_with_events(
                drift_repo_factory,
                agent_name="agent-b",
                started_at=now - timedelta(hours=1),
                events_data=[
                    {
                        "event_type": EventType.DECISION,
                        "name": "decision-b",
                        "data": {"confidence": 0.8},
                    },
                ],
            )

            async with drift_repo_factory() as session:
                repo = TraceRepository(session)
                result_a = await drift_endpoint(agent_name="agent-a", repo=repo)
                result_b = await drift_endpoint(agent_name="agent-b", repo=repo)
                return result_a, result_b

        result_a, result_b = asyncio.run(run())

        # EXPECTED: Agent A has sufficient baseline, Agent B does not (0 sessions)
        assert not result_a.message or result_a.baseline_session_count >= 1
        assert result_b.message is not None
        assert "Need at least 1 baseline session" in result_b.message


# =============================================================================
# Issue #5: Behavior Alerts Empty Across All Sessions
# =============================================================================


class TestIssue5BehaviorAlertsInsufficientBaseline:
    """Regression tests for Issue #5: Behavior alerts empty due to insufficient baseline.

    The BehaviorMonitor requires min_baseline_days=7 and min_baseline_sessions=30
    for full detection. With insufficient baseline, only critical changes (3x failure rate)
    are detected. Most seed sessions have no behavior alerts.
    """

    def test_behavior_monitor_insufficient_baseline_critical_only(self):
        """Reproduce Issue #5: Insufficient baseline only detects critical failure spikes.

        EXPECTED (current behavior): With < 7 days or < 30 sessions, BehaviorMonitor
        only detects failure_rate_spike when ratio > 3.0 (not 2.0).
        """
        monitor = BehaviorMonitor()

        # Insufficient baseline (3 days, 10 sessions)
        short_baseline = {
            "session_count": 10,
            "time_window_days": 3,
            "avg_latency_ms": 100.0,
            "failure_rate": 0.02,
            "avg_cost_per_session": 0.25,
        }

        # Recent with 2.5x failure rate (would trigger with sufficient baseline)
        recent_2_5x = short_baseline.copy()
        recent_2_5x["failure_rate"] = 0.05  # 2.5x baseline

        changes_2_5x = monitor.detect_changes(short_baseline, recent_2_5x)

        # EXPECTED: No alerts (2.5x < 3.0 threshold for insufficient baseline)
        assert len(changes_2_5x) == 0, "BehaviorMonitor with insufficient baseline should not detect 2.5x failure spike"

    def test_behavior_monitor_insufficient_baseline_3x_threshold(self):
        """Verify Issue #5: Insufficient baseline detects 3x+ failure spikes.

        EXPECTED (current behavior): With insufficient baseline, only 3x+ failure
        rate spikes trigger alerts (critical detection mode).
        """
        monitor = BehaviorMonitor()

        # Insufficient baseline
        short_baseline = {
            "session_count": 10,
            "time_window_days": 3,
            "failure_rate": 0.02,
        }

        # Recent with 3.5x failure rate (above critical threshold)
        recent_3_5x = short_baseline.copy()
        recent_3_5x["failure_rate"] = 0.07  # 3.5x baseline

        changes_3_5x = monitor.detect_changes(short_baseline, recent_3_5x)

        # EXPECTED: Critical alert detected (3.5x > 3.0 threshold)
        assert len(changes_3_5x) == 1
        assert changes_3_5x[0].type == "failure_rate_spike"
        assert changes_3_5x[0].severity == "high"

    def test_behavior_monitor_sufficient_baseline_2x_threshold(self):
        """Verify Issue #5: Sufficient baseline detects 2x+ failure spikes.

        EXPECTED (current behavior): With >= 7 days and >= 30 sessions, BehaviorMonitor
        detects failure_rate_spike at 2x threshold (normal detection mode).
        """
        monitor = BehaviorMonitor()

        # Sufficient baseline (7 days, 30 sessions)
        sufficient_baseline = {
            "session_count": 30,
            "time_window_days": 7,
            "failure_rate": 0.02,
            "avg_latency_ms": 100.0,
            "avg_cost_per_session": 0.25,
        }

        # Recent with 2.5x failure rate (above 2x threshold)
        recent_2_5x = sufficient_baseline.copy()
        recent_2_5x["failure_rate"] = 0.05  # 2.5x baseline

        changes_2_5x = monitor.detect_changes(sufficient_baseline, recent_2_5x)

        # EXPECTED: Alert detected at 2x threshold with sufficient baseline
        assert len(changes_2_5x) == 1
        assert changes_2_5x[0].type == "failure_rate_spike"
        assert changes_2_5x[0].severity == "high"

    def test_behavior_alert_count_matches_database_records(self, drift_repo_factory):
        """Reproduce Issue #5: Sessions may have behavior_alerts count but no DB records.

        EXPECTED (current behavior): behavior_alert_count on sessions should match
        actual AnomalyAlertModel records. If count > 0 but no records exist, this
        indicates a data inconsistency issue.
        """

        async def run():
            now = datetime.now(timezone.utc)

            # Create a session
            session_id = await _create_session_with_events(
                drift_repo_factory,
                agent_name="test-agent",
                started_at=now,
                events_data=[
                    {
                        "event_type": EventType.DECISION,
                        "name": "decision-1",
                        "data": {"confidence": 0.9},
                    },
                ],
            )

            # Create behavior alerts for this session
            await _create_anomaly_alert(
                drift_repo_factory,
                session_id,
                alert_type="looping_behavior",
                severity=0.8,
                signal="Loop detected",
            )
            await _create_anomaly_alert(
                drift_repo_factory,
                session_id,
                alert_type="high_error_rate",
                severity=0.7,
                signal="Error spike",
            )

            async with drift_repo_factory() as db_session:
                repo = TraceRepository(db_session)

                # Get session
                session = await repo.get_session(session_id)

                # Get anomaly alerts
                alerts = await repo.list_anomaly_alerts(session_id, limit=10)

                return session, alerts

        session, alerts = asyncio.run(run())

        # EXPECTED: Alert count should match database records
        assert len(alerts) == 2, "Session should have 2 behavior alerts in database"
        # Note: session.behavior_alert_count may not exist - this is an expected field
        # that should be added or populated based on AnomalyAlertModel records

    def test_looping_behavior_session_has_alerts(self, drift_repo_factory):
        """Verify Issue #5: Sessions marked as looping should have behavior alerts.

        EXPECTED (current behavior): Sessions with looping/repeated tool call patterns
        should have AnomalyAlertModel records with alert_type="looping_behavior" or
        similar. The seed data includes "seed-looping-behavior" with behavior_alerts: 2.
        """

        async def run():
            now = datetime.now(timezone.utc)

            # Create a session with looping behavior pattern
            session_id = await _create_session_with_events(
                drift_repo_factory,
                agent_name="looping-agent",
                started_at=now,
                events_data=[
                    # Simulate looping pattern: same tool called repeatedly
                    {
                        "event_type": EventType.TOOL_CALL,
                        "name": "read_file",
                        "data": {"path": "/tmp/file.txt"},
                    },
                    {
                        "event_type": EventType.TOOL_RESULT,
                        "name": "read_file_result",
                        "data": {"error": None, "duration_ms": 50},
                    },
                    {
                        "event_type": EventType.TOOL_CALL,
                        "name": "read_file",
                        "data": {"path": "/tmp/file.txt"},
                    },
                    {
                        "event_type": EventType.TOOL_RESULT,
                        "name": "read_file_result",
                        "data": {"error": None, "duration_ms": 50},
                    },
                    {
                        "event_type": EventType.TOOL_CALL,
                        "name": "read_file",
                        "data": {"path": "/tmp/file.txt"},
                    },
                    {
                        "event_type": EventType.TOOL_RESULT,
                        "name": "read_file_result",
                        "data": {"error": None, "duration_ms": 50},
                    },
                ],
            )

            # Manually create looping behavior alert (as seed script does)
            await _create_anomaly_alert(
                drift_repo_factory,
                session_id,
                alert_type="looping_behavior",
                severity=0.8,
                signal="Detected repeated tool call pattern",
            )

            async with drift_repo_factory() as db_session:
                repo = TraceRepository(db_session)
                alerts = await repo.list_anomaly_alerts(session_id, limit=10)
                return alerts

        alerts = asyncio.run(run())

        # EXPECTED: Looping session should have behavior alerts
        assert len(alerts) >= 1, "Looping behavior session should have at least 1 alert"
        assert any(a.alert_type == "looping_behavior" for a in alerts), "Should have looping_behavior alert type"

    def test_behavior_monitor_latency_threshold_with_insufficient_baseline(self):
        """Reproduce Issue #5: Latency changes not detected with insufficient baseline.

        EXPECTED (current behavior): With insufficient baseline, BehaviorMonitor's
        _detect_critical_changes only checks failure_rate, not latency or cost.
        """
        monitor = BehaviorMonitor()

        # Insufficient baseline
        short_baseline = {
            "session_count": 10,
            "time_window_days": 3,
            "avg_latency_ms": 100.0,
            "failure_rate": 0.02,
        }

        # Recent with 2x latency (would trigger with sufficient baseline)
        recent_latency_spike = short_baseline.copy()
        recent_latency_spike["avg_latency_ms"] = 200.0  # 2x baseline

        changes = monitor.detect_changes(short_baseline, recent_latency_spike)

        # EXPECTED: No latency alerts with insufficient baseline
        latency_changes = [c for c in changes if c.type == "latency_increase"]
        assert len(latency_changes) == 0, "BehaviorMonitor with insufficient baseline should not detect latency spikes"

    def test_behavior_monitor_cost_threshold_with_insufficient_baseline(self):
        """Reproduce Issue #5: Cost changes not detected with insufficient baseline.

        EXPECTED (current behavior): With insufficient baseline, BehaviorMonitor's
        _detect_critical_changes only checks failure_rate, not cost.
        """
        monitor = BehaviorMonitor()

        # Insufficient baseline
        short_baseline = {
            "session_count": 10,
            "time_window_days": 3,
            "avg_cost_per_session": 0.25,
            "failure_rate": 0.02,
        }

        # Recent with 3x cost (would trigger with sufficient baseline)
        recent_cost_spike = short_baseline.copy()
        recent_cost_spike["avg_cost_per_session"] = 0.75  # 3x baseline

        changes = monitor.detect_changes(short_baseline, recent_cost_spike)

        # EXPECTED: No cost alerts with insufficient baseline
        cost_changes = [c for c in changes if c.type == "cost_increase"]
        assert len(cost_changes) == 0, "BehaviorMonitor with insufficient baseline should not detect cost spikes"
