"""Behavior change detection by comparing baseline and recent session metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BehaviorChange:
    """Represents a detected behavior change between baseline and recent periods."""

    type: str  # e.g., "decision_pattern_shift", "latency_increase", "failure_rate_spike"
    severity: str  # "low", "medium", "high"
    before: Any  # Baseline value
    after: Any  # Current/recent value
    root_cause: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "type": self.type,
            "severity": self.severity,
            "before": self.before,
            "after": self.after,
            "root_cause": self.root_cause,
        }


class BehaviorMonitor:
    """Detects significant behavioral changes between a baseline and recent period."""

    _LATENCY_THRESHOLD = 0.50  # flag if latency increases by > 50%
    _FAILURE_RATE_MULTIPLIER = 2.0  # flag if failure rate exceeds 2x baseline
    _COST_MULTIPLIER = 2.0  # flag if cost exceeds 2x baseline
    _DISTRIBUTION_SHIFT_THRESHOLD = 0.20  # total variation distance threshold
    _MIN_BASELINE_DAYS = 7
    _MIN_BASELINE_SESSIONS = 15

    def detect_changes(
        self, baseline: dict[str, Any], recent: dict[str, Any]
    ) -> list[BehaviorChange]:
        """Compare baseline and recent metrics and return significant changes."""
        if (
            baseline.get("time_window_days", 0) < self._MIN_BASELINE_DAYS
            or baseline.get("session_count", 0) < self._MIN_BASELINE_SESSIONS
        ):
            return []

        changes: list[BehaviorChange] = []

        # Latency check
        try:
            b_lat = baseline.get("avg_latency_ms")
            r_lat = recent.get("avg_latency_ms")
            if b_lat is not None and r_lat is not None and b_lat > 0:
                if r_lat / b_lat > 1 + self._LATENCY_THRESHOLD:
                    changes.append(
                        BehaviorChange(type="latency_increase", severity="medium", before=b_lat, after=r_lat)
                    )
        except Exception:
            pass

        # Failure rate check
        try:
            b_fr = baseline.get("failure_rate")
            r_fr = recent.get("failure_rate")
            if b_fr is not None and r_fr is not None and b_fr > 0:
                if r_fr / b_fr > self._FAILURE_RATE_MULTIPLIER:
                    changes.append(
                        BehaviorChange(type="failure_rate_spike", severity="high", before=b_fr, after=r_fr)
                    )
        except Exception:
            pass

        # Cost check
        try:
            b_cost = baseline.get("avg_cost_per_session")
            r_cost = recent.get("avg_cost_per_session")
            if b_cost is not None and r_cost is not None and b_cost > 0:
                if r_cost / b_cost > self._COST_MULTIPLIER:
                    changes.append(
                        BehaviorChange(type="cost_increase", severity="high", before=b_cost, after=r_cost)
                    )
        except Exception:
            pass

        # Decision distribution check
        try:
            b_dist = baseline.get("decision_distribution")
            r_dist = recent.get("decision_distribution")
            if b_dist and r_dist:
                all_keys = set(b_dist) | set(r_dist)
                total_diff = sum(abs(b_dist.get(k, 0) - r_dist.get(k, 0)) for k in all_keys)
                if total_diff > self._DISTRIBUTION_SHIFT_THRESHOLD:
                    changes.append(
                        BehaviorChange(
                            type="decision_pattern_shift",
                            severity="medium",
                            before=b_dist,
                            after=r_dist,
                        )
                    )
        except Exception:
            pass

        return changes

    def identify_root_cause(
        self,
        baseline: dict[str, Any],
        recent: dict[str, Any],
        change: BehaviorChange,
    ) -> str | None:
        """Attempt to identify the root cause of a detected behavior change."""
        b_config = baseline.get("config_version")
        r_config = recent.get("config_version")
        if b_config is not None and r_config is not None and b_config != r_config:
            return f"Configuration change detected: version changed from {b_config} to {r_config}"
        return None
