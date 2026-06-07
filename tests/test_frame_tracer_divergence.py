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
    FrameCaptureContext,
    FrameEvent,
    FrameLifetimeTrace,
    TokenUsage,
    build_frame_tree,
    capture_function_call,
    filter_frames_by_name,
    from_dict,
    get_cost_breakdown,
    get_frames_at_depth,
    set_frame_context,
    to_dict,
)

# ===========================================================================
# TokenUsage
# ===========================================================================


def test_token_usage_default_values():
    t = TokenUsage()
    assert t.prompt_tokens == 0
    assert t.completion_tokens == 0
    assert t.total_tokens == 0


def test_token_usage_arithmetic():
    a = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    b = TokenUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30)
    result = a + b
    assert result.prompt_tokens == 30
    assert result.completion_tokens == 15
    assert result.total_tokens == 45


def test_token_usage_to_dict():
    t = TokenUsage(prompt_tokens=3, completion_tokens=7, total_tokens=10)
    d = t.to_dict()
    assert d == {"prompt_tokens": 3, "completion_tokens": 7, "total_tokens": 10}


# ===========================================================================
# FrameEvent
# ===========================================================================


def test_frame_event_minimal_construction():
    frame = FrameEvent(
        frame_id="frame-1",
        function_name="my_func",
        module_path="my_module.my_func",
    )
    assert frame.frame_id == "frame-1"
    assert frame.function_name == "my_func"
    assert frame.parent_frame_id is None
    assert frame.children == []
    assert frame.depth == 0


def test_frame_event_to_dict_basic():
    frame = FrameEvent(
        frame_id="f1",
        function_name="fn",
        module_path="mod.fn",
        depth=2,
        duration_ms=12.5,
    )
    d = frame.to_dict()
    assert d["frame_id"] == "f1"
    assert d["function_name"] == "fn"
    assert d["depth"] == 2
    assert d["duration_ms"] == 12.5
    assert d["token_usage"] is None
    assert d["exception"] is None
    assert d["children"] == []


def test_frame_event_to_dict_with_token_usage():
    usage = TokenUsage(prompt_tokens=5, completion_tokens=3, total_tokens=8)
    frame = FrameEvent(
        frame_id="f2",
        function_name="llm_call",
        module_path="mod.llm_call",
        token_usage=usage,
    )
    d = frame.to_dict()
    assert d["token_usage"] == {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}


def test_frame_event_to_dict_with_children():
    frame = FrameEvent(
        frame_id="parent",
        function_name="outer",
        module_path="mod.outer",
        children=["child1", "child2"],
    )
    d = frame.to_dict()
    assert d["children"] == ["child1", "child2"]


# ===========================================================================
# FrameLifetimeTrace
# ===========================================================================


def test_frame_lifetime_trace_construction():
    trace = FrameLifetimeTrace(trace_id="trace-abc")
    assert trace.trace_id == "trace-abc"
    assert trace.frames == []
    assert trace.total_duration_ms == 0.0
    assert trace.total_tokens == 0


def test_frame_lifetime_trace_to_dict():
    frame = FrameEvent(frame_id="f1", function_name="fn", module_path="mod")
    trace = FrameLifetimeTrace(
        trace_id="t1",
        frames=[frame],
        entry_point="fn",
        total_duration_ms=50.0,
        total_tokens=100,
    )
    d = trace.to_dict()
    assert d["trace_id"] == "t1"
    assert len(d["frames"]) == 1
    assert d["frames"][0]["frame_id"] == "f1"
    assert d["entry_point"] == "fn"
    assert d["total_duration_ms"] == 50.0
    assert d["total_tokens"] == 100


# ===========================================================================
# build_frame_tree
# ===========================================================================


def test_build_frame_tree_empty():
    assert build_frame_tree([]) == {}


def test_build_frame_tree_single_root():
    frame = FrameEvent(frame_id="root", function_name="fn", module_path="mod")
    tree = build_frame_tree([frame])
    assert tree["frame"]["frame_id"] == "root"
    assert tree["children"] == []


def test_build_frame_tree_parent_child():
    parent = FrameEvent(frame_id="p", function_name="outer", module_path="mod", children=["c"])
    child = FrameEvent(
        frame_id="c",
        function_name="inner",
        module_path="mod",
        parent_frame_id="p",
        depth=1,
    )
    tree = build_frame_tree([parent, child])
    assert tree["frame"]["frame_id"] == "p"
    assert len(tree["children"]) == 1
    assert tree["children"][0]["frame"]["frame_id"] == "c"


def test_build_frame_tree_multiple_roots():
    f1 = FrameEvent(frame_id="r1", function_name="a", module_path="mod")
    f2 = FrameEvent(frame_id="r2", function_name="b", module_path="mod")
    tree = build_frame_tree([f1, f2])
    assert tree["frame"] is None
    assert len(tree["children"]) == 2


# ===========================================================================
# FrameCaptureContext
# ===========================================================================


def test_frame_capture_context_build_trace_empty():
    ctx = FrameCaptureContext(trace_id="t1")
    trace = ctx.build_trace(entry_point="main")
    assert trace.trace_id == "t1"
    assert trace.entry_point == "main"
    assert trace.frames == []
    assert trace.total_duration_ms == 0.0
    assert trace.total_tokens == 0


def test_frame_capture_context_add_frame_updates_totals():
    ctx = FrameCaptureContext(trace_id="t2")
    frame = FrameEvent(
        frame_id="f1",
        function_name="fn",
        module_path="mod",
        duration_ms=25.0,
        token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )
    ctx.add_frame(frame)
    trace = ctx.build_trace()
    assert trace.total_duration_ms == 25.0
    assert trace.total_tokens == 15


def test_frame_capture_context_parent_child_tracking():
    ctx = FrameCaptureContext(trace_id="t3")
    parent_id = "parent"
    child_id = "child"

    parent = FrameEvent(frame_id=parent_id, function_name="outer", module_path="mod")
    ctx.add_frame(parent)
    ctx.enter_frame(parent_id)

    child = FrameEvent(frame_id=child_id, function_name="inner", module_path="mod")
    ctx.add_frame(child)
    ctx.exit_frame(parent_id)

    assert child.parent_frame_id == parent_id
    assert child.depth == 1
    assert child_id in parent.children


# ===========================================================================
# capture_function_call decorator
# ===========================================================================


def test_capture_function_call_no_context():
    """Without active context, decorator is transparent."""
    set_frame_context(None)

    @capture_function_call
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


def test_capture_function_call_records_frame():
    ctx = FrameCaptureContext(trace_id="dec-test")
    set_frame_context(ctx)

    try:
        @capture_function_call
        def multiply(x, y):
            return x * y

        result = multiply(4, 5)
        assert result == 20

        trace = ctx.build_trace(entry_point="multiply")
        assert len(trace.frames) == 1
        assert trace.frames[0].function_name == "multiply"
        assert trace.frames[0].duration_ms >= 0.0
    finally:
        set_frame_context(None)


def test_capture_function_call_captures_exception():
    ctx = FrameCaptureContext(trace_id="exc-test")
    set_frame_context(ctx)

    try:
        @capture_function_call
        def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            fail()

        assert len(ctx.frames) == 1
        assert ctx.frames[0].exception is not None
        assert ctx.frames[0].exception.exception_type == "ValueError"
        assert "boom" in ctx.frames[0].exception.message
    finally:
        set_frame_context(None)


def test_capture_function_call_with_options():
    ctx = FrameCaptureContext(trace_id="opts-test")
    set_frame_context(ctx)

    try:
        @capture_function_call(capture_args=False, capture_return=False)
        def process(data):
            return data * 2

        process(99)
        assert len(ctx.frames) == 1
        assert ctx.frames[0].call_args == {}
        assert ctx.frames[0].return_value is None
    finally:
        set_frame_context(None)


# ===========================================================================
# get_cost_breakdown
# ===========================================================================


def test_get_cost_breakdown_groups_by_function():
    frames = [
        FrameEvent(
            frame_id=f"f{i}",
            function_name="fn_a",
            module_path="mod",
            duration_ms=10.0,
            token_usage=TokenUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
        )
        for i in range(3)
    ] + [
        FrameEvent(
            frame_id="f3",
            function_name="fn_b",
            module_path="mod",
            duration_ms=20.0,
        )
    ]
    trace = FrameLifetimeTrace(trace_id="cost-test", frames=frames)
    breakdown = get_cost_breakdown(trace)

    assert "fn_a" in breakdown
    assert breakdown["fn_a"].total_calls == 3
    assert breakdown["fn_a"].total_duration_ms == 30.0
    assert breakdown["fn_a"].avg_duration_ms == 10.0
    assert breakdown["fn_a"].total_tokens == 30

    assert "fn_b" in breakdown
    assert breakdown["fn_b"].total_calls == 1
    assert breakdown["fn_b"].total_tokens == 0


def test_get_cost_breakdown_counts_errors():
    from agent_debugger_sdk.core.frame_tracer import ExceptionInfo

    frames = [
        FrameEvent(
            frame_id="ok",
            function_name="fn",
            module_path="mod",
        ),
        FrameEvent(
            frame_id="err",
            function_name="fn",
            module_path="mod",
            exception=ExceptionInfo(exception_type="RuntimeError", message="bad"),
        ),
    ]
    trace = FrameLifetimeTrace(trace_id="err-test", frames=frames)
    breakdown = get_cost_breakdown(trace)
    assert breakdown["fn"].error_count == 1


# ===========================================================================
# get_frames_at_depth / filter_frames_by_name
# ===========================================================================


def test_get_frames_at_depth():
    frames = [
        FrameEvent(frame_id="d0", function_name="root", module_path="m", depth=0),
        FrameEvent(frame_id="d1a", function_name="child_a", module_path="m", depth=1),
        FrameEvent(frame_id="d1b", function_name="child_b", module_path="m", depth=1),
        FrameEvent(frame_id="d2", function_name="grandchild", module_path="m", depth=2),
    ]
    trace = FrameLifetimeTrace(trace_id="depth-test", frames=frames)
    assert len(get_frames_at_depth(trace, 0)) == 1
    assert len(get_frames_at_depth(trace, 1)) == 2
    assert len(get_frames_at_depth(trace, 2)) == 1
    assert len(get_frames_at_depth(trace, 3)) == 0


def test_filter_frames_by_name():
    frames = [
        FrameEvent(frame_id="f1", function_name="fetch_data", module_path="m"),
        FrameEvent(frame_id="f2", function_name="process_data", module_path="m"),
        FrameEvent(frame_id="f3", function_name="save_result", module_path="m"),
    ]
    trace = FrameLifetimeTrace(trace_id="filter-test", frames=frames)
    matched = filter_frames_by_name(trace, "data")
    assert len(matched) == 2
    names = {f.function_name for f in matched}
    assert names == {"fetch_data", "process_data"}


# ===========================================================================
# to_dict / from_dict round-trip
# ===========================================================================


def test_frame_lifetime_trace_roundtrip():
    frame = FrameEvent(
        frame_id="rt1",
        function_name="fn",
        module_path="mod.fn",
        duration_ms=5.0,
        token_usage=TokenUsage(prompt_tokens=2, completion_tokens=3, total_tokens=5),
        children=["rt2"],
    )
    trace = FrameLifetimeTrace(
        trace_id="roundtrip",
        frames=[frame],
        entry_point="fn",
        total_duration_ms=5.0,
        total_tokens=5,
    )
    data = to_dict(trace)
    reconstructed = from_dict(data)

    assert reconstructed.trace_id == "roundtrip"
    assert len(reconstructed.frames) == 1
    assert reconstructed.frames[0].frame_id == "rt1"
    assert reconstructed.frames[0].token_usage is not None
    assert reconstructed.frames[0].token_usage.total_tokens == 5
    assert reconstructed.frames[0].children == ["rt2"]


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


def test_divergence_point_construction():
    dp = DivergencePoint(
        divergence_type=DivergenceType.BEHAVIORAL,
        severity=DivergenceSeverity.HIGH,
        description="confidence mismatch",
        divergence_score=0.7,
    )
    assert dp.divergence_type == DivergenceType.BEHAVIORAL
    assert dp.severity == DivergenceSeverity.HIGH
    assert dp.divergence_score == 0.7
    assert dp.primary_event_id is None


def test_divergence_point_to_dict():
    ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    dp = DivergencePoint(
        divergence_type=DivergenceType.TEMPORAL,
        severity=DivergenceSeverity.MEDIUM,
        primary_event_id="evt-1",
        secondary_event_id="evt-2",
        description="timing drift",
        timestamp=ts,
        divergence_score=0.3,
        metadata={"seconds": 12.5},
    )
    d = dp.to_dict()
    assert d["divergence_type"] == "temporal"
    assert d["severity"] == "medium"
    assert d["primary_event_id"] == "evt-1"
    assert d["secondary_event_id"] == "evt-2"
    assert d["description"] == "timing drift"
    assert d["timestamp"] == ts.isoformat()
    assert d["divergence_score"] == 0.3
    assert d["metadata"] == {"seconds": 12.5}


def test_divergence_point_no_timestamp():
    dp = DivergencePoint(
        divergence_type=DivergenceType.STRUCTURAL,
        severity=DivergenceSeverity.LOW,
    )
    assert dp.to_dict()["timestamp"] is None


# ===========================================================================
# Helpers — build minimal TraceEvent lists
# ===========================================================================


def _make_events(
    count: int,
    session_id: str = "s1",
    event_type: EventType = EventType.TOOL_CALL,
    base_time: datetime | None = None,
) -> list[TraceEvent]:
    if base_time is None:
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        TraceEvent(
            session_id=session_id,
            event_type=event_type,
            timestamp=base_time + timedelta(seconds=i),
        )
        for i in range(count)
    ]


# ===========================================================================
# detect_divergences
# ===========================================================================


def test_detect_divergences_both_empty():
    result = detect_divergences([], [])
    assert isinstance(result, SessionComparison)
    assert result.overall_divergence_score == 0.0
    assert result.structural_similarity == 1.0
    assert result.temporal_similarity == 1.0
    assert result.behavioral_similarity == 1.0


def test_detect_divergences_identical_events():
    events = _make_events(5, session_id="sess-a")
    # Use same events for both — counts should match
    result = detect_divergences(list(events), list(events))
    assert result.overall_divergence_score >= 0.0
    assert result.structural_similarity >= 0.0


def test_detect_divergences_count_mismatch_creates_structural_divergence():
    primary = _make_events(10, session_id="s1")
    secondary = _make_events(3, session_id="s2")
    result = detect_divergences(primary, secondary)
    structural_points = [
        dp for dp in result.divergence_points
        if dp.divergence_type == DivergenceType.STRUCTURAL
    ]
    assert len(structural_points) > 0


def test_detect_divergences_summary_fields():
    primary = _make_events(5, session_id="p")
    secondary = _make_events(3, session_id="q")
    result = detect_divergences(primary, secondary)
    summary = result.comparison_summary
    assert summary["primary_event_count"] == 5
    assert summary["secondary_event_count"] == 3
    assert "total_divergences" in summary
    assert "critical_divergences" in summary
    assert "divergence_by_type" in summary


def test_detect_divergences_session_ids_extracted():
    primary = _make_events(2, session_id="alpha")
    secondary = _make_events(2, session_id="beta")
    result = detect_divergences(primary, secondary)
    assert result.primary_session_id == "alpha"
    assert result.secondary_session_id == "beta"


def test_detect_divergences_large_count_diff_critical_severity():
    primary = _make_events(25, session_id="p")
    secondary = _make_events(1, session_id="s")
    result = detect_divergences(primary, secondary)
    critical_structural = [
        dp for dp in result.divergence_points
        if dp.divergence_type == DivergenceType.STRUCTURAL
        and dp.severity == DivergenceSeverity.CRITICAL
    ]
    assert len(critical_structural) > 0


# ===========================================================================
# compare_session_structures
# ===========================================================================


def test_compare_session_structures_empty():
    result = compare_session_structures([], [])
    assert result["primary_depth"] == 0
    assert result["secondary_depth"] == 0
    assert result["structural_similarity"] == 1.0


def test_compare_session_structures_keys_present():
    primary = _make_events(4, session_id="p")
    secondary = _make_events(4, session_id="s")
    result = compare_session_structures(primary, secondary)
    assert "primary_depth" in result
    assert "secondary_depth" in result
    assert "primary_branching_factor" in result
    assert "secondary_branching_factor" in result
    assert "event_type_distribution_primary" in result
    assert "event_type_distribution_secondary" in result
    assert "structural_similarity" in result
    assert 0.0 <= result["structural_similarity"] <= 1.0


def test_compare_session_structures_event_distribution():
    primary = (
        _make_events(3, session_id="p", event_type=EventType.TOOL_CALL)
        + _make_events(2, session_id="p", event_type=EventType.DECISION)
    )
    secondary = _make_events(5, session_id="s", event_type=EventType.TOOL_CALL)
    result = compare_session_structures(primary, secondary)
    assert result["event_type_distribution_primary"].get("tool_call", 0) == 3
    assert result["event_type_distribution_primary"].get("decision", 0) == 2
    assert result["event_type_distribution_secondary"].get("tool_call", 0) == 5


# ===========================================================================
# analyze_temporal_divergence
# ===========================================================================


def test_analyze_temporal_divergence_empty():
    result = analyze_temporal_divergence([], [])
    assert result["primary_duration_seconds"] == 0.0
    assert result["secondary_duration_seconds"] == 0.0
    assert result["temporal_divergence_score"] == 0.0
    assert result["timing_differences"] == []


def test_analyze_temporal_divergence_keys():
    base = datetime(2024, 6, 1, tzinfo=timezone.utc)
    primary = _make_events(5, session_id="p", base_time=base)
    secondary = _make_events(5, session_id="s", base_time=base)
    result = analyze_temporal_divergence(primary, secondary)
    assert "primary_duration_seconds" in result
    assert "secondary_duration_seconds" in result
    assert "duration_difference_seconds" in result
    assert "temporal_divergence_score" in result
    assert "timing_differences" in result


def test_analyze_temporal_divergence_similar_sessions_low_score():
    base = datetime(2024, 6, 1, tzinfo=timezone.utc)
    primary = _make_events(5, session_id="p", base_time=base)
    secondary = _make_events(5, session_id="s", base_time=base)
    result = analyze_temporal_divergence(primary, secondary)
    assert result["duration_difference_seconds"] == 0.0
    assert result["temporal_divergence_score"] == 0.0


def test_analyze_temporal_divergence_large_difference():
    base_p = datetime(2024, 6, 1, tzinfo=timezone.utc)
    base_s = datetime(2024, 6, 1, tzinfo=timezone.utc)
    primary = [
        TraceEvent(session_id="p", event_type=EventType.TOOL_CALL,
                   timestamp=base_p),
        TraceEvent(session_id="p", event_type=EventType.TOOL_CALL,
                   timestamp=base_p + timedelta(seconds=120)),
    ]
    secondary = [
        TraceEvent(session_id="s", event_type=EventType.TOOL_CALL,
                   timestamp=base_s),
        TraceEvent(session_id="s", event_type=EventType.TOOL_CALL,
                   timestamp=base_s + timedelta(seconds=10)),
    ]
    result = analyze_temporal_divergence(primary, secondary)
    assert result["duration_difference_seconds"] == pytest.approx(110.0)


# ===========================================================================
# analyze_behavioral_divergence
# ===========================================================================


def test_analyze_behavioral_divergence_empty():
    result = analyze_behavioral_divergence([], [])
    assert result["primary_decision_count"] == 0
    assert result["secondary_decision_count"] == 0
    assert result["primary_tool_call_count"] == 0
    assert result["secondary_tool_call_count"] == 0
    assert result["behavioral_divergence_score"] == 0.0


def test_analyze_behavioral_divergence_keys():
    primary = _make_events(3, session_id="p", event_type=EventType.TOOL_CALL)
    secondary = _make_events(2, session_id="s", event_type=EventType.TOOL_CALL)
    result = analyze_behavioral_divergence(primary, secondary)
    assert "primary_decision_count" in result
    assert "secondary_decision_count" in result
    assert "primary_tool_call_count" in result
    assert "secondary_tool_call_count" in result
    assert "decision_divergences" in result
    assert "tool_divergences" in result
    assert "behavioral_divergence_score" in result


def test_analyze_behavioral_divergence_counts_tool_events():
    primary = _make_events(4, session_id="p", event_type=EventType.TOOL_CALL)
    secondary = _make_events(2, session_id="s", event_type=EventType.TOOL_CALL)
    result = analyze_behavioral_divergence(primary, secondary)
    assert result["primary_tool_call_count"] == 4
    assert result["secondary_tool_call_count"] == 2


def test_analyze_behavioral_divergence_counts_decision_events():
    primary = _make_events(3, session_id="p", event_type=EventType.DECISION)
    secondary = _make_events(1, session_id="s", event_type=EventType.DECISION)
    result = analyze_behavioral_divergence(primary, secondary)
    assert result["primary_decision_count"] == 3
    assert result["secondary_decision_count"] == 1


def test_analyze_behavioral_divergence_score_range():
    primary = _make_events(5, session_id="p", event_type=EventType.TOOL_CALL)
    secondary = _make_events(5, session_id="s", event_type=EventType.DECISION)
    result = analyze_behavioral_divergence(primary, secondary)
    assert 0.0 <= result["behavioral_divergence_score"] <= 1.0


# ===========================================================================
# SessionComparison.to_dict
# ===========================================================================


def test_session_comparison_to_dict():
    dp = DivergencePoint(
        divergence_type=DivergenceType.STRUCTURAL,
        severity=DivergenceSeverity.LOW,
        description="minor",
    )
    sc = SessionComparison(
        primary_session_id="p",
        secondary_session_id="s",
        divergence_points=[dp],
        overall_divergence_score=0.1,
    )
    d = sc.to_dict()
    assert d["primary_session_id"] == "p"
    assert d["secondary_session_id"] == "s"
    assert len(d["divergence_points"]) == 1
    assert d["overall_divergence_score"] == 0.1
