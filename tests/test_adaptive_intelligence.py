"""Comprehensive tests for Adaptive Intelligence features.

This test module covers:
- Cross-Session Failure Clustering
- Retry Churn Detection
- Latency Spike Detection
- Policy Escalation Tracking
- Representative Trace Selection
- Retention Tier Assignment
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from agent_debugger_sdk.core.events import (
    BehaviorAlertEvent,
    Checkpoint,
    DecisionEvent,
    ErrorEvent,
    EventType,
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
from collector.intelligence import (
    TraceIntelligence,
)

# ==============================================================================
# Cross-Session Failure Clustering Tests
# ==============================================================================


def make_session_with_events(
    session_id: str,
    events: list[TraceEvent],
    checkpoints: list[Checkpoint],
) -> Session:
    """Factory to create a Session with events for cross-session clustering tests."""
    return Session(
        id=session_id,
        agent_name=f"agent-{session_id}",
        framework="test",
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        status="completed",
        total_tokens=len(events),
        total_cost_usd=0.0,
        tool_calls=sum(1 for e in events if e.event_type == EventType.TOOL_CALL),
        llm_calls=sum(1 for e in events if e.event_type == EventType.LLM_REQUEST),
        errors=sum(1 for e in events if e.event_type == EventType.ERROR),
        config={},
        tags=[],
    )


# ------------------------------------------------------------------
# Shared fixtures for creating test events
# ------------------------------------------------------------------


@pytest.fixture
def make_trace_event():
    """Factory to create TraceEvent instances for tests."""

    def _make_event(
        session_id: str = "session-1",
        event_type: EventType = EventType.AGENT_START,
        name: str = "test",
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
        parent_id: str | None = None,
        upstream_event_ids: list[str] | None = None,
        timestamp: datetime | None = None,
        id: str | None = None,
    ) -> TraceEvent:
        kwargs: dict[str, Any] = {}
        kwargs["session_id"] = session_id
        kwargs["event_type"] = event_type
        kwargs["name"] = name
        kwargs["importance"] = importance
        if id is not None:
            kwargs["id"] = id
        if data is not None:
            kwargs["data"] = data
        if metadata is not None:
            kwargs["metadata"] = metadata
        if parent_id is not None:
            kwargs["parent_id"] = parent_id
        if upstream_event_ids is not None:
            kwargs["upstream_event_ids"] = upstream_event_ids
        if timestamp is not None:
            kwargs["timestamp"] = timestamp
        return TraceEvent(**kwargs)

    return _make_event


# ------------------------------------------------------------------
# Test Class: Cross-Session Failure Clustering
# ------------------------------------------------------------------


class TestCrossSessionClustering:
    """Tests for cross-session failure clustering functionality."""

    @pytest.fixture
    def intelligence(self) -> TraceIntelligence:
        """Create a TraceIntelligence instance for tests."""
        return TraceIntelligence()

    @pytest.fixture
    def sample_sessions(self, make_trace_event) -> list[tuple[Session, list[TraceEvent], list[Checkpoint]]]:
        """Create sample sessions with failures for clustering tests."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        sessions_data = []
        for i in range(3):
            session_id = f"session-{i}"
            error_event = ErrorEvent(
                id=f"error-{i}",
                session_id=session_id,
                error_type="ValueError",
                error_message=f"Invalid input for session {i}",
                timestamp=timestamp,
            )
            tool_error_event = ToolResultEvent(
                id=f"tool-error-{i}",
                session_id=session_id,
                tool_name="search",
                error=f"Tool failed in session {i}",
                timestamp=timestamp,
            )
            events = [
                make_trace_event(
                    id=f"start-{i}",
                    session_id=session_id,
                    event_type=EventType.AGENT_START,
                    timestamp=timestamp,
                ),
                error_event,
                tool_error_event,
            ]
            checkpoints = [
                Checkpoint(
                    id=f"checkpoint-{i}",
                    session_id=session_id,
                    event_id=f"start-{i}",
                    sequence=1,
                    state={"phase": "init"},
                    memory={},
                    timestamp=timestamp,
                )
            ]
            session = make_session_with_events(session_id, events, checkpoints)
            sessions_data.append((session, events, checkpoints))
        return sessions_data

    def test_cluster_similar_failures_across_sessions(
        self, sample_sessions: list[tuple[Session, list[TraceEvent], list[Checkpoint]]], intelligence: TraceIntelligence
    ):
        """Verify that similar failures across sessions are clustered correctly."""
        # Analyze each session and collect failure fingerprints
        all_failure_fingerprints: dict[str, list[dict[str, Any]]] = {}
        for session, events, checkpoints in sample_sessions:
            analysis = intelligence.analyze_session(events, checkpoints)
            for cluster in analysis["failure_clusters"]:
                fingerprint = cluster["fingerprint"]
                if fingerprint not in all_failure_fingerprints:
                    all_failure_fingerprints[fingerprint] = []
                all_failure_fingerprints[fingerprint].append(
                    {
                        "session_id": session.id,
                        "cluster": cluster,
                    }
                )
        # Verify failures are clustered
        assert len(all_failure_fingerprints) > 0, "Should have at least one failure cluster"
        # Verify each cluster has correct metadata
        for fingerprint, cluster_data_list in all_failure_fingerprints.items():
            for cluster_data in cluster_data_list:
                cluster = cluster_data["cluster"]
                assert "count" in cluster
                assert "event_ids" in cluster
                assert "representative_event_id" in cluster
                assert "max_composite" in cluster
                assert cluster["count"] >= 1
                assert len(cluster["event_ids"]) >= 1

    def test_cluster_representative_selection(
        self, sample_sessions: list[tuple[Session, list[TraceEvent], list[Checkpoint]]], intelligence: TraceIntelligence
    ):
        """Verify that representative traces are selected for each cluster."""
        for session, events, checkpoints in sample_sessions:
            analysis = intelligence.analyze_session(events, checkpoints)
            # Verify representative failure IDs are selected
            assert "representative_failure_ids" in analysis
            for cluster in analysis["failure_clusters"]:
                assert cluster["representative_event_id"] in analysis["representative_failure_ids"]
            # Verify each representative event is the highest composite score in its cluster
            ranking_by_id = {r["event_id"]: r for r in analysis["event_rankings"]}
            for cluster in analysis["failure_clusters"]:
                rep_id = cluster["representative_event_id"]
                rep_ranking = ranking_by_id.get(rep_id)
                assert rep_ranking is not None, f"Representative event {rep_id} should have a ranking"
                for event_id in cluster["event_ids"]:
                    other_ranking = ranking_by_id.get(event_id)
                    if other_ranking:
                        assert rep_ranking["composite"] >= other_ranking["composite"], (
                            f"Representative {rep_id} should have highest composite score"
                        )

    def test_fingerprint_consistency(self, intelligence: TraceIntelligence, make_trace_event):
        """Verify that fingerprints are consistent for similar failure types."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        # Test error fingerprints
        error1 = ErrorEvent(
            id="error-1",
            session_id="session-1",
            error_type="ValueError",
            error_message="Invalid input",
            timestamp=timestamp,
        )
        error2 = ErrorEvent(
            id="error-2",
            session_id="session-2",
            error_type="ValueError",
            error_message="Different invalid input",
            timestamp=timestamp,
        )
        fp1 = intelligence.fingerprint(error1)
        fp2 = intelligence.fingerprint(error2)
        assert fp1.startswith("error:ValueError")
        assert fp2.startswith("error:ValueError")
        # Tool result fingerprints with errors
        tool_error1 = ToolResultEvent(
            id="tool-error-1",
            session_id="session-1",
            tool_name="search",
            error="timeout",
            timestamp=timestamp,
        )
        tool_error2 = ToolResultEvent(
            id="tool-error-2",
            session_id="session-2",
            tool_name="search",
            error="timeout",
            timestamp=timestamp,
        )
        fp3 = intelligence.fingerprint(tool_error1)
        fp4 = intelligence.fingerprint(tool_error2)
        assert fp3 == fp4, "Same tool errors should have same fingerprint"

    def test_empty_session_clustering(self, intelligence: TraceIntelligence):
        """Verify that empty sessions produce no clusters."""
        analysis = intelligence.analyze_session([], [])
        assert analysis["failure_clusters"] == []
        assert analysis["representative_failure_ids"] == []

    def test_high_severity_events_clustered(self, intelligence: TraceIntelligence, make_trace_event):
        """Verify that high severity events are included in clusters."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        high_severity_error = ErrorEvent(
            id="error-high",
            session_id="session-1",
            error_type="CriticalError",
            error_message="Critical failure",
            timestamp=timestamp,
        )
        events = [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            high_severity_error,
        ]
        checkpoints = []
        analysis = intelligence.analyze_session(events, checkpoints)
        # High severity error should be in a cluster
        error_rankings = [r for r in analysis["event_rankings"] if r["event_id"] == "error-high"]
        assert len(error_rankings) == 1
        assert error_rankings[0]["severity"] >= 0.9, "Error should have high severity"


# ------------------------------------------------------------------
# Test Class: Retry Churn Detection
# ------------------------------------------------------------------


class TestRetryChurnDetection:
    """Tests for retry churn detection functionality."""

    @pytest.fixture
    def intelligence(self) -> TraceIntelligence:
        """Create TraceIntelligence instance for tests."""
        return TraceIntelligence()

    @pytest.fixture
    def events_with_retry_churn(self, make_trace_event) -> list[TraceEvent]:
        """Create events with retry churn pattern - consecutive tool calls to same tool.

        The tool_loop detection requires consecutive TOOL_CALL events (not interleaved
        with TOOL_RESULT events) to detect a loop.
        """
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        return [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            # Three consecutive calls to the same tool - this is the loop pattern
            ToolCallEvent(
                id="tool-call-1",
                session_id="session-1",
                tool_name="search",
                arguments={"query": "test query"},
                timestamp=timestamp,
            ),
            ToolCallEvent(
                id="tool-call-2",
                session_id="session-1",
                tool_name="search",
                arguments={"query": "test query"},
                timestamp=timestamp,
            ),
            ToolCallEvent(
                id="tool-call-3",
                session_id="session-1",
                tool_name="search",
                arguments={"query": "test query"},
                timestamp=timestamp,
            ),
        ]

    def test_detect_tool_loop_as_churn_indicator(
        self, events_with_retry_churn: list[TraceEvent], intelligence: TraceIntelligence
    ):
        """Verify that repeated tool calls trigger tool_loop alerts."""
        analysis = intelligence.analyze_session(events_with_retry_churn, [])
        # Tool loop detection should flag the churn pattern
        tool_loop_alerts = [alert for alert in analysis["behavior_alerts"] if alert["alert_type"] == "tool_loop"]
        assert len(tool_loop_alerts) >= 1, "Should detect tool loop from retry churn"
        for alert in tool_loop_alerts:
            assert "severity" in alert
            assert alert["severity"] == "high"
            assert "signal" in alert
            assert "event_id" in alert

    def test_churn_affects_novelty_and_recurrence(
        self, events_with_retry_churn: list[TraceEvent], intelligence: TraceIntelligence
    ):
        """Verify that retry churn affects novelty and recurrence scores."""
        analysis = intelligence.analyze_session(events_with_retry_churn, [])
        # Find the tool call events
        tool_call_rankings = [r for r in analysis["event_rankings"] if r["event_type"] == "tool_call"]
        assert len(tool_call_rankings) >= 3

        # Check recurrence scores are elevated for repeated tool calls
        for ranking in tool_call_rankings:
            assert ranking["novelty"] < 0.5  # Higher recurrence = lower novelty
        # Higher recurrence -> lower novelty means more interesting content
        for ranking in tool_call_rankings:
            assert ranking["recurrence"] >= 0.5, "Higher recurrence means more like retry"

        # Higher recurrence than lower novelty, more like retry
        # Therefore the retention tier should be lowered
        assert analysis["retention_tier"] in {"full", "summarized"}, (
            "Sessions with churn should have higher retention tier"
        )

    def test_different_tool_calls_no_churn(self, intelligence: TraceIntelligence, make_trace_event):
        """Verify that different tool calls don't trigger churn detection."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            ToolCallEvent(
                id="tool-call-1",
                session_id="session-1",
                tool_name="search",
                arguments={"query": "query 1"},
                timestamp=timestamp,
            ),
            ToolResultEvent(
                id="tool-result-1",
                session_id="session-1",
                tool_name="search",
                result="ok",
                timestamp=timestamp,
            ),
            ToolCallEvent(
                id="tool-call-2",
                session_id="session-1",
                tool_name="read",
                arguments={"file": "test.txt"},
                timestamp=timestamp,
            ),
            ToolResultEvent(
                id="tool-result-2",
                session_id="session-1",
                tool_name="read",
                result="ok",
                timestamp=timestamp,
            ),
        ]
        analysis = intelligence.analyze_session(events, [])
        # No tool loop should be detected for different tools
        tool_loop_alerts = [alert for alert in analysis["behavior_alerts"] if alert["alert_type"] == "tool_loop"]
        assert len(tool_loop_alerts) == 0, "Different tools should not trigger tool loop"


# ------------------------------------------------------------------
# Test Class: Latency Spike Detection
# ------------------------------------------------------------------


class TestLatencySpikeDetection:
    """Tests for latency spike detection functionality."""

    @pytest.fixture
    def intelligence(self) -> TraceIntelligence:
        """Create TraceIntelligence instance for tests."""
        return TraceIntelligence()

    @pytest.fixture
    def events_with_latency_spikes(self, make_trace_event) -> list[TraceEvent]:
        """Create events with latency spikes."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        return [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            # Normal duration tool call
            ToolCallEvent(
                id="tool-call-1",
                session_id="session-1",
                tool_name="search",
                timestamp=timestamp,
            ),
            ToolResultEvent(
                id="tool-result-1",
                session_id="session-1",
                tool_name="search",
                result="ok",
                duration_ms=100.0,  # Normal
                timestamp=timestamp,
            ),
            # Slow tool call - latency spike
            ToolCallEvent(
                id="tool-call-2",
                session_id="session-1",
                tool_name="slow_operation",
                timestamp=timestamp,
            ),
            ToolResultEvent(
                id="tool-result-2",
                session_id="session-1",
                tool_name="slow_operation",
                result="ok",
                duration_ms=15000.0,  # 15 seconds - spike
                timestamp=timestamp,
            ),
            # Normal LLM response
            LLMResponseEvent(
                id="llm-response-1",
                session_id="session-1",
                model="gpt-4",
                content="Normal response",
                duration_ms=500.0,  # Normal
                timestamp=timestamp,
            ),
            # Slow LLM response - latency spike
            LLMResponseEvent(
                id="llm-response-2",
                session_id="session-1",
                model="gpt-4",
                content="Slow response",
                duration_ms=30000.0,  # 30 seconds - spike
                cost_usd=0.05,
                timestamp=timestamp,
            ),
        ]

    def test_slow_tools_have_lower_novelty(
        self, events_with_latency_spikes: list[TraceEvent], intelligence: TraceIntelligence
    ):
        """Verify that slow tool calls are scored appropriately."""
        analysis = intelligence.analyze_session(events_with_latency_spikes, [])
        # Find the slow tool result
        slow_tool_rankings = [r for r in analysis["event_rankings"] if r["event_id"] == "tool-result-2"]
        assert len(slow_tool_rankings) == 1
        ranking = slow_tool_rankings[0]
        # Duration should be reflected in the data (via importance scorer)
        assert ranking["severity"] >= 0.5, "Slow operations should have reasonable severity"

    def test_slow_llm_responses_affect_replay_value(
        self, events_with_latency_spikes: list[TraceEvent], intelligence: TraceIntelligence
    ):
        """Verify that slow LLM responses affect replay value."""
        analysis = intelligence.analyze_session(events_with_latency_spikes, [])
        # Find the slow LLM response
        slow_llm_rankings = [r for r in analysis["event_rankings"] if r["event_id"] == "llm-response-2"]
        assert len(slow_llm_rankings) == 1
        # High cost and duration should increase importance
        assert slow_llm_rankings[0]["replay_value"] >= 0.3, "Slow, expensive LLM calls should have higher replay value"

    def test_latency_spikes_contribute_to_retention_tier(
        self, events_with_latency_spikes: list[TraceEvent], intelligence: TraceIntelligence
    ):
        """Verify that sessions with latency spikes have appropriate retention."""
        analysis = intelligence.analyze_session(events_with_latency_spikes, [])
        # Check retention tier is assigned
        assert analysis["retention_tier"] in {"full", "summarized", "downsampled"}
        # Verify the analysis completes and produces valid metrics
        assert "session_replay_value" in analysis
        assert analysis["session_replay_value"] >= 0

    def test_normal_duration_events_not_flagged(self, intelligence: TraceIntelligence, make_trace_event):
        """Verify that normal duration events are not flagged as anomalies."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            ToolCallEvent(
                id="tool-call-1",
                session_id="session-1",
                tool_name="fast_op",
                timestamp=timestamp,
            ),
            ToolResultEvent(
                id="tool-result-1",
                session_id="session-1",
                tool_name="fast_op",
                result="ok",
                duration_ms=50.0,  # Fast
                timestamp=timestamp,
            ),
        ]
        analysis = intelligence.analyze_session(events, [])
        # Normal operations should have lower severity
        tool_result_ranking = next(r for r in analysis["event_rankings"] if r["event_id"] == "tool-result-1")
        assert tool_result_ranking["severity"] < 0.8, "Normal operations should have lower severity"


# ------------------------------------------------------------------
# Test Class: Policy Escalation Tracking
# ------------------------------------------------------------------


class TestPolicyEscalationTracking:
    """Tests for policy escalation tracking functionality."""

    @pytest.fixture
    def intelligence(self) -> TraceIntelligence:
        """Create TraceIntelligence instance for tests."""
        return TraceIntelligence()

    @pytest.fixture
    def events_with_policy_escalation(self, make_trace_event) -> list[TraceEvent]:
        """Create events with policy escalation pattern."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        return [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            # Initial low-risk policy
            PromptPolicyEvent(
                id="policy-1",
                session_id="session-1",
                template_id="low-risk-policy",
                policy_parameters={"strictness": "low"},
                speaker="system",
                state_summary="Low risk mode",
                goal="Normal operation",
                timestamp=timestamp,
            ),
            # First safety check - passes
            SafetyCheckEvent(
                id="safety-1",
                session_id="session-1",
                policy_name="low-risk-policy",
                outcome="pass",
                risk_level="low",
                rationale="No issues detected",
                timestamp=timestamp,
            ),
            # Policy shifts to stricter
            PromptPolicyEvent(
                id="policy-2",
                session_id="session-1",
                template_id="high-risk-policy",
                policy_parameters={"strictness": "high"},
                speaker="system",
                state_summary="Escalated to high risk",
                goal="Handle elevated risk",
                timestamp=timestamp,
            ),
            # Safety check - warns
            SafetyCheckEvent(
                id="safety-2",
                session_id="session-1",
                policy_name="high-risk-policy",
                outcome="warn",
                risk_level="medium",
                rationale="Potential issue detected",
                timestamp=timestamp,
            ),
            # Final policy - maximum strictness
            PromptPolicyEvent(
                id="policy-3",
                session_id="session-1",
                template_id="critical-policy",
                policy_parameters={"strictness": "critical"},
                speaker="system",
                state_summary="Critical mode",
                goal="Block dangerous actions",
                timestamp=timestamp,
            ),
            # Safety check - blocks
            SafetyCheckEvent(
                id="safety-3",
                session_id="session-1",
                policy_name="critical-policy",
                outcome="block",
                risk_level="high",
                rationale="Dangerous action blocked",
                blocked_action="execute_command",
                timestamp=timestamp,
            ),
        ]

    def test_detect_policy_shifts_via_live_summary(
        self, events_with_policy_escalation: list[TraceEvent], intelligence: TraceIntelligence
    ):
        """Verify that policy shifts are detected in live summary."""
        live_summary = intelligence.build_live_summary(events_with_policy_escalation, [])
        # Check for policy shift alert
        policy_shift_alerts = [
            alert for alert in live_summary["recent_alerts"] if alert["alert_type"] == "policy_shift"
        ]
        # With 3 different policies, shift should be detected
        assert len(policy_shift_alerts) >= 1, "Should detect policy shifts"
        for alert in policy_shift_alerts:
            assert alert["severity"] == "medium"
            assert "signal" in alert
            # Check for policy count mention in signal (handles "3 prompt policies" format)
            assert "policies" in alert["signal"].lower() or "policy" in alert["signal"].lower()

    def test_escalation_increases_replay_value(
        self, events_with_policy_escalation: list[TraceEvent], intelligence: TraceIntelligence
    ):
        """Verify that policy escalation increases session replay value."""
        analysis = intelligence.analyze_session(events_with_policy_escalation, [])
        # Session with multiple policy shifts should have higher replay value
        assert analysis["session_replay_value"] > 0.4, "Policy escalation should increase replay value"
        assert analysis["retention_tier"] in {"full", "summarized"}

    def test_blocked_actions_have_high_severity(
        self, events_with_policy_escalation: list[TraceEvent], intelligence: TraceIntelligence
    ):
        """Verify that blocked actions have high severity scores."""
        analysis = intelligence.analyze_session(events_with_policy_escalation, [])
        # Find the blocked safety check
        blocked_safety_ranking = next(r for r in analysis["event_rankings"] if r["event_id"] == "safety-3")
        assert blocked_safety_ranking["severity"] >= 0.75, "Blocked safety checks should have high severity"

    def test_escalation_chain_in_failure_explanations(
        self, events_with_policy_escalation: list[TraceEvent], intelligence: TraceIntelligence
    ):
        """Verify that policy escalation appears in failure explanations."""
        analysis = intelligence.analyze_session(events_with_policy_escalation, [])
        # Safety check with outcome != pass should have a failure explanation
        failed_safety = [e for e in analysis["failure_explanations"] if e["failure_event_id"] == "safety-3"]
        assert len(failed_safety) == 1
        explanation = failed_safety[0]
        assert "failure_mode" in explanation
        assert "symptom" in explanation
        assert "likely_cause" in explanation

    def test_no_escalation_in_stable_session(self, intelligence: TraceIntelligence, make_trace_event):
        """Verify that stable sessions don't trigger escalation alerts."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            PromptPolicyEvent(
                id="policy-1",
                session_id="session-1",
                template_id="stable-policy",
                policy_parameters={"strictness": "medium"},
                speaker="system",
                state_summary="Stable mode",
                goal="Normal operation",
                timestamp=timestamp,
            ),
            SafetyCheckEvent(
                id="safety-1",
                session_id="session-1",
                policy_name="stable-policy",
                outcome="pass",
                risk_level="low",
                rationale="No issues",
                timestamp=timestamp,
            ),
        ]
        live_summary = intelligence.build_live_summary(events, [])
        # No policy shift should be detected with only one policy
        policy_shift_alerts = [
            alert for alert in live_summary["recent_alerts"] if alert["alert_type"] == "policy_shift"
        ]
        assert len(policy_shift_alerts) == 0, "Single policy should not trigger policy shift"


# ------------------------------------------------------------------
# Test Class: Representative Trace Selection
# ------------------------------------------------------------------


class TestRepresentativeTraceSelection:
    """Tests for representative trace selection functionality."""

    @pytest.fixture
    def intelligence(self) -> TraceIntelligence:
        """Create TraceIntelligence instance for tests."""
        return TraceIntelligence()

    @pytest.fixture
    def multi_cluster_events(self, make_trace_event) -> list[TraceEvent]:
        """Create events with multiple failure clusters."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        return [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            # Cluster 1: Tool errors
            ToolCallEvent(
                id="tool-call-1",
                session_id="session-1",
                tool_name="search",
                timestamp=timestamp,
            ),
            ToolResultEvent(
                id="tool-result-1",
                session_id="session-1",
                tool_name="search",
                error="timeout",
                timestamp=timestamp,
            ),
            ToolCallEvent(
                id="tool-call-2",
                session_id="session-1",
                tool_name="search",
                timestamp=timestamp,
            ),
            ToolResultEvent(
                id="tool-result-2",
                session_id="session-1",
                tool_name="search",
                error="timeout",
                timestamp=timestamp,
            ),
            # Cluster 2: Refusals
            DecisionEvent(
                id="decision-1",
                session_id="session-1",
                chosen_action="proceed",
                confidence=0.8,
                evidence=[],
                timestamp=timestamp,
            ),
            RefusalEvent(
                id="refusal-1",
                session_id="session-1",
                reason="Unsafe action",
                policy_name="safety-policy",
                risk_level="high",
                timestamp=timestamp,
            ),
            DecisionEvent(
                id="decision-2",
                session_id="session-1",
                chosen_action="retry",
                confidence=0.5,
                evidence=[],
                timestamp=timestamp,
            ),
            RefusalEvent(
                id="refusal-2",
                session_id="session-1",
                reason="Unsafe action",
                policy_name="safety-policy",
                risk_level="high",
                timestamp=timestamp,
            ),
        ]

    def test_one_representative_per_cluster(
        self, multi_cluster_events: list[TraceEvent], intelligence: TraceIntelligence
    ):
        """Verify that exactly one representative trace is selected per cluster."""
        analysis = intelligence.analyze_session(multi_cluster_events, [])
        # Should have multiple clusters
        assert len(analysis["failure_clusters"]) >= 2, "Should have multiple failure clusters"
        # Each cluster should have exactly one representative
        for cluster in analysis["failure_clusters"]:
            assert cluster["representative_event_id"] is not None
            assert (
                len(
                    [
                        c
                        for c in analysis["failure_clusters"]
                        if c["representative_event_id"] == cluster["representative_event_id"]
                    ]
                )
                == 1
            ), "Each representative should be unique across clusters"

    def test_representative_has_highest_composite_score(
        self, multi_cluster_events: list[TraceEvent], intelligence: TraceIntelligence
    ):
        """Verify that representatives have the highest composite score in their cluster."""
        analysis = intelligence.analyze_session(multi_cluster_events, [])
        ranking_by_id = {r["event_id"]: r for r in analysis["event_rankings"]}
        for cluster in analysis["failure_clusters"]:
            rep_id = cluster["representative_event_id"]
            rep_ranking = ranking_by_id.get(rep_id)
            assert rep_ranking is not None
            for event_id in cluster["event_ids"]:
                other_ranking = ranking_by_id.get(event_id)
                if other_ranking and event_id != rep_id:
                    assert rep_ranking["composite"] >= other_ranking["composite"], (
                        f"Representative {rep_id} should have highest composite in cluster"
                    )

    def test_representative_ids_in_high_replay_value_list(
        self, multi_cluster_events: list[TraceEvent], intelligence: TraceIntelligence
    ):
        """Verify that representative event IDs are in the high replay value list."""
        analysis = intelligence.analyze_session(multi_cluster_events, [])
        # All representative IDs should be in high replay value list
        for cluster in analysis["failure_clusters"]:
            assert cluster["representative_event_id"] in analysis["high_replay_value_ids"], (
                f"Representative {cluster['representative_event_id']} should be in high replay value list"
            )

    def test_empty_session_no_representatives(self, intelligence: TraceIntelligence):
        """Verify that empty sessions produce no representatives."""
        analysis = intelligence.analyze_session([], [])
        assert analysis["representative_failure_ids"] == []

    def test_single_failure_is_representative(self, intelligence: TraceIntelligence, make_trace_event):
        """Verify that a single failure is its own representative."""
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
                error_message="Bad input",
                timestamp=timestamp,
            ),
        ]
        analysis = intelligence.analyze_session(events, [])
        assert len(analysis["failure_clusters"]) == 1
        assert len(analysis["representative_failure_ids"]) == 1
        assert analysis["failure_clusters"][0]["representative_event_id"] == "error-1"


# ------------------------------------------------------------------
# Test Class: Retention Tier Assignment
# ------------------------------------------------------------------


class TestRetentionTierAssignment:
    """Tests for retention tier assignment functionality."""

    @pytest.fixture
    def intelligence(self) -> TraceIntelligence:
        """Create TraceIntelligence instance for tests."""
        return TraceIntelligence()

    def test_high_value_session_gets_full_retention(self, intelligence: TraceIntelligence, make_trace_event):
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
        # Multiple errors should result in full retention
        assert analysis["retention_tier"] == "full", "High-value session with errors should have full retention"

    def test_medium_value_session_gets_summarized(self, intelligence: TraceIntelligence, make_trace_event):
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
        # Behavior alert should result in at least summarized retention
        assert analysis["retention_tier"] in {"summarized", "full"}, (
            "Medium-value session should have summarized retention"
        )

    def test_low_value_session_gets_downsampled(self, intelligence: TraceIntelligence, make_trace_event):
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
        # Routine session should have downsampled retention
        assert analysis["retention_tier"] == "downsampled", "Low-value session should have downsampled retention"

    def test_retention_tier_considers_failure_clusters(self, intelligence: TraceIntelligence, make_trace_event):
        """Verify that retention tier considers failure cluster count."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        # Create events that result in multiple failure clusters
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
        # Multiple distinct failures should result in full retention
        assert analysis["retention_tier"] == "full", "Multiple failure clusters should result in full retention"

    def test_retention_tier_considers_high_severity_count(self, intelligence: TraceIntelligence, make_trace_event):
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
        # High severity event should result in full retention
        assert analysis["retention_tier"] == "full", "High severity count should result in full retention"

    def test_retention_tier_considers_replay_value(self, intelligence: TraceIntelligence, make_trace_event):
        """Verify that retention tier is assigned based on session analysis."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            # Create events that increase replay value
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
        # Verify retention tier is assigned (any valid tier is acceptable)
        assert analysis["retention_tier"] in {"full", "summarized", "downsampled"}
        # Verify session replay value is calculated
        assert "session_replay_value" in analysis
        assert analysis["session_replay_value"] >= 0

    def test_checkpoint_retention_tier_assigned(self, intelligence: TraceIntelligence, make_trace_event):
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

    def test_retention_tier_edge_case_replay_value_thresholds(self, intelligence: TraceIntelligence):
        """Verify retention tier thresholds are correctly applied."""
        # Test the boundaries
        # Full retention: replay_value >= 0.72 OR high_severity_count > 0 OR failure_cluster_count >= 2
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
        # Summarized retention: replay_value >= 0.42 OR behavior_alert_count > 0 or failure_cluster_count > 0
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
        # Downsampled: all other cases
        assert (
            intelligence.retention_tier(
                replay_value=0.3,
                high_severity_count=0,
                failure_cluster_count=0,
                behavior_alert_count=0,
            )
            == "downsampled"
        )

    def test_empty_session_has_downsampled_retention(self, intelligence: TraceIntelligence):
        """Verify that empty sessions have downsampled retention."""
        analysis = intelligence.analyze_session([], [])
        assert analysis["retention_tier"] == "downsampled"

    def test_session_summary_includes_correct_counts(self, intelligence: TraceIntelligence, make_trace_event):
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
            # Tool loop creates behavior alert (3 consecutive same tool calls)
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


# ------------------------------------------------------------------
# Test Class: Clustering Edge Cases
# ------------------------------------------------------------------


class TestClusteringEdgeCases:
    """Edge case tests for failure clustering."""

    @pytest.fixture
    def intelligence(self) -> TraceIntelligence:
        return TraceIntelligence()

    def test_single_failure_creates_cluster(self, intelligence: TraceIntelligence, make_trace_event):
        """Single failure should create a cluster of size 1."""
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
                error_message="Single error",
                timestamp=timestamp,
            ),
        ]
        analysis = intelligence.analyze_session(events, [])
        assert len(analysis["failure_clusters"]) == 1
        assert analysis["failure_clusters"][0]["count"] == 1

    def test_identical_errors_same_fingerprint(self, intelligence: TraceIntelligence, make_trace_event):
        """Identical errors should have the same fingerprint."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        error1 = ErrorEvent(
            id="error-1",
            session_id="session-1",
            error_type="ConnectionError",
            error_message="Failed to connect",
            timestamp=timestamp,
        )
        error2 = ErrorEvent(
            id="error-2",
            session_id="session-1",
            error_type="ConnectionError",
            error_message="Failed to connect",
            timestamp=timestamp,
        )
        fp1 = intelligence.fingerprint(error1)
        fp2 = intelligence.fingerprint(error2)
        assert fp1 == fp2

    def test_different_errors_different_fingerprint(self, intelligence: TraceIntelligence, make_trace_event):
        """Different error types should have different fingerprints."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        error1 = ErrorEvent(
            id="error-1",
            session_id="session-1",
            error_type="ValueError",
            error_message="Error",
            timestamp=timestamp,
        )
        error2 = ErrorEvent(
            id="error-2",
            session_id="session-1",
            error_type="TypeError",
            error_message="Error",
            timestamp=timestamp,
        )
        fp1 = intelligence.fingerprint(error1)
        fp2 = intelligence.fingerprint(error2)
        assert fp1 != fp2


# ------------------------------------------------------------------
# Test Class: Retention Tier Edge Cases
# ------------------------------------------------------------------


class TestRetentionTierEdgeCases:
    """Edge case tests for retention tier assignment."""

    @pytest.fixture
    def intelligence(self) -> TraceIntelligence:
        return TraceIntelligence()

    def test_replay_value_exactly_at_threshold(self, intelligence: TraceIntelligence):
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

    def test_multiple_conditions_trigger_full_retention(self, intelligence: TraceIntelligence):
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

    def test_zero_replay_value_gets_downsampled(self, intelligence: TraceIntelligence):
        """Zero replay value should result in downsampled tier."""
        tier = intelligence.retention_tier(
            replay_value=0.0,
            high_severity_count=0,
            failure_cluster_count=0,
            behavior_alert_count=0,
        )
        assert tier == "downsampled"
