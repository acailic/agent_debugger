"""Tests for Feature 4: Behavior Change Alerts.

Tests for collector.behavior_monitor.BehaviorMonitor module which provides
detection of behavior changes between baseline and recent metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

# Note: Feature 4 (behavior_monitor) not yet implemented
pytestmark = pytest.mark.skip(reason="Feature 4 (behavior_monitor) not yet implemented")


# Define BehaviorChange dataclass as specified
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


@pytest.fixture
def baseline_data() -> dict[str, Any]:
    """Typical 7-day baseline data fixture."""
    return {
        "session_count": 50,
        "time_window_days": 7,
        "decision_distribution": {
            "action_a": 0.4,
            "action_b": 0.35,
            "action_c": 0.25,
        },
        "avg_latency_ms": 150.0,
        "failure_rate": 0.02,
        "avg_cost_per_session": 0.25,
        "error_count": 10,
        "total_events": 500,
        "tool_usage": {
            "read": 0.5,
            "write": 0.3,
            "delete": 0.2,
        },
    }


@pytest.fixture
def recent_data(baseline_data: dict[str, Any]) -> dict[str, Any]:
    """Recent period data based on baseline for modification in tests."""
    return baseline_data.copy()


class TestBehaviorAlertsHappyPath:
    """Happy path tests for behavior change detection."""

    def test_detect_changes_finds_decision_pattern_shift(self, baseline_data: dict[str, Any]):
        """Decision distribution changes should be detected."""
        from collector.behavior_monitor import BehaviorMonitor

        monitor = BehaviorMonitor()

        recent = baseline_data.copy()
        # Shift decision distribution significantly
        recent["decision_distribution"] = {
            "action_a": 0.2,  # Was 0.4, now 0.2 (50% drop)
            "action_b": 0.5,  # Was 0.35, now 0.5 (43% increase)
            "action_c": 0.3,  # Was 0.25, now 0.3 (20% increase)
        }

        changes = monitor.detect_changes(baseline_data, recent)

        decision_changes = [c for c in changes if c.type == "decision_pattern_shift"]
        assert len(decision_changes) >= 1
        assert decision_changes[0].severity in ("low", "medium", "high")

    def test_detect_changes_finds_latency_increase(self, baseline_data: dict[str, Any]):
        """Latency increases should be detected."""
        from collector.behavior_monitor import BehaviorMonitor

        monitor = BehaviorMonitor()

        recent = baseline_data.copy()
        # Increase latency by 60% (>50% threshold)
        recent["avg_latency_ms"] = 240.0

        changes = monitor.detect_changes(baseline_data, recent)

        latency_changes = [c for c in changes if c.type == "latency_increase"]
        assert len(latency_changes) >= 1
        assert latency_changes[0].before == 150.0
        assert latency_changes[0].after == 240.0

    def test_detect_changes_finds_failure_rate_spike(self, baseline_data: dict[str, Any]):
        """Failure rate increases should be detected with high severity."""
        from collector.behavior_monitor import BehaviorMonitor

        monitor = BehaviorMonitor()

        recent = baseline_data.copy()
        # Increase failure rate from 2% to 8% (4x, >2x threshold)
        recent["failure_rate"] = 0.08

        changes = monitor.detect_changes(baseline_data, recent)

        failure_changes = [c for c in changes if c.type == "failure_rate_spike"]
        assert len(failure_changes) >= 1
        assert failure_changes[0].severity == "high"
        assert failure_changes[0].before == 0.02
        assert failure_changes[0].after == 0.08

    def test_identify_root_cause_finds_config_change(self, baseline_data: dict[str, Any]):
        """Config changes should be identified as root cause."""
        from collector.behavior_monitor import BehaviorMonitor

        monitor = BehaviorMonitor()

        recent = baseline_data.copy()
        recent["failure_rate"] = 0.08
        recent["config_version"] = "v2.0"  # Config changed
        baseline_data["config_version"] = "v1.0"

        changes = monitor.detect_changes(baseline_data, recent)
        failure_change = next(c for c in changes if c.type == "failure_rate_spike")

        root_cause = monitor.identify_root_cause(baseline_data, recent, failure_change)

        assert root_cause is not None
        assert "config" in root_cause.lower() or "configuration" in root_cause.lower()

    def test_alert_includes_before_after_values(self, baseline_data: dict[str, Any]):
        """Change alerts should include both baseline and current values."""
        from collector.behavior_monitor import BehaviorMonitor

        monitor = BehaviorMonitor()

        recent = baseline_data.copy()
        recent["avg_latency_ms"] = 300.0

        changes = monitor.detect_changes(baseline_data, recent)

        assert len(changes) >= 1
        latency_change = next(c for c in changes if c.type == "latency_increase")
        assert latency_change.before == 150.0
        assert latency_change.after == 300.0


class TestBehaviorAlertsEdgeCases:
    """Edge case tests for behavior change detection."""

    def test_insufficient_baseline_returns_no_alerts(self, baseline_data: dict[str, Any]):
        """Less than 7 days of baseline should return empty or low severity alerts."""
        from collector.behavior_monitor import BehaviorMonitor

        monitor = BehaviorMonitor()

        # Create baseline with only 3 days
        short_baseline = baseline_data.copy()
        short_baseline["time_window_days"] = 3
        short_baseline["session_count"] = 10

        recent = baseline_data.copy()
        recent["failure_rate"] = 0.15

        changes = monitor.detect_changes(short_baseline, recent)

        # Either empty or all low severity
        if changes:
            assert all(c.severity == "low" for c in changes)
        else:
            assert changes == []

    def test_no_significant_changes_returns_empty(self, baseline_data: dict[str, Any]):
        """Small changes below threshold should return empty list."""
        from collector.behavior_monitor import BehaviorMonitor

        monitor = BehaviorMonitor()

        recent = baseline_data.copy()
        # Make tiny changes well below any threshold
        recent["avg_latency_ms"] = 155.0  # Only ~3% increase
        recent["failure_rate"] = 0.022  # Only 10% increase

        changes = monitor.detect_changes(baseline_data, recent)

        assert changes == []

    def test_multiple_simultaneous_changes_all_detected(self, baseline_data: dict[str, Any]):
        """Multiple simultaneous changes should all be reported."""
        from collector.behavior_monitor import BehaviorMonitor

        monitor = BehaviorMonitor()

        recent = baseline_data.copy()
        # Trigger multiple significant changes
        recent["avg_latency_ms"] = 300.0  # 100% increase (>50% threshold)
        recent["failure_rate"] = 0.10  # 5x increase (>2x threshold)
        recent["decision_distribution"] = {
            "action_a": 0.1,
            "action_b": 0.1,
            "action_d": 0.8,  # Major shift
        }
        recent["avg_cost_per_session"] = 0.60  # >2x increase

        changes = monitor.detect_changes(baseline_data, recent)

        change_types = {c.type for c in changes}
        assert "latency_increase" in change_types
        assert "failure_rate_spike" in change_types
        assert len(changes) >= 3

    def test_gradual_drift_below_threshold_not_flagged(self, baseline_data: dict[str, Any]):
        """Gradual drift below threshold should not be flagged."""
        from collector.behavior_monitor import BehaviorMonitor

        monitor = BehaviorMonitor()

        recent = baseline_data.copy()
        # Drift latency by 40% (<50% threshold)
        recent["avg_latency_ms"] = 210.0
        # Drift failure rate by 1.5x (<2x threshold)
        recent["failure_rate"] = 0.03

        changes = monitor.detect_changes(baseline_data, recent)

        assert changes == []


class TestBehaviorAlertsErrorHandling:
    """Error handling tests for behavior change detection."""

    def test_missing_metric_uses_default(self, baseline_data: dict[str, Any]):
        """Missing metrics should use sensible defaults without crashing."""
        from collector.behavior_monitor import BehaviorMonitor

        monitor = BehaviorMonitor()

        # Baseline missing latency
        incomplete_baseline = baseline_data.copy()
        del incomplete_baseline["avg_latency_ms"]

        recent = baseline_data.copy()
        recent["avg_latency_ms"] = 200.0

        # Should not crash, should handle gracefully
        changes = monitor.detect_changes(incomplete_baseline, recent)

        assert isinstance(changes, list)

    def test_malformed_distribution_handled(self, baseline_data: dict[str, Any]):
        """None or malformed distribution should not crash."""
        from collector.behavior_monitor import BehaviorMonitor

        monitor = BehaviorMonitor()

        recent = baseline_data.copy()
        # Set distribution to None (malformed)
        recent["decision_distribution"] = None

        # Should not crash
        changes = monitor.detect_changes(baseline_data, recent)

        assert isinstance(changes, list)

    def test_calculation_error_returns_partial_results(self, baseline_data: dict[str, Any]):
        """Error in one metric calculation should not block others."""
        from collector.behavior_monitor import BehaviorMonitor

        monitor = BehaviorMonitor()

        # Create data that might cause calculation issues
        problematic_baseline = baseline_data.copy()
        problematic_baseline["failure_rate"] = 0.0  # Zero could cause division issues

        recent = baseline_data.copy()
        recent["failure_rate"] = 0.05
        recent["avg_latency_ms"] = 300.0  # This should still be detected

        # Should still detect latency change even if failure rate calculation has issues
        changes = monitor.detect_changes(problematic_baseline, recent)

        latency_changes = [c for c in changes if c.type == "latency_increase"]
        assert len(latency_changes) >= 1


class TestBehaviorAlertsThresholds:
    """Threshold boundary tests for behavior change detection."""

    def test_failure_rate_threshold_is_2x(self, baseline_data: dict[str, Any]):
        """Failure rate >2x should be flagged, <2x should not."""
        from collector.behavior_monitor import BehaviorMonitor

        monitor = BehaviorMonitor()

        # Test just above threshold (>2x)
        recent_above = baseline_data.copy()
        recent_above["failure_rate"] = 0.05  # 2.5x baseline (0.02)

        changes_above = monitor.detect_changes(baseline_data, recent_above)
        failure_above = [c for c in changes_above if c.type == "failure_rate_spike"]
        assert len(failure_above) >= 1

        # Test just below threshold (<2x)
        recent_below = baseline_data.copy()
        recent_below["failure_rate"] = 0.035  # 1.75x baseline (0.02)

        changes_below = monitor.detect_changes(baseline_data, recent_below)
        failure_below = [c for c in changes_below if c.type == "failure_rate_spike"]
        assert len(failure_below) == 0

    def test_latency_threshold_is_50_percent(self, baseline_data: dict[str, Any]):
        """Latency >50% should be flagged, <50% should not."""
        from collector.behavior_monitor import BehaviorMonitor

        monitor = BehaviorMonitor()

        # Test just above threshold (>50%)
        recent_above = baseline_data.copy()
        recent_above["avg_latency_ms"] = 230.0  # ~53% increase from 150

        changes_above = monitor.detect_changes(baseline_data, recent_above)
        latency_above = [c for c in changes_above if c.type == "latency_increase"]
        assert len(latency_above) >= 1

        # Test just below threshold (<50%)
        recent_below = baseline_data.copy()
        recent_below["avg_latency_ms"] = 210.0  # 40% increase from 150

        changes_below = monitor.detect_changes(baseline_data, recent_below)
        latency_below = [c for c in changes_below if c.type == "latency_increase"]
        assert len(latency_below) == 0

    def test_cost_threshold_is_2x(self, baseline_data: dict[str, Any]):
        """Cost >2x should be flagged, <2x should not."""
        from collector.behavior_monitor import BehaviorMonitor

        monitor = BehaviorMonitor()

        # Test just above threshold (>2x)
        recent_above = baseline_data.copy()
        recent_above["avg_cost_per_session"] = 0.55  # 2.2x baseline (0.25)

        changes_above = monitor.detect_changes(baseline_data, recent_above)
        cost_above = [c for c in changes_above if c.type == "cost_increase"]
        assert len(cost_above) >= 1

        # Test just below threshold (<2x)
        recent_below = baseline_data.copy()
        recent_below["avg_cost_per_session"] = 0.45  # 1.8x baseline (0.25)

        changes_below = monitor.detect_changes(baseline_data, recent_below)
        cost_below = [c for c in changes_below if c.type == "cost_increase"]
        assert len(cost_below) == 0
