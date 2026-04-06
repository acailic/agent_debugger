"""Cross-session failure clustering analysis.

This module provides clustering of failure patterns across multiple sessions,
enabling identification of recurring issues and time-decay weighted scoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from agent_debugger_sdk.core.events import Session


@dataclass
class CrossSessionCluster:
    """Represents a cluster of similar failures across multiple sessions.

    Attributes:
        fingerprint: Unique identifier for the failure pattern
        count: Number of times this failure has occurred across sessions
        sessions: List of session IDs containing this failure
        representative: Session ID with highest composite score for this cluster
        first_seen: Timestamp of earliest occurrence
        last_seen: Timestamp of most recent occurrence
        score: Time-decay weighted composite score (0.0-1.0)
    """

    fingerprint: str
    count: int
    sessions: list[str]
    representative: str
    first_seen: datetime
    last_seen: datetime
    score: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "fingerprint": self.fingerprint,
            "count": self.count,
            "sessions": self.sessions,
            "representative": self.representative,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "score": round(self.score, 4),
        }


class CrossSessionClusterAnalyzer:
    """Analyzer for cross-session failure clustering.

    Groups failures by fingerprint across sessions and computes
    time-decay weighted scores to prioritize recent, recurring issues.
    """

    # Time-decay constants (in days)
    RECENT_SESSION_DAYS = 7
    STALE_SESSION_DAYS = 30

    def __init__(self, decay_half_life_days: float = 14.0):
        """Initialize the analyzer.

        Args:
            decay_half_life_days: Half-life for exponential time decay (default 14 days)
        """
        self.decay_half_life_days = decay_half_life_days

    def analyze(
        self,
        sessions: list[Session],
        session_rankings: dict[str, dict[str, Any]],
    ) -> list[CrossSessionCluster]:
        """Analyze failures across multiple sessions and create clusters.

        Args:
            sessions: List of Session objects to analyze
            session_rankings: Dict mapping session_id to ranking data including:
                - failure_fingerprints: list of (fingerprint, composite_score) tuples
                - replay_value: float session replay score

        Returns:
            List of CrossSessionCluster objects sorted by (-score, -count)
        """
        from collections import defaultdict

        # Group failures by fingerprint across all sessions
        fingerprint_data: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "sessions": [],
                "scores": [],
                "timestamps": [],
            }
        )

        now = datetime.now(timezone.utc)

        for session in sessions:
            if not session.started_at:
                continue

            rankings = session_rankings.get(session.id, {})
            failures = rankings.get("failure_fingerprints", [])

            for fingerprint, score in failures:
                data = fingerprint_data[fingerprint]
                data["sessions"].append(session.id)
                data["scores"].append(score)
                data["timestamps"].append(session.started_at)

        # Build clusters with time-decay weighting
        clusters: list[CrossSessionCluster] = []

        for fingerprint, data in fingerprint_data.items():
            if not data["sessions"]:
                continue

            # Find representative session (highest composite score)
            max_score_idx = max(range(len(data["scores"])), key=lambda i: data["scores"][i])
            representative = data["sessions"][max_score_idx]

            # Compute time bounds
            first_seen = min(data["timestamps"]) if data["timestamps"] else now
            last_seen = max(data["timestamps"]) if data["timestamps"] else now

            # Compute time-decay weighted score
            weighted_score = self._compute_time_decay_score(data["timestamps"], data["scores"])

            clusters.append(
                CrossSessionCluster(
                    fingerprint=fingerprint,
                    count=len(data["sessions"]),
                    sessions=data["sessions"],
                    representative=representative,
                    first_seen=first_seen,
                    last_seen=last_seen,
                    score=weighted_score,
                )
            )

        # Sort by score (descending) then count (descending)
        clusters.sort(key=lambda c: (-c.score, -c.count))
        return clusters

    def _compute_time_decay_score(
        self,
        timestamps: list[datetime],
        scores: list[float],
    ) -> float:
        """Compute time-decay weighted score using exponential decay.

        Recent sessions contribute more to the cluster score.
        Decay follows exp(-age / half_life).

        Args:
            timestamps: List of session timestamps
            scores: List of composite scores for each occurrence

        Returns:
            Time-decay weighted score between 0.0 and 1.0
        """
        import math

        now = datetime.now(timezone.utc)
        total_weight = 0.0
        weighted_sum = 0.0

        for ts, score in zip(timestamps, scores):
            # Calculate age in days
            age_days = (now - ts).total_seconds() / 86400.0

            # Exponential decay weight
            decay_factor = math.exp(-age_days / self.decay_half_life_days)
            weight = decay_factor

            weighted_sum += score * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        return min(1.0, weighted_sum / total_weight)

    def _is_recent(self, timestamp: datetime) -> bool:
        """Check if a timestamp is within the recent window."""
        now = datetime.now(timezone.utc)
        age_days = (now - timestamp).total_seconds() / 86400.0
        return age_days <= self.RECENT_SESSION_DAYS

    def _is_stale(self, timestamp: datetime) -> bool:
        """Check if a timestamp is beyond the stale threshold."""
        now = datetime.now(timezone.utc)
        age_days = (now - timestamp).total_seconds() / 86400.0
        return age_days >= self.STALE_SESSION_DAYS
