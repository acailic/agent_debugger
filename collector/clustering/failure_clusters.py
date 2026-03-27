"""Failure clustering analysis."""

from __future__ import annotations

from typing import Any


class FailureClusterAnalyzer:
    """Cluster failure events by fingerprint."""

    def cluster_failures(
        self,
        event_rankings: list[dict[str, Any]],
        severity_threshold: float = 0.78,
    ) -> list[dict[str, Any]]:
        """Cluster high-severity events by fingerprint.

        Args:
            event_rankings: List of event ranking dicts with fingerprint, severity, composite
            severity_threshold: Minimum severity to include in clustering

        Returns:
            List of cluster dicts sorted by (-count, -max_composite):
            - fingerprint, count, event_ids, representative_event_id, max_composite
        """
        clusters: dict[str, dict[str, Any]] = {}
        for ranking in event_rankings:
            if ranking["severity"] < severity_threshold:
                continue
            cluster = clusters.setdefault(
                ranking["fingerprint"],
                {
                    "fingerprint": ranking["fingerprint"],
                    "count": 0,
                    "event_ids": [],
                    "representative_event_id": ranking["event_id"],
                    "max_composite": ranking["composite"],
                },
            )
            cluster["count"] += 1
            cluster["event_ids"].append(ranking["event_id"])
            if ranking["composite"] > cluster["max_composite"]:
                cluster["max_composite"] = ranking["composite"]
                cluster["representative_event_id"] = ranking["event_id"]

        return sorted(clusters.values(), key=lambda item: (-item["count"], -item["max_composite"]))
