"""Tests for cross-session failure clustering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent_debugger_sdk.core.events import EventType, Session, SessionStatus, TraceEvent
from collector.clustering.cross_session import CrossSessionCluster, CrossSessionClusterAnalyzer
from collector.intelligence.compute import compute_latency_spike_score, compute_retry_churn_score


def create_test_session(
    session_id: str,
    started_at: datetime,
    agent_name: str = "test-agent",
) -> Session:
    """Create a test session."""
    return Session(
        id=session_id,
        agent_name=agent_name,
        framework="test",
        started_at=started_at,
        ended_at=None,
        status=SessionStatus.RUNNING,
        total_tokens=0,
        total_cost_usd=0.0,
        tool_calls=0,
        llm_calls=0,
        errors=0,
        replay_value=0.5,
        config={},
        tags=[],
    )


def create_test_tool_call(
    event_id: str,
    tool_name: str,
    duration_ms: float | None = None,
) -> TraceEvent:
    """Create a test tool call event."""
    data = {"tool_name": tool_name}
    if duration_ms is not None:
        data["duration_ms"] = duration_ms

    return TraceEvent(
        id=event_id,
        session_id="test-session",
        parent_id=None,
        event_type=EventType.TOOL_CALL,
        timestamp=datetime.now(timezone.utc),
        name=f"call_{tool_name}",
        data=data,
        metadata={},
        importance=0.5,
    )


def test_cross_session_clustering_with_multiple_sessions():
    """Test cross-session clustering with multiple sessions containing same failure fingerprint."""
    now = datetime.now(timezone.utc)
    analyzer = CrossSessionClusterAnalyzer()

    # Create 3 sessions with the same failure fingerprint
    sessions = [
        create_test_session("session-1", now - timedelta(days=1)),
        create_test_session("session-2", now - timedelta(days=5)),
        create_test_session("session-3", now - timedelta(hours=12)),
    ]

    # Mock rankings with same fingerprint across sessions
    session_rankings = {
        "session-1": {
            "failure_fingerprints": [("error:timeout", 0.85)],
            "replay_value": 0.7,
        },
        "session-2": {
            "failure_fingerprints": [("error:timeout", 0.75)],
            "replay_value": 0.6,
        },
        "session-3": {
            "failure_fingerprints": [("error:timeout", 0.90)],
            "replay_value": 0.8,
        },
    }

    clusters = analyzer.analyze(sessions, session_rankings)

    assert len(clusters) == 1
    cluster = clusters[0]

    assert cluster.fingerprint == "error:timeout"
    assert cluster.count == 3
    assert set(cluster.sessions) == {"session-1", "session-2", "session-3"}
    assert cluster.representative == "session-3"  # Highest score
    assert cluster.score > 0.0


def test_cross_session_clustering_with_different_fingerprints():
    """Test cross-session clustering with different failure fingerprints."""
    now = datetime.now(timezone.utc)
    analyzer = CrossSessionClusterAnalyzer()

    sessions = [
        create_test_session("session-1", now - timedelta(days=1)),
        create_test_session("session-2", now - timedelta(days=2)),
        create_test_session("session-3", now - timedelta(days=3)),
    ]

    session_rankings = {
        "session-1": {
            "failure_fingerprints": [("error:timeout", 0.85)],
            "replay_value": 0.7,
        },
        "session-2": {
            "failure_fingerprints": [("error:api_failure", 0.80)],
            "replay_value": 0.6,
        },
        "session-3": {
            "failure_fingerprints": [("error:timeout", 0.75), ("error:api_failure", 0.70)],
            "replay_value": 0.5,
        },
    }

    clusters = analyzer.analyze(sessions, session_rankings)

    # Should create 2 clusters (timeout has 2 sessions, api_failure has 2 sessions)
    assert len(clusters) == 2

    # Check that timeout cluster is ranked higher (more recent/recurrent)
    timeout_cluster = next((c for c in clusters if c.fingerprint == "error:timeout"), None)
    api_cluster = next((c for c in clusters if c.fingerprint == "error:api_failure"), None)

    assert timeout_cluster is not None
    assert api_cluster is not None
    assert timeout_cluster.count == 2
    assert api_cluster.count == 2


def test_time_decay_weighting():
    """Test that recent sessions contribute more to cluster score."""
    now = datetime.now(timezone.utc)
    analyzer = CrossSessionClusterAnalyzer(decay_half_life_days=7.0)

    # One old session, one recent session with same fingerprint
    sessions = [
        create_test_session("old-session", now - timedelta(days=30)),
        create_test_session("recent-session", now - timedelta(hours=6)),
    ]

    session_rankings = {
        "old-session": {
            "failure_fingerprints": [("error:test", 0.90)],  # High score but old
            "replay_value": 0.5,
        },
        "recent-session": {
            "failure_fingerprints": [("error:test", 0.95)],  # Even higher score and recent
            "replay_value": 0.5,
        },
    }

    clusters = analyzer.analyze(sessions, session_rankings)

    assert len(clusters) == 1
    cluster = clusters[0]

    # Recent session should be representative due to both score and time decay
    assert cluster.representative == "recent-session"
    assert cluster.count == 2


def test_representative_selection():
    """Test that representative is selected based on highest composite score."""
    now = datetime.now(timezone.utc)
    analyzer = CrossSessionClusterAnalyzer()

    sessions = [
        create_test_session("session-1", now),
        create_test_session("session-2", now),
        create_test_session("session-3", now),
    ]

    session_rankings = {
        "session-1": {
            "failure_fingerprints": [("error:test", 0.60)],
            "replay_value": 0.5,
        },
        "session-2": {
            "failure_fingerprints": [("error:test", 0.95)],  # Highest score
            "replay_value": 0.5,
        },
        "session-3": {
            "failure_fingerprints": [("error:test", 0.75)],
            "replay_value": 0.5,
        },
    }

    clusters = analyzer.analyze(sessions, session_rankings)

    assert len(clusters) == 1
    assert clusters[0].representative == "session-2"


def test_retry_churn_scoring():
    """Test retry churn score computation."""
    # No tool calls
    assert compute_retry_churn_score([]) == 0.0

    # Single tool call
    events = [create_test_tool_call("event-1", "search")]
    assert compute_retry_churn_score(events) == 0.0

    # Same tool called repeatedly
    events = [
        create_test_tool_call("event-1", "search"),
        create_test_tool_call("event-2", "search"),
        create_test_tool_call("event-3", "search"),
        create_test_tool_call("event-4", "search"),
    ]
    score = compute_retry_churn_score(events)
    assert score > 0.0
    assert score <= 0.5  # Capped at 0.5 for this signal alone

    # Different tools (no retry pattern)
    events = [
        create_test_tool_call("event-1", "search"),
        create_test_tool_call("event-2", "read"),
        create_test_tool_call("event-3", "write"),
    ]
    score = compute_retry_churn_score(events)
    assert score < 0.1  # Should be very low


def test_latency_spike_scoring():
    """Test latency spike score computation."""
    # No events with durations
    events = [
        create_test_tool_call("event-1", "search", duration_ms=0),
        create_test_tool_call("event-2", "read", duration_ms=0),
    ]
    assert compute_latency_spike_score(events) == 0.0

    # Normal latencies (no spikes)
    events = [
        create_test_tool_call("event-1", "search", duration_ms=100),
        create_test_tool_call("event-2", "search", duration_ms=120),
        create_test_tool_call("event-3", "search", duration_ms=110),
        create_test_tool_call("event-4", "search", duration_ms=105),
    ]
    score = compute_latency_spike_score(events)
    assert score == 0.0  # No spikes >3x median (median ~110)

    # Significant latency spikes
    events = [
        create_test_tool_call("event-1", "search", duration_ms=100),
        create_test_tool_call("event-2", "search", duration_ms=105),
        create_test_tool_call("event-3", "search", duration_ms=110),
        create_test_tool_call("event-4", "search", duration_ms=500),  # >3x spike
        create_test_tool_call("event-5", "search", duration_ms=600),  # >3x spike
    ]
    score = compute_latency_spike_score(events)
    assert score > 0.0
    assert score <= 1.0


def test_edge_cases():
    """Test edge cases for cross-session clustering."""
    analyzer = CrossSessionClusterAnalyzer()

    # Empty sessions
    clusters = analyzer.analyze([], {})
    assert len(clusters) == 0

    # Sessions with no failures
    now = datetime.now(timezone.utc)
    sessions = [
        create_test_session("session-1", now),
        create_test_session("session-2", now),
    ]

    session_rankings = {
        "session-1": {"failure_fingerprints": [], "replay_value": 0.5},
        "session-2": {"failure_fingerprints": [], "replay_value": 0.5},
    }

    clusters = analyzer.analyze(sessions, session_rankings)
    assert len(clusters) == 0

    # Single session
    sessions = [create_test_session("session-1", now)]
    session_rankings = {
        "session-1": {
            "failure_fingerprints": [("error:test", 0.8)],
            "replay_value": 0.5,
        },
    }

    clusters = analyzer.analyze(sessions, session_rankings)
    assert len(clusters) == 1
    assert clusters[0].count == 1


def test_cross_session_cluster_to_dict():
    """Test CrossSessionCluster to_dict conversion."""
    now = datetime.now(timezone.utc)
    cluster = CrossSessionCluster(
        fingerprint="error:test",
        count=3,
        sessions=["s1", "s2", "s3"],
        representative="s2",
        first_seen=now - timedelta(days=10),
        last_seen=now,
        score=0.85,
    )

    result = cluster.to_dict()

    assert result["fingerprint"] == "error:test"
    assert result["count"] == 3
    assert result["sessions"] == ["s1", "s2", "s3"]
    assert result["representative"] == "s2"
    assert result["first_seen"] is not None
    assert result["last_seen"] is not None
    assert result["score"] == 0.85


def test_similar_tool_detection():
    """Test that similar tool names are detected as retry patterns."""
    from collector.intelligence.compute import _tools_are_similar

    # Exact match
    assert _tools_are_similar("search_file", "search_file") is True

    # Substring match
    assert _tools_are_similar("search_file", "search_files") is True
    assert _tools_are_similar("read_file", "read") is True

    # Different tools
    assert _tools_are_similar("search", "write") is False

    # Edge cases
    assert _tools_are_similar("", "search") is False
    assert _tools_are_similar("abc", "def") is False
