"""Tests for representative trace selection functionality."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import (
    DecisionEvent,
    EventType,
    RefusalEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from collector.intelligence.facade import TraceIntelligence


class TestRepresentativeTraceSelection:
    """Tests for representative trace selection functionality."""

    @pytest.fixture
    def intelligence(self) -> TraceIntelligence:
        """Create a TraceIntelligence instance for tests."""
        return TraceIntelligence()

    @pytest.fixture
    def multi_cluster_events(self, make_trace_event):
        """Create events with multiple failure clusters."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        return [
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

    def test_one_representative_per_cluster(self, multi_cluster_events, intelligence):
        """Verify that exactly one representative trace is selected per cluster."""
        analysis = intelligence.analyze_session(multi_cluster_events, [])
        assert len(analysis["failure_clusters"]) >= 2, "Should have multiple failure clusters"
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

    def test_representative_has_highest_composite_score(self, multi_cluster_events, intelligence):
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

    def test_representative_ids_in_high_replay_value_list(self, multi_cluster_events, intelligence):
        """Verify that representative event IDs are in the high replay value list."""
        analysis = intelligence.analyze_session(multi_cluster_events, [])
        for cluster in analysis["failure_clusters"]:
            assert cluster["representative_event_id"] in analysis["high_replay_value_ids"], (
                f"Representative {cluster['representative_event_id']} should be in high replay value list"
            )

    def test_empty_session_no_representatives(self, intelligence):
        """Verify that empty sessions produce no representatives."""
        analysis = intelligence.analyze_session([], [])
        assert analysis["representative_failure_ids"] == []

    def test_single_failure_is_representative(self, intelligence, make_trace_event):
        """Verify that a single failure is its own representative."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        from agent_debugger_sdk.core.events import ErrorEvent

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
