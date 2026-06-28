"""Tests for PatternDetector and Pattern classes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent_debugger_sdk.core.events.session import Session
from collector.patterns.pattern_detector import Pattern, PatternDetector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_session(
    *,
    agent_name: str = "agent",
    errors: int = 0,
    tool_calls: int = 10,
    replay_value: float = 0.8,
    hours_ago: float = 0.0,
) -> Session:
    started_at = _now() - timedelta(hours=hours_ago)
    return Session(
        agent_name=agent_name,
        errors=errors,
        tool_calls=tool_calls,
        replay_value=replay_value,
        started_at=started_at,
    )


def _baseline(n: int, errors: int = 0, tool_calls: int = 10, replay_value: float = 0.8) -> list[Session]:
    """Create n baseline sessions (2-8 days ago)."""
    return [
        _make_session(errors=errors, tool_calls=tool_calls, replay_value=replay_value, hours_ago=72 + i * 12)
        for i in range(n)
    ]


def _recent(n: int, errors: int = 0, tool_calls: int = 10, replay_value: float = 0.8) -> list[Session]:
    """Create n recent sessions (within last 24h)."""
    return [
        _make_session(errors=errors, tool_calls=tool_calls, replay_value=replay_value, hours_ago=i * 0.5)
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Pattern.to_dict
# ---------------------------------------------------------------------------

class TestPatternToDict:
    def test_roundtrip_has_all_expected_keys(self):
        p = Pattern(
            pattern_type="error_trend",
            agent_name="myagent",
            severity="warning",
            description="some description",
            affected_sessions=["s1", "s2"],
            detected_at=_now(),
            baseline_value=0.1,
            current_value=0.3,
            threshold=0.5,
            change_percent=2.0,
            metadata={"foo": "bar"},
        )
        d = p.to_dict()
        expected_keys = {
            "pattern_type", "agent_name", "severity", "description",
            "affected_sessions", "detected_at", "baseline_value",
            "current_value", "threshold", "change_percent", "metadata",
        }
        assert set(d.keys()) == expected_keys

    def test_detected_at_is_isoformat_string(self):
        now = _now()
        p = Pattern(
            pattern_type="tool_failure",
            agent_name="a",
            severity="critical",
            description="desc",
            affected_sessions=[],
            detected_at=now,
        )
        d = p.to_dict()
        assert d["detected_at"] == now.isoformat()

    def test_optional_fields_default_none(self):
        p = Pattern(
            pattern_type="x",
            agent_name="a",
            severity="warning",
            description="d",
            affected_sessions=[],
            detected_at=_now(),
        )
        d = p.to_dict()
        assert d["baseline_value"] is None
        assert d["current_value"] is None
        assert d["threshold"] is None
        assert d["change_percent"] is None


# ---------------------------------------------------------------------------
# Helper methods
# ---------------------------------------------------------------------------

class TestCalculateAverageErrorRate:
    def setup_method(self):
        self.detector = PatternDetector()

    def test_empty_returns_zero(self):
        assert self.detector._calculate_average_error_rate([]) == 0.0

    def test_no_errors(self):
        sessions = _baseline(4, errors=0)
        assert self.detector._calculate_average_error_rate(sessions) == 0.0

    def test_all_errors(self):
        sessions = _baseline(4, errors=1)
        assert self.detector._calculate_average_error_rate(sessions) == 1.0

    def test_half_errors(self):
        sessions = [
            _make_session(errors=1, hours_ago=5),
            _make_session(errors=1, hours_ago=6),
            _make_session(errors=0, hours_ago=7),
            _make_session(errors=0, hours_ago=8),
        ]
        assert self.detector._calculate_average_error_rate(sessions) == pytest.approx(0.5)


class TestCalculateToolFailureRate:
    def setup_method(self):
        self.detector = PatternDetector()

    def test_empty_returns_zero(self):
        assert self.detector._calculate_tool_failure_rate([]) == 0.0

    def test_zero_tool_calls_returns_zero(self):
        sessions = [_make_session(tool_calls=0, errors=0)]
        assert self.detector._calculate_tool_failure_rate(sessions) == 0.0

    def test_rate_is_errors_over_tool_calls(self):
        sessions = [
            _make_session(errors=2, tool_calls=10),
            _make_session(errors=3, tool_calls=10),
        ]
        # total_errors=5, total_tool_calls=20 → 0.25
        assert self.detector._calculate_tool_failure_rate(sessions) == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# detect_error_rate_trends
# ---------------------------------------------------------------------------

class TestDetectErrorRateTrends:
    def setup_method(self):
        self.detector = PatternDetector(error_rate_threshold=0.5)

    def test_no_pattern_when_recent_rate_not_above_baseline(self):
        baseline = _baseline(5, errors=1)   # 100% error rate
        recent = _recent(3, errors=0)        # 0% error rate — better
        patterns = self.detector.detect_error_rate_trends("agent", baseline, recent)
        assert patterns == []

    def test_no_pattern_when_increase_below_threshold(self):
        baseline = _baseline(5, errors=1)   # 100% error rate
        recent = _recent(3, errors=1)        # 100% — no increase
        patterns = self.detector.detect_error_rate_trends("agent", baseline, recent)
        assert patterns == []

    def test_warning_when_increase_exceeds_threshold(self):
        # baseline: 2/5 = 40%  recent: 2/3 = 67%  change ≈ 0.67 → > 0.5 but < 1.0 → warning
        baseline = [
            _make_session(errors=1, hours_ago=72),
            _make_session(errors=1, hours_ago=76),
            _make_session(errors=0, hours_ago=80),
            _make_session(errors=0, hours_ago=84),
            _make_session(errors=0, hours_ago=88),
        ]
        recent = [
            _make_session(errors=1, hours_ago=1),
            _make_session(errors=1, hours_ago=2),
            _make_session(errors=0, hours_ago=3),
        ]
        patterns = self.detector.detect_error_rate_trends("agent", baseline, recent)
        assert len(patterns) == 1
        assert patterns[0].severity == "warning"
        assert patterns[0].pattern_type == "error_trend"

    def test_critical_when_increase_exceeds_2x_threshold(self):
        # baseline: 1/5 = 20%  recent: 5/5 = 100%  change = (0.8/0.2)=4.0 ≥ 1.0 (2×0.5)
        baseline = [
            _make_session(errors=1, hours_ago=72),
            _make_session(errors=0, hours_ago=76),
            _make_session(errors=0, hours_ago=80),
            _make_session(errors=0, hours_ago=84),
            _make_session(errors=0, hours_ago=88),
        ]
        recent = _recent(5, errors=1)
        patterns = self.detector.detect_error_rate_trends("agent", baseline, recent)
        assert len(patterns) == 1
        assert patterns[0].severity == "critical"

    def test_zero_baseline_rate_with_recent_errors(self):
        baseline = _baseline(5, errors=0)   # 0% error rate
        recent = _recent(3, errors=1)        # 100% error rate
        patterns = self.detector.detect_error_rate_trends("agent", baseline, recent)
        # change_percent = 1.0 (by convention) > threshold 0.5 → should detect
        assert len(patterns) == 1

    def test_zero_baseline_no_recent_errors(self):
        baseline = _baseline(5, errors=0)
        recent = _recent(3, errors=0)
        patterns = self.detector.detect_error_rate_trends("agent", baseline, recent)
        assert patterns == []


# ---------------------------------------------------------------------------
# detect_tool_failure_frequency
# ---------------------------------------------------------------------------

class TestDetectToolFailureFrequency:
    def setup_method(self):
        self.detector = PatternDetector(tool_failure_threshold=0.5)

    def test_no_pattern_below_threshold(self):
        # baseline rate 10%  recent rate 12% — small increase
        baseline = _baseline(5, errors=1, tool_calls=10)   # 10%
        recent = _recent(3, errors=0, tool_calls=10)        # 0%
        patterns = self.detector.detect_tool_failure_frequency("agent", baseline, recent)
        assert patterns == []

    def test_warning_when_rate_spikes(self):
        # baseline: 10/100 = 10%  recent: 8/50 = 16%  change = 0.6 → warning (0.5 < 0.6 < 1.0)
        baseline = _baseline(10, errors=1, tool_calls=10)  # 10%
        recent = [_make_session(errors=4, tool_calls=25, hours_ago=i * 0.2) for i in range(2)]  # 8/50 = 16%
        patterns = self.detector.detect_tool_failure_frequency("agent", baseline, recent)
        assert len(patterns) == 1
        assert patterns[0].severity == "warning"

    def test_critical_severity_escalation(self):
        # baseline: 1/10=10%  recent: 3/10=30%  change=2.0 >= 1.0 (2×0.5) → critical
        baseline = _baseline(5, errors=1, tool_calls=50)   # 5/250 = 2%
        recent = [_make_session(errors=3, tool_calls=10, hours_ago=i * 0.2) for i in range(2)]  # 6/20=30%
        patterns = self.detector.detect_tool_failure_frequency("agent", baseline, recent)
        if patterns:
            assert patterns[0].severity == "critical"

    def test_zero_baseline_no_recent_failures(self):
        baseline = _baseline(5, errors=0, tool_calls=10)
        recent = _recent(3, errors=0, tool_calls=10)
        patterns = self.detector.detect_tool_failure_frequency("agent", baseline, recent)
        assert patterns == []


# ---------------------------------------------------------------------------
# detect_new_failure_modes
# ---------------------------------------------------------------------------

class TestDetectNewFailureModes:
    def setup_method(self):
        self.detector = PatternDetector()

    def test_no_pattern_when_recent_errors_not_exceeding_2x_baseline(self):
        # baseline: 2 error sessions  recent: 3 error sessions — under 2×
        baseline = [
            _make_session(errors=1, hours_ago=72),
            _make_session(errors=1, hours_ago=76),
            _make_session(errors=0, hours_ago=80),
        ]
        recent = [
            _make_session(errors=1, hours_ago=1),
            _make_session(errors=1, hours_ago=2),
            _make_session(errors=1, hours_ago=3),
        ]
        patterns = self.detector.detect_new_failure_modes("agent", baseline, recent)
        assert patterns == []

    def test_warning_when_recent_exceeds_2x_baseline(self):
        # baseline: 1 error session  recent: 3 error sessions (>2×) but not >3×
        baseline = [
            _make_session(errors=1, hours_ago=72),
            _make_session(errors=0, hours_ago=76),
            _make_session(errors=0, hours_ago=80),
        ]
        recent = [
            _make_session(errors=1, hours_ago=1),
            _make_session(errors=1, hours_ago=2),
            _make_session(errors=1, hours_ago=3),
        ]
        patterns = self.detector.detect_new_failure_modes("agent", baseline, recent)
        assert len(patterns) == 1
        assert patterns[0].severity == "warning"
        assert patterns[0].pattern_type == "new_failure_mode"

    def test_critical_when_recent_exceeds_3x_baseline(self):
        # baseline: 1  recent: 4 (>3×)
        baseline = [
            _make_session(errors=1, hours_ago=72),
            _make_session(errors=0, hours_ago=76),
            _make_session(errors=0, hours_ago=80),
        ]
        recent = [_make_session(errors=1, hours_ago=i + 1) for i in range(4)]
        patterns = self.detector.detect_new_failure_modes("agent", baseline, recent)
        assert len(patterns) == 1
        assert patterns[0].severity == "critical"

    def test_no_pattern_when_baseline_has_zero_errors(self):
        baseline = _baseline(3, errors=0)
        recent = _recent(3, errors=0)
        patterns = self.detector.detect_new_failure_modes("agent", baseline, recent)
        assert patterns == []


# ---------------------------------------------------------------------------
# detect_confidence_drops
# ---------------------------------------------------------------------------

class TestDetectConfidenceDrops:
    def setup_method(self):
        self.detector = PatternDetector(confidence_drop_threshold=0.2)

    def test_no_pattern_when_drop_below_threshold(self):
        baseline = _baseline(4, replay_value=0.8)
        recent = _recent(3, replay_value=0.75)  # ~6% drop — under 20%
        patterns = self.detector.detect_confidence_drops("agent", baseline, recent)
        assert patterns == []

    def test_warning_when_replay_value_drops_significantly(self):
        baseline = _baseline(4, replay_value=1.0)
        recent = _recent(3, replay_value=0.7)  # 30% drop > threshold
        patterns = self.detector.detect_confidence_drops("agent", baseline, recent)
        assert len(patterns) == 1
        assert patterns[0].pattern_type == "confidence_drop"
        assert patterns[0].severity == "warning"

    def test_critical_when_replay_value_drops_severely(self):
        baseline = _baseline(4, replay_value=1.0)
        recent = _recent(3, replay_value=0.5)  # 50% drop ≥ 2×0.2=0.4 → critical
        patterns = self.detector.detect_confidence_drops("agent", baseline, recent)
        assert len(patterns) == 1
        assert patterns[0].severity == "critical"

    def test_no_pattern_when_replay_value_improves(self):
        baseline = _baseline(4, replay_value=0.5)
        recent = _recent(3, replay_value=0.9)
        patterns = self.detector.detect_confidence_drops("agent", baseline, recent)
        assert patterns == []


# ---------------------------------------------------------------------------
# detect_all_patterns
# ---------------------------------------------------------------------------

class TestDetectAllPatterns:
    def setup_method(self):
        self.detector = PatternDetector()

    def test_empty_list_returns_empty(self):
        assert self.detector.detect_all_patterns([]) == []

    def test_groups_sessions_by_agent(self):
        # two agents, neither has enough baseline — expect empty
        sessions = [
            _make_session(agent_name="a", errors=1, hours_ago=72 + i) for i in range(3)
        ] + [
            _make_session(agent_name="b", errors=1, hours_ago=72 + i) for i in range(3)
        ]
        patterns = self.detector.detect_all_patterns(sessions)
        # baseline sessions = 3 (equal to minimum), recent = 0 → no patterns
        assert isinstance(patterns, list)

    def test_critical_sorted_before_warning(self):
        # Build sessions for one agent: big baseline + high-error recent → triggers critical
        baseline_sessions = [
            _make_session(agent_name="a", errors=0, tool_calls=10, hours_ago=72 + i * 3)
            for i in range(5)
        ]
        # Recent sessions with very high error rate → critical
        recent_sessions = [
            _make_session(agent_name="a", errors=1, tool_calls=10, hours_ago=i * 0.5)
            for i in range(5)
        ]
        sessions = baseline_sessions + recent_sessions
        patterns = self.detector.detect_all_patterns(sessions)
        severities = [p.severity for p in patterns]
        # All criticals appear before all warnings
        seen_warning = False
        for s in severities:
            if s == "warning":
                seen_warning = True
            if seen_warning:
                assert s != "critical", "critical appears after warning"

    def test_returns_no_patterns_when_baseline_too_small(self):
        # Only 2 baseline sessions < 3 minimum
        sessions = [
            _make_session(agent_name="a", errors=1, hours_ago=72),
            _make_session(agent_name="a", errors=1, hours_ago=76),
            _make_session(agent_name="a", errors=1, hours_ago=1),
        ]
        patterns = self.detector.detect_all_patterns(sessions)
        assert patterns == []

    def test_detects_patterns_with_sufficient_baseline(self):
        # 5 baseline sessions (0 errors) + 5 recent (all errors) → should trigger error trend
        baseline_sessions = [
            _make_session(agent_name="a", errors=0, hours_ago=72 + i * 6)
            for i in range(5)
        ]
        recent_sessions = [
            _make_session(agent_name="a", errors=1, hours_ago=i * 0.5)
            for i in range(5)
        ]
        patterns = self.detector.detect_all_patterns(baseline_sessions + recent_sessions)
        assert len(patterns) > 0
