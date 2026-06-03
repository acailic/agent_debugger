"""Tests for violation detector module."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import EventType, TraceEvent
from agent_debugger_sdk.core.violation_detector import (
    CrossTraceSearch,
    SessionEmbedding,
    SparseFailureDetector,
    SparseFailurePattern,
    TraceCluster,
    TraceClusterer,
    ViolationEvidence,
    ViolationReport,
    ViolationSeverity,
    ViolationType,
    cluster_sessions,
    compute_session_embedding,
    detect_sparse_failures,
    search_violations_across_traces,
)


@pytest.fixture
def sample_events():
    """Create sample trace events for testing."""
    now = datetime.now(timezone.utc)
    events = [
        TraceEvent(
            id="event_1",
            session_id="session_1",
            timestamp=now,
            event_type=EventType.AGENT_START,
            name="Agent Start",
            data={},
            metadata={},
            importance=0.5,
            upstream_event_ids=[],
            parent_id=None,
        ),
        TraceEvent(
            id="event_2",
            session_id="session_1",
            timestamp=now,
            event_type=EventType.TOOL_CALL,
            name="Tool Call",
            data={},
            metadata={},
            importance=0.7,
            upstream_event_ids=[],
            parent_id="event_1",
            tool_name="search_tool",
        ),
        TraceEvent(
            id="event_3",
            session_id="session_1",
            timestamp=now,
            event_type=EventType.ERROR,
            name="Error",
            data={},
            metadata={},
            importance=0.9,
            upstream_event_ids=[],
            parent_id="event_2",
            error_type="ValueError",
            error_message="Invalid input",
        ),
    ]
    return events


@pytest.fixture
def sample_sessions(sample_events):
    """Create sample sessions for testing."""
    sessions = {
        "session_1": sample_events,
        "session_2": sample_events,  # Similar session
        "session_3": sample_events,  # Another similar session
    }
    return sessions


def test_compute_session_embedding(sample_events):
    """Test session embedding computation."""
    embedding = compute_session_embedding("test_session", sample_events)

    assert embedding.session_id == "test_session"
    assert len(embedding.embedding_vector) > 0
    assert len(embedding.feature_weights) > 0
    assert embedding.summary_hash != ""


def test_session_embedding_similarity(sample_events):
    """Test session embedding similarity calculation."""
    embedding1 = compute_session_embedding("session_1", sample_events)
    embedding2 = compute_session_embedding("session_2", sample_events)

    # Same events should have high similarity
    similarity = embedding1.similarity(embedding2)
    assert similarity > 0.5


def test_session_embedding_similarity_different_vectors():
    """Test similarity with different embedding vectors."""
    embedding1 = SessionEmbedding(
        session_id="session_1",
        embedding_vector=[1.0, 0.0, 0.0],
    )
    embedding2 = SessionEmbedding(
        session_id="session_2",
        embedding_vector=[0.0, 1.0, 0.0],
    )

    similarity = embedding1.similarity(embedding2)
    # Orthogonal vectors should have low similarity
    assert similarity < 0.5


def test_trace_clusterer_initialization(sample_sessions):
    """Test TraceClusterer initialization."""
    clusterer = TraceClusterer(sample_sessions)

    assert len(clusterer.sessions) == 3
    assert len(clusterer.embeddings) == 3
    assert clusterer.sessions == sample_sessions


def test_cluster_sessions(sample_sessions):
    """Test session clustering."""
    clusters = cluster_sessions(sample_sessions, similarity_threshold=0.5, min_cluster_size=2)

    # With high similarity threshold, should form at least one cluster
    assert len(clusters) >= 1

    for cluster in clusters:
        assert len(cluster.session_ids) >= 2
        assert cluster.cluster_id.startswith("cluster_")


def test_identify_global_outliers(sample_sessions):
    """Test global outlier identification."""
    # Add an outlier session with different events
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    outlier_events = [
        TraceEvent(
            id="event_10",
            session_id="outlier_session",
            timestamp=now + timedelta(days=1),
            event_type=EventType.AGENT_START,
            name="Different Agent",
            data={"different": "data"},
            metadata={},
            importance=0.5,
            upstream_event_ids=[],
            parent_id=None,
        )
    ]

    all_sessions = {**sample_sessions, "outlier_session": outlier_events}

    clusterer = TraceClusterer(all_sessions)
    outliers = clusterer.identify_global_outliers(z_threshold=1.0)

    # Should identify at least some sessions as potential outliers
    assert isinstance(outliers, list)


def test_cross_trace_search_initialization(sample_sessions):
    """Test CrossTraceSearch initialization."""
    searcher = CrossTraceSearch(sample_sessions)

    assert searcher.sessions == sample_sessions


def test_search_violations_basic(sample_sessions):
    """Test basic violation search."""
    searcher = CrossTraceSearch(sample_sessions)
    violations = searcher.search_violations("error", max_results=10)

    # Should find violations matching "error" keyword
    assert len(violations) > 0

    for violation in violations:
        assert violation.violation_id.startswith("violation_")
        assert violation.violation_type in ViolationType
        assert violation.severity in ViolationSeverity
        assert len(violation.evidence) > 0


def test_search_violations_no_results():
    """Test search with no matching results."""
    sessions = {
        "session_1": [
            TraceEvent(
                id="event_1",
                session_id="session_1",
                timestamp=datetime.now(timezone.utc),
                event_type=EventType.AGENT_START,
                name="Normal Event",
                data={},
                metadata={},
                importance=0.5,
                upstream_event_ids=[],
                parent_id=None,
            )
        ]
    }

    searcher = CrossTraceSearch(sessions)
    violations = searcher.search_violations("xyz_nonexistent_pattern", max_results=10)

    # Should return empty list
    assert len(violations) == 0


def test_sparse_failure_detector_initialization(sample_sessions):
    """Test SparseFailureDetector initialization."""
    detector = SparseFailureDetector(sample_sessions)

    assert detector.sessions == sample_sessions


def test_detect_sparse_failures_with_errors(sample_sessions):
    """Test sparse failure detection with error events."""
    detector = SparseFailureDetector(sample_sessions)
    patterns = detector.detect_sparse_failures(min_occurrences=2)

    # All our test sessions have the same error, so should find patterns
    assert len(patterns) > 0

    for pattern in patterns:
        assert pattern.pattern_id.startswith("sparse_failure_")
        assert pattern.failure_type != ""
        assert len(pattern.session_ids) >= 2


def test_detect_sparse_failures_no_errors():
    """Test sparse failure detection with no error events."""
    now = datetime.now(timezone.utc)
    sessions = {
        "session_1": [
            TraceEvent(
                id="event_1",
                session_id="session_1",
                timestamp=now,
                event_type=EventType.AGENT_START,
                name="Normal Event",
                data={},
                metadata={},
                importance=0.5,
                upstream_event_ids=[],
                parent_id=None,
            )
        ]
    }

    detector = SparseFailureDetector(sessions)
    patterns = detector.detect_sparse_failures(min_occurrences=2)

    # No errors, so no patterns
    assert len(patterns) == 0


def test_violation_evidence_serialization():
    """Test ViolationEvidence serialization."""
    now = datetime.now(timezone.utc)
    evidence = ViolationEvidence(
        session_id="test_session",
        event_id="test_event",
        evidence_type="test_type",
        description="Test evidence",
        timestamp=now,
        confidence=0.8,
        metadata={"key": "value"},
    )

    evidence_dict = evidence.to_dict()

    assert evidence_dict["session_id"] == "test_session"
    assert evidence_dict["event_id"] == "test_event"
    assert evidence_dict["confidence"] == 0.8
    assert evidence_dict["metadata"]["key"] == "value"


def test_violation_report_serialization():
    """Test ViolationReport serialization."""
    now = datetime.now(timezone.utc)
    report = ViolationReport(
        violation_id="test_violation",
        violation_type=ViolationType.SPARSE_FAILURE,
        severity=ViolationSeverity.HIGH,
        title="Test Violation",
        description="Test violation description",
        affected_sessions=["session_1", "session_2"],
        evidence=[
            ViolationEvidence(
                session_id="session_1",
                event_id="event_1",
                evidence_type="error",
                description="Error evidence",
                timestamp=now,
                confidence=0.9,
            )
        ],
    )

    report_dict = report.to_dict()

    assert report_dict["violation_id"] == "test_violation"
    assert report_dict["violation_type"] == "sparse_failure"
    assert report_dict["severity"] == "high"
    assert len(report_dict["affected_sessions"]) == 2
    assert len(report_dict["evidence"]) == 1


def test_trace_cluster_serialization():
    """Test TraceCluster serialization."""
    cluster = TraceCluster(
        cluster_id="test_cluster",
        session_ids=["session_1", "session_2"],
        centroid_embedding=SessionEmbedding(
            session_id="centroid",
            embedding_vector=[0.5, 0.5, 0.5],
        ),
        cluster_characteristics={"avg_duration": 10.0},
        outlier_session_ids=["session_3"],
    )

    cluster_dict = cluster.to_dict()

    assert cluster_dict["cluster_id"] == "test_cluster"
    assert len(cluster_dict["session_ids"]) == 2
    assert cluster_dict["centroid_embedding"] is not None
    assert cluster_dict["outlier_session_ids"] == ["session_3"]


def test_sparse_failure_pattern_serialization():
    """Test SparseFailurePattern serialization."""
    pattern = SparseFailurePattern(
        pattern_id="test_pattern",
        failure_type="ValueError",
        description="Test pattern",
        required_sessions=2,
        session_ids=["session_1", "session_2"],
        failure_points=[
            {
                "session_id": "session_1",
                "event_id": "event_1",
                "timestamp": "2024-01-01T00:00:00Z",
                "error_type": "ValueError",
                "error_message": "Test error",
            }
        ],
        confidence=0.8,
    )

    pattern_dict = pattern.to_dict()

    assert pattern_dict["pattern_id"] == "test_pattern"
    assert pattern_dict["failure_type"] == "ValueError"
    assert pattern_dict["confidence"] == 0.8
    assert len(pattern_dict["failure_points"]) == 1


def test_integration_cluster_sessions_function(sample_sessions):
    """Test the convenience function for clustering sessions."""
    clusters = cluster_sessions(sample_sessions, similarity_threshold=0.5, min_cluster_size=2)

    assert isinstance(clusters, list)
    # With our similar sessions, should form at least one cluster
    assert len(clusters) >= 1


def test_integration_search_violations_function(sample_sessions):
    """Test the convenience function for searching violations."""
    violations = search_violations_across_traces(
        sample_sessions, nl_query="error", max_results=10
    )

    assert isinstance(violations, list)
    assert len(violations) > 0


def test_integration_detect_sparse_failures_function(sample_sessions):
    """Test the convenience function for detecting sparse failures."""
    patterns = detect_sparse_failures(sample_sessions, min_occurrences=2)

    assert isinstance(patterns, list)
    assert len(patterns) > 0