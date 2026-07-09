"""Cross-trace violation detection for identifying patterns across multiple sessions.

Based on Meerkat design for cross-trace analysis, this module provides tools for
detecting violations that only become visible when analyzing multiple agent sessions
together. It identifies outlier behaviors, sparse failures, and patterns that span
across execution traces.

Key capabilities:
- Cluster similar agent sessions and identify outliers
- Search for NL violation description patterns across sessions
- Detect sparse failures visible only in N+ trace comparisons
- Generate violation reports with multi-trace evidence
- Lightweight session embeddings for similarity comparison
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agent_debugger_sdk.core._compat import StrEnum
from agent_debugger_sdk.core.events import EventType, TraceEvent

__all__ = [
    "ViolationType",
    "ViolationSeverity",
    "ViolationEvidence",
    "ViolationReport",
    "TraceCluster",
    "SessionEmbedding",
    "SparseFailurePattern",
    "TraceClusterer",
    "CrossTraceSearch",
    "SparseFailureDetector",
    "cluster_sessions",
    "search_violations_across_traces",
    "detect_sparse_failures",
    "compute_session_embedding",
]


class ViolationType(StrEnum):
    """Types of cross-trace violations."""

    OUTLIER_BEHAVIOR = "outlier_behavior"  # Session behaves differently from cluster
    SPARSE_FAILURE = "sparse_failure"  # Failure only visible across N+ traces
    PATTERN_DEVIATION = "pattern_deviation"  # Deviates from established patterns
    TEMPORAL_ANOMALY = "temporal_anomaly"  # Unusual timing patterns
    RESOURCE_ANOMALY = "resource_anomaly"  # Unusual resource usage
    SAFETY_VIOLATION = "safety_violation"  # Cross-trace safety concerns


class ViolationSeverity(StrEnum):
    """Severity levels for detected violations."""

    CRITICAL = "critical"  # Requires immediate attention
    HIGH = "high"  # Significant concern
    MEDIUM = "medium"  # Moderate concern
    LOW = "low"  # Minor concern


@dataclass(kw_only=True)
class ViolationEvidence:
    """Evidence supporting a violation from multiple traces."""

    session_id: str
    event_id: str | None = None
    evidence_type: str = ""
    description: str = ""
    timestamp: datetime | None = None
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "session_id": self.session_id,
            "event_id": self.event_id,
            "evidence_type": self.evidence_type,
            "description": self.description,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
        }


@dataclass(kw_only=True)
class ViolationReport:
    """A detected violation with supporting evidence from multiple traces."""

    violation_id: str
    violation_type: ViolationType
    severity: ViolationSeverity
    title: str = ""
    description: str = ""
    affected_sessions: list[str] = field(default_factory=list)
    evidence: list[ViolationEvidence] = field(default_factory=list)
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "violation_id": self.violation_id,
            "violation_type": str(self.violation_type),
            "severity": str(self.severity),
            "title": self.title,
            "description": self.description,
            "affected_sessions": self.affected_sessions,
            "evidence": [e.to_dict() for e in self.evidence],
            "detected_at": self.detected_at.isoformat(),
            "metadata": dict(self.metadata),
        }


@dataclass(kw_only=True)
class SessionEmbedding:
    """Lightweight text embedding for session similarity."""

    session_id: str
    embedding_vector: list[float] = field(default_factory=list)
    feature_weights: dict[str, float] = field(default_factory=dict)
    summary_hash: str = ""

    def similarity(self, other: SessionEmbedding) -> float:
        """Calculate cosine similarity with another embedding."""
        if not self.embedding_vector or not other.embedding_vector:
            return 0.0

        # Ensure vectors are same length
        min_len = min(len(self.embedding_vector), len(other.embedding_vector))
        v1 = self.embedding_vector[:min_len]
        v2 = other.embedding_vector[:min_len]

        # Cosine similarity
        dot_product = sum(a * b for a, b in zip(v1, v2))
        magnitude1 = math.sqrt(sum(a * a for a in v1))
        magnitude2 = math.sqrt(sum(b * b for b in v2))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "session_id": self.session_id,
            "embedding_vector": self.embedding_vector[:100],  # Truncate for response
            "feature_weights": self.feature_weights,
            "summary_hash": self.summary_hash,
        }


@dataclass(kw_only=True)
class TraceCluster:
    """A cluster of similar agent sessions."""

    cluster_id: str
    session_ids: list[str] = field(default_factory=list)
    centroid_embedding: SessionEmbedding | None = None
    cluster_characteristics: dict[str, Any] = field(default_factory=dict)
    outlier_session_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "cluster_id": self.cluster_id,
            "session_ids": self.session_ids,
            "centroid_embedding": self.centroid_embedding.to_dict() if self.centroid_embedding else None,
            "cluster_characteristics": dict(self.cluster_characteristics),
            "outlier_session_ids": self.outlier_session_ids,
        }


@dataclass(kw_only=True)
class SparseFailurePattern:
    """A failure pattern only visible across multiple traces."""

    pattern_id: str
    failure_type: str
    description: str = ""
    required_sessions: int = 2  # Minimum sessions needed to detect
    session_ids: list[str] = field(default_factory=list)
    failure_points: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "pattern_id": self.pattern_id,
            "failure_type": self.failure_type,
            "description": self.description,
            "required_sessions": self.required_sessions,
            "session_ids": self.session_ids,
            "failure_points": self.failure_points,
            "confidence": self.confidence,
        }


class TraceClusterer:
    """Cluster similar agent sessions and identify outliers."""

    def __init__(self, sessions: dict[str, list[TraceEvent]]) -> None:
        """Initialize the clusterer with session data.

        Args:
            sessions: Dictionary mapping session IDs to their event traces
        """
        self.sessions = sessions
        self.embeddings: dict[str, SessionEmbedding] = {}
        self.clusters: list[TraceCluster] = []
        self._compute_embeddings()

    def _compute_embeddings(self) -> None:
        """Compute embeddings for all sessions."""
        for session_id, events in self.sessions.items():
            self.embeddings[session_id] = compute_session_embedding(session_id, events)

    def cluster_sessions(
        self,
        similarity_threshold: float = 0.7,
        min_cluster_size: int = 2,
    ) -> list[TraceCluster]:
        """Cluster sessions based on similarity.

        Args:
            similarity_threshold: Minimum similarity to be in same cluster
            min_cluster_size: Minimum sessions to form a valid cluster

        Returns:
            List of trace clusters
        """
        # Simple clustering based on similarity threshold
        visited: set[str] = set()
        clusters: list[TraceCluster] = []

        for session_id in self.sessions:
            if session_id in visited:
                continue

            # Find similar sessions
            similar_sessions = [session_id]
            for other_id in self.sessions:
                if other_id == session_id or other_id in visited:
                    continue

                similarity = self.embeddings[session_id].similarity(self.embeddings[other_id])
                if similarity >= similarity_threshold:
                    similar_sessions.append(other_id)

            # Create cluster if enough sessions
            if len(similar_sessions) >= min_cluster_size:
                cluster_id = f"cluster_{len(clusters)}"
                centroid = self._compute_centroid(similar_sessions)

                cluster = TraceCluster(
                    cluster_id=cluster_id,
                    session_ids=similar_sessions,
                    centroid_embedding=centroid,
                    cluster_characteristics=self._analyze_cluster_characteristics(similar_sessions),
                )

                # Identify outliers within cluster
                cluster.outlier_session_ids = self._find_outliers(cluster)

                clusters.append(cluster)
                visited.update(similar_sessions)

        self.clusters = clusters
        return clusters

    def identify_global_outliers(self, z_threshold: float = 2.0) -> list[str]:
        """Identify sessions that are outliers globally.

        Args:
            z_threshold: Number of standard deviations for outlier detection

        Returns:
            List of outlier session IDs
        """
        if len(self.sessions) < 3:
            return []

        # Compute average similarity for each session to all others
        similarities: dict[str, list[float]] = {}
        for session_id in self.sessions:
            sims: list[float] = []
            for other_id in self.sessions:
                if session_id != other_id:
                    sims.append(self.embeddings[session_id].similarity(self.embeddings[other_id]))
            similarities[session_id] = sims

        # Find outliers using z-score
        avg_similarities = {
            sid: (sum(sims) / len(sims) if sims else 0.0)
            for sid, sims in similarities.items()
        }

        mean = sum(avg_similarities.values()) / len(avg_similarities)
        std = math.sqrt(sum((x - mean) ** 2 for x in avg_similarities.values()) / len(avg_similarities))

        outliers: list[str] = []
        for sid, avg_sim in avg_similarities.items():
            if std > 0:
                z_score = (avg_sim - mean) / std
                if z_score < -z_threshold:  # Low similarity outlier
                    outliers.append(sid)

        return outliers

    def _compute_centroid(self, session_ids: list[str]) -> SessionEmbedding:
        """Compute centroid embedding for a cluster."""
        if not session_ids:
            return SessionEmbedding(session_id="")

        embeddings = [self.embeddings[sid] for sid in session_ids if sid in self.embeddings]
        if not embeddings:
            return SessionEmbedding(session_id="")

        # Average the embedding vectors
        max_len = max(len(e.embedding_vector) for e in embeddings)
        centroid_vector: list[float] = []

        for i in range(max_len):
            values = [e.embedding_vector[i] for e in embeddings if i < len(e.embedding_vector)]
            if values:
                centroid_vector.append(sum(values) / len(values))

        return SessionEmbedding(
            session_id=f"centroid_{len(session_ids)}_sessions",
            embedding_vector=centroid_vector,
        )

    def _analyze_cluster_characteristics(self, session_ids: list[str]) -> dict[str, Any]:
        """Analyze common characteristics of sessions in a cluster."""
        characteristics: dict[str, Any] = {
            "event_type_distribution": {},
            "avg_event_count": 0.0,
            "avg_duration": 0.0,
            "common_tools": [],
        }

        event_counts: list[int] = []
        durations: list[float] = []
        all_tools: list[str] = []
        event_type_counts: dict[str, int] = {}

        for sid in session_ids:
            if sid not in self.sessions:
                continue

            events = self.sessions[sid]
            event_counts.append(len(events))

            # Duration
            if events:
                timestamps = [e.timestamp for e in events if e.timestamp]
                if timestamps:
                    duration = (max(timestamps) - min(timestamps)).total_seconds()
                    durations.append(duration)

            # Event types
            for event in events:
                etype = str(event.event_type)
                event_type_counts[etype] = event_type_counts.get(etype, 0) + 1

                # Tool names
                if event.event_type == EventType.TOOL_CALL:
                    tool_name = getattr(event, "tool_name", None)
                    if tool_name:
                        all_tools.append(tool_name)

        if event_counts:
            characteristics["avg_event_count"] = sum(event_counts) / len(event_counts)

        if durations:
            characteristics["avg_duration"] = sum(durations) / len(durations)

        if event_type_counts:
            total = sum(event_type_counts.values())
            characteristics["event_type_distribution"] = {
                etype: count / total for etype, count in event_type_counts.items()
            }

        # Most common tools
        if all_tools:
            tool_counter = Counter(all_tools)
            characteristics["common_tools"] = [tool for tool, _ in tool_counter.most_common(5)]

        return characteristics

    def _find_outliers(self, cluster: TraceCluster) -> list[str]:
        """Find outlier sessions within a cluster."""
        if not cluster.centroid_embedding or len(cluster.session_ids) < 3:
            return []

        similarities: list[tuple[str, float]] = []
        for sid in cluster.session_ids:
            if sid in self.embeddings:
                sim = self.embeddings[sid].similarity(cluster.centroid_embedding)
                similarities.append((sid, sim))

        if not similarities:
            return []

        # Find sessions with low similarity to centroid (below median)
        median_sim = sorted(sim for _, sim in similarities)[len(similarities) // 2]
        outliers = [sid for sid, sim in similarities if sim < median_sim * 0.8]

        return outliers


class CrossTraceSearch:
    """Search for NL violation description patterns across sessions."""

    def __init__(self, sessions: dict[str, list[TraceEvent]]) -> None:
        """Initialize the searcher with session data.

        Args:
            sessions: Dictionary mapping session IDs to their event traces
        """
        self.sessions = sessions

    def search_violations(
        self,
        nl_query: str,
        max_results: int = 50,
    ) -> list[ViolationReport]:
        """Search for violations matching NL description across sessions.

        Args:
            nl_query: Natural language description of violation to search for
            max_results: Maximum number of violation reports to return

        Returns:
            List of violation reports with evidence
        """
        # Parse query into keywords
        keywords = self._extract_keywords(nl_query)
        if not keywords:
            return []

        reports: list[ViolationReport] = []
        report_id = 0

        # Search for patterns across sessions
        for session_id, events in self.sessions.items():
            matching_events = self._find_matching_events(events, keywords)

            if matching_events:
                report = ViolationReport(
                    violation_id=f"violation_{report_id}",
                    violation_type=self._classify_violation_type(nl_query),
                    severity=self._estimate_severity(matching_events),
                    title=f"Violation matching: {nl_query[:50]}...",
                    description=f"Found {len(matching_events)} events matching the violation pattern",
                    affected_sessions=[session_id],
                    evidence=[
                        ViolationEvidence(
                            session_id=session_id,
                            event_id=event.id,
                            evidence_type=str(event.event_type),
                            description=self._extract_event_description(event),
                            timestamp=event.timestamp,
                            confidence=self._compute_match_confidence(event, keywords),
                        )
                        for event in matching_events[:10]  # Limit evidence
                    ],
                    metadata={"query": nl_query, "matched_keywords": keywords},
                )
                reports.append(report)
                report_id += 1

                if len(reports) >= max_results:
                    break

        return reports

    def _extract_keywords(self, query: str) -> list[str]:
        """Extract meaningful keywords from NL query."""
        # Remove common stopwords and extract meaningful terms
        stopwords = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
            "been", "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "must", "can", "this",
            "that", "these", "those", "what", "which", "who", "when", "where",
            "why", "how", "find", "search", "look", "detect", "identify", "show",
        }

        # Split into words and filter
        words = re.findall(r"\b\w+\b", query.lower())
        keywords = [w for w in words if w not in stopwords and len(w) > 2]

        return keywords

    def _find_matching_events(
        self,
        events: list[TraceEvent],
        keywords: list[str],
    ) -> list[TraceEvent]:
        """Find events matching the keyword pattern."""
        matching: list[TraceEvent] = []

        for event in events:
            # Search in event name, data, and reasoning
            searchable_text = ""
            searchable_text += event.name.lower()
            searchable_text += " " + str(event.data).lower()

            reasoning = getattr(event, "reasoning", None) or ""
            searchable_text += " " + str(reasoning).lower()

            error_message = getattr(event, "error_message", None) or ""
            searchable_text += " " + str(error_message).lower()

            # Check if any keyword matches
            if any(keyword in searchable_text for keyword in keywords):
                matching.append(event)

        return matching

    def _classify_violation_type(self, query: str) -> ViolationType:
        """Classify violation type based on query keywords."""
        query_lower = query.lower()

        if any(word in query_lower for word in ["unsafe", "dangerous", "harmful", "risk"]):
            return ViolationType.SAFETY_VIOLATION
        elif any(word in query_lower for word in ["slow", "timeout", "delay", "performance"]):
            return ViolationType.TEMPORAL_ANOMALY
        elif any(word in query_lower for word in ["cost", "token", "expensive"]):
            return ViolationType.RESOURCE_ANOMALY
        elif any(word in query_lower for word in ["error", "failure", "crash", "exception"]):
            return ViolationType.SPARSE_FAILURE
        elif any(word in query_lower for word in ["different", "unusual", "unexpected", "weird"]):
            return ViolationType.OUTLIER_BEHAVIOR
        else:
            return ViolationType.PATTERN_DEVIATION

    def _estimate_severity(self, matching_events: list[TraceEvent]) -> ViolationSeverity:
        """Estimate severity based on matching events."""
        if not matching_events:
            return ViolationSeverity.LOW

        # Count error events
        error_count = sum(1 for e in matching_events if e.event_type == EventType.ERROR)

        if error_count > 2:
            return ViolationSeverity.CRITICAL
        elif error_count > 0 or len(matching_events) > 5:
            return ViolationSeverity.HIGH
        elif len(matching_events) > 2:
            return ViolationSeverity.MEDIUM
        else:
            return ViolationSeverity.LOW

    def _extract_event_description(self, event: TraceEvent) -> str:
        """Extract a description from an event."""
        parts = []

        reasoning = getattr(event, "reasoning", None)
        if reasoning:
            parts.append(str(reasoning)[:100])

        error = getattr(event, "error_message", None)
        if error:
            parts.append(str(error)[:100])

        if parts:
            return " | ".join(parts)
        return event.name

    def _compute_match_confidence(self, event: TraceEvent, keywords: list[str]) -> float:
        """Compute confidence score for keyword match."""
        searchable_text = ""
        searchable_text += event.name.lower()
        searchable_text += " " + str(event.data).lower()

        reasoning = getattr(event, "reasoning", None) or ""
        searchable_text += " " + str(reasoning).lower()

        # Count matching keywords
        match_count = sum(1 for kw in keywords if kw in searchable_text)
        return min(match_count / len(keywords), 1.0) if keywords else 0.0


class SparseFailureDetector:
    """Find failures only visible when N+ traces are compared."""

    def __init__(self, sessions: dict[str, list[TraceEvent]]) -> None:
        """Initialize the detector with session data.

        Args:
            sessions: Dictionary mapping session IDs to their event traces
        """
        self.sessions = sessions

    def detect_sparse_failures(
        self,
        min_occurrences: int = 2,
    ) -> list[SparseFailurePattern]:
        """Detect failure patterns across multiple sessions.

        Args:
            min_occurrences: Minimum sessions showing pattern to report

        Returns:
            List of sparse failure patterns
        """
        patterns: list[SparseFailurePattern] = []
        pattern_id = 0

        # Collect error events from all sessions
        error_patterns: dict[str, list[tuple[str, TraceEvent]]] = {}

        for session_id, events in self.sessions.items():
            for event in events:
                if event.event_type == EventType.ERROR:
                    # Create pattern key from error type/message
                    error_type = getattr(event, "error_type", "unknown")
                    error_msg = getattr(event, "error_message", "")

                    pattern_key = f"{error_type}:{error_msg[:50] if error_msg else ''}"

                    if pattern_key not in error_patterns:
                        error_patterns[pattern_key] = []
                    error_patterns[pattern_key].append((session_id, event))

        # Find patterns that appear across multiple sessions
        for pattern_key, occurrences in error_patterns.items():
            if len(occurrences) >= min_occurrences:
                # Get unique session IDs
                session_ids = list(set(sid for sid, _ in occurrences))

                if len(session_ids) >= min_occurrences:
                    pattern = SparseFailurePattern(
                        pattern_id=f"sparse_failure_{pattern_id}",
                        failure_type=pattern_key.split(":")[0],
                        description=f"Error pattern '{pattern_key[:50]}...' found across {len(session_ids)} sessions",
                        required_sessions=min_occurrences,
                        session_ids=session_ids,
                        failure_points=[
                            {
                                "session_id": sid,
                                "event_id": event.id,
                                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                                "error_type": getattr(event, "error_type", "unknown"),
                                "error_message": getattr(event, "error_message", ""),
                            }
                            for sid, event in occurrences[:10]
                        ],
                        confidence=min(len(session_ids) / len(self.sessions), 1.0),
                    )
                    patterns.append(pattern)
                    pattern_id += 1

        return patterns


def compute_session_embedding(session_id: str, events: list[TraceEvent]) -> SessionEmbedding:
    """Compute lightweight embedding for a session.

    Args:
        session_id: Session identifier
        events: Event trace for the session

    Returns:
        Session embedding with similarity comparison capability
    """
    # Create feature vector based on event statistics
    features: dict[str, float] = {}

    # Event type distribution
    event_type_counts: dict[str, int] = {}
    for event in events:
        etype = str(event.event_type)
        event_type_counts[etype] = event_type_counts.get(etype, 0) + 1

    total_events = len(events)
    if total_events > 0:
        for etype, count in event_type_counts.items():
            features[f"event_type_{etype}"] = count / total_events

    # Tool usage patterns
    tool_names: list[str] = []
    for event in events:
        if event.event_type == EventType.TOOL_CALL:
            tool_name = getattr(event, "tool_name", None)
            if tool_name:
                tool_names.append(tool_name)

    # Hash of tool names as feature
    tool_features = {}
    for tool in set(tool_names):
        tool_features[f"tool_{tool}"] = tool_names.count(tool) / max(len(tool_names), 1)

    features.update(tool_features)

    # Temporal features
    if events:
        timestamps = [e.timestamp for e in events if e.timestamp]
        if timestamps:
            duration = (max(timestamps) - min(timestamps)).total_seconds()
            features["duration_seconds"] = min(duration / 3600.0, 1.0)  # Normalize to hours

    # Create embedding vector from features
    embedding_vector = list(features.values())

    # Create summary hash
    summary_hash = str(hash(frozenset(features.items())))

    return SessionEmbedding(
        session_id=session_id,
        embedding_vector=embedding_vector,
        feature_weights=features,
        summary_hash=summary_hash,
    )


def cluster_sessions(
    sessions: dict[str, list[TraceEvent]],
    similarity_threshold: float = 0.7,
    min_cluster_size: int = 2,
) -> list[TraceCluster]:
    """Cluster sessions and identify outliers.

    Args:
        sessions: Dictionary mapping session IDs to event traces
        similarity_threshold: Minimum similarity for clustering
        min_cluster_size: Minimum sessions to form a cluster

    Returns:
        List of trace clusters with outliers identified
    """
    clusterer = TraceClusterer(sessions)
    return clusterer.cluster_sessions(
        similarity_threshold=similarity_threshold,
        min_cluster_size=min_cluster_size,
    )


def search_violations_across_traces(
    sessions: dict[str, list[TraceEvent]],
    nl_query: str,
    max_results: int = 50,
) -> list[ViolationReport]:
    """Search for violations matching NL description across sessions.

    Args:
        sessions: Dictionary mapping session IDs to event traces
        nl_query: Natural language description of violation
        max_results: Maximum results to return

    Returns:
        List of violation reports with evidence
    """
    searcher = CrossTraceSearch(sessions)
    return searcher.search_violations(nl_query=nl_query, max_results=max_results)


def detect_sparse_failures(
    sessions: dict[str, list[TraceEvent]],
    min_occurrences: int = 2,
) -> list[SparseFailurePattern]:
    """Detect sparse failures across multiple sessions.

    Args:
        sessions: Dictionary mapping session IDs to event traces
        min_occurrences: Minimum sessions showing pattern

    Returns:
        List of sparse failure patterns
    """
    detector = SparseFailureDetector(sessions)
    return detector.detect_sparse_failures(min_occurrences=min_occurrences)
