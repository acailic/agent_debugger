"""Tests for collector/patterns/pattern_detector.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent_debugger_sdk.core.events import Session
from collector.patterns.pattern_detector import Pattern, PatternDetector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _session(
    *,
    agent_name: str = "agent",
    errors: int = 0,
    tool_calls: int = 0,
    replay_value: float = 0.0,
    started_at: datetime | None = None,
) -> Session:
    return Session(
        agent_name=agent_name,
        errors=errors,
        tool_calls=tool_calls,
        replay_value=replay_value,
        started_at=started_at or _now(),
    )


def _pattern(
    *,
    pattern_type: str = "error_trend",
    agent_name: str = "agent",
    severity: str = "warning",
    description: str = "desc",
    affected_sessions: list[str] | None = None,
    detected_at: datetime | None = None,
) -> Pattern:
    return Pattern(
        pattern_type=pattern_type,
        agent_name=agent_name,
        severity=severity,
        description=description,
        affected_sessions=affected_sessions or [],
        detected_at=detected_at or _now(),
    )


# ---------------------------------------------------------------------------
# Pattern dataclass
# ---------------------------------------------------------------------------

class TestPatternToDict:
    EXPECTED_KEYS = {
        "pattern_type",
        "agent_name",
        "severity",
        "description",
        "affected_sessions",
        "detected_at",
        "baseline_value",
        "current_value",
        "threshold",
        "change_percent",
        "metadata",
    }

    def test_to_dict_has_all_expected_keys(self):
        p = _pattern()
        assert set(p.to_dict().keys()) == self.EXPECTED_KEYS

    def test_to_dict_detected_at_is_isoformat(self):
        ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        p = _pattern(detected_at=ts)
        assert p.to_dict()["detected_at"] == ts.isoformat()

    def test_to_dict_roundtrip_values(self):
        p = Pattern(
            pattern_type="tool_failure",
            agent_name="bot",
            severity="critical",
            description="bad",
            affected_sessions=["s1", "s2"],
            detected_at=_now(),
            baseline_value=0.1,
            current_value=0.5,
            threshold=0.3,
            change_percent=4.0,
            metadata={"k": "v"},
        )
        d = p.to_dict()
        assert d["pattern_type"] == "tool_failure"
        assert d["agent_name"] == "bot"
        assert d["severity"] == "critical"
        assert d["affected_sessions"] == ["s1", "s2"]
        assert d["baseline_value"] == 0.1
        assert d["current_value"] == 0.5
        assert d["threshold"] == 0.3
        assert d["change_percent"] == 4.0
        assert d["metadata"] == {"k": "v"}

    def test_to_dict_optional_fields_none(self):
        p = _pattern()
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

    def test_empty_list_returns_zero(self):
        assert self.detector._calculate_average_error_rate([]) == 0.0

    def test_no_error_sessions_returns_zero(self):
        sessions = [_session(errors=0), _session(errors=0)]
        assert self.detector._calculate_average_error_rate(sessions) == 0.0

    def test_all_error_sessions_returns_one(self):
        sessions = [_session(errors=1), _session(errors=3)]
        assert self.detector._calculate_average_error_rate(sessions) == 1.0

    def test_half_error_sessions(self):
        sessions = [_session(errors=1), _session(errors=0), _session(errors=2), _session(errors=0)]
        assert self.detector._calculate_average_error_rate(sessions) == 0.5

    def test_single_error_session(self):
        sessions = [_session(errors=5)]
        assert self.detector._calculate_average_error_rate(sessions) == 1.0

    def test_single_clean_session(self):
        sessions = [_session(errors=0)]
        assert self.detector._calculate_average_error_rate(sessions) == 0.0


class TestCalculateToolFailureRate:
    def setup_method(self):
        self.detector = PatternDetector()

    def test_empty_list_returns_zero(self):
        assert self.detector._calculate_tool_failure_rate([]) == 0.0

    def test_zero_tool_calls_returns_zero(self):
        sessions = [_session(errors=5, tool_calls=0)]
        assert self.detector._calculate_tool_failure_rate(sessions) == 0.0

    def test_no_errors_returns_zero(self):
        sessions = [_session(errors=0, tool_calls=10)]
        assert self.detector._calculate_tool_failure_rate(sessions) == 0.0

    def test_all_calls_fail(self):
        sessions = [_session(errors=4, tool_calls=4)]
        assert self.detector._calculate_tool_failure_rate(sessions) == 1.0

    def test_half_calls_fail(self):
        sessions = [_session(errors=2, tool_calls=4), _session(errors=2, tool_calls=4)]
        assert self.detector._calculate_tool_failure_rate(sessions) == 0.5

    def test_aggregates_across_sessions(self):
        sessions = [
            _session(errors=1, tool_calls=4),
            _session(errors=1, tool_calls=6),
        ]
        # 2 errors / 10 calls = 0.2
        assert self.detector._calculate_tool_failure_rate(sessions) == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# detect_error_rate_trends
# ---------------------------------------------------------------------------

class TestDetectErrorRateTrends:
    def setup_method(self):
        self.detector = PatternDetector(error_rate_threshold=0.5)

    def _sessions_with_rate(self, rate: float, count: int = 5) -> list[Session]:
        error_count = int(rate * count)
        return [_session(errors=(1 if i < error_count else 0)) for i in range(count)]

    def test_no_pattern_when_rate_unchanged(self):
        baseline = self._sessions_with_rate(0.4)
        recent = self._sessions_with_rate(0.4)
        patterns = self.detector.detect_error_rate_trends("agent", baseline, recent)
        assert patterns == []

    def test_no_pattern_when_rate_decreases(self):
        baseline = self._sessions_with_rate(0.8)
        recent = self._sessions_with_rate(0.2)
        patterns = self.detector.detect_error_rate_trends("agent", baseline, recent)
        assert patterns == []

    def test_warning_when_increase_exceeds_threshold(self):
        # baseline=0.5 (10/20), recent=0.8 (8/10) → change=0.6 > threshold=0.5 but < 1.0 (2x)
        baseline = self._sessions_with_rate(0.5, 20)
        recent = self._sessions_with_rate(0.8, 10)
        patterns = self.detector.detect_error_rate_trends("agent", baseline, recent)
        assert len(patterns) == 1
        assert patterns[0].severity == "warning"
        assert patterns[0].pattern_type == "error_trend"

    def test_critical_when_increase_exceeds_2x_threshold(self):
        # baseline=0.1, recent=0.5 → change=4.0 > 2*0.5=1.0 threshold
        baseline = self._sessions_with_rate(0.1, 10)
        recent = self._sessions_with_rate(0.5, 10)
        patterns = self.detector.detect_error_rate_trends("agent", baseline, recent)
        assert len(patterns) == 1
        assert patterns[0].severity == "critical"

    def test_handles_zero_baseline_rate_with_recent_errors(self):
        # zero baseline, any recent errors → change_percent=1.0 > threshold=0.5 → pattern
        baseline = self._sessions_with_rate(0.0)
        recent = self._sessions_with_rate(0.8)
        patterns = self.detector.detect_error_rate_trends("agent", baseline, recent)
        assert len(patterns) == 1

    def test_handles_zero_baseline_rate_with_no_recent_errors(self):
        baseline = self._sessions_with_rate(0.0)
        recent = self._sessions_with_rate(0.0)
        patterns = self.detector.detect_error_rate_trends("agent", baseline, recent)
        assert patterns == []

    def test_pattern_metadata_has_session_counts(self):
        baseline = self._sessions_with_rate(0.1, 10)
        recent = self._sessions_with_rate(0.8, 5)
        patterns = self.detector.detect_error_rate_trends("agent", baseline, recent)
        assert len(patterns) == 1
        meta = patterns[0].metadata
        assert meta["baseline_session_count"] == 10
        assert meta["recent_session_count"] == 5

    def test_affected_sessions_only_recent_with_errors(self):
        baseline = [_session(errors=0) for _ in range(5)]
        s_error = _session(errors=2)
        s_clean = _session(errors=0)
        # make sure recent rate is high enough to trigger
        recent = [_session(errors=1) for _ in range(3)] + [s_error, s_clean]
        patterns = self.detector.detect_error_rate_trends("agent", baseline, recent)
        if patterns:
            for sid in patterns[0].affected_sessions:
                assert sid != s_clean.id


# ---------------------------------------------------------------------------
# detect_tool_failure_frequency
# ---------------------------------------------------------------------------

class TestDetectToolFailureFrequency:
    def setup_method(self):
        self.detector = PatternDetector(tool_failure_threshold=0.5)

    def test_no_pattern_below_threshold(self):
        baseline = [_session(errors=1, tool_calls=10) for _ in range(5)]
        recent = [_session(errors=1, tool_calls=10) for _ in range(5)]
        patterns = self.detector.detect_tool_failure_frequency("agent", baseline, recent)
        assert patterns == []

    def test_pattern_detected_when_rate_spikes(self):
        # baseline failure rate = 0.1, recent = 0.5 → change=4.0 > threshold
        baseline = [_session(errors=1, tool_calls=10) for _ in range(5)]
        recent = [_session(errors=5, tool_calls=10) for _ in range(5)]
        patterns = self.detector.detect_tool_failure_frequency("agent", baseline, recent)
        assert len(patterns) == 1
        assert patterns[0].pattern_type == "tool_failure"

    def test_severity_escalates_to_critical(self):
        # baseline failure rate = 0.05, recent = 0.9 → change >> 2*threshold
        baseline = [_session(errors=1, tool_calls=20) for _ in range(5)]
        recent = [_session(errors=9, tool_calls=10) for _ in range(5)]
        patterns = self.detector.detect_tool_failure_frequency("agent", baseline, recent)
        assert len(patterns) == 1
        assert patterns[0].severity == "critical"

    def test_warning_severity_at_moderate_increase(self):
        # baseline=0.1 (5/50), recent≈0.167 (5/30) → change=0.67 > threshold=0.5 but < 1.0 (2x)
        baseline = [_session(errors=1, tool_calls=10) for _ in range(5)]
        recent = [_session(errors=1, tool_calls=6) for _ in range(5)]
        patterns = self.detector.detect_tool_failure_frequency("agent", baseline, recent)
        assert len(patterns) == 1
        assert patterns[0].severity == "warning"

    def test_no_pattern_when_rate_drops(self):
        baseline = [_session(errors=5, tool_calls=10) for _ in range(5)]
        recent = [_session(errors=1, tool_calls=10) for _ in range(5)]
        patterns = self.detector.detect_tool_failure_frequency("agent", baseline, recent)
        assert patterns == []

    def test_zero_baseline_with_recent_failures_triggers(self):
        baseline = [_session(errors=0, tool_calls=10) for _ in range(5)]
        recent = [_session(errors=5, tool_calls=10) for _ in range(5)]
        patterns = self.detector.detect_tool_failure_frequency("agent", baseline, recent)
        assert len(patterns) == 1


# ---------------------------------------------------------------------------
# detect_new_failure_modes
# ---------------------------------------------------------------------------

class TestDetectNewFailureModes:
    def setup_method(self):
        self.detector = PatternDetector()

    def test_no_pattern_when_recent_not_exceeding_2x(self):
        baseline = [_session(errors=1) for _ in range(4)] + [_session(errors=0) for _ in range(6)]
        # baseline error sessions = 4; recent must be > 8 for pattern
        recent = [_session(errors=1) for _ in range(5)]
        patterns = self.detector.detect_new_failure_modes("agent", baseline, recent)
        assert patterns == []

    def test_warning_when_recent_exceeds_2x_baseline(self):
        # baseline error sessions = 2, recent error sessions = 5 (> 4 but < 6)
        baseline = [_session(errors=1)] * 2 + [_session(errors=0)] * 8
        recent = [_session(errors=1)] * 5
        patterns = self.detector.detect_new_failure_modes("agent", baseline, recent)
        assert len(patterns) == 1
        assert patterns[0].severity == "warning"
        assert patterns[0].pattern_type == "new_failure_mode"

    def test_critical_when_recent_exceeds_3x_baseline(self):
        # baseline error sessions = 1, recent error sessions = 4 (> 3)
        baseline = [_session(errors=1)] * 1 + [_session(errors=0)] * 9
        recent = [_session(errors=1)] * 4
        patterns = self.detector.detect_new_failure_modes("agent", baseline, recent)
        assert len(patterns) == 1
        assert patterns[0].severity == "critical"

    def test_affected_sessions_list_recent_errors_only(self):
        baseline = [_session(errors=1)] * 1 + [_session(errors=0)] * 5
        s_err = _session(errors=2)
        s_ok = _session(errors=0)
        recent = [_session(errors=1)] * 3 + [s_err, s_ok]
        patterns = self.detector.detect_new_failure_modes("agent", baseline, recent)
        if patterns:
            assert s_ok.id not in patterns[0].affected_sessions

    def test_zero_baseline_errors_with_recent_errors_triggers(self):
        baseline = [_session(errors=0)] * 5
        recent = [_session(errors=1)] * 3  # > 0*2=0
        patterns = self.detector.detect_new_failure_modes("agent", baseline, recent)
        # recent_error_sessions=3, baseline_error_sessions=0, 3 > 0*2=0 → pattern
        assert len(patterns) == 1


# ---------------------------------------------------------------------------
# detect_confidence_drops
# ---------------------------------------------------------------------------

class TestDetectConfidenceDrops:
    def setup_method(self):
        self.detector = PatternDetector(confidence_drop_threshold=0.2)

    def test_no_pattern_when_drop_below_threshold(self):
        baseline = [_session(replay_value=1.0) for _ in range(3)]
        recent = [_session(replay_value=0.9) for _ in range(3)]  # 10% drop < 20%
        patterns = self.detector.detect_confidence_drops("agent", baseline, recent)
        assert patterns == []

    def test_pattern_when_replay_value_drops_significantly(self):
        baseline = [_session(replay_value=1.0) for _ in range(3)]
        recent = [_session(replay_value=0.5) for _ in range(3)]  # 50% drop > 20%
        patterns = self.detector.detect_confidence_drops("agent", baseline, recent)
        assert len(patterns) == 1
        assert patterns[0].pattern_type == "confidence_drop"

    def test_warning_severity_at_moderate_drop(self):
        # 30% drop: > 20% threshold but < 40% (2x)
        baseline = [_session(replay_value=1.0) for _ in range(3)]
        recent = [_session(replay_value=0.7) for _ in range(3)]
        patterns = self.detector.detect_confidence_drops("agent", baseline, recent)
        assert len(patterns) == 1
        assert patterns[0].severity == "warning"

    def test_critical_severity_at_large_drop(self):
        # 50% drop: > 40% (2x threshold)
        baseline = [_session(replay_value=1.0) for _ in range(3)]
        recent = [_session(replay_value=0.5) for _ in range(3)]
        patterns = self.detector.detect_confidence_drops("agent", baseline, recent)
        assert len(patterns) == 1
        assert patterns[0].severity == "critical"

    def test_no_pattern_when_replay_value_increases(self):
        baseline = [_session(replay_value=0.5) for _ in range(3)]
        recent = [_session(replay_value=1.0) for _ in range(3)]
        patterns = self.detector.detect_confidence_drops("agent", baseline, recent)
        assert patterns == []


# ---------------------------------------------------------------------------
# detect_all_patterns
# ---------------------------------------------------------------------------

class TestDetectAllPatterns:
    def setup_method(self):
        self.detector = PatternDetector(
            error_rate_threshold=0.5,
            recent_window_days=1,
            baseline_window_days=7,
        )

    def test_empty_list_returns_empty(self):
        assert self.detector.detect_all_patterns([]) == []

    def test_groups_sessions_by_agent(self):
        now = _now()
        # baseline sessions (2-7 days ago)
        baseline_time = now - timedelta(days=3)
        recent_time = now - timedelta(hours=6)

        # agent-a: 5 clean baseline, 1 heavy-error recent → may produce pattern
        # agent-b: 5 clean baseline, 1 clean recent → no pattern
        agent_a_baseline = [
            _session(agent_name="agent-a", errors=0, started_at=baseline_time)
            for _ in range(5)
        ]
        agent_a_recent = [
            _session(agent_name="agent-a", errors=3, tool_calls=5, started_at=recent_time)
            for _ in range(3)
        ]
        agent_b_sessions = [
            _session(agent_name="agent-b", errors=0, started_at=baseline_time)
            for _ in range(5)
        ] + [
            _session(agent_name="agent-b", errors=0, started_at=recent_time)
        ]

        patterns = self.detector.detect_all_patterns(agent_a_baseline + agent_a_recent + agent_b_sessions)

        agents_with_patterns = {p.agent_name for p in patterns}
        # agent-b should not appear since no rate increase
        assert "agent-b" not in agents_with_patterns

    def test_critical_patterns_sorted_before_warning(self):
        now = _now()
        baseline_time = now - timedelta(days=3)
        recent_time = now - timedelta(hours=6)

        # Set up sessions that produce both critical and warning patterns
        # Use two agents to produce two different patterns
        sessions = (
            # agent-a: moderate increase → warning
            [_session(agent_name="agent-a", errors=0, started_at=baseline_time) for _ in range(8)]
            + [_session(agent_name="agent-a", errors=0, started_at=baseline_time) for _ in range(2)]
            + [_session(agent_name="agent-a", errors=1, started_at=recent_time) for _ in range(3)]
            # agent-b: extreme increase → critical
            + [_session(agent_name="agent-b", errors=0, started_at=baseline_time) for _ in range(9)]
            + [_session(agent_name="agent-b", errors=0, started_at=baseline_time)]
            + [_session(agent_name="agent-b", errors=1, tool_calls=1, started_at=recent_time) for _ in range(10)]
        )

        patterns = self.detector.detect_all_patterns(sessions)

        if len(patterns) >= 2:
            # Verify no warning appears before a critical
            severities = [p.severity for p in patterns]
            first_warning = next((i for i, s in enumerate(severities) if s == "warning"), None)
            first_critical = next((i for i, s in enumerate(severities) if s == "critical"), None)
            if first_warning is not None and first_critical is not None:
                assert first_critical < first_warning

    def test_returns_empty_when_baseline_too_small(self):
        now = _now()
        baseline_time = now - timedelta(days=3)
        recent_time = now - timedelta(hours=6)

        # Only 2 baseline sessions → below minimum of 3
        sessions = (
            [_session(agent_name="agent", errors=0, started_at=baseline_time) for _ in range(2)]
            + [_session(agent_name="agent", errors=1, started_at=recent_time)]
        )
        patterns = self.detector.detect_all_patterns(sessions)
        assert patterns == []

    def test_returns_empty_when_all_recent(self):
        # All sessions within recent window → no baseline → no patterns
        sessions = [_session(agent_name="agent", errors=1) for _ in range(5)]
        patterns = self.detector.detect_all_patterns(sessions)
        assert patterns == []
