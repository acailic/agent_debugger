"""Tests for collector/baseline.py baseline computation and drift detection."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import (
    EventType,
    Session,
    TraceEvent,
)
from collector.baseline import (
    AgentBaseline,
    DriftAlert,
    MultiAgentMetrics,
    compute_baseline_from_sessions,
    detect_drift,
)


@pytest.fixture
def sample_session():
    """Create a sample session for testing."""
    return Session(
        id="test-session-1",
        agent_name="test-agent",
        framework="pydantic_ai",
        started_at=datetime.now(timezone.utc),
        total_tokens=1000,
        total_cost_usd=0.01,
        replay_value=0.5,
    )


@pytest.fixture
def sample_events():
    """Create sample events for testing."""
    return [
        TraceEvent(
            id="event-1",
            session_id="test-session-1",
            event_type=EventType.DECISION,
            timestamp=datetime.now(timezone.utc),
            name="test_decision",
            data={"confidence": 0.8, "evidence_event_ids": ["ev1", "ev2"]},
        ),
        TraceEvent(
            id="event-2",
            session_id="test-session-1",
            event_type=EventType.TOOL_RESULT,
            timestamp=datetime.now(timezone.utc),
            name="test_tool_result",
            data={"duration_ms": 100},
        ),
        TraceEvent(
            id="event-3",
            session_id="test-session-1",
            event_type=EventType.AGENT_TURN,
            timestamp=datetime.now(timezone.utc),
            name="test_agent_turn",
            data={"speaker": "agent-1"},
        ),
    ]


class TestMultiAgentMetrics:
    """Tests for MultiAgentMetrics dataclass."""

    def test_multi_agent_metrics_creation(self):
        """MultiAgentMetrics should initialize with default values."""
        metrics = MultiAgentMetrics()
        assert metrics.avg_policy_shifts_per_session == 0.0
        assert metrics.avg_turns_per_session == 0
        assert metrics.avg_speaker_count == 0.0
        assert metrics.escalation_pattern_rate == 0.0
        assert metrics.evidence_grounding_rate == 0.0

    def test_multi_agent_metrics_to_dict(self):
        """MultiAgentMetrics should serialize to dictionary correctly."""
        metrics = MultiAgentMetrics(
            avg_policy_shifts_per_session=1.5,
            avg_turns_per_session=10,
            avg_speaker_count=2.5,
            escalation_pattern_rate=0.3,
            evidence_grounding_rate=0.8,
        )
        result = metrics.to_dict()
        assert result["avg_policy_shifts_per_session"] == 1.5
        assert result["avg_turns_per_session"] == 10
        assert result["avg_speaker_count"] == 2.5
        assert result["escalation_pattern_rate"] == 0.3
        assert result["evidence_grounding_rate"] == 0.8


class TestAgentBaseline:
    """Tests for AgentBaseline dataclass."""

    def test_agent_baseline_creation(self):
        """AgentBaseline should initialize with required fields."""
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
        )
        assert baseline.agent_name == "test-agent"
        assert baseline.session_count == 5
        assert baseline.time_window_days == 7  # default

    def test_agent_baseline_to_dict(self):
        """AgentBaseline should serialize to dictionary correctly."""
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.75,
            error_rate=0.1,
        )
        result = baseline.to_dict()
        assert result["agent_name"] == "test-agent"
        assert result["session_count"] == 5
        assert result["avg_decision_confidence"] == 0.75
        assert result["error_rate"] == 0.1

    def test_agent_baseline_with_multi_agent_metrics(self):
        """AgentBaseline should include multi-agent metrics when present."""
        multi_metrics = MultiAgentMetrics(
            avg_turns_per_session=10,
            escalation_pattern_rate=0.2,
        )
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            multi_agent_metrics=multi_metrics,
        )
        result = baseline.to_dict()
        assert "multi_agent_metrics" in result
        assert result["multi_agent_metrics"]["avg_turns_per_session"] == 10


class TestDriftAlert:
    """Tests for DriftAlert dataclass."""

    def test_drift_alert_creation(self):
        """DriftAlert should initialize with all required fields."""
        alert = DriftAlert(
            metric="error_rate",
            metric_label="Error Rate",
            baseline_value=0.1,
            current_value=0.2,
            change_percent=100.0,
            severity="warning",
            description="Error rate doubled",
            likely_cause="API degradation",
        )
        assert alert.metric == "error_rate"
        assert alert.severity == "warning"
        assert alert.change_percent == 100.0

    def test_drift_alert_to_dict(self):
        """DriftAlert should serialize to dictionary correctly."""
        alert = DriftAlert(
            metric="cost",
            metric_label="Cost",
            baseline_value=0.5,
            current_value=0.75,
            change_percent=50.0,
            severity="critical",
            description="Cost increased",
        )
        result = alert.to_dict()
        assert result["metric"] == "cost"
        assert result["baseline_value"] == 0.5
        assert result["current_value"] == 0.75
        assert result["change_percent"] == 50.0


class TestComputeBaselineFromSessions:
    """Tests for compute_baseline_from_sessions function."""

    def test_empty_session_list(self):
        """Empty session list should return baseline with zero counts."""
        baseline = compute_baseline_from_sessions(
            agent_name="test-agent",
            sessions=[],
            events_by_session={},
        )
        assert baseline.session_count == 0
        assert baseline.agent_name == "test-agent"
        assert baseline.avg_decision_confidence == 0.0

    def test_single_session_baseline(self):
        """Single session should compute baseline correctly."""
        session = Session(
            id="session-1",
            agent_name="test-agent",
            framework="pydantic_ai",
            started_at=datetime.now(timezone.utc),
            total_tokens=1000,
            total_cost_usd=0.01,
            replay_value=0.5,
        )
        events = [
            TraceEvent(
                id="ev1",
                session_id="session-1",
                event_type=EventType.DECISION,
                timestamp=datetime.now(timezone.utc),
                name="decision",
                data={"confidence": 0.8},
            ),
            TraceEvent(
                id="ev2",
                session_id="session-1",
                event_type=EventType.TOOL_RESULT,
                timestamp=datetime.now(timezone.utc),
                name="tool",
                data={"duration_ms": 100},
            ),
        ]
        baseline = compute_baseline_from_sessions(
            agent_name="test-agent",
            sessions=[session],
            events_by_session={"session-1": events},
        )
        assert baseline.session_count == 1
        assert baseline.avg_decision_confidence == 0.8
        assert baseline.avg_cost_per_session == 0.01
        assert baseline.avg_tokens_per_session == 1000

    def test_multiple_sessions_aggregation(self):
        """Multiple sessions should aggregate metrics correctly."""
        sessions = [
            Session(
                id=f"session-{i}",
                agent_name="test-agent",
                framework="pydantic_ai",
                started_at=datetime.now(timezone.utc),
                total_tokens=1000 * (i + 1),
                total_cost_usd=0.01 * (i + 1),
                replay_value=0.5 * (i + 1),
            )
            for i in range(3)
        ]
        events_by_session = {}
        for i, session in enumerate(sessions):
            events_by_session[session.id] = [
                TraceEvent(
                    id=f"ev-{i}",
                    session_id=session.id,
                    event_type=EventType.DECISION,
                    timestamp=datetime.now(timezone.utc),
                    name="decision",
                    data={"confidence": 0.6 + (i * 0.1)},
                ),
            ]
        baseline = compute_baseline_from_sessions(
            agent_name="test-agent",
            sessions=sessions,
            events_by_session=events_by_session,
        )
        assert baseline.session_count == 3
        assert baseline.avg_decision_confidence == pytest.approx(0.7, rel=0.1)
        assert baseline.avg_cost_per_session == pytest.approx(0.02, rel=0.1)

    def test_identical_sessions_baseline(self):
        """Identical sessions should produce consistent baseline."""
        sessions = []
        events_by_session = {}
        for i in range(5):
            session = Session(
                id=f"session-{i}",
                agent_name="test-agent",
                framework="pydantic_ai",
                started_at=datetime.now(timezone.utc),
                total_tokens=1000,
                total_cost_usd=0.01,
                replay_value=0.5,
            )
            sessions.append(session)
            events_by_session[session.id] = [
                TraceEvent(
                    id=f"ev{i}",
                    session_id=session.id,
                    event_type=EventType.DECISION,
                    timestamp=datetime.now(timezone.utc),
                    name="decision",
                    data={"confidence": 0.8},
                ),
            ]
        baseline = compute_baseline_from_sessions(
            agent_name="test-agent",
            sessions=sessions,
            events_by_session=events_by_session,
        )
        assert baseline.session_count == 5
        assert baseline.avg_decision_confidence == 0.8
        assert baseline.avg_cost_per_session == 0.01

    def test_low_confidence_rate_calculation(self):
        """Baseline should correctly calculate low confidence rate."""
        session = Session(
            id="session-1",
            agent_name="test-agent",
            framework="pydantic_ai",
            started_at=datetime.now(timezone.utc),
        )
        events = [
            TraceEvent(
                id=f"ev{i}",
                session_id="session-1",
                event_type=EventType.DECISION,
                timestamp=datetime.now(timezone.utc),
                name="decision",
                data={"confidence": 0.3 if i < 3 else 0.8},
            )
            for i in range(5)
        ]
        baseline = compute_baseline_from_sessions(
            agent_name="test-agent",
            sessions=[session],
            events_by_session={"session-1": events},
        )
        assert baseline.low_confidence_rate == 0.6  # 3 out of 5

    def test_tool_error_rate_calculation(self):
        """Baseline should correctly calculate tool error rate."""
        session = Session(
            id="session-1",
            agent_name="test-agent",
            framework="pydantic_ai",
            started_at=datetime.now(timezone.utc),
        )
        events = [
            TraceEvent(
                id=f"ev{i}",
                session_id="session-1",
                event_type=EventType.TOOL_RESULT,
                timestamp=datetime.now(timezone.utc),
                name="tool",
                data={"error": "failed" if i < 2 else None, "duration_ms": 100},
            )
            for i in range(5)
        ]
        baseline = compute_baseline_from_sessions(
            agent_name="test-agent",
            sessions=[session],
            events_by_session={"session-1": events},
        )
        assert baseline.error_rate == 0.4  # 2 out of 5

    def test_multi_agent_metrics_computation(self):
        """Baseline should compute multi-agent metrics when enabled."""
        session = Session(
            id="session-1",
            agent_name="test-agent",
            framework="autogen",
            started_at=datetime.now(timezone.utc),
        )
        events = [
            TraceEvent(
                id="ev1",
                session_id="session-1",
                event_type=EventType.AGENT_TURN,
                timestamp=datetime.now(timezone.utc),
                name="turn",
                data={"speaker": "agent-1"},
            ),
            TraceEvent(
                id="ev2",
                session_id="session-1",
                event_type=EventType.AGENT_TURN,
                timestamp=datetime.now(timezone.utc),
                name="turn",
                data={"speaker": "agent-2"},
            ),
            TraceEvent(
                id="ev3",
                session_id="session-1",
                event_type=EventType.PROMPT_POLICY,
                timestamp=datetime.now(timezone.utc),
                name="policy",
                data={"template_id": "template-a"},
            ),
            TraceEvent(
                id="ev4",
                session_id="session-1",
                event_type=EventType.PROMPT_POLICY,
                timestamp=datetime.now(timezone.utc),
                name="policy",
                data={"template_id": "template-b"},
            ),
        ]
        baseline = compute_baseline_from_sessions(
            agent_name="test-agent",
            sessions=[session],
            events_by_session={"session-1": events},
            include_multi_agent=True,
        )
        assert baseline.multi_agent_metrics is not None
        assert baseline.multi_agent_metrics.avg_turns_per_session == 2
        assert baseline.multi_agent_metrics.avg_speaker_count == 2.0
        assert baseline.multi_agent_metrics.avg_policy_shifts_per_session == 1.0

    def test_multi_agent_metrics_disabled(self):
        """Baseline should skip multi-agent metrics when disabled."""
        session = Session(
            id="session-1",
            agent_name="test-agent",
            framework="pydantic_ai",
            started_at=datetime.now(timezone.utc),
        )
        baseline = compute_baseline_from_sessions(
            agent_name="test-agent",
            sessions=[session],
            events_by_session={},
            include_multi_agent=False,
        )
        assert baseline.multi_agent_metrics is None


class TestDetectDrift:
    """Tests for detect_drift function."""

    def test_small_baseline_no_drift(self):
        """Baselines with less than 1 session should not trigger drift."""
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
            avg_decision_confidence=0.4,
        )
        alerts = detect_drift(baseline, current)
        assert len(alerts) == 0

    def test_warning_threshold_drift(self):
        """Changes above 25% should trigger warning alerts."""
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.8,
        )
        current = AgentBaseline(
            agent_name="test-agent",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.5,  # 37.5% decrease
        )
        alerts = detect_drift(baseline, current)
        assert len(alerts) == 1
        assert alerts[0].severity == "warning"
        assert alerts[0].metric == "decision_confidence"

    def test_critical_threshold_drift(self):
        """Changes above 50% should trigger critical alerts."""
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.8,
        )
        current = AgentBaseline(
            agent_name="test-agent",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.3,  # 62.5% decrease
        )
        alerts = detect_drift(baseline, current)
        assert len(alerts) == 1
        assert alerts[0].severity == "critical"

    def test_no_drift_within_threshold(self):
        """Changes below 25% should not trigger alerts."""
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.8,
        )
        current = AgentBaseline(
            agent_name="test-agent",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.7,  # 12.5% decrease
        )
        alerts = detect_drift(baseline, current)
        assert len(alerts) == 0

    def test_error_rate_increase_drift(self):
        """Error rate increases should trigger drift alerts."""
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            error_rate=0.1,
        )
        current = AgentBaseline(
            agent_name="test-agent",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            error_rate=0.2,  # 100% increase
        )
        alerts = detect_drift(baseline, current)
        assert len(alerts) == 1
        assert alerts[0].metric == "error_rate"
        assert alerts[0].severity == "critical"

    def test_cost_increase_drift(self):
        """Cost increases should trigger drift alerts."""
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            avg_cost_per_session=0.1,
        )
        current = AgentBaseline(
            agent_name="test-agent",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            avg_cost_per_session=0.2,  # 100% increase - critical
        )
        alerts = detect_drift(baseline, current)
        assert len(alerts) == 1
        assert alerts[0].metric == "avg_cost"
        assert alerts[0].severity == "critical"

    def test_multiple_metrics_drift(self):
        """Multiple metrics drifting should generate multiple alerts."""
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.8,
            error_rate=0.1,
            avg_cost_per_session=0.1,
        )
        current = AgentBaseline(
            agent_name="test-agent",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.4,  # 50% decrease
            error_rate=0.25,  # 150% increase
            avg_cost_per_session=0.2,  # 100% increase
        )
        alerts = detect_drift(baseline, current)
        assert len(alerts) == 3

    def test_drift_alerts_sorted_by_severity(self):
        """Drift alerts should be sorted with critical first."""
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.8,
            error_rate=0.1,
            tool_loop_rate=0.1,
        )
        current = AgentBaseline(
            agent_name="test-agent",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.3,  # critical
            error_rate=0.25,  # critical
            tool_loop_rate=0.15,  # warning
        )
        alerts = detect_drift(baseline, current)
        # Critical alerts should come first
        assert alerts[0].severity == "critical"
        assert alerts[1].severity == "critical"

    def test_zero_to_nonzero_drift(self):
        """Going from zero to non-zero should trigger warning."""
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            tool_loop_rate=0.0,
        )
        current = AgentBaseline(
            agent_name="test-agent",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            tool_loop_rate=0.5,
        )
        alerts = detect_drift(baseline, current)
        assert len(alerts) == 1
        assert alerts[0].severity == "warning"
        assert alerts[0].change_percent == 100.0

    def test_improvement_no_drift(self):
        """Metric improvements should not trigger drift alerts."""
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            error_rate=0.3,
        )
        current = AgentBaseline(
            agent_name="test-agent",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            error_rate=0.1,  # 67% decrease (improvement)
        )
        alerts = detect_drift(baseline, current)
        assert len(alerts) == 0

    def test_refusal_rate_drift(self):
        """Refusal rate increases should trigger drift alerts."""
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            refusal_rate=0.1,
        )
        current = AgentBaseline(
            agent_name="test-agent",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            refusal_rate=0.3,  # 200% increase
        )
        alerts = detect_drift(baseline, current)
        assert len(alerts) == 1
        assert alerts[0].metric == "refusal_rate"
        assert alerts[0].severity == "critical"

    def test_tool_duration_drift(self):
        """Tool duration increases should trigger drift alerts."""
        baseline = AgentBaseline(
            agent_name="test-agent",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            avg_tool_duration_ms=100.0,
        )
        current = AgentBaseline(
            agent_name="test-agent",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            avg_tool_duration_ms=150.0,  # 50% increase
        )
        alerts = detect_drift(baseline, current)
        assert len(alerts) == 1
        assert alerts[0].metric == "tool_duration"
        assert alerts[0].severity == "critical"
