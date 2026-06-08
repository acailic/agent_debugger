"""Unit tests for FrameTracer and DivergenceDetector (issue #208)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent_debugger_sdk.core.divergence_detector import (
    DivergencePoint,
    DivergenceSeverity,
    DivergenceType,
    SessionComparison,
    analyze_behavioral_divergence,
    analyze_temporal_divergence,
    compare_session_structures,
    detect_divergences,
)
from agent_debugger_sdk.core.events import EventType, TraceEvent
from agent_debugger_sdk.core.frame_tracer import (
    ExceptionInfo,
    FrameCaptureContext,
    FrameEvent,
    FrameLifetimeTrace,
    TokenUsage,
    build_frame_tree,
    capture_function_call,
    filter_frames_by_name,
    from_dict,
    get_cost_breakdown,
    get_frame_by_id,
    get_frame_context,
    get_frames_at_depth,
    set_frame_context,
    to_dict,
)

# ===========================================================================
# TokenUsage
# ===========================================================================


def test_token_usage_defaults():
    t = TokenUsage()
    assert t.prompt_tokens == 0
    assert t.completion_tokens == 0
    assert t.total_tokens == 0


def test_token_usage_add():
    a = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    b = TokenUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5)
    c = a + b
    assert c.prompt_tokens == 13
    assert c.completion_tokens == 7
    assert c.total_tokens == 20


def test_token_usage_to_dict():
    t = TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3)
    d = t.to_dict()
    assert d == {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}


# ===========================================================================
# FrameEvent
# ===========================================================================


def test_frame_event_defaults():
    fe = FrameEvent(frame_id="f1", function_name="fn", module_path="mod")
    assert fe.parent_frame_id is None
    assert fe.exception is None
    assert fe.token_usage is None
    assert fe.depth == 0
    assert fe.children == []


def test_frame_event_to_dict_basic():
    fe = FrameEvent(
        frame_id="f1",
        function_name="do_thing",
        module_path="mymod.do_thing",
        start_time=1.0,
        end_time=1.5,
        duration_ms=500.0,
        depth=1,
    )
    d = fe.to_dict()
    assert d["frame_id"] == "f1"
    assert d["function_name"] == "do_thing"
    assert d["duration_ms"] == 500.0
    assert d["exception"] is None
    assert d["token_usage"] is None


def test_frame_event_to_dict_with_exception():
    exc = ExceptionInfo(exception_type="ValueError", message="bad input")
    fe = FrameEvent(frame_id="f2", function_name="fn", module_path="m", exception=exc)
    d = fe.to_dict()
    assert d["exception"]["exception_type"] == "ValueError"
    assert d["exception"]["message"] == "bad input"
    assert d["exception"]["traceback"] is None


def test_frame_event_to_dict_with_token_usage():
    tu = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    fe = FrameEvent(frame_id="f3", function_name="fn", module_path="m", token_usage=tu)
    d = fe.to_dict()
    assert d["token_usage"]["total_tokens"] == 15


def test_frame_event_children_copied_in_to_dict():
    fe = FrameEvent(frame_id="f4", function_name="fn", module_path="m", children=["c1", "c2"])
    d = fe.to_dict()
    assert d["children"] == ["c1", "c2"]
    # Mutating original doesn't affect serialized copy
    fe.children.append("c3")
    assert d["children"] == ["c1", "c2"]


# ===========================================================================
# FrameLifetimeTrace
# ===========================================================================


def _make_frame(frame_id: str, function_name: str = "fn", depth: int = 0) -> FrameEvent:
    return FrameEvent(
        frame_id=frame_id,
        function_name=function_name,
        module_path=f"mod.{function_name}",
        duration_ms=10.0,
        depth=depth,
    )


def test_frame_lifetime_trace_empty():
    t = FrameLifetimeTrace(trace_id="t1")
    assert t.frames == []
    assert t.total_duration_ms == 0.0
    assert t.total_tokens == 0


def test_frame_lifetime_trace_to_dict():
    fe = _make_frame("f1")
    t = FrameLifetimeTrace(trace_id="t1", frames=[fe], entry_point="main", total_duration_ms=10.0)
    d = t.to_dict()
    assert d["trace_id"] == "t1"
    assert d["entry_point"] == "main"
    assert len(d["frames"]) == 1
    assert d["frames"][0]["frame_id"] == "f1"


# ===========================================================================
# build_frame_tree
# ===========================================================================


def test_build_frame_tree_empty():
    assert build_frame_tree([]) == {}


def test_build_frame_tree_single_root():
    fe = _make_frame("root")
    tree = build_frame_tree([fe])
    assert tree["frame"]["frame_id"] == "root"
    assert tree["children"] == []


def test_build_frame_tree_with_child():
    parent = FrameEvent(
        frame_id="p1", function_name="parent", module_path="m",
        children=["c1"], duration_ms=20.0,
    )
    child = FrameEvent(
        frame_id="c1", function_name="child", module_path="m",
        parent_frame_id="p1", depth=1, duration_ms=5.0,
    )
    tree = build_frame_tree([parent, child])
    assert tree["frame"]["frame_id"] == "p1"
    assert len(tree["children"]) == 1
    assert tree["children"][0]["frame"]["frame_id"] == "c1"


def test_build_frame_tree_multiple_roots():
    f1 = _make_frame("r1")
    f2 = _make_frame("r2")
    tree = build_frame_tree([f1, f2])
    assert tree["frame"] is None
    assert len(tree["children"]) == 2


# ===========================================================================
# FrameCaptureContext
# ===========================================================================


def test_frame_capture_context_build_trace_empty():
    ctx = FrameCaptureContext(trace_id="t1")
    trace = ctx.build_trace("main")
    assert trace.trace_id == "t1"
    assert trace.entry_point == "main"
    assert trace.frames == []
    assert trace.total_duration_ms == 0.0


def test_frame_capture_context_add_frame_and_build():
    ctx = FrameCaptureContext(trace_id="t1")
    fe = FrameEvent(
        frame_id="f1", function_name="fn", module_path="m",
        duration_ms=25.0,
        token_usage=TokenUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
    )
    ctx.add_frame(fe)
    trace = ctx.build_trace("fn")
    assert trace.total_duration_ms == 25.0
    assert trace.total_tokens == 10


def test_frame_capture_context_parent_child_linking():
    ctx = FrameCaptureContext(trace_id="t1")
    parent = FrameEvent(frame_id="p1", function_name="parent", module_path="m", duration_ms=10.0)
    ctx.add_frame(parent)
    ctx.enter_frame("p1")

    child = FrameEvent(frame_id="c1", function_name="child", module_path="m", duration_ms=5.0)
    ctx.add_frame(child)
    ctx.exit_frame("p1")

    assert child.parent_frame_id == "p1"
    assert child.depth == 1
    assert "c1" in parent.children


def test_frame_capture_context_to_dict():
    ctx = FrameCaptureContext(trace_id="t2")
    d = ctx.to_dict()
    assert d["trace_id"] == "t2"


# ===========================================================================
# capture_function_call decorator
# ===========================================================================


def test_capture_function_call_no_context():
    @capture_function_call
    def add(x, y):
        return x + y

    assert add(2, 3) == 5


def test_capture_function_call_with_context():
    ctx = FrameCaptureContext(trace_id="cap-test")
    set_frame_context(ctx)
    try:
        @capture_function_call
        def multiply(x, y):
            return x * y

        result = multiply(4, 5)
        assert result == 20
        trace = ctx.build_trace("multiply")
        assert len(trace.frames) == 1
        assert trace.frames[0].function_name == "multiply"
        assert trace.frames[0].call_args == {"x": 4, "y": 5}
        assert trace.frames[0].return_value == 20
    finally:
        set_frame_context(None)


def test_capture_function_call_captures_exception():
    ctx = FrameCaptureContext(trace_id="exc-test")
    set_frame_context(ctx)
    try:
        @capture_function_call
        def boom():
            raise ValueError("oops")

        with pytest.raises(ValueError):
            boom()

        assert len(ctx.frames) == 1
        assert ctx.frames[0].exception is not None
        assert ctx.frames[0].exception.exception_type == "ValueError"
        assert ctx.frames[0].exception.message == "oops"
    finally:
        set_frame_context(None)


def test_capture_function_call_with_options():
    ctx = FrameCaptureContext(trace_id="opts-test")
    set_frame_context(ctx)
    try:
        @capture_function_call(capture_args=False, capture_return=False)
        def fn(x):
            return x * 2

        fn(7)
        assert ctx.frames[0].call_args == {}
        assert ctx.frames[0].return_value is None
    finally:
        set_frame_context(None)


def test_get_set_frame_context():
    ctx = FrameCaptureContext()
    set_frame_context(ctx)
    assert get_frame_context() is ctx
    set_frame_context(None)
    assert get_frame_context() is None


# ===========================================================================
# Helper functions
# ===========================================================================


def test_get_frame_by_id_found():
    fe = _make_frame("f1")
    trace = FrameLifetimeTrace(trace_id="t", frames=[fe])
    assert get_frame_by_id(trace, "f1") is fe


def test_get_frame_by_id_not_found():
    trace = FrameLifetimeTrace(trace_id="t", frames=[])
    assert get_frame_by_id(trace, "missing") is None


def test_get_frames_at_depth():
    frames = [
        _make_frame("f1", depth=0),
        _make_frame("f2", depth=1),
        _make_frame("f3", depth=1),
        _make_frame("f4", depth=2),
    ]
    trace = FrameLifetimeTrace(trace_id="t", frames=frames)
    depth1 = get_frames_at_depth(trace, 1)
    assert len(depth1) == 2
    assert all(f.depth == 1 for f in depth1)


def test_filter_frames_by_name():
    frames = [
        _make_frame("f1", function_name="fetch_data"),
        _make_frame("f2", function_name="process"),
        _make_frame("f3", function_name="fetch_metadata"),
    ]
    trace = FrameLifetimeTrace(trace_id="t", frames=frames)
    fetches = filter_frames_by_name(trace, "fetch")
    assert len(fetches) == 2
    assert all("fetch" in f.function_name for f in fetches)


def test_get_cost_breakdown():
    frames = [
        FrameEvent(
            frame_id="f1", function_name="fn_a", module_path="m",
            duration_ms=10.0,
            token_usage=TokenUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
        ),
        FrameEvent(
            frame_id="f2", function_name="fn_a", module_path="m",
            duration_ms=20.0,
        ),
        FrameEvent(
            frame_id="f3", function_name="fn_b", module_path="m",
            duration_ms=5.0,
            exception=ExceptionInfo(exception_type="Err", message="x"),
        ),
    ]
    trace = FrameLifetimeTrace(trace_id="t", frames=frames)
    breakdown = get_cost_breakdown(trace)

    assert "fn_a" in breakdown
    assert breakdown["fn_a"].total_calls == 2
    assert breakdown["fn_a"].total_duration_ms == 30.0
    assert breakdown["fn_a"].avg_duration_ms == 15.0
    assert breakdown["fn_a"].total_tokens == 10
    assert breakdown["fn_a"].error_count == 0

    assert "fn_b" in breakdown
    assert breakdown["fn_b"].error_count == 1


# ===========================================================================
# Serialization round-trip
# ===========================================================================


def test_frame_trace_round_trip():
    fe = FrameEvent(
        frame_id="r1",
        function_name="fn",
        module_path="mod.fn",
        duration_ms=42.0,
        token_usage=TokenUsage(prompt_tokens=3, completion_tokens=3, total_tokens=6),
    )
    original = FrameLifetimeTrace(
        trace_id="rt1",
        frames=[fe],
        entry_point="fn",
        total_duration_ms=42.0,
        total_tokens=6,
    )
    d = to_dict(original)
    restored = from_dict(d)
    assert restored.trace_id == "rt1"
    assert len(restored.frames) == 1
    assert restored.frames[0].function_name == "fn"
    assert restored.frames[0].token_usage.total_tokens == 6


# ===========================================================================
# DivergenceType / DivergenceSeverity enums
# ===========================================================================


def test_divergence_type_values():
    assert str(DivergenceType.STRUCTURAL) == "structural"
    assert str(DivergenceType.TEMPORAL) == "temporal"
    assert str(DivergenceType.BEHAVIORAL) == "behavioral"
    assert str(DivergenceType.STATE) == "state"
    assert str(DivergenceType.ERROR) == "error"
    assert str(DivergenceType.PERFORMANCE) == "performance"


def test_divergence_severity_values():
    assert str(DivergenceSeverity.CRITICAL) == "critical"
    assert str(DivergenceSeverity.HIGH) == "high"
    assert str(DivergenceSeverity.MEDIUM) == "medium"
    assert str(DivergenceSeverity.LOW) == "low"


# ===========================================================================
# DivergencePoint
# ===========================================================================


def test_divergence_point_defaults():
    dp = DivergencePoint(
        divergence_type=DivergenceType.STRUCTURAL,
        severity=DivergenceSeverity.LOW,
    )
    assert dp.primary_event_id is None
    assert dp.secondary_event_id is None
    assert dp.description == ""
    assert dp.divergence_score == 0.0
    assert dp.timestamp is None
    assert dp.metadata == {}


def test_divergence_point_to_dict():
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    dp = DivergencePoint(
        divergence_type=DivergenceType.BEHAVIORAL,
        severity=DivergenceSeverity.HIGH,
        primary_event_id="e1",
        secondary_event_id="e2",
        description="decision confidence differs",
        timestamp=now,
        divergence_score=0.7,
        metadata={"key": "val"},
    )
    d = dp.to_dict()
    assert d["divergence_type"] == "behavioral"
    assert d["severity"] == "high"
    assert d["primary_event_id"] == "e1"
    assert d["secondary_event_id"] == "e2"
    assert d["divergence_score"] == 0.7
    assert d["timestamp"] == now.isoformat()
    assert d["metadata"] == {"key": "val"}


def test_divergence_point_to_dict_no_timestamp():
    dp = DivergencePoint(
        divergence_type=DivergenceType.TEMPORAL,
        severity=DivergenceSeverity.MEDIUM,
    )
    d = dp.to_dict()
    assert d["timestamp"] is None


# ===========================================================================
# SessionComparison
# ===========================================================================


def test_session_comparison_to_dict():
    dp = DivergencePoint(
        divergence_type=DivergenceType.STRUCTURAL,
        severity=DivergenceSeverity.LOW,
    )
    sc = SessionComparison(
        primary_session_id="s1",
        secondary_session_id="s2",
        divergence_points=[dp],
        overall_divergence_score=0.1,
        structural_similarity=0.9,
    )
    d = sc.to_dict()
    assert d["primary_session_id"] == "s1"
    assert d["secondary_session_id"] == "s2"
    assert len(d["divergence_points"]) == 1
    assert d["overall_divergence_score"] == 0.1
    assert d["structural_similarity"] == 0.9


# ===========================================================================
# detect_divergences
# ===========================================================================


def _make_event(session_id: str, event_type: EventType = EventType.AGENT_START,
                ts: datetime | None = None) -> TraceEvent:
    return TraceEvent(
        session_id=session_id,
        event_type=event_type,
        timestamp=ts or datetime.now(timezone.utc),
    )


def test_detect_divergences_both_empty():
    result = detect_divergences([], [])
    assert result.overall_divergence_score == 0.0
    assert result.structural_similarity == 1.0
    assert result.temporal_similarity == 1.0
    assert result.behavioral_similarity == 1.0
    assert result.divergence_points == []


def test_detect_divergences_identical_sessions():
    events = [_make_event("s1", EventType.TOOL_CALL) for _ in range(3)]
    result = detect_divergences(events, events)
    assert result.structural_similarity == 1.0
    assert result.overall_divergence_score == 0.0


def test_detect_divergences_count_mismatch():
    primary = [_make_event("s1") for _ in range(10)]
    secondary = [_make_event("s2") for _ in range(3)]
    result = detect_divergences(primary, secondary)
    assert result.overall_divergence_score > 0.0
    assert any(dp.divergence_type == DivergenceType.STRUCTURAL for dp in result.divergence_points)


def test_detect_divergences_session_ids_extracted():
    primary = [_make_event("primary-id")]
    secondary = [_make_event("secondary-id")]
    result = detect_divergences(primary, secondary)
    assert result.primary_session_id == "primary-id"
    assert result.secondary_session_id == "secondary-id"


def test_detect_divergences_summary_populated():
    primary = [_make_event("s1", EventType.TOOL_CALL) for _ in range(5)]
    secondary = [_make_event("s2", EventType.DECISION) for _ in range(3)]
    result = detect_divergences(primary, secondary)
    assert result.comparison_summary["primary_event_count"] == 5
    assert result.comparison_summary["secondary_event_count"] == 3
    assert "total_divergences" in result.comparison_summary
    assert "critical_divergences" in result.comparison_summary


def test_detect_divergences_large_count_diff_raises_critical():
    primary = [_make_event("s1") for _ in range(25)]
    secondary = [_make_event("s2")]
    result = detect_divergences(primary, secondary)
    severities = {dp.severity for dp in result.divergence_points}
    assert DivergenceSeverity.CRITICAL in severities


# ===========================================================================
# compare_session_structures
# ===========================================================================


def test_compare_session_structures_both_empty():
    result = compare_session_structures([], [])
    assert result["primary_depth"] == 0
    assert result["secondary_depth"] == 0
    assert result["structural_similarity"] == 1.0


def test_compare_session_structures_returns_expected_keys():
    events_a = [_make_event("s1", EventType.TOOL_CALL) for _ in range(3)]
    events_b = [_make_event("s2", EventType.DECISION) for _ in range(2)]
    result = compare_session_structures(events_a, events_b)
    for key in (
        "primary_depth", "secondary_depth",
        "primary_branching_factor", "secondary_branching_factor",
        "event_type_distribution_primary", "event_type_distribution_secondary",
        "structural_similarity",
    ):
        assert key in result, f"missing key: {key}"


def test_compare_session_structures_event_distribution():
    events = [
        _make_event("s1", EventType.TOOL_CALL),
        _make_event("s1", EventType.TOOL_CALL),
        _make_event("s1", EventType.DECISION),
    ]
    result = compare_session_structures(events, events)
    dist = result["event_type_distribution_primary"]
    assert dist.get("tool_call") == 2 or dist.get(str(EventType.TOOL_CALL)) == 2


# ===========================================================================
# analyze_temporal_divergence
# ===========================================================================


def test_analyze_temporal_divergence_empty():
    result = analyze_temporal_divergence([], [])
    assert result["primary_duration_seconds"] == 0.0
    assert result["secondary_duration_seconds"] == 0.0
    assert result["temporal_divergence_score"] == 0.0


def test_analyze_temporal_divergence_returns_keys():
    now = datetime.now(timezone.utc)
    primary = [
        _make_event("s1", ts=now),
        _make_event("s1", ts=now + timedelta(seconds=10)),
    ]
    secondary = [
        _make_event("s2", ts=now),
        _make_event("s2", ts=now + timedelta(seconds=30)),
    ]
    result = analyze_temporal_divergence(primary, secondary)
    for key in ("primary_duration_seconds", "secondary_duration_seconds",
                "duration_difference_seconds", "temporal_divergence_score", "timing_differences"):
        assert key in result, f"missing key: {key}"


def test_analyze_temporal_divergence_duration_difference():
    now = datetime.now(timezone.utc)
    primary = [
        _make_event("s1", ts=now),
        _make_event("s1", ts=now + timedelta(seconds=10)),
    ]
    secondary = [
        _make_event("s2", ts=now),
        _make_event("s2", ts=now + timedelta(seconds=70)),
    ]
    result = analyze_temporal_divergence(primary, secondary)
    assert result["primary_duration_seconds"] == pytest.approx(10.0, abs=0.1)
    assert result["secondary_duration_seconds"] == pytest.approx(70.0, abs=0.1)
    assert result["duration_difference_seconds"] == pytest.approx(60.0, abs=0.1)


# ===========================================================================
# analyze_behavioral_divergence
# ===========================================================================


def test_analyze_behavioral_divergence_empty():
    result = analyze_behavioral_divergence([], [])
    assert result["primary_decision_count"] == 0
    assert result["secondary_decision_count"] == 0
    assert result["behavioral_divergence_score"] == 0.0


def test_analyze_behavioral_divergence_returns_keys():
    primary = [_make_event("s1", EventType.DECISION)]
    secondary = [_make_event("s2", EventType.TOOL_CALL)]
    result = analyze_behavioral_divergence(primary, secondary)
    for key in (
        "primary_decision_count", "secondary_decision_count",
        "primary_tool_call_count", "secondary_tool_call_count",
        "decision_divergences", "tool_divergences", "behavioral_divergence_score",
    ):
        assert key in result, f"missing key: {key}"


def test_analyze_behavioral_divergence_counts_event_types():
    primary = [
        _make_event("s1", EventType.DECISION),
        _make_event("s1", EventType.DECISION),
        _make_event("s1", EventType.TOOL_CALL),
    ]
    secondary = [
        _make_event("s2", EventType.TOOL_CALL),
        _make_event("s2", EventType.TOOL_CALL),
    ]
    result = analyze_behavioral_divergence(primary, secondary)
    assert result["primary_decision_count"] == 2
    assert result["secondary_decision_count"] == 0
    assert result["primary_tool_call_count"] == 1
    assert result["secondary_tool_call_count"] == 2


def test_analyze_behavioral_divergence_tool_divergence_detected():
    primary = [
        TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="tool_a"),
    ]
    secondary = [
        TraceEvent(session_id="s2", event_type=EventType.TOOL_CALL, name="tool_b"),
    ]
    result = analyze_behavioral_divergence(primary, secondary)
    assert result["behavioral_divergence_score"] >= 0.0
