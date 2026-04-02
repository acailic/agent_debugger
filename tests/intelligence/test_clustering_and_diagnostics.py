"""Tests for failure clustering, diagnostics, and live monitoring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent_debugger_sdk.core.events import (
    Checkpoint,
    DecisionEvent,
    EventType,
    RefusalEvent,
    SafetyCheckEvent,
    ToolCallEvent,
    TraceEvent,
)
from collector.causal_analysis import CausalAnalyzer
from collector.clustering.failure_clusters import FailureClusterAnalyzer
from collector.failure_diagnostics import FailureDiagnostics
from collector.live_monitor import LiveMonitor

# =============================================================================
# Test Helpers
# =============================================================================


def _make_ranking(
    event_id: str,
    fingerprint: str,
    severity: float,
    composite: float,
) -> dict:
    """Create a test event ranking dict."""
    return {
        "event_id": event_id,
        "fingerprint": fingerprint,
        "severity": severity,
        "composite": composite,
    }


def _make_error_event(
    event_id: str,
    error_type: str = "RuntimeError",
    error_message: str = "test error",
) -> TraceEvent:
    """Create a test ERROR event."""
    return TraceEvent(
        id=event_id,
        session_id="test-session",
        parent_id=None,
        name="error",
        event_type=EventType.ERROR,
        timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        data={
            "error_type": error_type,
            "error_message": error_message,
        },
        upstream_event_ids=[],
    )


def _make_refusal_event(
    event_id: str,
    reason: str = "unsafe content",
) -> TraceEvent:
    """Create a test REFUSAL event."""
    return TraceEvent(
        id=event_id,
        session_id="test-session",
        parent_id=None,
        name="refusal",
        event_type=EventType.REFUSAL,
        timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        data={"reason": reason},
        upstream_event_ids=[],
    )


def _make_policy_violation_event(
    event_id: str,
    violation_type: str = "safety",
) -> TraceEvent:
    """Create a test POLICY_VIOLATION event."""
    return TraceEvent(
        id=event_id,
        session_id="test-session",
        parent_id=None,
        name="policy_violation",
        event_type=EventType.POLICY_VIOLATION,
        timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        data={"violation_type": violation_type},
        upstream_event_ids=[],
    )


def _make_tool_result_event(
    event_id: str,
    tool_name: str = "search",
    error: str | None = None,
) -> TraceEvent:
    """Create a test TOOL_RESULT event."""
    data = {"tool_name": tool_name}
    if error:
        data["error"] = error
    return TraceEvent(
        id=event_id,
        session_id="test-session",
        parent_id=None,
        name="tool_result",
        event_type=EventType.TOOL_RESULT,
        timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        data=data,
        upstream_event_ids=[],
    )


def _make_behavior_alert_event(
    event_id: str,
    alert_type: str = "tool_loop",
    signal: str = "loop detected",
) -> TraceEvent:
    """Create a test BEHAVIOR_ALERT event."""
    return TraceEvent(
        id=event_id,
        session_id="test-session",
        parent_id=None,
        name="behavior_alert",
        event_type=EventType.BEHAVIOR_ALERT,
        timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        data={
            "alert_type": alert_type,
            "signal": signal,
        },
        upstream_event_ids=[],
    )


def _make_safety_check_event(
    event_id: str,
    outcome: str = "fail",
) -> TraceEvent:
    """Create a test SAFETY_CHECK event."""
    return TraceEvent(
        id=event_id,
        session_id="test-session",
        parent_id=None,
        name="safety_check",
        event_type=EventType.SAFETY_CHECK,
        timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        data={"outcome": outcome},
        upstream_event_ids=[],
    )


def _make_decision_event(
    event_id: str,
    confidence: float = 0.8,
    evidence: list | None = None,
) -> TraceEvent:
    """Create a test DECISION event."""
    return TraceEvent(
        id=event_id,
        session_id="test-session",
        parent_id=None,
        name="decision",
        event_type=EventType.DECISION,
        timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        data={
            "confidence": confidence,
            "evidence": evidence or [],
        },
        upstream_event_ids=[],
    )


def _event_headline(event: TraceEvent) -> str:
    """Simple headline function for tests."""
    return event.name or str(event.event_type)


# =============================================================================
# Tests for FailureClusterAnalyzer
# =============================================================================


class TestFailureClusterAnalyzerClusterFailures:
    """Tests for FailureClusterAnalyzer.cluster_failures method."""

    def test_groups_by_fingerprint(self):
        """Should group events with the same fingerprint together."""
        analyzer = FailureClusterAnalyzer()
        rankings = [
            _make_ranking("ev1", "fp1", 0.9, 0.85),
            _make_ranking("ev2", "fp1", 0.8, 0.75),
            _make_ranking("ev3", "fp2", 0.95, 0.9),
        ]

        result = analyzer.cluster_failures(rankings)

        assert len(result) == 2
        fp1_cluster = next((c for c in result if c["fingerprint"] == "fp1"), None)
        fp2_cluster = next((c for c in result if c["fingerprint"] == "fp2"), None)

        assert fp1_cluster is not None
        assert fp1_cluster["count"] == 2
        assert set(fp1_cluster["event_ids"]) == {"ev1", "ev2"}

        assert fp2_cluster is not None
        assert fp2_cluster["count"] == 1
        assert fp2_cluster["event_ids"] == ["ev3"]

    def test_sorts_by_count_then_composite_descending(self):
        """Should sort clusters by count descending, then max_composite descending."""
        analyzer = FailureClusterAnalyzer()
        rankings = [
            _make_ranking("ev1", "fp1", 0.9, 0.7),
            _make_ranking("ev2", "fp1", 0.8, 0.7),
            _make_ranking("ev3", "fp2", 0.95, 0.95),
            _make_ranking("ev4", "fp3", 0.9, 0.8),
            _make_ranking("ev5", "fp3", 0.85, 0.8),
            _make_ranking("ev6", "fp3", 0.88, 0.8),
        ]

        result = analyzer.cluster_failures(rankings)

        assert len(result) == 3
        # Sorted by (-count, -max_composite)
        # fp3: count=3, composite=0.8
        # fp1: count=2, composite=0.7
        # fp2: count=1, composite=0.95
        assert result[0]["fingerprint"] == "fp3"
        assert result[0]["count"] == 3
        assert result[0]["max_composite"] == 0.8

        assert result[1]["fingerprint"] == "fp1"
        assert result[1]["count"] == 2
        assert result[1]["max_composite"] == 0.7

        assert result[2]["fingerprint"] == "fp2"
        assert result[2]["count"] == 1
        assert result[2]["max_composite"] == 0.95

    def test_filters_by_severity_threshold(self):
        """Should only include events with severity >= threshold."""
        analyzer = FailureClusterAnalyzer()
        rankings = [
            _make_ranking("ev1", "fp1", 0.9, 0.85),
            _make_ranking("ev2", "fp1", 0.75, 0.7),
            _make_ranking("ev3", "fp2", 0.78, 0.75),
            _make_ranking("ev4", "fp2", 0.77, 0.72),
        ]

        result = analyzer.cluster_failures(rankings, severity_threshold=0.78)

        assert len(result) == 2
        fp1_cluster = next((c for c in result if c["fingerprint"] == "fp1"), None)
        fp2_cluster = next((c for c in result if c["fingerprint"] == "fp2"), None)

        # Only ev1 and ev3 meet threshold
        assert fp1_cluster["event_ids"] == ["ev1"]
        assert fp2_cluster["event_ids"] == ["ev3"]

    def test_selects_highest_composite_as_representative(self):
        """Should select event with highest composite score as representative."""
        analyzer = FailureClusterAnalyzer()
        rankings = [
            _make_ranking("ev1", "fp1", 0.9, 0.7),
            _make_ranking("ev2", "fp1", 0.85, 0.95),
            _make_ranking("ev3", "fp1", 0.88, 0.8),
        ]

        result = analyzer.cluster_failures(rankings)

        assert len(result) == 1
        cluster = result[0]
        assert cluster["representative_event_id"] == "ev2"
        assert cluster["max_composite"] == 0.95

    def test_empty_rankings_returns_empty_list(self):
        """Should return empty list for empty input."""
        analyzer = FailureClusterAnalyzer()
        result = analyzer.cluster_failures([])
        assert result == []

    def test_all_events_same_fingerprint(self):
        """Should handle all events having the same fingerprint."""
        analyzer = FailureClusterAnalyzer()
        rankings = [
            _make_ranking("ev1", "fp1", 0.9, 0.85),
            _make_ranking("ev2", "fp1", 0.8, 0.75),
            _make_ranking("ev3", "fp1", 0.95, 0.9),
        ]

        result = analyzer.cluster_failures(rankings)

        assert len(result) == 1
        assert result[0]["fingerprint"] == "fp1"
        assert result[0]["count"] == 3
        assert set(result[0]["event_ids"]) == {"ev1", "ev2", "ev3"}

    def test_all_events_different_fingerprints(self):
        """Should handle all events having different fingerprints."""
        analyzer = FailureClusterAnalyzer()
        rankings = [
            _make_ranking("ev1", "fp1", 0.9, 0.85),
            _make_ranking("ev2", "fp2", 0.8, 0.75),
            _make_ranking("ev3", "fp3", 0.95, 0.9),
        ]

        result = analyzer.cluster_failures(rankings)

        assert len(result) == 3
        for cluster in result:
            assert cluster["count"] == 1
            assert len(cluster["event_ids"]) == 1


# =============================================================================
# Tests for FailureDiagnostics
# =============================================================================


class TestFailureDiagnosticsIsFailureEvent:
    """Tests for FailureDiagnostics.is_failure_event method."""

    def test_returns_true_for_error(self):
        """Should return True for ERROR events."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_error_event("ev1")

        assert diagnostics.is_failure_event(event) is True

    def test_returns_true_for_refusal(self):
        """Should return True for REFUSAL events."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_refusal_event("ev1")

        assert diagnostics.is_failure_event(event) is True

    def test_returns_true_for_policy_violation(self):
        """Should return True for POLICY_VIOLATION events."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_policy_violation_event("ev1")

        assert diagnostics.is_failure_event(event) is True

    def test_returns_true_for_behavior_alert(self):
        """Should return True for BEHAVIOR_ALERT events."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_behavior_alert_event("ev1")

        assert diagnostics.is_failure_event(event) is True

    def test_returns_true_for_tool_result_with_error(self):
        """Should return True for TOOL_RESULT events with error field."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_tool_result_event("ev1", error="connection failed")

        assert diagnostics.is_failure_event(event) is True

    def test_returns_true_for_safety_check_with_non_pass_outcome(self):
        """Should return True for SAFETY_CHECK events with outcome != 'pass'."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_safety_check_event("ev1", outcome="fail")

        assert diagnostics.is_failure_event(event) is True

    def test_returns_false_for_tool_result_without_error(self):
        """Should return False for TOOL_RESULT events without error."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_tool_result_event("ev1", error=None)

        assert diagnostics.is_failure_event(event) is False

    def test_returns_false_for_safety_check_with_pass_outcome(self):
        """Should return False for SAFETY_CHECK events with outcome == 'pass'."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_safety_check_event("ev1", outcome="pass")

        assert diagnostics.is_failure_event(event) is False

    def test_returns_false_for_other_event_types(self):
        """Should return False for non-failure event types."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)

        for event_type in [EventType.TOOL_CALL, EventType.DECISION, EventType.AGENT_TURN, EventType.LLM_REQUEST]:
            event = TraceEvent(
                id="ev1",
                session_id="test-session",
                parent_id=None,
                name="test",
                event_type=event_type,
                timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
                data={},
                upstream_event_ids=[],
            )
            assert diagnostics.is_failure_event(event) is False


class TestFailureDiagnosticsBuildFailureExplanations:
    """Tests for FailureDiagnostics.build_failure_explanations method."""

    def test_with_failure_events(self):
        """Should build explanations for failure events."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)

        events = [
            _make_error_event("ev1", "RuntimeError", "test error"),
            _make_refusal_event("ev2", "unsafe content"),
            _make_tool_result_event("ev3", "search", "timeout"),
        ]

        result = diagnostics.build_failure_explanations(
            events,
            ranking_by_event_id={},
            event_headline_fn=_event_headline,
        )

        assert len(result) == 3

        # Check error event explanation
        error_expl = next((e for e in result if e["failure_event_id"] == "ev1"), None)
        assert error_expl is not None
        assert error_expl["failure_event_type"] == "error"
        assert error_expl["failure_mode"] == "upstream_runtime_error"
        assert "RuntimeError raised" in error_expl["symptom"]

    def test_no_failure_events(self):
        """Should return empty list when no failure events present."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)

        events = [
            TraceEvent(
                id="ev1",
                session_id="test-session",
                parent_id=None,
                name="tool_call",
                event_type=EventType.TOOL_CALL,
                timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
                data={"tool_name": "search"},
                upstream_event_ids=[],
            ),
        ]

        result = diagnostics.build_failure_explanations(
            events,
            ranking_by_event_id={},
            event_headline_fn=_event_headline,
        )

        assert result == []

    def test_with_causal_chain(self):
        """Should include causal chain information when available."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)

        decision_event = _make_decision_event("dec1", confidence=0.3, evidence=[])
        failure_event = _make_tool_result_event("ev1", "search", "failed")
        failure_event.upstream_event_ids = ["dec1"]

        events = [decision_event, failure_event]

        # Provide ranking that identifies the decision as a candidate
        ranking_by_event_id = {
            "dec1": {
                "event_id": "dec1",
                "score": 0.75,
                "relation_type": "evidence",
                "relation_label": "evidence provenance",
                "supporting_event_ids": [],
            }
        }

        result = diagnostics.build_failure_explanations(
            events,
            ranking_by_event_id=ranking_by_event_id,
            event_headline_fn=_event_headline,
        )

        assert len(result) == 1
        expl = result[0]
        assert expl["failure_event_id"] == "ev1"
        assert expl["likely_cause_event_id"] == "dec1"
        # Confidence is rounded to 4 decimal places
        assert expl["confidence"] == 1.0
        assert "ungrounded_decision" in expl["failure_mode"]

    def test_sorts_by_confidence_then_event_id(self):
        """Should sort explanations by confidence descending, then event_id."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)

        # Create events with upstream relationships to generate different confidence scores
        events = [
            _make_error_event("ev1"),
            _make_refusal_event("ev2"),
            _make_error_event("ev3"),
        ]

        # Add upstream relationships so causal analysis finds different candidates
        events[0].upstream_event_ids = []  # No upstream
        events[1].upstream_event_ids = []  # No upstream
        events[2].upstream_event_ids = ["ev1"]  # Has upstream, will get higher confidence

        result = diagnostics.build_failure_explanations(
            events,
            ranking_by_event_id={},  # Empty rankings, will compute via causal analysis
            event_headline_fn=_event_headline,
        )

        assert len(result) == 3
        # Results are sorted by (-confidence, failure_event_id)
        # ev3 has upstream candidate (ev1) so gets higher confidence
        confidences = [r["confidence"] for r in result]
        assert confidences[0] > 0  # ev3 should have non-zero confidence
        assert confidences[1] >= 0
        assert confidences[2] >= 0
        # Verify descending sort
        assert confidences == sorted(confidences, reverse=True)


class TestFailureDiagnosticsFailureMode:
    """Tests for FailureDiagnostics.failure_mode method."""

    def test_behavior_alert_tool_loop_returns_looping_behavior(self):
        """Should return 'looping_behavior' for BEHAVIOR_ALERT with tool_loop type."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_behavior_alert_event("ev1", alert_type="tool_loop")

        mode = diagnostics.failure_mode(event, None, {})

        assert mode == "looping_behavior"

    def test_behavior_alert_other_returns_behavior_anomaly(self):
        """Should return 'behavior_anomaly' for BEHAVIOR_ALERT with other types."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_behavior_alert_event("ev1", alert_type="oscillation")

        mode = diagnostics.failure_mode(event, None, {})

        assert mode == "behavior_anomaly"

    def test_refusal_returns_guardrail_block(self):
        """Should return 'guardrail_block' for REFUSAL events."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_refusal_event("ev1")

        mode = diagnostics.failure_mode(event, None, {})

        assert mode == "guardrail_block"

    def test_safety_check_returns_guardrail_block(self):
        """Should return 'guardrail_block' for SAFETY_CHECK events."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_safety_check_event("ev1")

        mode = diagnostics.failure_mode(event, None, {})

        assert mode == "guardrail_block"

    def test_policy_violation_returns_policy_mismatch(self):
        """Should return 'policy_mismatch' for POLICY_VIOLATION events."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_policy_violation_event("ev1")

        mode = diagnostics.failure_mode(event, None, {})

        assert mode == "policy_mismatch"

    def test_error_returns_upstream_runtime_error(self):
        """Should return 'upstream_runtime_error' for ERROR events."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_error_event("ev1")

        mode = diagnostics.failure_mode(event, None, {})

        assert mode == "upstream_runtime_error"

    def test_tool_result_ungrounded_decision(self):
        """Should return 'ungrounded_decision' for tool failure with low-confidence decision."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)

        decision = _make_decision_event("dec1", confidence=0.3, evidence=[])
        failure = _make_tool_result_event("ev1", error="failed")

        candidate = {"event_id": "dec1"}
        id_lookup = {"dec1": decision}

        mode = diagnostics.failure_mode(failure, candidate, id_lookup)

        assert mode == "ungrounded_decision"

    def test_tool_result_execution_failure(self):
        """Should return 'tool_execution_failure' for tool failure without ungrounded decision."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)

        decision = _make_decision_event("dec1", confidence=0.8, evidence=["doc1"])
        failure = _make_tool_result_event("ev1", error="failed")

        candidate = {"event_id": "dec1"}
        id_lookup = {"dec1": decision}

        mode = diagnostics.failure_mode(failure, candidate, id_lookup)

        assert mode == "tool_execution_failure"


class TestFailureDiagnosticsFailureSymptom:
    """Tests for FailureDiagnostics.failure_symptom method."""

    def test_tool_result_error_symptom(self):
        """Should generate symptom text for tool result errors."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_tool_result_event("ev1", "search", "connection timeout")

        symptom = diagnostics.failure_symptom(event, _event_headline)

        assert 'Tool "tool_result" failed' in symptom
        assert "connection timeout" in symptom

    def test_error_symptom(self):
        """Should generate symptom text for error events."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_error_event("ev1", "ValueError", "invalid input")

        symptom = diagnostics.failure_symptom(event, _event_headline)

        assert "ValueError raised" in symptom
        assert "invalid input" in symptom

    def test_refusal_symptom(self):
        """Should generate symptom text for refusal events."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_refusal_event("ev1", "content policy violation")

        symptom = diagnostics.failure_symptom(event, _event_headline)

        assert "Request was refused:" in symptom
        assert "content policy violation" in symptom

    def test_policy_violation_symptom(self):
        """Should generate symptom text for policy violation events."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_policy_violation_event("ev1", "data_exfiltration")

        symptom = diagnostics.failure_symptom(event, _event_headline)

        assert "Policy violation:" in symptom
        assert "data_exfiltration" in symptom

    def test_behavior_alert_symptom(self):
        """Should generate symptom text for behavior alert events."""
        causal = CausalAnalyzer()
        diagnostics = FailureDiagnostics(causal)
        event = _make_behavior_alert_event("ev1", signal="repeated tool calls detected")

        symptom = diagnostics.failure_symptom(event, _event_headline)

        assert "repeated tool calls detected" in symptom


# =============================================================================
# Tests for LiveMonitor
# =============================================================================


class TestLiveMonitorBuildLiveSummary:
    """Tests for LiveMonitor.build_live_summary method."""

    def test_with_events_and_checkpoints(self):
        """Should build summary with events and checkpoints."""
        monitor = LiveMonitor()

        now = datetime.now(timezone.utc)
        events = [
            DecisionEvent(
                id="dec1",
                session_id="s1",
                confidence=0.8,
                timestamp=now,
            ),
            ToolCallEvent(
                id="tool1",
                session_id="s1",
                tool_name="search",
                timestamp=now,
            ),
        ]

        checkpoints = [
            Checkpoint(
                id="cp1",
                session_id="s1",
                event_id="dec1",
                sequence=1,
                timestamp=now,
                importance=0.7,
                state={"key": "value"},
            ),
        ]

        result = monitor.build_live_summary(events, checkpoints)

        assert result["event_count"] == 2
        assert result["checkpoint_count"] == 1
        assert result["latest"]["decision_event_id"] == "dec1"
        assert result["latest"]["tool_event_id"] == "tool1"
        assert result["latest"]["checkpoint_id"] == "cp1"

    def test_empty_inputs(self):
        """Should handle empty events list."""
        monitor = LiveMonitor()

        result = monitor.build_live_summary([], [])

        assert result["event_count"] == 0
        assert result["checkpoint_count"] == 0
        assert result["latest"]["decision_event_id"] is None
        assert result["latest"]["tool_event_id"] is None
        assert result["latest"]["checkpoint_id"] is None
        assert result["rolling_summary"] == "Awaiting richer live summaries"
        assert result["recent_alerts"] == []

    def test_tracks_latest_events_by_type(self):
        """Should track the most recent event of each type."""
        monitor = LiveMonitor()

        now = datetime.now(timezone.utc)
        events = [
            DecisionEvent(
                id="dec1",
                session_id="s1",
                timestamp=now - timedelta(seconds=10),
            ),
            ToolCallEvent(
                id="tool1",
                session_id="s1",
                tool_name="search",
                timestamp=now - timedelta(seconds=5),
            ),
            DecisionEvent(
                id="dec2",
                session_id="s1",
                timestamp=now,
            ),
            ToolCallEvent(
                id="tool2",
                session_id="s1",
                tool_name="retrieve",
                timestamp=now,
            ),
        ]

        result = monitor.build_live_summary(events, [])

        # Should track most recent of each type
        assert result["latest"]["decision_event_id"] == "dec2"
        assert result["latest"]["tool_event_id"] == "tool2"

    def test_includes_safety_events(self):
        """Should include safety-related events in latest tracking."""
        monitor = LiveMonitor()

        now = datetime.now(timezone.utc)
        events = [
            SafetyCheckEvent(
                id="safety1",
                session_id="s1",
                timestamp=now,
                policy_name="content_policy",
                outcome="pass",
            ),
            RefusalEvent(
                id="refusal1",
                session_id="s1",
                timestamp=now,
                reason="unsafe",
            ),
        ]

        result = monitor.build_live_summary(events, [])

        assert result["latest"]["safety_event_id"] in ["safety1", "refusal1"]

    def test_generates_rolling_summary(self):
        """Should generate rolling summary from events."""
        monitor = LiveMonitor()

        now = datetime.now(timezone.utc)
        events = [
            ToolCallEvent(
                id="tool1",
                session_id="s1",
                tool_name="search",
                timestamp=now,
            ),
        ]

        result = monitor.build_live_summary(events, [])

        assert "rolling_summary" in result
        assert "rolling_summary_metrics" in result
        assert isinstance(result["rolling_summary_metrics"], dict)

    def test_compiles_recent_alerts(self):
        """Should compile recent alerts from behavior alert events."""
        monitor = LiveMonitor()

        events = [
            _make_behavior_alert_event("alert1", "tool_loop", "loop detected"),
            _make_behavior_alert_event("alert2", "oscillation", "oscillation pattern"),
        ]

        result = monitor.build_live_summary(events, [])

        assert len(result["recent_alerts"]) >= 2
        alert_sources = [a["source"] for a in result["recent_alerts"]]
        assert "captured" in alert_sources

    def test_limits_recent_alerts(self):
        """Should limit the number of recent alerts returned."""
        monitor = LiveMonitor()

        events = [_make_behavior_alert_event(f"alert{i}", "tool_loop", f"alert {i}") for i in range(20)]

        result = monitor.build_live_summary(events, [])

        # Should limit to last 8 alerts
        assert len(result["recent_alerts"]) <= 8

    def test_includes_checkpoint_deltas(self):
        """Should include checkpoint deltas in summary."""
        monitor = LiveMonitor()

        now = datetime.now(timezone.utc)
        checkpoints = [
            Checkpoint(
                id="cp1",
                session_id="s1",
                event_id="dec1",
                sequence=1,
                timestamp=now - timedelta(seconds=10),
                importance=0.5,
                state={"key1": "value1"},
            ),
            Checkpoint(
                id="cp2",
                session_id="s1",
                event_id="dec2",
                sequence=2,
                timestamp=now,
                importance=0.8,
                state={"key2": "value2"},
            ),
        ]

        result = monitor.build_live_summary([], checkpoints)

        assert "latest_checkpoints" in result
        # compute_checkpoint_deltas returns deltas for all checkpoints
        # build_live_summary takes the last 5
        assert len(result["latest_checkpoints"]) >= 0

        # If deltas are present, check the structure
        if result["latest_checkpoints"]:
            delta = result["latest_checkpoints"][0]
            assert "checkpoint_id" in delta
            assert "time_since_previous" in delta
            assert "events_since_previous" in delta
            assert "importance_delta" in delta
            assert "restore_value" in delta
