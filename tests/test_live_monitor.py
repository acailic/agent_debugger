"""Tests for collector/live_monitor.py LiveMonitor class."""

from datetime import datetime, timedelta, timezone

import pytest

from agent_debugger_sdk.core.events import Checkpoint, EventType, TraceEvent
from collector.live_monitor import LiveMonitor, auto_checkpoint_on_alert


@pytest.fixture
def monitor():
    """Create a LiveMonitor instance for testing."""
    return LiveMonitor()


@pytest.fixture
def test_session_id():
    """Provide a consistent session_id for testing.

    Note: Many existing tests use hardcoded "s1". This fixture is available
    for new tests to avoid ID collision issues and improve maintainability.
    """
    return "test-session-1"


class TestComputeRollingWindow:
    """Tests for LiveMonitor.compute_rolling_window()."""

    def test_empty_events(self, monitor):
        """compute_rolling_window with empty events list."""
        window = monitor.compute_rolling_window([])
        assert window.event_count == 0
        assert window.tool_calls == 0
        assert window.llm_calls == 0
        assert window.decisions == 0
        assert window.errors == 0
        assert window.refusals == 0
        assert window.total_tokens == 0
        assert window.total_cost_usd == 0.0
        assert window.unique_tools == set()
        assert window.unique_agents == set()
        assert window.avg_confidence == 0.0
        assert window.state_progression == []

    def test_with_events(self, monitor):
        """compute_rolling_window with various event types."""
        now = datetime.now(timezone.utc)
        events = [
            TraceEvent(
                session_id="s1",
                event_type=EventType.TOOL_CALL,
                name="search",
                data={"tool_name": "search"},
                importance=0.5,
                timestamp=now,
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.DECISION,
                name="decide_action",
                data={"confidence": 0.8},
                importance=0.7,
                timestamp=now + timedelta(seconds=1),
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.ERROR,
                name="error_occurred",
                data={"error": "test error"},
                importance=0.9,
                timestamp=now + timedelta(seconds=2),
                upstream_event_ids=[],
            ),
        ]
        window = monitor.compute_rolling_window(events)
        assert window.event_count == 3
        assert window.tool_calls == 1
        assert window.decisions == 1
        assert window.errors == 1


class TestBuildRollingSummary:
    """Tests for LiveMonitor.build_rolling_summary()."""

    def test_build_rolling_summary(self, monitor):
        """build_rolling_summary from a RollingWindow."""
        now = datetime.now(timezone.utc)
        window = monitor.compute_rolling_window(
            [
                TraceEvent(
                    session_id="s1",
                    event_type=EventType.DECISION,
                    name="decide",
                    data={"confidence": 0.9},
                    importance=0.7,
                    timestamp=now,
                    upstream_event_ids=[],
                )
            ]
        )
        summary = monitor.build_rolling_summary(window)
        assert summary.text is not None
        assert isinstance(summary.metrics, dict)
        assert summary.window_type in ["time", "event_count"]
        assert summary.window_size > 0
        assert isinstance(summary.computed_at, datetime)


class TestComputeCheckpointDeltas:
    """Tests for LiveMonitor.compute_checkpoint_deltas()."""

    def test_empty_checkpoints(self, monitor):
        """compute_checkpoint_deltas with empty checkpoints list."""
        deltas = monitor.compute_checkpoint_deltas([], [])
        assert deltas == []

    def test_single_checkpoint(self, monitor):
        """compute_checkpoint_deltas with single checkpoint."""
        now = datetime.now(timezone.utc)
        checkpoint = Checkpoint(
            session_id="s1",
            event_id="e1",
            sequence=1,
            state={"key": "value"},
            importance=0.5,
            timestamp=now,
        )
        deltas = monitor.compute_checkpoint_deltas([checkpoint], [])
        assert len(deltas) == 1
        delta = deltas[0]
        assert delta.checkpoint_id == checkpoint.id
        assert delta.event_id == "e1"
        assert delta.sequence == 1
        assert delta.time_since_previous == 0.0
        assert delta.events_since_previous == 1
        assert delta.importance_delta == 0.0
        assert delta.restore_value > 0
        assert delta.state_keys_changed == []

    def test_multiple_checkpoints(self, monitor):
        """compute_checkpoint_deltas with multiple checkpoints."""
        now = datetime.now(timezone.utc)
        checkpoint1 = Checkpoint(
            session_id="s1",
            event_id="e1",
            sequence=1,
            state={"key": "value1"},
            importance=0.5,
            timestamp=now,
        )
        checkpoint2 = Checkpoint(
            session_id="s1",
            event_id="e2",
            sequence=3,
            state={"key": "value2", "new_key": "new_value"},
            importance=0.7,
            timestamp=now + timedelta(seconds=10),
        )
        checkpoint3 = Checkpoint(
            session_id="s1",
            event_id="e3",
            sequence=6,
            state={"key": "value2", "new_key": "new_value"},
            importance=0.6,
            timestamp=now + timedelta(seconds=25),
        )

        events = [
            TraceEvent(
                session_id="s1",
                event_type=EventType.DECISION,
                name="decision",
                data={},
                importance=0.5,
                upstream_event_ids=[],
            )
        ]

        deltas = monitor.compute_checkpoint_deltas([checkpoint1, checkpoint2, checkpoint3], events)
        assert len(deltas) == 3

        # First checkpoint
        assert deltas[0].time_since_previous == 0.0
        assert deltas[0].events_since_previous == 1
        assert deltas[0].importance_delta == 0.0

        # Second checkpoint
        assert deltas[1].time_since_previous == 10.0
        assert deltas[1].events_since_previous == 2  # 3 - 1
        assert deltas[1].importance_delta == 0.2  # 0.7 - 0.5
        assert "key" in deltas[1].state_keys_changed or "new_key" in deltas[1].state_keys_changed

        # Third checkpoint
        assert deltas[2].time_since_previous == 15.0
        assert deltas[2].events_since_previous == 3  # 6 - 3
        assert deltas[2].importance_delta == -0.1  # 0.6 - 0.7


class TestBuildLiveSummary:
    """Tests for LiveMonitor.build_live_summary()."""

    def test_empty_events(self, monitor):
        """build_live_summary with empty events list."""
        summary = monitor.build_live_summary([], [])
        assert summary["event_count"] == 0
        assert summary["checkpoint_count"] == 0
        assert summary["latest"]["decision_event_id"] is None
        assert summary["latest"]["tool_event_id"] is None
        assert summary["latest"]["safety_event_id"] is None
        assert summary["latest"]["turn_event_id"] is None
        assert summary["latest"]["policy_event_id"] is None
        assert summary["latest"]["checkpoint_id"] is None
        assert summary["rolling_summary"] == "Awaiting richer live summaries"
        assert summary["rolling_summary_metrics"] == {}
        assert summary["recent_alerts"] == []
        assert summary["oscillation_alert"] is None
        assert summary["latest_checkpoints"] == []

    def test_with_mixed_event_types(self, monitor):
        """build_live_summary with mixed event types."""
        now = datetime.now(timezone.utc)
        events = [
            TraceEvent(
                session_id="s1",
                event_type=EventType.DECISION,
                name="choose_action",
                data={"reasoning": "Need to search", "chosen_action": "search"},
                importance=0.6,
                timestamp=now,
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.TOOL_CALL,
                name="execute_search",
                data={"tool_name": "search", "args": {"query": "test"}},
                importance=0.5,
                timestamp=now + timedelta(seconds=1),
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.SAFETY_CHECK,
                name="check_safety",
                data={"outcome": "pass"},
                importance=0.4,
                timestamp=now + timedelta(seconds=2),
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.AGENT_TURN,
                name="agent_turn",
                data={"goal": "complete task", "state_summary": "In progress"},
                importance=0.7,
                timestamp=now + timedelta(seconds=3),
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.PROMPT_POLICY,
                name="policy_check",
                data={"state_summary": "Policy verified"},
                importance=0.3,
                timestamp=now + timedelta(seconds=4),
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.BEHAVIOR_ALERT,
                name="alert_detected",
                data={"alert_type": "tool_loop", "severity": "high", "signal": "Repeated tool calls"},
                importance=0.9,
                timestamp=now + timedelta(seconds=5),
                upstream_event_ids=[],
            ),
        ]

        summary = monitor.build_live_summary(events, [])

        # Verify all output keys exist
        assert "event_count" in summary
        assert "checkpoint_count" in summary
        assert "latest" in summary
        assert "rolling_summary" in summary
        assert "rolling_summary_metrics" in summary
        assert "recent_alerts" in summary
        assert "oscillation_alert" in summary
        assert "latest_checkpoints" in summary

        # Verify counts
        assert summary["event_count"] == 6
        assert summary["checkpoint_count"] == 0

        # Verify latest event IDs
        assert summary["latest"]["decision_event_id"] is not None
        assert summary["latest"]["tool_event_id"] is not None
        assert summary["latest"]["safety_event_id"] is not None
        assert summary["latest"]["turn_event_id"] is not None
        assert summary["latest"]["policy_event_id"] is not None

        # Verify rolling summary
        assert summary["rolling_summary"] is not None
        assert isinstance(summary["rolling_summary_metrics"], dict)

        # Verify alerts
        assert len(summary["recent_alerts"]) > 0
        alert = summary["recent_alerts"][0]
        assert alert["alert_type"] == "tool_loop"
        assert alert["severity"] == "high"
        assert alert["source"] == "captured"


class TestAutoCheckpointOnAlert:
    """Tests for auto_checkpoint_on_alert() function."""

    def test_high_severity_creates_checkpoint(self):
        """auto_checkpoint_on_alert with high severity returns Checkpoint."""
        now = datetime.now(timezone.utc)
        alert_event = TraceEvent(
            session_id="s1",
            event_type=EventType.BEHAVIOR_ALERT,
            name="high_severity_alert",
            data={"alert_type": "guardrail_pressure", "severity": "high", "signal": "Critical pattern detected"},
            importance=0.9,
            timestamp=now,
            upstream_event_ids=[],
        )

        events = [
            TraceEvent(
                session_id="s1",
                event_type=EventType.AGENT_TURN,
                name="turn",
                data={"goal": "test goal", "speaker": "agent", "state_summary": "Working"},
                importance=0.5,
                timestamp=now - timedelta(seconds=1),
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.DECISION,
                name="decision",
                data={"chosen_action": "act", "confidence": 0.8},
                importance=0.6,
                timestamp=now - timedelta(seconds=0.5),
                upstream_event_ids=[],
            ),
        ]

        checkpoint = auto_checkpoint_on_alert(alert_event, "s1", events)

        assert checkpoint is not None
        assert checkpoint.session_id == "s1"
        assert checkpoint.event_id == alert_event.id
        assert checkpoint.sequence == len(events)
        assert checkpoint.importance == 0.8  # high severity
        assert checkpoint.state["checkpoint_reason"] == "behavior_alert:guardrail_pressure"
        assert checkpoint.state["alert_severity"] == "high"
        assert checkpoint.state["alert_signal"] == "Critical pattern detected"
        assert checkpoint.state["recent_turn_goal"] == "test goal"
        assert checkpoint.state["recent_decision_action"] == "act"

    def test_medium_severity_creates_checkpoint(self):
        """auto_checkpoint_on_alert with medium severity returns Checkpoint."""
        now = datetime.now(timezone.utc)
        alert_event = TraceEvent(
            session_id="s1",
            event_type=EventType.BEHAVIOR_ALERT,
            name="medium_alert",
            data={"alert_type": "policy_shift", "severity": "medium", "signal": "Policy changed"},
            importance=0.6,
            timestamp=now,
            upstream_event_ids=[],
        )

        checkpoint = auto_checkpoint_on_alert(alert_event, "s1", [])

        assert checkpoint is not None
        assert checkpoint.session_id == "s1"
        assert checkpoint.importance == 0.6  # medium severity
        assert checkpoint.state["checkpoint_reason"] == "behavior_alert:policy_shift"
        assert checkpoint.state["alert_severity"] == "medium"

    def test_low_severity_returns_none(self):
        """auto_checkpoint_on_alert with low severity returns None."""
        now = datetime.now(timezone.utc)
        alert_event = TraceEvent(
            session_id="s1",
            event_type=EventType.BEHAVIOR_ALERT,
            name="low_alert",
            data={"alert_type": "minor", "severity": "low", "signal": "Minor issue"},
            importance=0.3,
            timestamp=now,
            upstream_event_ids=[],
        )

        checkpoint = auto_checkpoint_on_alert(alert_event, "s1", [])

        assert checkpoint is None

    def test_unknown_alert_type_returns_none(self):
        """auto_checkpoint_on_alert with unknown alert_type returns None."""
        now = datetime.now(timezone.utc)
        alert_event = TraceEvent(
            session_id="s1",
            event_type=EventType.BEHAVIOR_ALERT,
            name="unknown_alert",
            data={"alert_type": "unknown", "severity": "high", "signal": "Unknown alert"},
            importance=0.8,
            timestamp=now,
            upstream_event_ids=[],
        )

        checkpoint = auto_checkpoint_on_alert(alert_event, "s1", [])

        assert checkpoint is None
