"""Tests for collector behavior monitor."""

from __future__ import annotations

import pytest

from collector.behavior_monitor import BehaviorChange, BehaviorMonitor


class TestBehaviorChange:
    """Tests for BehaviorChange dataclass."""

    def test_to_dict_serialization(self):
        """Test that to_dict correctly serializes all fields."""
        change = BehaviorChange(
            type="latency_increase",
            severity="high",
            before=100.0,
            after=250.0,
            root_cause="Database slowdown",
        )

        result = change.to_dict()

        assert result == {
            "type": "latency_increase",
            "severity": "high",
            "before": 100.0,
            "after": 250.0,
            "root_cause": "Database slowdown",
        }

    def test_to_dict_with_none_root_cause(self):
        """Test that to_dict handles None root_cause."""
        change = BehaviorChange(
            type="decision_pattern_shift",
            severity="medium",
            before={"A": 0.5, "B": 0.5},
            after={"A": 0.3, "B": 0.7},
            root_cause=None,
        )

        result = change.to_dict()

        assert result["root_cause"] is None


class TestBehaviorMonitorInit:
    """Tests for BehaviorMonitor initialization."""

    def test_initialization_defaults(self):
        """Test that BehaviorMonitor initializes with correct default thresholds."""
        monitor = BehaviorMonitor()

        assert monitor.latency_threshold == 0.5
        assert monitor.failure_rate_threshold == 2.0
        assert monitor.cost_threshold == 2.0
        assert monitor.min_baseline_days == 7
        assert monitor.min_baseline_sessions == 30


class TestDetectChanges:
    """Tests for detect_changes method."""

    def test_detect_changes_no_changes_identical_data(self):
        """Test that no changes are detected when data is identical."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 100,
            "avg_latency_ms": 100.0,
            "failure_rate": 0.01,
            "decision_distribution": {"A": 0.5, "B": 0.5},
            "avg_cost_per_session": 0.50,
        }
        recent = baseline.copy()

        changes = monitor.detect_changes(baseline, recent)

        assert changes == []

    def test_detect_changes_latency_increase_low_severity(self):
        """Test latency increase detection with low severity (60% increase)."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 100,
            "avg_latency_ms": 100.0,
        }
        recent = {
            "avg_latency_ms": 160.0,  # 60% increase (above 0.5 threshold)
        }

        changes = monitor.detect_changes(baseline, recent)

        assert len(changes) == 1
        assert changes[0].type == "latency_increase"
        assert changes[0].severity == "low"
        assert changes[0].before == 100.0
        assert changes[0].after == 160.0

    def test_detect_changes_latency_increase_medium_severity(self):
        """Test latency increase detection with medium severity (80% increase)."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 100,
            "avg_latency_ms": 100.0,
        }
        recent = {
            "avg_latency_ms": 180.0,  # 80% increase
        }

        changes = monitor.detect_changes(baseline, recent)

        assert len(changes) == 1
        assert changes[0].type == "latency_increase"
        assert changes[0].severity == "medium"

    def test_detect_changes_latency_increase_high_severity(self):
        """Test latency increase detection with high severity (120% increase)."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 100,
            "avg_latency_ms": 100.0,
        }
        recent = {
            "avg_latency_ms": 220.0,  # 120% increase
        }

        changes = monitor.detect_changes(baseline, recent)

        assert len(changes) == 1
        assert changes[0].type == "latency_increase"
        assert changes[0].severity == "high"

    def test_detect_changes_latency_below_threshold(self):
        """Test that latency changes below threshold are not detected."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 100,
            "avg_latency_ms": 100.0,
        }
        recent = {
            "avg_latency_ms": 140.0,  # 40% increase (below 0.5 threshold)
        }

        changes = monitor.detect_changes(baseline, recent)

        assert changes == []

    def test_detect_changes_failure_rate_spike(self):
        """Test failure rate spike detection."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 100,
            "failure_rate": 0.01,
        }
        recent = {
            "failure_rate": 0.03,  # 3x increase (above 2.0 threshold)
        }

        changes = monitor.detect_changes(baseline, recent)

        assert len(changes) == 1
        assert changes[0].type == "failure_rate_spike"
        assert changes[0].severity == "high"
        assert changes[0].before == 0.01
        assert changes[0].after == 0.03

    def test_detect_changes_failure_rate_below_threshold(self):
        """Test that failure rate changes below threshold are not detected."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 100,
            "failure_rate": 0.01,
        }
        recent = {
            "failure_rate": 0.015,  # 1.5x increase (below 2.0 threshold)
        }

        changes = monitor.detect_changes(baseline, recent)

        assert changes == []

    def test_detect_changes_decision_pattern_shift(self):
        """Test decision pattern shift detection."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 100,
            "decision_distribution": {"A": 0.5, "B": 0.5},
        }
        recent = {
            "decision_distribution": {"A": 0.1, "B": 0.9},  # 40% shift (|0.5-0.1| + |0.5-0.9|) / 2 = 0.4
        }

        changes = monitor.detect_changes(baseline, recent)

        assert len(changes) == 1
        assert changes[0].type == "decision_pattern_shift"
        assert changes[0].severity == "low"  # 0.4 is not > 0.4, so it's low
        assert changes[0].before == {"A": 0.5, "B": 0.5}
        assert changes[0].after == {"A": 0.1, "B": 0.9}

    def test_detect_changes_decision_pattern_shift_below_threshold(self):
        """Test that small decision distribution changes are not detected."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 100,
            "decision_distribution": {"A": 0.5, "B": 0.5},
        }
        recent = {
            "decision_distribution": {"A": 0.4, "B": 0.6},  # 20% shift (below 0.3 threshold)
        }

        changes = monitor.detect_changes(baseline, recent)

        assert changes == []

    def test_detect_changes_cost_increase(self):
        """Test cost increase detection."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 100,
            "avg_cost_per_session": 1.0,
        }
        recent = {
            "avg_cost_per_session": 2.5,  # 2.5x increase
        }

        changes = monitor.detect_changes(baseline, recent)

        assert len(changes) == 1
        assert changes[0].type == "cost_increase"
        assert changes[0].severity == "medium"
        assert changes[0].before == 1.0
        assert changes[0].after == 2.5

    def test_detect_changes_cost_below_threshold(self):
        """Test that cost changes below threshold are not detected."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 100,
            "avg_cost_per_session": 1.0,
        }
        recent = {
            "avg_cost_per_session": 1.8,  # 1.8x increase (below 2.0 threshold)
        }

        changes = monitor.detect_changes(baseline, recent)

        assert changes == []

    def test_detect_changes_multiple_simultaneous_changes(self):
        """Test detection of multiple changes at once."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 100,
            "avg_latency_ms": 100.0,
            "failure_rate": 0.01,
            "decision_distribution": {"A": 0.5, "B": 0.5},
            "avg_cost_per_session": 1.0,
        }
        recent = {
            "avg_latency_ms": 200.0,  # 100% increase
            "failure_rate": 0.03,  # 3x increase
            "decision_distribution": {"A": 0.1, "B": 0.9},  # 80% shift
            "avg_cost_per_session": 3.5,  # 3.5x increase
        }

        changes = monitor.detect_changes(baseline, recent)

        assert len(changes) == 4
        change_types = {c.type for c in changes}
        assert change_types == {
            "latency_increase",
            "failure_rate_spike",
            "decision_pattern_shift",
            "cost_increase",
        }

    def test_detect_changes_insufficient_baseline_days(self):
        """Test that insufficient baseline days triggers critical changes detection."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 3,  # Below 7 day threshold
            "session_count": 100,
            "failure_rate": 0.01,
        }
        recent = {
            "failure_rate": 0.04,  # 4x increase (above 3.0 critical threshold)
        }

        changes = monitor.detect_changes(baseline, recent)

        # Should only detect critical failure rate spike at 3x threshold
        assert len(changes) == 1
        assert changes[0].type == "failure_rate_spike"
        assert changes[0].severity == "high"

    def test_detect_changes_insufficient_baseline_sessions(self):
        """Test that insufficient baseline sessions triggers critical changes detection."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 20,  # Below 30 session threshold
            "failure_rate": 0.01,
        }
        recent = {
            "failure_rate": 0.04,  # 4x increase
        }

        changes = monitor.detect_changes(baseline, recent)

        assert len(changes) == 1
        assert changes[0].type == "failure_rate_spike"

    def test_detect_changes_insufficient_baseline_below_critical_threshold(self):
        """Test that insufficient baseline with sub-critical failure rate returns no changes."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 3,  # Below threshold
            "session_count": 20,
            "failure_rate": 0.01,
        }
        recent = {
            "failure_rate": 0.02,  # 2x increase (below 3.0 critical threshold)
        }

        changes = monitor.detect_changes(baseline, recent)

        assert changes == []

    def test_detect_changes_zero_baseline_latency(self):
        """Test that zero baseline latency does not cause division by zero."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 100,
            "avg_latency_ms": 0.0,
        }
        recent = {
            "avg_latency_ms": 100.0,
        }

        changes = monitor.detect_changes(baseline, recent)

        # Should not detect change when baseline is zero
        assert changes == []

    def test_detect_changes_zero_baseline_failure_rate(self):
        """Test that zero baseline failure rate does not cause division by zero."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 100,
            "failure_rate": 0.0,
        }
        recent = {
            "failure_rate": 0.05,
        }

        changes = monitor.detect_changes(baseline, recent)

        # Should not detect change when baseline is zero
        assert changes == []

    def test_detect_changes_zero_baseline_cost(self):
        """Test that zero baseline cost does not cause division by zero."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 100,
            "avg_cost_per_session": 0.0,
        }
        recent = {
            "avg_cost_per_session": 1.5,
        }

        changes = monitor.detect_changes(baseline, recent)

        # Should not detect change when baseline is zero
        assert changes == []

    def test_detect_changes_missing_optional_fields(self):
        """Test that missing optional fields don't cause errors."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 100,
            "avg_latency_ms": 100.0,
        }
        recent = {
            "avg_latency_ms": 200.0,
        }

        changes = monitor.detect_changes(baseline, recent)

        # Should detect the latency change
        assert len(changes) == 1
        assert changes[0].type == "latency_increase"

    def test_detect_changes_empty_decision_distributions(self):
        """Test handling of empty decision distributions."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 100,
            "decision_distribution": {},
        }
        recent = {
            "decision_distribution": {},
        }

        changes = monitor.detect_changes(baseline, recent)

        assert changes == []

    def test_detect_changes_new_decision_keys(self):
        """Test decision shift when new keys are added."""
        monitor = BehaviorMonitor()
        baseline = {
            "time_window_days": 14,
            "session_count": 100,
            "decision_distribution": {"A": 1.0},
        }
        recent = {
            "decision_distribution": {"A": 0.5, "B": 0.5},  # New key B
        }

        changes = monitor.detect_changes(baseline, recent)

        # 50% shift (0.5 total variation distance / 2 = 0.25, below 0.3 threshold)
        # Actually: |1.0-0.5| + |0.0-0.5| = 1.0, /2 = 0.5 (above threshold)
        assert len(changes) == 1
        assert changes[0].type == "decision_pattern_shift"


class TestIdentifyRootCause:
    """Tests for identify_root_cause method."""

    def test_identify_root_cause_config_change(self):
        """Test root cause identification for configuration changes."""
        monitor = BehaviorMonitor()
        baseline = {
            "config_version": "v1.0",
            "deployment_version": "deploy-123",
            "environment": "production",
        }
        recent = {
            "config_version": "v2.0",
            "deployment_version": "deploy-123",
            "environment": "production",
        }
        change = BehaviorChange(
            type="latency_increase", severity="high", before=100, after=200
        )

        root_cause = monitor.identify_root_cause(baseline, recent, change)

        assert root_cause == "Configuration changed from v1.0 to v2.0"

    def test_identify_root_cause_deployment_change(self):
        """Test root cause identification for deployment changes."""
        monitor = BehaviorMonitor()
        baseline = {
            "config_version": "v1.0",
            "deployment_version": "deploy-123",
            "environment": "production",
        }
        recent = {
            "config_version": "v1.0",
            "deployment_version": "deploy-456",
            "environment": "production",
        }
        change = BehaviorChange(
            type="failure_rate_spike", severity="high", before=0.01, after=0.05
        )

        root_cause = monitor.identify_root_cause(baseline, recent, change)

        assert root_cause == "Deployment changed from deploy-123 to deploy-456"

    def test_identify_root_cause_environment_change(self):
        """Test root cause identification for environment changes."""
        monitor = BehaviorMonitor()
        baseline = {
            "config_version": "v1.0",
            "deployment_version": "deploy-123",
            "environment": "staging",
        }
        recent = {
            "config_version": "v1.0",
            "deployment_version": "deploy-123",
            "environment": "production",
        }
        change = BehaviorChange(
            type="cost_increase", severity="medium", before=1.0, after=2.5
        )

        root_cause = monitor.identify_root_cause(baseline, recent, change)

        assert root_cause == "Environment changed from staging to production"

    def test_identify_root_cause_latency_inference(self):
        """Test root cause inference for latency increase."""
        monitor = BehaviorMonitor()
        baseline = {
            "config_version": "v1.0",
            "deployment_version": "deploy-123",
            "environment": "production",
        }
        recent = {
            "config_version": "v1.0",
            "deployment_version": "deploy-123",
            "environment": "production",
        }
        change = BehaviorChange(
            type="latency_increase", severity="high", before=100, after=200
        )

        root_cause = monitor.identify_root_cause(baseline, recent, change)

        assert root_cause == "Possible resource bottleneck or external service degradation"

    def test_identify_root_cause_failure_rate_inference(self):
        """Test root cause inference for failure rate spike."""
        monitor = BehaviorMonitor()
        baseline = {
            "config_version": "v1.0",
            "deployment_version": "deploy-123",
            "environment": "production",
        }
        recent = {
            "config_version": "v1.0",
            "deployment_version": "deploy-123",
            "environment": "production",
        }
        change = BehaviorChange(
            type="failure_rate_spike", severity="high", before=0.01, after=0.05
        )

        root_cause = monitor.identify_root_cause(baseline, recent, change)

        assert root_cause == "Possible code bug, dependency issue, or configuration error"

    def test_identify_root_cause_decision_pattern_inference(self):
        """Test root cause inference for decision pattern shift."""
        monitor = BehaviorMonitor()
        baseline = {
            "config_version": "v1.0",
            "deployment_version": "deploy-123",
            "environment": "production",
        }
        recent = {
            "config_version": "v1.0",
            "deployment_version": "deploy-123",
            "environment": "production",
        }
        change = BehaviorChange(
            type="decision_pattern_shift",
            severity="high",
            before={"A": 0.5, "B": 0.5},
            after={"A": 0.1, "B": 0.9},
        )

        root_cause = monitor.identify_root_cause(baseline, recent, change)

        assert root_cause == "Possible change in input data distribution or model parameters"

    def test_identify_root_cause_cost_inference(self):
        """Test root cause inference for cost increase."""
        monitor = BehaviorMonitor()
        baseline = {
            "config_version": "v1.0",
            "deployment_version": "deploy-123",
            "environment": "production",
        }
        recent = {
            "config_version": "v1.0",
            "deployment_version": "deploy-123",
            "environment": "production",
        }
        change = BehaviorChange(
            type="cost_increase", severity="medium", before=1.0, after=2.5
        )

        root_cause = monitor.identify_root_cause(baseline, recent, change)

        assert root_cause == "Possible increase in resource usage or API costs"

    def test_identify_root_cause_unknown_change_type(self):
        """Test root cause returns None for unknown change types."""
        monitor = BehaviorMonitor()
        baseline = {
            "config_version": "v1.0",
            "deployment_version": "deploy-123",
            "environment": "production",
        }
        recent = {
            "config_version": "v1.0",
            "deployment_version": "deploy-123",
            "environment": "production",
        }
        change = BehaviorChange(
            type="unknown_type", severity="low", before=None, after=None
        )

        root_cause = monitor.identify_root_cause(baseline, recent, change)

        assert root_cause is None

    def test_identify_root_cause_missing_version_fields(self):
        """Test root cause when version fields are missing."""
        monitor = BehaviorMonitor()
        baseline = {}
        recent = {}
        change = BehaviorChange(
            type="latency_increase", severity="high", before=100, after=200
        )

        root_cause = monitor.identify_root_cause(baseline, recent, change)

        # Should fall back to inference
        assert root_cause == "Possible resource bottleneck or external service degradation"


class TestDetectCriticalChanges:
    """Tests for _detect_critical_changes method."""

    def test_detect_critical_changes_failure_rate_above_threshold(self):
        """Test critical detection for failure rate above 3x threshold."""
        monitor = BehaviorMonitor()
        baseline = {
            "failure_rate": 0.01,
        }
        recent = {
            "failure_rate": 0.04,  # 4x increase (above 3.0 threshold)
        }

        changes = monitor._detect_critical_changes(baseline, recent)

        assert len(changes) == 1
        assert changes[0].type == "failure_rate_spike"
        assert changes[0].severity == "high"
        assert changes[0].before == 0.01
        assert changes[0].after == 0.04

    def test_detect_critical_changes_failure_rate_below_threshold(self):
        """Test critical detection ignores failure rate below 3x threshold."""
        monitor = BehaviorMonitor()
        baseline = {
            "failure_rate": 0.01,
        }
        recent = {
            "failure_rate": 0.02,  # 2x increase (below 3.0 threshold)
        }

        changes = monitor._detect_critical_changes(baseline, recent)

        assert changes == []

    def test_detect_critical_changes_zero_baseline(self):
        """Test critical detection with zero baseline failure rate."""
        monitor = BehaviorMonitor()
        baseline = {
            "failure_rate": 0.0,
        }
        recent = {
            "failure_rate": 0.05,
        }

        changes = monitor._detect_critical_changes(baseline, recent)

        # Should not detect change when baseline is zero
        assert changes == []

    def test_detect_critical_changes_only_checks_failure_rate(self):
        """Test that critical detection only checks failure rate, not other metrics."""
        monitor = BehaviorMonitor()
        baseline = {
            "avg_latency_ms": 100.0,
            "failure_rate": 0.01,
            "avg_cost_per_session": 1.0,
        }
        recent = {
            "avg_latency_ms": 500.0,  # Large latency increase
            "failure_rate": 0.02,  # Below 3x threshold
            "avg_cost_per_session": 10.0,  # Large cost increase
        }

        changes = monitor._detect_critical_changes(baseline, recent)

        # Should only check failure rate, ignore latency and cost
        assert changes == []


class TestCalculateDistributionShift:
    """Tests for _calculate_distribution_shift method."""

    def test_calculate_distribution_shift_identical(self):
        """Test distribution shift with identical distributions."""
        monitor = BehaviorMonitor()
        baseline = {"A": 0.5, "B": 0.5}
        recent = {"A": 0.5, "B": 0.5}

        shift = monitor._calculate_distribution_shift(baseline, recent)

        assert shift == 0.0

    def test_calculate_distribution_shift_completely_different(self):
        """Test distribution shift with completely different distributions."""
        monitor = BehaviorMonitor()
        baseline = {"A": 1.0, "B": 0.0}
        recent = {"A": 0.0, "B": 1.0}

        shift = monitor._calculate_distribution_shift(baseline, recent)

        # Total variation distance: |1.0-0.0| + |0.0-1.0| = 2.0, /2 = 1.0
        assert shift == 1.0

    def test_calculate_distribution_shift_partial_change(self):
        """Test distribution shift with partial change."""
        monitor = BehaviorMonitor()
        baseline = {"A": 0.5, "B": 0.5}
        recent = {"A": 0.3, "B": 0.7}

        shift = monitor._calculate_distribution_shift(baseline, recent)

        # |0.5-0.3| + |0.5-0.7| = 0.4, /2 = 0.2
        assert shift == pytest.approx(0.2)

    def test_calculate_distribution_shift_new_keys(self):
        """Test distribution shift when new keys are added."""
        monitor = BehaviorMonitor()
        baseline = {"A": 1.0}
        recent = {"A": 0.5, "B": 0.5}

        shift = monitor._calculate_distribution_shift(baseline, recent)

        # |1.0-0.5| + |0.0-0.5| = 1.0, /2 = 0.5
        assert shift == 0.5

    def test_calculate_distribution_shift_removed_keys(self):
        """Test distribution shift when keys are removed."""
        monitor = BehaviorMonitor()
        baseline = {"A": 0.5, "B": 0.5}
        recent = {"A": 1.0}

        shift = monitor._calculate_distribution_shift(baseline, recent)

        # |0.5-1.0| + |0.5-0.0| = 1.0, /2 = 0.5
        assert shift == 0.5

    def test_calculate_distribution_shift_multiple_keys(self):
        """Test distribution shift with multiple keys."""
        monitor = BehaviorMonitor()
        baseline = {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}
        recent = {"A": 0.5, "B": 0.3, "C": 0.1, "D": 0.1}

        shift = monitor._calculate_distribution_shift(baseline, recent)

        # |0.25-0.5| + |0.25-0.3| + |0.25-0.1| + |0.25-0.1| = 0.25 + 0.05 + 0.15 + 0.15 = 0.6, /2 = 0.3
        assert shift == pytest.approx(0.3)


class TestCalculateLatencySeverity:
    """Tests for _calculate_latency_severity method."""

    def test_calculate_latency_severity_high(self):
        """Test high severity for >100% increase."""
        monitor = BehaviorMonitor()

        assert monitor._calculate_latency_severity(1.5) == "high"
        assert monitor._calculate_latency_severity(2.0) == "high"
        assert monitor._calculate_latency_severity(10.0) == "high"

    def test_calculate_latency_severity_medium(self):
        """Test medium severity for >75% increase up to 1.0."""
        monitor = BehaviorMonitor()

        assert monitor._calculate_latency_severity(0.8) == "medium"
        assert monitor._calculate_latency_severity(0.9) == "medium"
        assert monitor._calculate_latency_severity(1.0) == "medium"  # Boundary: >1.0 is high, so 1.0 is still medium
        assert monitor._calculate_latency_severity(1.01) == "high"  # Just above 1.0

    def test_calculate_latency_severity_low(self):
        """Test low severity for <=75% increase."""
        monitor = BehaviorMonitor()

        assert monitor._calculate_latency_severity(0.5) == "low"
        assert monitor._calculate_latency_severity(0.6) == "low"
        assert monitor._calculate_latency_severity(0.75) == "low"


class TestCalculateShiftSeverity:
    """Tests for _calculate_shift_severity method."""

    def test_calculate_shift_severity_high(self):
        """Test high severity for >0.6 shift magnitude."""
        monitor = BehaviorMonitor()

        assert monitor._calculate_shift_severity(0.7) == "high"
        assert monitor._calculate_shift_severity(0.8) == "high"
        assert monitor._calculate_shift_severity(1.0) == "high"

    def test_calculate_shift_severity_medium(self):
        """Test medium severity for >0.4 shift magnitude."""
        monitor = BehaviorMonitor()

        assert monitor._calculate_shift_severity(0.5) == "medium"
        assert monitor._calculate_shift_severity(0.6) == "medium"

    def test_calculate_shift_severity_low(self):
        """Test low severity for <=0.4 shift magnitude."""
        monitor = BehaviorMonitor()

        assert monitor._calculate_shift_severity(0.3) == "low"
        assert monitor._calculate_shift_severity(0.4) == "low"
        assert monitor._calculate_shift_severity(0.1) == "low"


class TestCalculateCostSeverity:
    """Tests for _calculate_cost_severity method."""

    def test_calculate_cost_severity_high(self):
        """Test high severity for >3.0 cost ratio."""
        monitor = BehaviorMonitor()

        assert monitor._calculate_cost_severity(3.5) == "high"
        assert monitor._calculate_cost_severity(5.0) == "high"
        assert monitor._calculate_cost_severity(10.0) == "high"

    def test_calculate_cost_severity_medium(self):
        """Test medium severity for >2.0 cost ratio."""
        monitor = BehaviorMonitor()

        assert monitor._calculate_cost_severity(2.5) == "medium"
        assert monitor._calculate_cost_severity(3.0) == "medium"

    def test_calculate_cost_severity_low(self):
        """Test low severity for <=2.0 cost ratio."""
        monitor = BehaviorMonitor()

        assert monitor._calculate_cost_severity(1.5) == "low"
        assert monitor._calculate_cost_severity(2.0) == "low"
        assert monitor._calculate_cost_severity(1.0) == "low"
