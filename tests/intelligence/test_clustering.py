"""Tests for cross-session failure clustering functionality."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import (
    ErrorEvent,
    EventType,
    ToolResultEvent,
)
from collector.intelligence import TraceIntelligence


class TestCrossSessionClustering:
    """Tests for cross-session failure clustering functionality."""

    @pytest.fixture
    def intelligence(self) -> TraceIntelligence:
        """Create a TraceIntelligence instance for tests."""
        return TraceIntelligence()

    @pytest.fixture
    def sample_sessions(self, make_trace_event):
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
            from agent_debugger_sdk.core.events import Checkpoint
            from tests.intelligence.conftest import make_session_with_events

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

    def test_cluster_similar_failures_across_sessions(self, sample_sessions, intelligence):
        """Verify that similar failures across sessions are clustered correctly."""
        from typing import Any

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
        assert len(all_failure_fingerprints) > 0, "Should have at least one failure cluster"
        for fingerprint, cluster_data_list in all_failure_fingerprints.items():
            for cluster_data in cluster_data_list:
                cluster = cluster_data["cluster"]
                assert "count" in cluster
                assert "event_ids" in cluster
                assert "representative_event_id" in cluster
                assert "max_composite" in cluster
                assert cluster["count"] >= 1
                assert len(cluster["event_ids"]) >= 1

    def test_cluster_representative_selection(self, sample_sessions, intelligence):
        """Verify that representative traces are selected for each cluster."""
        for session, events, checkpoints in sample_sessions:
            analysis = intelligence.analyze_session(events, checkpoints)
            assert "representative_failure_ids" in analysis
            for cluster in analysis["failure_clusters"]:
                assert cluster["representative_event_id"] in analysis["representative_failure_ids"]
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

    def test_fingerprint_consistency(self, intelligence, make_trace_event):
        """Verify that fingerprints are consistent for similar failure types."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
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

    def test_empty_session_clustering(self, intelligence):
        """Verify that empty sessions produce no clusters."""
        analysis = intelligence.analyze_session([], [])
        assert analysis["failure_clusters"] == []
        assert analysis["representative_failure_ids"] == []

    def test_high_severity_events_clustered(self, intelligence, make_trace_event):
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
        analysis = intelligence.analyze_session(events, [])
        error_rankings = [r for r in analysis["event_rankings"] if r["event_id"] == "error-high"]
        assert len(error_rankings) == 1
        assert error_rankings[0]["severity"] >= 0.9, "Error should have high severity"


class TestClusteringEdgeCases:
    """Edge case tests for failure clustering."""

    @pytest.fixture
    def intelligence(self) -> TraceIntelligence:
        return TraceIntelligence()

    def test_single_failure_creates_cluster(self, intelligence, make_trace_event):
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

    def test_identical_errors_same_fingerprint(self, intelligence, make_trace_event):
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

    def test_different_errors_different_fingerprint(self, intelligence, make_trace_event):
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
