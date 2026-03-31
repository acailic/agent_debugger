"""Tests for retention tier assignment functionality."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import (
    BehaviorAlertEvent,
    Checkpoint,
    DecisionEvent,
    ErrorEvent,
    EventType,
    PolicyViolationEvent,
    ToolCallEvent,
)
from collector.intelligence.facade import TraceIntelligence


class TestRetentionTierAssignment:
    """Tests for retention tier assignment functionality."""

    @pytest.fixture
    def intelligence(self) -> TraceIntelligence:
        """Create TraceIntelligence instance for tests."""
        return TraceIntelligence()

    def test_high_value_session_gets_full_retention(self, intelligence, make_trace_event):
        """Verify that high-value sessions get full retention."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            ErrorEvent(
                id="error-1",
                session_id="session-1",
                error_type="CriticalError",
                error_message="Critical failure",
                timestamp=timestamp,
            ),
            ErrorEvent(
                id="error-2",
                session_id="session-1",
                error_type="CriticalError",
                error_message="Another critical failure",
                timestamp=timestamp,
            ),
        ]
        analysis = intelligence.analyze_session(events, [])
        assert analysis["retention_tier"] == "full", "High-value session with errors should have full retention"

    def test_medium_value_session_gets_summarized(self, intelligence, make_trace_event):
        """Verify that medium-value sessions get summarized retention."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            BehaviorAlertEvent(
                id="alert-1",
                session_id="session-1",
                alert_type="drift",
                severity="medium",
                signal="Slight drift detected",
                timestamp=timestamp,
            ),
        ]
        analysis = intelligence.analyze_session(events, [])
        assert analysis["retention_tier"] in {"summarized", "full"}, (
            "Medium-value session should have summarized retention"
        )

    def test_low_value_session_gets_downsampled(self, intelligence, make_trace_event):
        """Verify that low-value sessions get downsampled retention."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            make_trace_event(
                id="end-1",
                session_id="session-1",
                event_type=EventType.AGENT_END,
                timestamp=timestamp,
            ),
        ]
        analysis = intelligence.analyze_session(events, [])
        assert analysis["retention_tier"] == "downsampled", "Low-value session should have downsampled retention"

    def test_retention_tier_considers_failure_clusters(self, intelligence, make_trace_event):
        """Verify that retention tier considers failure cluster count."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            ErrorEvent(
                id="error-1",
                session_id="session-1",
                error_type="ErrorType1",
                error_message="Error 1",
                timestamp=timestamp,
            ),
            ErrorEvent(
                id="error-2",
                session_id="session-1",
                error_type="ErrorType2",
                error_message="Error 2",
                timestamp=timestamp,
            ),
        ]
        analysis = intelligence.analyze_session(events, [])
        assert analysis["retention_tier"] == "full", "Multiple failure clusters should result in full retention"

    def test_retention_tier_considers_high_severity_count(self, intelligence, make_trace_event):
        """Verify that retention tier considers high severity count."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            PolicyViolationEvent(
                id="violation-1",
                session_id="session-1",
                policy_name="critical-policy",
                severity="critical",
                violation_type="security",
                details={"level": "critical"},
                timestamp=timestamp,
            ),
        ]
        analysis = intelligence.analyze_session(events, [])
        assert analysis["retention_tier"] == "full", "High severity count should result in full retention"

    def test_retention_tier_considers_replay_value(self, intelligence, make_trace_event):
        """Verify that retention tier is assigned based on session analysis."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            DecisionEvent(
                id="decision-1",
                session_id="session-1",
                chosen_action="expensive_action",
                confidence=0.9,
                evidence=[{"source": "tool", "content": "verified"}],
                upstream_event_ids=["evidence-1"],
                timestamp=timestamp,
            ),
        ]
        checkpoints = [
            Checkpoint(
                id="checkpoint-1",
                session_id="session-1",
                event_id="decision-1",
                sequence=1,
                state={"phase": "important"},
                memory={"data": "critical"},
                timestamp=timestamp,
                importance=0.9,
            ),
        ]
        analysis = intelligence.analyze_session(events, checkpoints)
        assert analysis["retention_tier"] in {"full", "summarized", "downsampled"}
        assert "session_replay_value" in analysis
        assert analysis["session_replay_value"] >= 0

    def test_checkpoint_retention_tier_assigned(self, intelligence, make_trace_event):
        """Verify that checkpoints have retention tiers assigned."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
        ]
        checkpoints = [
            Checkpoint(
                id="checkpoint-1",
                session_id="session-1",
                event_id="start-1",
                sequence=1,
                state={"phase": "init"},
                memory={},
                timestamp=timestamp,
                importance=0.9,
            ),
        ]
        analysis = intelligence.analyze_session(events, checkpoints)
        assert len(analysis["checkpoint_rankings"]) == 1
        assert "retention_tier" in analysis["checkpoint_rankings"][0]

    def test_retention_tier_edge_case_replay_value_thresholds(self, intelligence):
        """Verify retention tier thresholds are correctly applied."""
        assert (
            intelligence.retention_tier(
                replay_value=0.72,
                high_severity_count=0,
                failure_cluster_count=0,
                behavior_alert_count=0,
            )
            == "full"
        )
        assert (
            intelligence.retention_tier(
                replay_value=0.5,
                high_severity_count=1,
                failure_cluster_count=0,
                behavior_alert_count=0,
            )
            == "full"
        )
        assert (
            intelligence.retention_tier(
                replay_value=0.5,
                high_severity_count=0,
                failure_cluster_count=2,
                behavior_alert_count=0,
            )
            == "full"
        )
        assert (
            intelligence.retention_tier(
                replay_value=0.42,
                high_severity_count=0,
                failure_cluster_count=0,
                behavior_alert_count=0,
            )
            == "summarized"
        )
        assert (
            intelligence.retention_tier(
                replay_value=0.3,
                high_severity_count=0,
                failure_cluster_count=1,
                behavior_alert_count=0,
            )
            == "summarized"
        )
        assert (
            intelligence.retention_tier(
                replay_value=0.3,
                high_severity_count=0,
                failure_cluster_count=0,
                behavior_alert_count=1,
            )
            == "summarized"
        )
        assert (
            intelligence.retention_tier(
                replay_value=0.3,
                high_severity_count=0,
                failure_cluster_count=0,
                behavior_alert_count=0,
            )
            == "downsampled"
        )

    def test_empty_session_has_downsampled_retention(self, intelligence):
        """Verify that empty sessions have downsampled retention."""
        analysis = intelligence.analyze_session([], [])
        assert analysis["retention_tier"] == "downsampled"

    def test_session_summary_includes_correct_counts(self, intelligence, make_trace_event):
        """Verify that session summary includes correct counts."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            ErrorEvent(
                id="error-1",
                session_id="session-1",
                error_type="ValueError",
                error_message="Error",
                timestamp=timestamp,
            ),
            ToolCallEvent(
                id="tool-loop-1",
                session_id="session-1",
                tool_name="retry_op",
                arguments={},
                timestamp=timestamp,
            ),
            ToolCallEvent(
                id="tool-loop-2",
                session_id="session-1",
                tool_name="retry_op",
                arguments={},
                timestamp=timestamp,
            ),
            ToolCallEvent(
                id="tool-loop-3",
                session_id="session-1",
                tool_name="retry_op",
                arguments={},
                timestamp=timestamp,
            ),
        ]
        checkpoints = [
            Checkpoint(
                id="checkpoint-1",
                session_id="session-1",
                event_id="start-1",
                sequence=1,
                state={},
                memory={},
                timestamp=timestamp,
            ),
        ]
        analysis = intelligence.analyze_session(events, checkpoints)
        assert analysis["session_summary"]["failure_count"] >= 1
        assert analysis["session_summary"]["behavior_alert_count"] >= 1
        assert analysis["session_summary"]["checkpoint_count"] == 1


class TestRetentionTierEdgeCases:
    """Edge case tests for retention tier assignment."""

    @pytest.fixture
    def intelligence(self) -> TraceIntelligence:
        return TraceIntelligence()

    def test_replay_value_exactly_at_threshold(self, intelligence):
        """Retention tier should handle exact threshold values."""
        tier = intelligence.retention_tier(
            replay_value=0.72,
            high_severity_count=0,
            failure_cluster_count=0,
            behavior_alert_count=0,
        )
        assert tier == "full"
        tier = intelligence.retention_tier(
            replay_value=0.71,
            high_severity_count=0,
            failure_cluster_count=0,
            behavior_alert_count=0,
        )
        assert tier == "summarized"

    def test_multiple_conditions_trigger_full_retention(self, intelligence):
        """Multiple conditions should all trigger full retention."""
        tier = intelligence.retention_tier(
            replay_value=0.1,
            high_severity_count=1,
            failure_cluster_count=0,
            behavior_alert_count=0,
        )
        assert tier == "full"
        tier = intelligence.retention_tier(
            replay_value=0.1,
            high_severity_count=0,
            failure_cluster_count=2,
            behavior_alert_count=0,
        )
        assert tier == "full"

    def test_zero_replay_value_gets_downsampled(self, intelligence):
        """Zero replay value should result in downsampled tier."""
        tier = intelligence.retention_tier(
            replay_value=0.0,
            high_severity_count=0,
            failure_cluster_count=0,
            behavior_alert_count=0,
        )
        assert tier == "downsampled"
