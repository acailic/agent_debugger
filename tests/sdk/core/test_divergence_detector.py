"""Unit tests for agent_debugger_sdk.core.divergence_detector."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from agent_debugger_sdk.core.divergence_detector import (
    DivergencePoint,
    DivergenceSeverity,
    DivergenceType,
    SessionComparison,
    _avg_branching_factor,
    _build_event_tree,
    _calculate_session_duration,
    _calculate_structural_similarity,
    _compare_checkpoint_states,
    _compare_decision_patterns,
    _compare_tool_usage,
    _count_divergences_by_type,
    _get_event_distribution,
    _max_tree_depth,
    _pair_checkpoints_by_sequence,
    _severity_for_count_difference,
    _severity_for_timing_difference,
    analyze_behavioral_divergence,
    analyze_temporal_divergence,
    compare_session_structures,
    detect_divergences,
)
from agent_debugger_sdk.core.events import EventType, TraceEvent


def make_event(
    event_type: EventType = EventType.AGENT_START,
    session_id: str = "sess-1",
    parent_id: str | None = None,
    timestamp: datetime | None = None,
) -> TraceEvent:
    return TraceEvent(
        id=str(uuid.uuid4()),
        session_id=session_id,
        event_type=event_type,
        parent_id=parent_id,
        timestamp=timestamp or datetime.now(timezone.utc),
    )


def make_decision_event(
    session_id: str = "sess-1",
    confidence: float = 0.9,
) -> TraceEvent:
    e = make_event(event_type=EventType.DECISION, session_id=session_id)
    e.confidence = confidence  # type: ignore[attr-defined]
    return e


def make_tool_event(
    session_id: str = "sess-1",
    tool_name: str = "search",
) -> TraceEvent:
    e = make_event(event_type=EventType.TOOL_CALL, session_id=session_id)
    e.tool_name = tool_name  # type: ignore[attr-defined]
    return e


# ── DivergencePoint ───────────────────────────────────────────────────────────

class TestDivergencePoint:
    def test_to_dict_minimal(self):
        dp = DivergencePoint(
            divergence_type=DivergenceType.STRUCTURAL,
            severity=DivergenceSeverity.LOW,
        )
        d = dp.to_dict()
        assert d["divergence_type"] == "structural"
        assert d["severity"] == "low"
        assert d["timestamp"] is None
        assert d["primary_event_id"] is None

    def test_to_dict_with_timestamp(self):
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        dp = DivergencePoint(
            divergence_type=DivergenceType.TEMPORAL,
            severity=DivergenceSeverity.HIGH,
            timestamp=ts,
        )
        assert dp.to_dict()["timestamp"] == ts.isoformat()

    def test_to_dict_with_event_ids(self):
        dp = DivergencePoint(
            divergence_type=DivergenceType.BEHAVIORAL,
            severity=DivergenceSeverity.MEDIUM,
            primary_event_id="e1",
            secondary_event_id="e2",
        )
        d = dp.to_dict()
        assert d["primary_event_id"] == "e1"
        assert d["secondary_event_id"] == "e2"


# ── SessionComparison ─────────────────────────────────────────────────────────

class TestSessionComparison:
    def test_to_dict(self):
        sc = SessionComparison(
            primary_session_id="s1",
            secondary_session_id="s2",
            overall_divergence_score=0.3,
            structural_similarity=0.9,
        )
        d = sc.to_dict()
        assert d["primary_session_id"] == "s1"
        assert d["secondary_session_id"] == "s2"
        assert d["overall_divergence_score"] == 0.3
        assert d["divergence_points"] == []

    def test_to_dict_with_divergence_points(self):
        dp = DivergencePoint(
            divergence_type=DivergenceType.ERROR,
            severity=DivergenceSeverity.CRITICAL,
        )
        sc = SessionComparison(
            primary_session_id="s1",
            secondary_session_id="s2",
            divergence_points=[dp],
        )
        d = sc.to_dict()
        assert len(d["divergence_points"]) == 1
        assert d["divergence_points"][0]["divergence_type"] == "error"


# ── detect_divergences ────────────────────────────────────────────────────────

class TestDetectDivergences:
    def test_empty_both(self):
        result = detect_divergences([], [])
        assert result.overall_divergence_score == 0.0
        assert result.structural_similarity == 1.0
        assert result.temporal_similarity == 1.0
        assert result.behavioral_similarity == 1.0

    def test_same_events(self):
        events = [make_event(session_id="s1") for _ in range(3)]
        result = detect_divergences(events, events)
        # Identical sessions should have low divergence
        assert result.overall_divergence_score < 0.5

    def test_different_counts(self):
        primary = [make_event(session_id="s1") for _ in range(5)]
        secondary = [make_event(session_id="s2") for _ in range(2)]
        result = detect_divergences(primary, secondary)
        assert result.primary_session_id == "s1"
        assert result.secondary_session_id == "s2"
        assert len(result.divergence_points) > 0

    def test_session_ids_extracted(self):
        p = [make_event(session_id="primary-sess")]
        s = [make_event(session_id="secondary-sess")]
        result = detect_divergences(p, s)
        assert result.primary_session_id == "primary-sess"
        assert result.secondary_session_id == "secondary-sess"

    def test_summary_populated(self):
        p = [make_event(session_id="s1") for _ in range(3)]
        s = [make_event(session_id="s2") for _ in range(5)]
        result = detect_divergences(p, s)
        assert result.comparison_summary["primary_event_count"] == 3
        assert result.comparison_summary["secondary_event_count"] == 5
        assert "total_divergences" in result.comparison_summary

    def test_divergence_score_bounded(self):
        p = [make_event(session_id="s1") for _ in range(100)]
        s = [make_event(session_id="s2")]
        result = detect_divergences(p, s)
        assert 0.0 <= result.overall_divergence_score <= 1.0

    def test_primary_empty_secondary_not(self):
        s = [make_event(session_id="s2") for _ in range(3)]
        result = detect_divergences([], s)
        assert result.overall_divergence_score >= 0.0

    def test_with_checkpoints(self):
        class FakeCP:
            def __init__(self, seq: int):
                self.sequence = seq
                self.timestamp = datetime.now(timezone.utc)
                self.state = {"key": "value"}

        p = [make_event(session_id="s1")]
        s = [make_event(session_id="s2")]
        cp1 = FakeCP(1)
        cp2 = FakeCP(1)
        cp2.state = {"key": "different"}
        result = detect_divergences(p, s, [cp1], [cp2])
        # State divergence should be detected
        state_divs = [d for d in result.divergence_points if d.divergence_type == DivergenceType.STATE]
        assert len(state_divs) > 0


# ── compare_session_structures ────────────────────────────────────────────────

class TestCompareSessionStructures:
    def test_empty_sessions(self):
        result = compare_session_structures([], [])
        assert result["structural_similarity"] == 1.0

    def test_basic_comparison(self):
        p = [make_event()]
        s = [make_event()]
        result = compare_session_structures(p, s)
        assert "primary_depth" in result
        assert "secondary_depth" in result
        assert "structural_similarity" in result
        assert "event_type_distribution_primary" in result
        assert "event_type_distribution_secondary" in result

    def test_same_events_high_similarity(self):
        events = [make_event(event_type=EventType.AGENT_START)]
        result = compare_session_structures(events, events)
        assert result["structural_similarity"] >= 0.8


# ── analyze_temporal_divergence ───────────────────────────────────────────────

class TestAnalyzeTemporalDivergence:
    def test_empty_events(self):
        result = analyze_temporal_divergence([], [])
        assert result["primary_duration_seconds"] == 0.0
        assert result["secondary_duration_seconds"] == 0.0
        assert result["temporal_divergence_score"] == 0.0

    def test_duration_difference(self):
        now = datetime.now(timezone.utc)
        p = [
            make_event(timestamp=now),
            make_event(timestamp=now + timedelta(seconds=10)),
        ]
        s = [
            make_event(timestamp=now),
            make_event(timestamp=now + timedelta(seconds=30)),
        ]
        result = analyze_temporal_divergence(p, s)
        assert result["primary_duration_seconds"] == pytest.approx(10.0, abs=0.1)
        assert result["secondary_duration_seconds"] == pytest.approx(30.0, abs=0.1)
        assert result["duration_difference_seconds"] == pytest.approx(20.0, abs=0.1)

    def test_result_has_timing_differences_key(self):
        result = analyze_temporal_divergence([], [])
        assert "timing_differences" in result


# ── analyze_behavioral_divergence ─────────────────────────────────────────────

class TestAnalyzeBehavioralDivergence:
    def test_empty_events(self):
        result = analyze_behavioral_divergence([], [])
        assert result["primary_decision_count"] == 0
        assert result["secondary_decision_count"] == 0
        assert result["behavioral_divergence_score"] == 0.0

    def test_decision_count_difference(self):
        p = [make_decision_event("s1", confidence=0.9) for _ in range(3)]
        s = [make_decision_event("s2", confidence=0.9)]
        result = analyze_behavioral_divergence(p, s)
        assert result["primary_decision_count"] == 3
        assert result["secondary_decision_count"] == 1

    def test_tool_divergence_detected(self):
        p = [make_tool_event("s1", "search"), make_tool_event("s1", "read_file")]
        s = [make_tool_event("s2", "search")]
        result = analyze_behavioral_divergence(p, s)
        assert result["primary_tool_call_count"] == 2
        assert result["secondary_tool_call_count"] == 1
        # read_file only in primary → divergence
        assert len(result["tool_divergences"]) > 0

    def test_same_tools_no_divergence(self):
        p = [make_tool_event("s1", "search")]
        s = [make_tool_event("s2", "search")]
        result = analyze_behavioral_divergence(p, s)
        assert result["behavioral_divergence_score"] == 0.0


# ── Internal helpers ──────────────────────────────────────────────────────────

class TestBuildEventTree:
    def test_empty(self):
        assert _build_event_tree([]) == {}

    def test_flat(self):
        e1 = make_event()
        e2 = make_event()
        tree = _build_event_tree([e1, e2])
        assert e1.id in tree
        assert e2.id in tree

    def test_parent_child(self):
        parent = make_event()
        child = make_event(parent_id=parent.id)
        tree = _build_event_tree([parent, child])
        assert child.id in tree[parent.id]


class TestMaxTreeDepth:
    def test_empty(self):
        assert _max_tree_depth({}) == 0

    def test_single_node(self):
        tree = {"a": []}
        assert _max_tree_depth(tree) == 0

    def test_depth_one(self):
        tree = {"a": ["b"], "b": []}
        assert _max_tree_depth(tree) == 1

    def test_depth_two(self):
        tree = {"a": ["b"], "b": ["c"], "c": []}
        assert _max_tree_depth(tree) == 2


class TestAvgBranchingFactor:
    def test_empty(self):
        assert _avg_branching_factor({}) == 0.0

    def test_no_children(self):
        tree = {"a": [], "b": []}
        assert _avg_branching_factor(tree) == 0.0

    def test_uniform(self):
        tree = {"a": ["b", "c"], "b": [], "c": []}
        # branches: a=2, b=0, c=0 → avg = 2/3
        assert _avg_branching_factor(tree) == pytest.approx(2 / 3, abs=0.01)


class TestGetEventDistribution:
    def test_empty(self):
        assert _get_event_distribution([]) == {}

    def test_counts(self):
        events = [
            make_event(EventType.AGENT_START),
            make_event(EventType.TOOL_CALL),
            make_event(EventType.TOOL_CALL),
        ]
        dist = _get_event_distribution(events)
        assert dist[str(EventType.TOOL_CALL)] == 2
        assert dist[str(EventType.AGENT_START)] == 1


class TestCalculateStructuralSimilarity:
    def test_both_empty(self):
        assert _calculate_structural_similarity({}, {}) == 1.0

    def test_one_empty(self):
        assert _calculate_structural_similarity({"a": []}, {}) == 0.0

    def test_identical(self):
        tree = {"a": ["b"], "b": []}
        sim = _calculate_structural_similarity(tree, tree)
        assert sim == pytest.approx(1.0, abs=0.01)


class TestCalculateSessionDuration:
    def test_empty(self):
        assert _calculate_session_duration([]) == 0.0

    def test_no_timestamps(self):
        e = make_event()
        e.timestamp = None  # type: ignore[assignment]
        assert _calculate_session_duration([e]) == 0.0

    def test_duration(self):
        now = datetime.now(timezone.utc)
        e1 = make_event(timestamp=now)
        e2 = make_event(timestamp=now + timedelta(seconds=5))
        assert _calculate_session_duration([e1, e2]) == pytest.approx(5.0, abs=0.01)


class TestCompareDecisionPatterns:
    def test_empty(self):
        assert _compare_decision_patterns([], []) == []

    def test_similar_confidence_no_diff(self):
        p = [make_decision_event(confidence=0.9)]
        s = [make_decision_event(confidence=0.85)]
        diffs = _compare_decision_patterns(p, s)
        assert diffs == []  # diff < 0.2 threshold

    def test_significant_confidence_diff(self):
        p = [make_decision_event(confidence=0.9)]
        s = [make_decision_event(confidence=0.3)]
        diffs = _compare_decision_patterns(p, s)
        assert len(diffs) == 1
        assert diffs[0]["confidence_difference"] == pytest.approx(0.6, abs=0.01)

    def test_no_confidence_attribute(self):
        p = [make_event(EventType.DECISION)]
        s = [make_event(EventType.DECISION)]
        # No confidence attr → no diffs
        assert _compare_decision_patterns(p, s) == []


class TestCompareToolUsage:
    def test_empty(self):
        assert _compare_tool_usage([], []) == []

    def test_shared_tools_no_diff(self):
        p = [make_tool_event(tool_name="search")]
        s = [make_tool_event(tool_name="search")]
        assert _compare_tool_usage(p, s) == []

    def test_exclusive_tool_in_primary(self):
        p = [make_tool_event(tool_name="write_file")]
        s = []
        diffs = _compare_tool_usage(p, s)
        assert any(d["tool_name"] == "write_file" for d in diffs)

    def test_exclusive_tool_in_secondary(self):
        p = []
        s = [make_tool_event(tool_name="delete_file")]
        diffs = _compare_tool_usage(p, s)
        assert any(d["tool_name"] == "delete_file" for d in diffs)


class TestCountDivergencesByType:
    def test_empty(self):
        assert _count_divergences_by_type([]) == {}

    def test_counts(self):
        points = [
            DivergencePoint(divergence_type=DivergenceType.STRUCTURAL, severity=DivergenceSeverity.LOW),
            DivergencePoint(divergence_type=DivergenceType.STRUCTURAL, severity=DivergenceSeverity.HIGH),
            DivergencePoint(divergence_type=DivergenceType.TEMPORAL, severity=DivergenceSeverity.MEDIUM),
        ]
        counts = _count_divergences_by_type(points)
        assert counts["structural"] == 2
        assert counts["temporal"] == 1


class TestPairCheckpointsBySequence:
    def test_empty(self):
        assert _pair_checkpoints_by_sequence([], []) == []

    def test_matching_sequences(self):
        class FakeCP:
            def __init__(self, seq: int):
                self.sequence = seq

        p = [FakeCP(1), FakeCP(2)]
        s = [FakeCP(1), FakeCP(3)]
        pairs = _pair_checkpoints_by_sequence(p, s)
        # Sequences 1, 2, 3
        assert len(pairs) == 3
        seq_map = {pp.sequence if pp else None: (pp, sp) for pp, sp in pairs}
        pp1, sp1 = seq_map[1]
        assert pp1.sequence == 1
        assert sp1.sequence == 1


class TestCompareCheckpointStates:
    def test_no_state(self):
        class FakeCP:
            state = None

        result = _compare_checkpoint_states(FakeCP(), FakeCP())
        assert result["significant_difference"] is False
        assert result["divergence_score"] == 0.0

    def test_identical_state(self):
        class FakeCP:
            state = {"key": "value"}

        result = _compare_checkpoint_states(FakeCP(), FakeCP())
        assert result["significant_difference"] is False

    def test_different_state(self):
        class FakeCP1:
            state = {"key": "a"}

        class FakeCP2:
            state = {"key": "b"}

        result = _compare_checkpoint_states(FakeCP1(), FakeCP2())
        assert result["significant_difference"] is True
        assert result["divergence_score"] > 0.0

    def test_extra_key_in_one(self):
        class FakeCP1:
            state = {"k1": "v1", "k2": "v2"}

        class FakeCP2:
            state = {"k1": "v1"}

        result = _compare_checkpoint_states(FakeCP1(), FakeCP2())
        assert result["significant_difference"] is True


class TestSeverityHelpers:
    def test_count_difference_severity(self):
        assert _severity_for_count_difference(1) == DivergenceSeverity.LOW
        assert _severity_for_count_difference(6) == DivergenceSeverity.MEDIUM
        assert _severity_for_count_difference(11) == DivergenceSeverity.HIGH
        assert _severity_for_count_difference(21) == DivergenceSeverity.CRITICAL

    def test_timing_difference_severity(self):
        assert _severity_for_timing_difference(10.0) == DivergenceSeverity.LOW
        assert _severity_for_timing_difference(35.0) == DivergenceSeverity.MEDIUM
        assert _severity_for_timing_difference(65.0) == DivergenceSeverity.HIGH


# ── DivergenceType / DivergenceSeverity enums ────────────────────────────────

class TestEnums:
    def test_divergence_types(self):
        assert str(DivergenceType.STRUCTURAL) == "structural"
        assert str(DivergenceType.TEMPORAL) == "temporal"
        assert str(DivergenceType.BEHAVIORAL) == "behavioral"
        assert str(DivergenceType.STATE) == "state"
        assert str(DivergenceType.ERROR) == "error"
        assert str(DivergenceType.PERFORMANCE) == "performance"

    def test_severity_levels(self):
        assert str(DivergenceSeverity.CRITICAL) == "critical"
        assert str(DivergenceSeverity.HIGH) == "high"
        assert str(DivergenceSeverity.MEDIUM) == "medium"
        assert str(DivergenceSeverity.LOW) == "low"
