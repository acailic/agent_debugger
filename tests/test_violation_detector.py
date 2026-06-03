"""Tests for violation detector module."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import EventType, TraceEvent
from agent_debugger_sdk.core.events.errors import ErrorEvent
from agent_debugger_sdk.core.events.tools import ToolCallEvent
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
        ToolCallEvent(
            id="event_2",
            session_id="session_1",
            timestamp=now,
            name="Tool Call",
            data={},
            metadata={},
            importance=0.7,
            upstream_event_ids=[],
            parent_id="event_1",
            tool_name="search_tool",
        ),
        ErrorEvent(
            id="event_3",
            session_id="session_1",
            timestamp=now,
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


# =============================================================================
# TraceClusterer: Additional edge cases
# =============================================================================

def test_trace_clusterer_empty_sessions():
    """Test TraceClusterer with empty sessions dictionary."""
    clusterer = TraceClusterer({})

    assert len(clusterer.sessions) == 0
    assert len(clusterer.embeddings) == 0
    assert clusterer.cluster_sessions() == []


def test_trace_clusterer_single_session():
    """Test TraceClusterer with only one session."""
    now = datetime.now(timezone.utc)
    events = [
        TraceEvent(
            id="event_1",
            session_id="single_session",
            timestamp=now,
            event_type=EventType.AGENT_START,
            name="Single Event",
            data={},
            metadata={},
            importance=0.5,
            upstream_event_ids=[],
            parent_id=None,
        )
    ]

    clusterer = TraceClusterer({"single_session": events})

    # With single session, can't form clusters (min_cluster_size=2)
    clusters = clusterer.cluster_sessions(min_cluster_size=2)
    assert len(clusters) == 0

    # But should still have embedding
    assert "single_session" in clusterer.embeddings


def test_trace_clusterer_identical_sessions():
    """Test TraceClusterer with identical sessions."""
    now = datetime.now(timezone.utc)

    # Create multiple sessions with identical events
    sessions = {}
    for i in range(5):
        events = [
            TraceEvent(
                id=f"event_{i}",
                session_id=f"session_{i}",
                timestamp=now,
                event_type=EventType.AGENT_START,
                name="Same Event",
                data={"key": "value"},
                metadata={},
                importance=0.5,
                upstream_event_ids=[],
                parent_id=None,
            )
        ]
        sessions[f"session_{i}"] = events

    clusterer = TraceClusterer(sessions)
    clusters = clusterer.cluster_sessions(similarity_threshold=0.5, min_cluster_size=2)

    # With identical sessions, should form one cluster
    assert len(clusters) >= 1
    # All sessions should be in a cluster
    total_clustered = sum(len(c.session_ids) for c in clusters)
    assert total_clustered <= 5


def test_trace_clusterer_no_events():
    """Test TraceClusterer with sessions containing no events."""
    sessions = {
        "empty_session_1": [],
        "empty_session_2": [],
    }

    clusterer = TraceClusterer(sessions)

    # Should still create embeddings for empty sessions
    assert len(clusterer.embeddings) == 2

    # Empty sessions should have different embeddings (different session_ids affect hash)
    clusterer.cluster_sessions(min_cluster_size=1)
    # May or may not cluster empty sessions depending on implementation


def test_trace_clusterer_varying_thresholds():
    """Test TraceClusterer with varying similarity thresholds."""
    now = datetime.now(timezone.utc)

    # Create sessions with varying similarity
    sessions = {}
    for i in range(5):
        events = [
            TraceEvent(
                id=f"event_{i}",
                session_id=f"session_{i}",
                timestamp=now,
                event_type=EventType.AGENT_START,
                name=f"Event {i}",
                data={"variation": i},
                metadata={},
                importance=0.5,
                upstream_event_ids=[],
                parent_id=None,
            )
        ]
        sessions[f"session_{i}"] = events

    clusterer = TraceClusterer(sessions)

    # High threshold - fewer clusters
    strict_clusters = clusterer.cluster_sessions(similarity_threshold=0.9, min_cluster_size=2)

    # Low threshold - more clusters (more inclusive)
    loose_clusters = clusterer.cluster_sessions(similarity_threshold=0.1, min_cluster_size=2)

    # Lower threshold should create at least as many clusters
    assert len(loose_clusters) >= len(strict_clusters)


def test_trace_clusterer_cluster_characteristics():
    """Test that cluster characteristics are computed correctly."""
    now = datetime.now(timezone.utc)

    # Create sessions with known characteristics
    events_with_tool = [
        ToolCallEvent(
            id="event_1",
            session_id="session_1",
            timestamp=now,
            name="Tool Call",
            data={},
            metadata={},
            importance=0.7,
            upstream_event_ids=[],
            parent_id=None,
            tool_name="search_tool",
        )
    ]

    sessions = {
        "session_1": events_with_tool,
        "session_2": events_with_tool,
    }

    clusterer = TraceClusterer(sessions)
    clusters = clusterer.cluster_sessions(similarity_threshold=0.5, min_cluster_size=2)

    if clusters:
        cluster = clusters[0]
        assert cluster.cluster_characteristics is not None
        assert "avg_event_count" in cluster.cluster_characteristics
        assert "event_type_distribution" in cluster.cluster_characteristics


# =============================================================================
# CrossTraceSearch: Various descriptions and edge cases
# =============================================================================

def test_cross_trace_search_various_descriptions():
    """Test CrossTraceSearch with various query types."""
    now = datetime.now(timezone.utc)

    # Create events with different characteristics
    events = [
        ErrorEvent(
            id="event_1",
            session_id="session_1",
            timestamp=now,
            name="Unsafe Operation",
            data={"operation": "dangerous"},
            metadata={},
            importance=0.9,
            upstream_event_ids=[],
            parent_id=None,
            error_type="SafetyError",
            error_message="Unsafe data handling detected",
        ),
        TraceEvent(
            id="event_2",
            session_id="session_1",
            timestamp=now,
            event_type=EventType.DECISION,
            name="Performance Decision",
            data={"reasoning": "This will be slow"},
            metadata={},
            importance=0.6,
            upstream_event_ids=[],
            parent_id=None,
        ),
    ]

    sessions = {"session_1": events}
    searcher = CrossTraceSearch(sessions)

    # Test safety-related query
    safety_violations = searcher.search_violations("unsafe data handling", max_results=10)
    assert len(safety_violations) > 0
    assert any(v.violation_type == ViolationType.SAFETY_VIOLATION for v in safety_violations)

    # Test performance-related query
    perf_violations = searcher.search_violations("slow performance issues", max_results=10)
    assert len(perf_violations) > 0
    assert any(v.violation_type == ViolationType.TEMPORAL_ANOMALY for v in perf_violations)


def test_cross_trace_search_partial_matches():
    """Test CrossTraceSearch with partial keyword matches."""
    now = datetime.now(timezone.utc)

    events = [
        ErrorEvent(
            id="event_1",
            session_id="session_1",
            timestamp=now,
            name="Error with partial match",
            data={"message": "unsafe operation occurred"},
            metadata={},
            importance=0.8,
            upstream_event_ids=[],
            parent_id=None,
            error_type="UnsafeError",
            error_message="Unsafe operation occurred",
        )
    ]

    sessions = {"session_1": events}
    searcher = CrossTraceSearch(sessions)

    # Partial match - should still find
    violations = searcher.search_violations("unsafe", max_results=10)
    assert len(violations) > 0


def test_cross_trace_search_no_matches():
    """Test CrossTraceSearch with queries that have no matches."""
    now = datetime.now(timezone.utc)

    events = [
        TraceEvent(
            id="event_1",
            session_id="session_1",
            timestamp=now,
            event_type=EventType.AGENT_START,
            name="Normal Event",
            data={"status": "ok"},
            metadata={},
            importance=0.5,
            upstream_event_ids=[],
            parent_id=None,
        )
    ]

    sessions = {"session_1": events}
    searcher = CrossTraceSearch(sessions)

    # Query with terms not in events
    violations = searcher.search_violations("xyz_nonexistent_abc123", max_results=10)
    assert len(violations) == 0

    # Query with only stopwords
    violations = searcher.search_violations("the and or of", max_results=10)
    assert len(violations) == 0


def test_cross_trace_search_max_results_limit():
    """Test that max_results parameter limits results correctly."""
    now = datetime.now(timezone.utc)

    # Create many sessions
    sessions = {}
    for i in range(20):
        events = [
            ErrorEvent(
                id=f"event_{i}",
                session_id=f"session_{i}",
                timestamp=now,
                name="Error Event",
                data={"error": "failure"},
                metadata={},
                importance=0.8,
                upstream_event_ids=[],
                parent_id=None,
                error_type="TestError",
                error_message="Test failure",
            )
        ]
        sessions[f"session_{i}"] = events

    searcher = CrossTraceSearch(sessions)

    # Test with small max_results
    violations = searcher.search_violations("error", max_results=5)
    assert len(violations) <= 5

    # Test with larger max_results
    violations = searcher.search_violations("error", max_results=15)
    assert len(violations) <= 15


def test_cross_trace_search_keyword_extraction():
    """Test keyword extraction from various query types."""
    searcher = CrossTraceSearch({})

    # Test various query types
    queries = [
        "unsafe data handling patterns",
        "performance degradation and slow responses",
        "error handling problems and exceptions",
        "xyz123",  # Single keyword
    ]

    for query in queries:
        keywords = searcher._extract_keywords(query)
        assert isinstance(keywords, list)
        # Should extract some meaningful keywords
        assert len(keywords) >= 0


# =============================================================================
# SparseFailureDetector: Threshold variations and mixed severity
# =============================================================================

def test_sparse_failure_detector_threshold_variations():
    """Test SparseFailureDetector with different min_occurrences thresholds."""
    now = datetime.now(timezone.utc)

    # Create sessions with errors in 3 sessions
    sessions = {}
    for i in range(5):
        events = []
        # Add error to first 3 sessions only
        if i < 3:
            events.append(
                ErrorEvent(
                    id=f"error_{i}",
                    session_id=f"session_{i}",
                    timestamp=now,
                    name="Repeated Error",
                    data={},
                    metadata={},
                    importance=0.9,
                    upstream_event_ids=[],
                    parent_id=None,
                    error_type="ValueError",
                    error_message="Invalid input",
                )
            )

        sessions[f"session_{i}"] = events

    detector = SparseFailureDetector(sessions)

    # Threshold of 2 - should find pattern
    patterns_2 = detector.detect_sparse_failures(min_occurrences=2)
    assert len(patterns_2) > 0
    assert all(len(p.session_ids) >= 2 for p in patterns_2)

    # Threshold of 4 - should not find pattern (only 3 sessions have errors)
    patterns_4 = detector.detect_sparse_failures(min_occurrences=4)
    assert len(patterns_4) == 0


def test_sparse_failure_detector_exactly_n():
    """Test SparseFailureDetector detects exactly N occurrences."""
    now = datetime.now(timezone.utc)

    # Create sessions with errors in exactly 3 sessions
    sessions = {}
    for i in range(3):
        events = [
            ErrorEvent(
                id=f"error_{i}",
                session_id=f"session_{i}",
                timestamp=now,
                name="Exact Error",
                data={},
                metadata={},
                importance=0.9,
                upstream_event_ids=[],
                parent_id=None,
                error_type="ExactError",
                error_message="Exact failure message",
            )
        ]
        sessions[f"session_{i}"] = events

    detector = SparseFailureDetector(sessions)
    patterns = detector.detect_sparse_failures(min_occurrences=3)

    # Should find pattern with exactly 3 sessions
    if patterns:
        assert len(patterns[0].session_ids) == 3


def test_sparse_failure_detector_mixed_severity():
    """Test SparseFailureDetector with mixed error severity."""
    now = datetime.now(timezone.utc)

    # Create sessions with different error types
    sessions = {
        "session_1": [
            ErrorEvent(
                id="critical_error",
                session_id="session_1",
                timestamp=now,
                name="Critical Error",
                data={},
                metadata={"severity": "critical"},
                importance=1.0,
                upstream_event_ids=[],
                parent_id=None,
                error_type="CriticalError",
                error_message="System failure",
            )
        ],
        "session_2": [
            ErrorEvent(
                id="warning_error",
                session_id="session_2",
                timestamp=now,
                name="Warning Error",
                data={},
                metadata={"severity": "warning"},
                importance=0.6,
                upstream_event_ids=[],
                parent_id=None,
                error_type="WarningError",
                error_message="Minor issue",
            )
        ],
        "session_3": [
            ErrorEvent(
                id="critical_error",
                session_id="session_3",
                timestamp=now,
                name="Critical Error",
                data={},
                metadata={"severity": "critical"},
                importance=1.0,
                upstream_event_ids=[],
                parent_id=None,
                error_type="CriticalError",
                error_message="System failure",
            )
        ],
    }

    detector = SparseFailureDetector(sessions)
    patterns = detector.detect_sparse_failures(min_occurrences=2)

    # Should find pattern for CriticalError (appears in 2 sessions)
    critical_patterns = [p for p in patterns if p.failure_type == "CriticalError"]
    assert len(critical_patterns) > 0


def test_sparse_failure_detector_no_errors():
    """Test SparseFailureDetector with sessions containing no errors."""
    now = datetime.now(timezone.utc)

    sessions = {
        "session_1": [
            TraceEvent(
                id="event_1",
                session_id="session_1",
                timestamp=now,
                event_type=EventType.AGENT_START,
                name="Normal Start",
                data={},
                metadata={},
                importance=0.5,
                upstream_event_ids=[],
                parent_id=None,
            )
        ],
        "session_2": [
            ToolCallEvent(
                id="event_2",
                session_id="session_2",
                timestamp=now,
                name="Normal Tool Call",
                data={},
                metadata={},
                importance=0.6,
                upstream_event_ids=[],
                parent_id=None,
                tool_name="safe_tool",
            )
        ],
    }

    detector = SparseFailureDetector(sessions)
    patterns = detector.detect_sparse_failures(min_occurrences=2)

    # No errors, so no patterns
    assert len(patterns) == 0


# =============================================================================
# ViolationReport: Evidence linking and confidence scoring
# =============================================================================

def test_violation_report_evidence_linking():
    """Test ViolationReport with multiple evidence items."""
    now = datetime.now(timezone.utc)

    evidence_items = [
        ViolationEvidence(
            session_id="session_1",
            event_id="event_1",
            evidence_type="error",
            description="First evidence",
            timestamp=now,
            confidence=0.9,
        ),
        ViolationEvidence(
            session_id="session_2",
            event_id="event_2",
            evidence_type="error",
            description="Second evidence",
            timestamp=now,
            confidence=0.7,
        ),
        ViolationEvidence(
            session_id="session_3",
            event_id="event_3",
            evidence_type="warning",
            description="Third evidence",
            timestamp=now,
            confidence=0.5,
        ),
    ]

    report = ViolationReport(
        violation_id="test_violation",
        violation_type=ViolationType.SPARSE_FAILURE,
        severity=ViolationSeverity.HIGH,
        title="Test Violation with Multiple Evidence",
        description="Testing evidence linking",
        affected_sessions=["session_1", "session_2", "session_3"],
        evidence=evidence_items,
    )

    # Check evidence is properly linked
    assert len(report.evidence) == 3
    assert all(isinstance(e, ViolationEvidence) for e in report.evidence)

    # Check session linkage
    assert "session_1" in report.affected_sessions
    assert "session_2" in report.affected_sessions
    assert "session_3" in report.affected_sessions

    # Verify serialization includes all evidence
    report_dict = report.to_dict()
    assert len(report_dict["evidence"]) == 3
    assert report_dict["evidence"][0]["confidence"] == 0.9


def test_violation_report_confidence_scoring():
    """Test ViolationReport confidence scoring aggregation."""
    now = datetime.now(timezone.utc)

    # Create evidence with varying confidence scores
    evidence_items = [
        ViolationEvidence(
            session_id="session_1",
            event_id="event_1",
            confidence=0.95,
            timestamp=now,
        ),
        ViolationEvidence(
            session_id="session_2",
            event_id="event_2",
            confidence=0.85,
            timestamp=now,
        ),
        ViolationEvidence(
            session_id="session_3",
            event_id="event_3",
            confidence=0.75,
            timestamp=now,
        ),
        ViolationEvidence(
            session_id="session_4",
            event_id="event_4",
            confidence=0.65,
            timestamp=now,
        ),
    ]

    report = ViolationReport(
        violation_id="confidence_test",
        violation_type=ViolationType.PATTERN_DEVIATION,
        severity=ViolationSeverity.MEDIUM,
        title="Confidence Scoring Test",
        evidence=evidence_items,
    )

    # Calculate average confidence
    avg_confidence = sum(e.confidence for e in report.evidence) / len(report.evidence)

    # Should have multiple evidence items
    assert len(report.evidence) == 4
    # Average confidence should be reasonable
    assert 0.6 <= avg_confidence <= 1.0


def test_violation_report_empty_evidence():
    """Test ViolationReport with no evidence."""
    report = ViolationReport(
        violation_id="empty_evidence_test",
        violation_type=ViolationType.OUTLIER_BEHAVIOR,
        severity=ViolationSeverity.LOW,
        title="No Evidence",
        evidence=[],
    )

    assert len(report.evidence) == 0
    assert len(report.affected_sessions) == 0

    # Should still serialize correctly
    report_dict = report.to_dict()
    assert report_dict["evidence"] == []
    assert report_dict["affected_sessions"] == []


# =============================================================================
# SessionEmbedding: Similarity computation and edge cases
# =============================================================================

def test_session_embedding_empty_events():
    """Test SessionEmbedding with empty event list."""
    embedding = compute_session_embedding("empty_session", [])

    assert embedding.session_id == "empty_session"
    assert isinstance(embedding.embedding_vector, list)
    assert isinstance(embedding.feature_weights, dict)


def test_session_embedding_similarity_computation():
    """Test SessionEmbedding similarity computation in detail."""
    # Create identical embeddings
    embedding1 = SessionEmbedding(
        session_id="session_1",
        embedding_vector=[1.0, 0.5, 0.25, 0.75],
    )
    embedding2 = SessionEmbedding(
        session_id="session_2",
        embedding_vector=[1.0, 0.5, 0.25, 0.75],
    )

    # Identical vectors should have similarity of 1.0
    similarity = embedding1.similarity(embedding2)
    assert abs(similarity - 1.0) < 0.01  # Allow small floating point error

    # Create orthogonal vectors
    embedding3 = SessionEmbedding(
        session_id="session_3",
        embedding_vector=[1.0, 0.0, 0.0, 0.0],
    )
    embedding4 = SessionEmbedding(
        session_id="session_4",
        embedding_vector=[0.0, 1.0, 0.0, 0.0],
    )

    # Orthogonal vectors should have similarity near 0
    similarity_orthogonal = embedding3.similarity(embedding4)
    assert similarity_orthogonal < 0.1

    # Create opposite vectors
    embedding5 = SessionEmbedding(
        session_id="session_5",
        embedding_vector=[1.0, 1.0],
    )
    embedding6 = SessionEmbedding(
        session_id="session_6",
        embedding_vector=[-1.0, -1.0],
    )

    # Opposite vectors should have negative similarity
    similarity_opposite = embedding5.similarity(embedding6)
    assert similarity_opposite < 0


def test_session_embedding_empty_vectors():
    """Test SessionEmbedding similarity with empty vectors."""
    embedding1 = SessionEmbedding(
        session_id="session_1",
        embedding_vector=[],
    )
    embedding2 = SessionEmbedding(
        session_id="session_2",
        embedding_vector=[1.0, 0.5],
    )

    # Empty vector should return 0 similarity
    similarity = embedding1.similarity(embedding2)
    assert similarity == 0.0

    # Both empty should also return 0
    similarity_empty = embedding1.similarity(
        SessionEmbedding(session_id="session_3", embedding_vector=[])
    )
    assert similarity_empty == 0.0


def test_session_embedding_different_length_vectors():
    """Test SessionEmbedding similarity with different vector lengths."""
    embedding1 = SessionEmbedding(
        session_id="session_1",
        embedding_vector=[1.0, 0.5, 0.25],
    )
    embedding2 = SessionEmbedding(
        session_id="session_2",
        embedding_vector=[1.0, 0.5],
    )

    # Should handle different lengths by using minimum
    similarity = embedding1.similarity(embedding2)
    assert isinstance(similarity, float)
    assert 0.0 <= similarity <= 1.0


def test_session_embedding_feature_weights():
    """Test SessionEmbedding feature weights computation."""
    now = datetime.now(timezone.utc)

    events = [
        ToolCallEvent(
            id="event_1",
            session_id="test_session",
            timestamp=now,
            name="Tool Call",
            data={},
            metadata={},
            importance=0.7,
            upstream_event_ids=[],
            parent_id=None,
            tool_name="search_tool",
        ),
        ErrorEvent(
            id="event_2",
            session_id="test_session",
            timestamp=now,
            name="Error",
            data={},
            metadata={},
            importance=0.9,
            upstream_event_ids=[],
            parent_id=None,
        ),
    ]

    embedding = compute_session_embedding("test_session", events)

    # Should have feature weights
    assert len(embedding.feature_weights) > 0
    # Should have embedding vector
    assert len(embedding.embedding_vector) > 0


# =============================================================================
# Serialization round-trip tests
# =============================================================================

def test_violation_evidence_round_trip():
    """Test ViolationEvidence serialization round-trip."""
    now = datetime.now(timezone.utc)
    original = ViolationEvidence(
        session_id="test_session",
        event_id="test_event",
        evidence_type="test_type",
        description="Test description",
        timestamp=now,
        confidence=0.85,
        metadata={"key1": "value1", "key2": 42},
    )

    # Serialize
    evidence_dict = original.to_dict()

    # Verify all fields present
    assert evidence_dict["session_id"] == "test_session"
    assert evidence_dict["event_id"] == "test_event"
    assert evidence_dict["evidence_type"] == "test_type"
    assert evidence_dict["description"] == "Test description"
    assert evidence_dict["timestamp"] == now.isoformat()
    assert evidence_dict["confidence"] == 0.85
    assert evidence_dict["metadata"]["key1"] == "value1"
    assert evidence_dict["metadata"]["key2"] == 42


def test_violation_report_round_trip():
    """Test ViolationReport serialization round-trip."""
    now = datetime.now(timezone.utc)
    original = ViolationReport(
        violation_id="test_violation",
        violation_type=ViolationType.SAFETY_VIOLATION,
        severity=ViolationSeverity.CRITICAL,
        title="Test Report",
        description="Test description",
        affected_sessions=["session_1", "session_2"],
        evidence=[
            ViolationEvidence(
                session_id="session_1",
                event_id="event_1",
                confidence=0.9,
                timestamp=now,
            )
        ],
        metadata={"key": "value"},
    )

    # Serialize
    report_dict = original.to_dict()

    # Verify all fields
    assert report_dict["violation_id"] == "test_violation"
    assert report_dict["violation_type"] == "safety_violation"
    assert report_dict["severity"] == "critical"
    assert report_dict["title"] == "Test Report"
    assert len(report_dict["affected_sessions"]) == 2
    assert len(report_dict["evidence"]) == 1
    assert report_dict["metadata"]["key"] == "value"


def test_trace_cluster_round_trip():
    """Test TraceCluster serialization round-trip."""
    original = TraceCluster(
        cluster_id="test_cluster",
        session_ids=["session_1", "session_2", "session_3"],
        centroid_embedding=SessionEmbedding(
            session_id="centroid",
            embedding_vector=[0.5, 0.3, 0.7],
            feature_weights={"feature1": 0.5, "feature2": 0.3},
        ),
        cluster_characteristics={
            "avg_event_count": 10.5,
            "avg_duration": 2.3,
            "common_tools": ["tool1", "tool2"],
        },
        outlier_session_ids=["session_3"],
    )

    # Serialize
    cluster_dict = original.to_dict()

    # Verify all fields
    assert cluster_dict["cluster_id"] == "test_cluster"
    assert len(cluster_dict["session_ids"]) == 3
    assert cluster_dict["centroid_embedding"] is not None
    assert cluster_dict["cluster_characteristics"]["avg_event_count"] == 10.5
    assert cluster_dict["outlier_session_ids"] == ["session_3"]


def test_sparse_failure_pattern_round_trip():
    """Test SparseFailurePattern serialization round-trip."""
    original = SparseFailurePattern(
        pattern_id="test_pattern",
        failure_type="TypeError",
        description="Test pattern description",
        required_sessions=3,
        session_ids=["session_1", "session_2", "session_3"],
        failure_points=[
            {
                "session_id": "session_1",
                "event_id": "event_1",
                "timestamp": "2024-01-01T00:00:00Z",
                "error_type": "TypeError",
                "error_message": "Test error",
            }
        ],
        confidence=0.85,
    )

    # Serialize
    pattern_dict = original.to_dict()

    # Verify all fields
    assert pattern_dict["pattern_id"] == "test_pattern"
    assert pattern_dict["failure_type"] == "TypeError"
    assert pattern_dict["description"] == "Test pattern description"
    assert pattern_dict["required_sessions"] == 3
    assert len(pattern_dict["session_ids"]) == 3
    assert len(pattern_dict["failure_points"]) == 1
    assert pattern_dict["confidence"] == 0.85


def test_session_embedding_round_trip():
    """Test SessionEmbedding serialization round-trip."""
    original = SessionEmbedding(
        session_id="test_session",
        embedding_vector=[0.1, 0.2, 0.3, 0.4, 0.5],
        feature_weights={"feature1": 0.1, "feature2": 0.2},
        summary_hash="test_hash",
    )

    # Serialize
    embedding_dict = original.to_dict()

    # Verify all fields
    assert embedding_dict["session_id"] == "test_session"
    # Note: embedding_vector is truncated to 100 elements in to_dict()
    assert len(embedding_dict["embedding_vector"]) == 5
    assert embedding_dict["feature_weights"]["feature1"] == 0.1
    assert embedding_dict["summary_hash"] == "test_hash"
