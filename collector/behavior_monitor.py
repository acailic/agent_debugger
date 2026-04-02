"""Behavior Monitor module for detecting behavior changes in agent sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BehaviorChange:
    """Represents a detected behavior change."""

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
    """Detects behavior changes between baseline and recent metrics."""

    def __init__(self) -> None:
        """Initialize the behavior monitor."""
        self.latency_threshold = 0.5  # 50% increase
        self.failure_rate_threshold = 2.0  # 2x increase
        self.cost_threshold = 2.0  # 2x increase
        self.min_baseline_days = 7
        self.min_baseline_sessions = 30

    def detect_changes(self, baseline_data: dict[str, Any], recent_data: dict[str, Any]) -> list[BehaviorChange]:
        """Detect behavior changes between baseline and recent data."""
        changes: list[BehaviorChange] = []

        # Check if baseline is sufficient
        baseline_days = baseline_data.get("time_window_days", 0)
        baseline_sessions = baseline_data.get("session_count", 0)

        if baseline_days < self.min_baseline_days or baseline_sessions < self.min_baseline_sessions:
            # Insufficient baseline - only detect high severity changes
            return self._detect_critical_changes(baseline_data, recent_data)

        # Check for latency increase
        if "avg_latency_ms" in baseline_data and "avg_latency_ms" in recent_data:
            baseline_latency = baseline_data["avg_latency_ms"]
            recent_latency = recent_data["avg_latency_ms"]

            if baseline_latency > 0:
                latency_change = (recent_latency - baseline_latency) / baseline_latency
                if latency_change > self.latency_threshold:
                    severity = self._calculate_latency_severity(latency_change)
                    changes.append(
                        BehaviorChange(
                            type="latency_increase",
                            severity=severity,
                            before=baseline_latency,
                            after=recent_latency,
                        )
                    )

        # Check for failure rate spike
        if "failure_rate" in baseline_data and "failure_rate" in recent_data:
            baseline_failure = baseline_data["failure_rate"]
            recent_failure = recent_data["failure_rate"]

            if baseline_failure > 0:
                failure_ratio = recent_failure / baseline_failure
                if failure_ratio > self.failure_rate_threshold:
                    changes.append(
                        BehaviorChange(
                            type="failure_rate_spike",
                            severity="high",
                            before=baseline_failure,
                            after=recent_failure,
                        )
                    )

        # Check for decision pattern shift
        if "decision_distribution" in baseline_data and "decision_distribution" in recent_data:
            baseline_dist = baseline_data["decision_distribution"]
            recent_dist = recent_data["decision_distribution"]

            if baseline_dist and recent_dist and isinstance(baseline_dist, dict) and isinstance(recent_dist, dict):
                shift_magnitude = self._calculate_distribution_shift(baseline_dist, recent_dist)
                if shift_magnitude > 0.3:  # 30% shift threshold
                    severity = self._calculate_shift_severity(shift_magnitude)
                    changes.append(
                        BehaviorChange(
                            type="decision_pattern_shift",
                            severity=severity,
                            before=baseline_dist,
                            after=recent_dist,
                        )
                    )

        # Check for cost increase
        if "avg_cost_per_session" in baseline_data and "avg_cost_per_session" in recent_data:
            baseline_cost = baseline_data["avg_cost_per_session"]
            recent_cost = recent_data["avg_cost_per_session"]

            if baseline_cost > 0:
                cost_ratio = recent_cost / baseline_cost
                if cost_ratio > self.cost_threshold:
                    severity = self._calculate_cost_severity(cost_ratio)
                    changes.append(
                        BehaviorChange(
                            type="cost_increase",
                            severity=severity,
                            before=baseline_cost,
                            after=recent_cost,
                        )
                    )

        return changes

    def identify_root_cause(
        self,
        baseline_data: dict[str, Any],
        recent_data: dict[str, Any],
        change: BehaviorChange,
    ) -> str | None:
        """Identify potential root cause for a behavior change."""
        # Check for configuration changes
        baseline_config = baseline_data.get("config_version")
        recent_config = recent_data.get("config_version")

        if baseline_config and recent_config and baseline_config != recent_config:
            return f"Configuration changed from {baseline_config} to {recent_config}"

        # Check for deployment changes
        baseline_deploy = baseline_data.get("deployment_version")
        recent_deploy = recent_data.get("deployment_version")

        if baseline_deploy and recent_deploy and baseline_deploy != recent_deploy:
            return f"Deployment changed from {baseline_deploy} to {recent_deploy}"

        # Check for environment changes
        baseline_env = baseline_data.get("environment")
        recent_env = recent_data.get("environment")

        if baseline_env and recent_env and baseline_env != recent_env:
            return f"Environment changed from {baseline_env} to {recent_env}"

        # Infer from change type
        if change.type == "latency_increase":
            return "Possible resource bottleneck or external service degradation"
        elif change.type == "failure_rate_spike":
            return "Possible code bug, dependency issue, or configuration error"
        elif change.type == "decision_pattern_shift":
            return "Possible change in input data distribution or model parameters"
        elif change.type == "cost_increase":
            return "Possible increase in resource usage or API costs"

        return None

    def _detect_critical_changes(
        self, baseline_data: dict[str, Any], recent_data: dict[str, Any]
    ) -> list[BehaviorChange]:
        """Only detect high-severity changes when baseline is insufficient."""
        changes: list[BehaviorChange] = []

        # Only check for critical failure rate spikes
        if "failure_rate" in baseline_data and "failure_rate" in recent_data:
            baseline_failure = baseline_data["failure_rate"]
            recent_failure = recent_data["failure_rate"]

            if baseline_failure > 0 and recent_failure / baseline_failure > 3.0:  # 3x threshold
                changes.append(
                    BehaviorChange(
                        type="failure_rate_spike",
                        severity="high",
                        before=baseline_failure,
                        after=recent_failure,
                    )
                )

        return changes

    def _calculate_distribution_shift(self, baseline: dict[str, float], recent: dict[str, float]) -> float:
        """Calculate the magnitude of distribution shift."""
        all_keys = set(baseline.keys()) | set(recent.keys())
        total_shift = 0.0

        for key in all_keys:
            baseline_val = baseline.get(key, 0.0)
            recent_val = recent.get(key, 0.0)
            total_shift += abs(recent_val - baseline_val)

        return total_shift / 2  # Normalize by 2 since total probability is 1

    def _calculate_latency_severity(self, change_ratio: float) -> str:
        """Calculate severity based on latency increase ratio."""
        if change_ratio > 1.0:  # >100% increase
            return "high"
        elif change_ratio > 0.75:  # >75% increase
            return "medium"
        else:
            return "low"

    def _calculate_shift_severity(self, shift_magnitude: float) -> str:
        """Calculate severity based on distribution shift magnitude."""
        if shift_magnitude > 0.6:
            return "high"
        elif shift_magnitude > 0.4:
            return "medium"
        else:
            return "low"

    def _calculate_cost_severity(self, cost_ratio: float) -> str:
        """Calculate severity based on cost increase ratio."""
        if cost_ratio > 3.0:
            return "high"
        elif cost_ratio > 2.0:
            return "medium"
        else:
            return "low"
