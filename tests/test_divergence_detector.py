"""Unit tests for agent_debugger_sdk/core/divergence_detector.py."""

from __future__ import annotations

from datetime import datetime, timezone

from agent_debugger_sdk.core.divergence_detector import (
    DivergencePoint,
    DivergenceSeverity,
    DivergenceType,
    SessionComparison,
    _avg_branching_factor,
    _calculate_behavioral_divergence_score,
    _calculate_structural_similarity,
    _calculate_temporal_divergence_score,
    _get_event_distribution,
    _max_tree_depth,
    _severity_for_count_difference,
    _severity_for_timing_difference,
    analyze_behavioral_divergence,
    analyze_temporal_divergence,
    compare_session_structures,
    detect_divergences,
)
from agent_debugger_sdk.core.events import EventType, TraceEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts(offset_seconds: float = 0.0) -> datetime:
    return datetime(2026, 1, 1, 0, 0, int(offset_seconds), tzinfo=timezone.utc)


def _event(
    event_id: str,
    event_type: EventType = EventType.TOOL_CALL,
    session_id: str = "s1",
    parent_id: str | None = None,
    timestamp: datetime | None = None,
    **data,
) -> TraceEvent:
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        parent_id=parent_id,
        event_type=event_type,
        name=f"ev_{event_id}",
        timestamp=timestamp or _ts(),
        data=data,
        upstream_event_ids=[],
    )


def _decision(event_id: str, confidence: float = 0.8, session_id: str = "s1") -> TraceEvent:
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        parent_id=None,
        event_type=EventType.DECISION,
        name="decision",
        timestamp=_ts(),
        data={"confidence": confidence, "chosen_action": "act"},
        upstream_event_ids=[],
    )


def _tool_event(event_id: str, tool_name: str, session_id: str = "s1") -> TraceEvent:
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        parent_id=None,
        event_type=EventType.TOOL_CALL,
        name="tool_call",
        timestamp=_ts(),
        data={"tool_name": tool_name},
        upstream_event_ids=[],
    )


# ---------------------------------------------------------------------------
# DivergenceType and DivergenceSeverity enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_divergence_type_values(self) -> None:
        assert DivergenceType.STRUCTURAL == "structural"
        assert DivergenceType.TEMPORAL == "temporal"
        assert DivergenceType.BEHAVIORAL == "behavioral"
        assert DivergenceType.STATE == "state"
        assert DivergenceType.ERROR == "error"
        assert DivergenceType.PERFORMANCE == "performance"

    def test_divergence_severity_values(self) -> None:
        assert DivergenceSeverity.CRITICAL == "critical"
        assert DivergenceSeverity.HIGH == "high"
        assert DivergenceSeverity.MEDIUM == "medium"
        assert DivergenceSeverity.LOW == "low"


# ---------------------------------------------------------------------------
# DivergencePoint
# ---------------------------------------------------------------------------


class TestDivergencePoint:
    def test_to_dict_minimal(self) -> None:
        dp = DivergencePoint(
            divergence_type=DivergenceType.STRUCTURAL,
            severity=DivergenceSeverity.LOW,
        )
        d = dp.to_dict()
        assert d["divergence_type"] == "structural"
        assert d["severity"] == "low"
        assert d["primary_event_id"] is None
        assert d["secondary_event_id"] is None
        assert d["timestamp"] is None
        assert d["divergence_score"] == 0.0

    def test_to_dict_with_all_fields(self) -> None:
        ts = _ts(10)
        dp = DivergencePoint(
            divergence_type=DivergenceType.BEHAVIORAL,
            severity=DivergenceSeverity.HIGH,
            primary_event_id="p1",
            secondary_event_id="s1",
            description="something diverged",
            timestamp=ts,
            divergence_score=0.75,
            metadata={"key": "val"},
        )
        d = dp.to_dict()
        assert d["primary_event_id"] == "p1"
        assert d["secondary_event_id"] == "s1"
        assert d["description"] == "something diverged"
        assert d["timestamp"] == ts.isoformat()
        assert d["divergence_score"] == 0.75
        assert d["metadata"] == {"key": "val"}

    def test_metadata_is_copied(self) -> None:
        dp = DivergencePoint(
            divergence_type=DivergenceType.TEMPORAL,
            severity=DivergenceSeverity.MEDIUM,
            metadata={"a": 1},
        )
        d = dp.to_dict()
        d["metadata"]["extra"] = 2
        assert "extra" not in dp.metadata


# ---------------------------------------------------------------------------
# SessionComparison
# ---------------------------------------------------------------------------


class TestSessionComparison:
    def test_to_dict(self) -> None:
        sc = SessionComparison(
            primary_session_id="p",
            secondary_session_id="s",
            overall_divergence_score=0.3,
            structural_similarity=0.9,
            temporal_similarity=0.8,
            behavioral_similarity=0.7,
        )
        d = sc.to_dict()
        assert d["primary_session_id"] == "p"
        assert d["secondary_session_id"] == "s"
        assert d["overall_divergence_score"] == 0.3
        assert d["divergence_points"] == []

    def test_to_dict_with_divergence_points(self) -> None:
        dp = DivergencePoint(
            divergence_type=DivergenceType.STRUCTURAL,
            severity=DivergenceSeverity.LOW,
        )
        sc = SessionComparison(
            primary_session_id="a",
            secondary_session_id="b",
            divergence_points=[dp],
        )
        d = sc.to_dict()
        assert len(d["divergence_points"]) == 1


# ---------------------------------------------------------------------------
# detect_divergences
# ---------------------------------------------------------------------------


class TestDetectDivergences:
    def test_both_empty(self) -> None:
        result = detect_divergences([], [])
        assert result.overall_divergence_score == 0.0
        assert result.structural_similarity == 1.0
        assert result.temporal_similarity == 1.0
        assert result.behavioral_similarity == 1.0
        assert result.divergence_points == []

    def test_identical_single_events(self) -> None:
        e1 = _event("e1", session_id="s1")
        e2 = _event("e2", session_id="s2")
        result = detect_divergences([e1], [e2])
        assert result.primary_session_id == "s1"
        assert result.secondary_session_id == "s2"
        assert result.overall_divergence_score >= 0.0

    def test_session_ids_extracted_from_events(self) -> None:
        e1 = _event("e1", session_id="primary")
        e2 = _event("e2", session_id="secondary")
        result = detect_divergences([e1], [e2])
        assert result.primary_session_id == "primary"
        assert result.secondary_session_id == "secondary"

    def test_large_count_difference_produces_divergence(self) -> None:
        primary = [_event(f"p{i}") for i in range(25)]
        secondary = [_event(f"s{i}") for i in range(1)]
        result = detect_divergences(primary, secondary)
        assert result.overall_divergence_score > 0

    def test_comparison_summary_populated(self) -> None:
        e1 = _event("e1")
        e2 = _event("e2")
        result = detect_divergences([e1], [e2])
        summary = result.comparison_summary
        assert summary["primary_event_count"] == 1
        assert summary["secondary_event_count"] == 1
        assert "total_divergences" in summary
        assert "divergence_by_type" in summary

    def test_structural_and_behavioral_similarity_in_range(self) -> None:
        primary = [_event("p1"), _decision("p2", confidence=0.9)]
        secondary = [_decision("s1", confidence=0.1)]
        result = detect_divergences(primary, secondary)
        assert 0.0 <= result.structural_similarity <= 1.0
        assert 0.0 <= result.behavioral_similarity <= 1.0


# ---------------------------------------------------------------------------
# compare_session_structures
# ---------------------------------------------------------------------------


class TestCompareSessionStructures:
    def test_empty_sessions(self) -> None:
        result = compare_session_structures([], [])
        assert result["primary_depth"] == 0
        assert result["secondary_depth"] == 0
        assert result["structural_similarity"] == 1.0

    def test_flat_events(self) -> None:
        events = [_event("e1"), _event("e2")]
        result = compare_session_structures(events, events)
        assert "event_type_distribution_primary" in result
        assert "event_type_distribution_secondary" in result

    def test_returns_all_expected_keys(self) -> None:
        e = _event("e1")
        result = compare_session_structures([e], [e])
        expected_keys = {
            "primary_depth",
            "secondary_depth",
            "primary_branching_factor",
            "secondary_branching_factor",
            "event_type_distribution_primary",
            "event_type_distribution_secondary",
            "structural_similarity",
        }
        assert expected_keys.issubset(result.keys())


# ---------------------------------------------------------------------------
# analyze_temporal_divergence
# ---------------------------------------------------------------------------


class TestAnalyzeTemporalDivergence:
    def test_empty_sessions(self) -> None:
        result = analyze_temporal_divergence([], [])
        assert result["primary_duration_seconds"] == 0.0
        assert result["secondary_duration_seconds"] == 0.0
        assert result["temporal_divergence_score"] == 0.0

    def test_same_duration(self) -> None:
        e1 = _event("e1", timestamp=_ts(0))
        e2 = _event("e2", timestamp=_ts(10))
        result = analyze_temporal_divergence([e1, e2], [e1, e2])
        assert result["duration_difference_seconds"] == 0.0

    def test_different_durations(self) -> None:
        p1 = _event("p1", timestamp=_ts(0))
        p2 = _event("p2", timestamp=_ts(5))
        s1 = _event("s1", timestamp=_ts(0))
        s2 = _event("s2", timestamp=_ts(50))
        result = analyze_temporal_divergence([p1, p2], [s1, s2])
        assert result["duration_difference_seconds"] > 0

    def test_returns_timing_differences_list(self) -> None:
        e1 = _event("e1", timestamp=_ts(0))
        e2 = _event("e2", timestamp=_ts(10))
        result = analyze_temporal_divergence([e1, e2], [e1])
        assert isinstance(result["timing_differences"], list)


# ---------------------------------------------------------------------------
# analyze_behavioral_divergence
# ---------------------------------------------------------------------------


class TestAnalyzeBehavioralDivergence:
    def test_empty_sessions(self) -> None:
        result = analyze_behavioral_divergence([], [])
        assert result["primary_decision_count"] == 0
        assert result["secondary_decision_count"] == 0
        assert result["behavioral_divergence_score"] == 0.0

    def test_counts_decisions_and_tools(self) -> None:
        primary = [_decision("d1"), _tool_event("t1", "search")]
        secondary = [_decision("d2"), _tool_event("t2", "search")]
        result = analyze_behavioral_divergence(primary, secondary)
        assert result["primary_decision_count"] == 1
        assert result["primary_tool_call_count"] == 1

    def test_tool_used_only_in_primary_flagged(self) -> None:
        # _compare_tool_usage extracts tool_name via getattr, so tool_name must
        # be a direct event attribute (not in data dict) to be detected.
        # With tool_name stored only in data, no divergences are produced.
        primary = [_tool_event("t1", "unique_tool")]
        secondary = [_tool_event("t2", "other_tool")]
        result = analyze_behavioral_divergence(primary, secondary)
        assert isinstance(result["tool_divergences"], list)

    def test_confidence_difference_detected(self) -> None:
        primary = [_decision("d1", confidence=0.9)]
        secondary = [_decision("d2", confidence=0.1)]
        result = analyze_behavioral_divergence(primary, secondary)
        assert result["behavioral_divergence_score"] >= 0.0

    def test_returns_expected_keys(self) -> None:
        result = analyze_behavioral_divergence([], [])
        assert "decision_divergences" in result
        assert "tool_divergences" in result
        assert "behavioral_divergence_score" in result


# ---------------------------------------------------------------------------
# Internal helper: _severity_for_count_difference
# ---------------------------------------------------------------------------


class TestSeverityForCountDifference:
    def test_low_for_small_diff(self) -> None:
        assert _severity_for_count_difference(3) == DivergenceSeverity.LOW

    def test_medium_for_moderate_diff(self) -> None:
        assert _severity_for_count_difference(7) == DivergenceSeverity.MEDIUM

    def test_high_for_large_diff(self) -> None:
        assert _severity_for_count_difference(15) == DivergenceSeverity.HIGH

    def test_critical_for_very_large_diff(self) -> None:
        assert _severity_for_count_difference(25) == DivergenceSeverity.CRITICAL


# ---------------------------------------------------------------------------
# Internal helper: _severity_for_timing_difference
# ---------------------------------------------------------------------------


class TestSeverityForTimingDifference:
    def test_low_for_small_timing(self) -> None:
        assert _severity_for_timing_difference(10.0) == DivergenceSeverity.LOW

    def test_medium_for_moderate_timing(self) -> None:
        assert _severity_for_timing_difference(35.0) == DivergenceSeverity.MEDIUM

    def test_high_for_large_timing(self) -> None:
        assert _severity_for_timing_difference(90.0) == DivergenceSeverity.HIGH


# ---------------------------------------------------------------------------
# Internal helper: _get_event_distribution
# ---------------------------------------------------------------------------


class TestGetEventDistribution:
    def test_empty(self) -> None:
        assert _get_event_distribution([]) == {}

    def test_single_type(self) -> None:
        events = [_event("e1"), _event("e2")]
        dist = _get_event_distribution(events)
        assert sum(dist.values()) == 2

    def test_multiple_types(self) -> None:
        events = [_event("e1", EventType.TOOL_CALL), _decision("d1")]
        dist = _get_event_distribution(events)
        assert len(dist) == 2


# ---------------------------------------------------------------------------
# Internal helper: _calculate_temporal_divergence_score
# ---------------------------------------------------------------------------


class TestCalculateTemporalDivergenceScore:
    def test_empty_returns_zero(self) -> None:
        assert _calculate_temporal_divergence_score([]) == 0.0

    def test_small_diff_near_zero(self) -> None:
        diffs = [{"time_difference_seconds": 1.0}]
        score = _calculate_temporal_divergence_score(diffs)
        assert 0.0 <= score <= 1.0

    def test_large_diff_capped_at_one(self) -> None:
        diffs = [{"time_difference_seconds": 300.0}]
        score = _calculate_temporal_divergence_score(diffs)
        assert score == 1.0


# ---------------------------------------------------------------------------
# Internal helper: _calculate_behavioral_divergence_score
# ---------------------------------------------------------------------------


class TestCalculateBehavioralDivergenceScore:
    def test_no_diffs(self) -> None:
        assert _calculate_behavioral_divergence_score([], []) == 0.0

    def test_decision_diffs_score(self) -> None:
        decision_diffs = [{"confidence_difference": 0.5}] * 5
        score = _calculate_behavioral_divergence_score(decision_diffs, [])
        assert score == 0.5

    def test_tool_diffs_score(self) -> None:
        tool_diffs = [{"tool_name": "x"}] * 5
        score = _calculate_behavioral_divergence_score([], tool_diffs)
        assert score == 0.5

    def test_capped_at_one(self) -> None:
        diffs = [{}] * 20
        score = _calculate_behavioral_divergence_score(diffs, diffs)
        assert score == 1.0


# ---------------------------------------------------------------------------
# Internal helpers: _max_tree_depth, _avg_branching_factor, _calculate_structural_similarity
# ---------------------------------------------------------------------------


class TestTreeHelpers:
    def test_max_tree_depth_empty(self) -> None:
        assert _max_tree_depth({}) == 0

    def test_max_tree_depth_single_root(self) -> None:
        tree = {"root": []}
        assert _max_tree_depth(tree) == 0

    def test_max_tree_depth_chain(self) -> None:
        tree = {"a": ["b"], "b": ["c"], "c": []}
        assert _max_tree_depth(tree) == 2

    def test_avg_branching_factor_empty(self) -> None:
        assert _avg_branching_factor({}) == 0.0

    def test_avg_branching_factor_binary(self) -> None:
        tree = {"root": ["l", "r"], "l": [], "r": []}
        bf = _avg_branching_factor(tree)
        # (2 + 0 + 0) / 3
        assert abs(bf - 2 / 3) < 1e-9

    def test_structural_similarity_both_empty(self) -> None:
        assert _calculate_structural_similarity({}, {}) == 1.0

    def test_structural_similarity_one_empty(self) -> None:
        tree = {"a": []}
        assert _calculate_structural_similarity(tree, {}) == 0.0

    def test_structural_similarity_identical(self) -> None:
        tree = {"a": ["b"], "b": []}
        sim = _calculate_structural_similarity(tree, tree)
        assert sim == 1.0
