"""Unit tests for FrameTracer and DivergenceDetector (issue #208)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

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
    get_frames_at_depth,
    set_frame_context,
    to_dict,
)

# ===========================================================================
# TokenUsage
# ===========================================================================


def test_token_usage_defaults():
    tu = TokenUsage()
    assert tu.prompt_tokens == 0
    assert tu.completion_tokens == 0
    assert tu.total_tokens == 0


def test_token_usage_add():
    a = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    b = TokenUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30)
    c = a + b
    assert c.prompt_tokens == 30
    assert c.completion_tokens == 15
    assert c.total_tokens == 45


def test_token_usage_to_dict():
    tu = TokenUsage(prompt_tokens=3, completion_tokens=7, total_tokens=10)
    d = tu.to_dict()
    assert d == {"prompt_tokens": 3, "completion_tokens": 7, "total_tokens": 10}


# ===========================================================================
# FrameEvent
# ===========================================================================


def _make_frame(**kwargs: Any) -> FrameEvent:
    defaults: dict[str, Any] = {
        "frame_id": "frame-1",
        "function_name": "my_func",
        "module_path": "mymodule.my_func",
    }
    defaults.update(kwargs)
    return FrameEvent(**defaults)


def test_frame_event_defaults():
    fe = _make_frame()
    assert fe.frame_id == "frame-1"
    assert fe.function_name == "my_func"
    assert fe.module_path == "mymodule.my_func"
    assert fe.parent_frame_id is None
    assert fe.call_args == {}
    assert fe.return_value is None
    assert fe.exception is None
    assert fe.depth == 0
    assert fe.children == []


def test_frame_event_to_dict_basic():
    fe = _make_frame(depth=2)
    d = fe.to_dict()
    assert d["frame_id"] == "frame-1"
    assert d["function_name"] == "my_func"
    assert d["depth"] == 2
    assert d["exception"] is None
    assert d["token_usage"] is None


def test_frame_event_to_dict_with_token_usage():
    tu = TokenUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10)
    fe = _make_frame(token_usage=tu)
    d = fe.to_dict()
    assert d["token_usage"] == {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}


def test_frame_event_to_dict_with_exception():
    exc = ExceptionInfo(exception_type="ValueError", message="bad value", traceback="tb text")
    fe = _make_frame(exception=exc)
    d = fe.to_dict()
    assert d["exception"]["exception_type"] == "ValueError"
    assert d["exception"]["message"] == "bad value"
    assert d["exception"]["traceback"] == "tb text"


def test_frame_event_children_serialized():
    fe = _make_frame(children=["child-1", "child-2"])
    d = fe.to_dict()
    assert d["children"] == ["child-1", "child-2"]


# ===========================================================================
# FrameLifetimeTrace
# ===========================================================================


def test_frame_lifetime_trace_empty():
    trace = FrameLifetimeTrace(trace_id="t1")
    assert trace.frames == []
    assert trace.total_tokens == 0
    assert trace.entry_point == ""


def test_frame_lifetime_trace_to_dict():
    fe = _make_frame()
    trace = FrameLifetimeTrace(trace_id="t1", frames=[fe], entry_point="main", total_duration_ms=42.0, total_tokens=10)
    d = trace.to_dict()
    assert d["trace_id"] == "t1"
    assert len(d["frames"]) == 1
    assert d["entry_point"] == "main"
    assert d["total_duration_ms"] == 42.0
    assert d["total_tokens"] == 10


# ===========================================================================
# build_frame_tree
# ===========================================================================


def test_build_frame_tree_empty():
    result = build_frame_tree([])
    assert result == {}


def test_build_frame_tree_single_root():
    fe = _make_frame(frame_id="root")
    result = build_frame_tree([fe])
    assert result["frame"]["frame_id"] == "root"
    assert result["children"] == []


def test_build_frame_tree_parent_child():
    parent = _make_frame(frame_id="parent", function_name="parent_fn", module_path="m.parent_fn")
    child = _make_frame(
        frame_id="child",
        function_name="child_fn",
        module_path="m.child_fn",
        parent_frame_id="parent",
    )
    parent.children = ["child"]
    result = build_frame_tree([parent, child])
    assert result["frame"]["frame_id"] == "parent"
    assert len(result["children"]) == 1
    assert result["children"][0]["frame"]["frame_id"] == "child"


def test_build_frame_tree_multiple_roots():
    a = _make_frame(frame_id="a", function_name="a", module_path="m.a")
    b = _make_frame(frame_id="b", function_name="b", module_path="m.b")
    result = build_frame_tree([a, b])
    assert result["frame"] is None
    assert len(result["children"]) == 2


# ===========================================================================
# get_frame_by_id / get_frames_at_depth / filter_frames_by_name
# ===========================================================================


def _make_trace(*frames: FrameEvent) -> FrameLifetimeTrace:
    return FrameLifetimeTrace(trace_id="t", frames=list(frames))


def test_get_frame_by_id_found():
    fe = _make_frame(frame_id="x")
    trace = _make_trace(fe)
    assert get_frame_by_id(trace, "x") is fe


def test_get_frame_by_id_not_found():
    trace = _make_trace(_make_frame(frame_id="x"))
    assert get_frame_by_id(trace, "missing") is None


def test_get_frames_at_depth():
    d0 = _make_frame(frame_id="d0", function_name="d0", module_path="m", depth=0)
    d1 = _make_frame(frame_id="d1", function_name="d1", module_path="m", depth=1)
    d1b = _make_frame(frame_id="d1b", function_name="d1b", module_path="m", depth=1)
    trace = _make_trace(d0, d1, d1b)
    assert get_frames_at_depth(trace, 0) == [d0]
    assert set(f.frame_id for f in get_frames_at_depth(trace, 1)) == {"d1", "d1b"}


def test_filter_frames_by_name():
    fa = _make_frame(frame_id="a", function_name="compute_score", module_path="m")
    fb = _make_frame(frame_id="b", function_name="fetch_data", module_path="m")
    fc = _make_frame(frame_id="c", function_name="COMPUTE_TOTAL", module_path="m")
    trace = _make_trace(fa, fb, fc)
    matches = filter_frames_by_name(trace, "compute")
    assert {f.frame_id for f in matches} == {"a", "c"}


# ===========================================================================
# get_cost_breakdown
# ===========================================================================


def test_get_cost_breakdown_basic():
    tu = TokenUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10)
    f1 = _make_frame(frame_id="f1", function_name="llm_call", module_path="m", duration_ms=100.0, token_usage=tu)
    f2 = _make_frame(frame_id="f2", function_name="llm_call", module_path="m", duration_ms=200.0, token_usage=tu)
    f3 = _make_frame(frame_id="f3", function_name="other", module_path="m", duration_ms=50.0)
    trace = _make_trace(f1, f2, f3)

    costs = get_cost_breakdown(trace)
    assert "llm_call" in costs
    assert costs["llm_call"].total_calls == 2
    assert costs["llm_call"].total_duration_ms == 300.0
    assert costs["llm_call"].avg_duration_ms == 150.0
    assert costs["llm_call"].total_tokens == 20
    assert costs["llm_call"].avg_tokens == 10.0
    assert costs["llm_call"].error_count == 0
    assert costs["other"].total_calls == 1


def test_get_cost_breakdown_counts_errors():
    exc = ExceptionInfo(exception_type="IOError", message="fail")
    fe = _make_frame(frame_id="f1", function_name="bad_fn", module_path="m", exception=exc)
    trace = _make_trace(fe)
    costs = get_cost_breakdown(trace)
    assert costs["bad_fn"].error_count == 1


# ===========================================================================
# FrameCaptureContext
# ===========================================================================


def test_frame_capture_context_add_frame():
    ctx = FrameCaptureContext(trace_id="ctx-1")
    fe = _make_frame(frame_id="f1")
    ctx.add_frame(fe)
    assert len(ctx.frames) == 1


def test_frame_capture_context_parent_child_tracking():
    ctx = FrameCaptureContext(trace_id="ctx-1")

    parent = _make_frame(frame_id="parent", function_name="parent_fn", module_path="m")
    ctx.enter_frame("parent")
    ctx.add_frame(parent)

    child = _make_frame(frame_id="child", function_name="child_fn", module_path="m")
    ctx.add_frame(child)

    ctx.exit_frame("parent")

    assert child.parent_frame_id == "parent"
    assert "child" in parent.children


def test_frame_capture_context_build_trace():
    ctx = FrameCaptureContext(trace_id="ctx-2")
    fe = _make_frame(frame_id="f1", duration_ms=50.0)
    tu = TokenUsage(total_tokens=20)
    fe.token_usage = tu
    ctx.add_frame(fe)

    trace = ctx.build_trace(entry_point="main")
    assert trace.trace_id == "ctx-2"
    assert trace.entry_point == "main"
    assert trace.total_duration_ms == 50.0
    assert trace.total_tokens == 20
    assert len(trace.frames) == 1


def test_frame_capture_context_exit_noop_on_wrong_id():
    ctx = FrameCaptureContext()
    ctx.enter_frame("frame-1")
    ctx.exit_frame("wrong-id")
    assert ctx._parent_stack == ["frame-1"]


# ===========================================================================
# capture_function_call decorator
# ===========================================================================


def test_capture_function_call_no_context():
    @capture_function_call
    def add(a: int, b: int) -> int:
        return a + b

    set_frame_context(None)
    result = add(2, 3)
    assert result == 5


def test_capture_function_call_with_context():
    ctx = FrameCaptureContext(trace_id="dec-test")
    set_frame_context(ctx)

    @capture_function_call
    def multiply(x: int, y: int) -> int:
        return x * y

    try:
        result = multiply(3, 4)
        assert result == 12
        assert len(ctx.frames) == 1
        assert ctx.frames[0].function_name == "multiply"
        assert ctx.frames[0].call_args == {"x": 3, "y": 4}
    finally:
        set_frame_context(None)


def test_capture_function_call_captures_exception():
    ctx = FrameCaptureContext(trace_id="exc-test")
    set_frame_context(ctx)

    @capture_function_call
    def broken() -> None:
        raise RuntimeError("oops")

    try:
        with pytest.raises(RuntimeError):
            broken()
        assert len(ctx.frames) == 1
        assert ctx.frames[0].exception is not None
        assert ctx.frames[0].exception.exception_type == "RuntimeError"
    finally:
        set_frame_context(None)


def test_capture_function_call_with_args_false():
    ctx = FrameCaptureContext(trace_id="no-args")
    set_frame_context(ctx)

    @capture_function_call(capture_args=False)
    def secret(password: str) -> str:
        return password

    try:
        secret("hunter2")
        assert ctx.frames[0].call_args == {}
    finally:
        set_frame_context(None)


# ===========================================================================
# to_dict / from_dict round-trip
# ===========================================================================


def test_frame_tracer_round_trip():
    tu = TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3)
    fe = _make_frame(
        frame_id="rt-1",
        duration_ms=77.0,
        token_usage=tu,
        children=["rt-2"],
    )
    trace = FrameLifetimeTrace(trace_id="rt", frames=[fe], entry_point="entry", total_duration_ms=77.0, total_tokens=3)
    d = to_dict(trace)
    restored = from_dict(d)

    assert restored.trace_id == "rt"
    assert len(restored.frames) == 1
    assert restored.frames[0].frame_id == "rt-1"
    assert restored.frames[0].token_usage is not None
    assert restored.frames[0].token_usage.total_tokens == 3
    assert restored.frames[0].children == ["rt-2"]


# ===========================================================================
# DivergenceType / DivergenceSeverity enums
# ===========================================================================


def test_divergence_type_values():
    assert DivergenceType.STRUCTURAL == "structural"
    assert DivergenceType.TEMPORAL == "temporal"
    assert DivergenceType.BEHAVIORAL == "behavioral"
    assert DivergenceType.STATE == "state"
    assert DivergenceType.ERROR == "error"
    assert DivergenceType.PERFORMANCE == "performance"


def test_divergence_severity_values():
    assert DivergenceSeverity.CRITICAL == "critical"
    assert DivergenceSeverity.HIGH == "high"
    assert DivergenceSeverity.MEDIUM == "medium"
    assert DivergenceSeverity.LOW == "low"


# ===========================================================================
# DivergencePoint
# ===========================================================================


def test_divergence_point_to_dict_basic():
    dp = DivergencePoint(
        divergence_type=DivergenceType.STRUCTURAL,
        severity=DivergenceSeverity.LOW,
        description="test divergence",
        divergence_score=0.3,
    )
    d = dp.to_dict()
    assert d["divergence_type"] == "structural"
    assert d["severity"] == "low"
    assert d["description"] == "test divergence"
    assert d["divergence_score"] == 0.3
    assert d["timestamp"] is None
    assert d["primary_event_id"] is None
    assert d["secondary_event_id"] is None


def test_divergence_point_to_dict_with_timestamp():
    ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    dp = DivergencePoint(
        divergence_type=DivergenceType.TEMPORAL,
        severity=DivergenceSeverity.HIGH,
        timestamp=ts,
    )
    d = dp.to_dict()
    assert "2024-01-01" in d["timestamp"]


def test_divergence_point_metadata():
    dp = DivergencePoint(
        divergence_type=DivergenceType.BEHAVIORAL,
        severity=DivergenceSeverity.MEDIUM,
        metadata={"key": "value"},
    )
    assert dp.to_dict()["metadata"] == {"key": "value"}


# ===========================================================================
# detect_divergences
# ===========================================================================


def _make_event(session_id: str = "s1", event_type: EventType = EventType.AGENT_START, **kwargs: Any) -> TraceEvent:
    return TraceEvent(session_id=session_id, event_type=event_type, **kwargs)


def test_detect_divergences_both_empty():
    result = detect_divergences([], [])
    assert isinstance(result, SessionComparison)
    assert result.overall_divergence_score == 0.0
    assert result.structural_similarity == 1.0
    assert result.temporal_similarity == 1.0
    assert result.behavioral_similarity == 1.0


def test_detect_divergences_identical_sessions():
    events = [_make_event("s1", EventType.AGENT_START), _make_event("s1", EventType.TOOL_CALL)]
    result = detect_divergences(events, events)
    assert result.primary_session_id == "s1"
    assert result.secondary_session_id == "s1"
    assert result.overall_divergence_score == 0.0


def test_detect_divergences_count_mismatch():
    primary = [_make_event("s1") for _ in range(3)]
    secondary = [_make_event("s2") for _ in range(15)]
    result = detect_divergences(primary, secondary)
    assert result.overall_divergence_score > 0.0
    assert len(result.divergence_points) > 0


def test_detect_divergences_summary_keys():
    primary = [_make_event("p", EventType.AGENT_START)]
    secondary = [_make_event("s", EventType.AGENT_END)]
    result = detect_divergences(primary, secondary)
    assert "primary_event_count" in result.comparison_summary
    assert "secondary_event_count" in result.comparison_summary
    assert "total_divergences" in result.comparison_summary
    assert "critical_divergences" in result.comparison_summary
    assert "divergence_by_type" in result.comparison_summary


def test_detect_divergences_session_ids_from_events():
    primary = [_make_event("session-A")]
    secondary = [_make_event("session-B")]
    result = detect_divergences(primary, secondary)
    assert result.primary_session_id == "session-A"
    assert result.secondary_session_id == "session-B"


def test_detect_divergences_divergence_score_bounded():
    primary = [_make_event("p") for _ in range(50)]
    secondary = [_make_event("s") for _ in range(1)]
    result = detect_divergences(primary, secondary)
    assert 0.0 <= result.overall_divergence_score <= 1.0


# ===========================================================================
# compare_session_structures
# ===========================================================================


def test_compare_session_structures_empty():
    result = compare_session_structures([], [])
    assert result["primary_depth"] == 0
    assert result["secondary_depth"] == 0
    assert result["structural_similarity"] == 1.0


def test_compare_session_structures_keys():
    ev = [_make_event("s")]
    result = compare_session_structures(ev, ev)
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


def test_compare_session_structures_distribution():
    primary = [
        _make_event("p", EventType.TOOL_CALL),
        _make_event("p", EventType.TOOL_CALL),
        _make_event("p", EventType.DECISION),
    ]
    secondary = [_make_event("s", EventType.AGENT_START)]
    result = compare_session_structures(primary, secondary)
    assert result["event_type_distribution_primary"]["tool_call"] == 2
    assert result["event_type_distribution_primary"]["decision"] == 1
    # structural_similarity is tree-topology-based (depth/branching), not event-count-based
    assert 0.0 <= result["structural_similarity"] <= 1.0


# ===========================================================================
# analyze_temporal_divergence
# ===========================================================================


def test_analyze_temporal_divergence_empty():
    result = analyze_temporal_divergence([], [])
    assert result["primary_duration_seconds"] == 0.0
    assert result["secondary_duration_seconds"] == 0.0
    assert result["temporal_divergence_score"] == 0.0
    assert result["timing_differences"] == []


def test_analyze_temporal_divergence_same_duration():
    now = datetime.now(timezone.utc)
    ev = [
        TraceEvent(session_id="s", event_type=EventType.AGENT_START, timestamp=now),
        TraceEvent(session_id="s", event_type=EventType.AGENT_END, timestamp=now + timedelta(seconds=10)),
    ]
    result = analyze_temporal_divergence(ev, ev)
    assert result["duration_difference_seconds"] == 0.0


def test_analyze_temporal_divergence_different_duration():
    now = datetime.now(timezone.utc)
    primary = [
        TraceEvent(session_id="p", event_type=EventType.AGENT_START, timestamp=now),
        TraceEvent(session_id="p", event_type=EventType.AGENT_END, timestamp=now + timedelta(seconds=5)),
    ]
    secondary = [
        TraceEvent(session_id="s", event_type=EventType.AGENT_START, timestamp=now),
        TraceEvent(session_id="s", event_type=EventType.AGENT_END, timestamp=now + timedelta(seconds=120)),
    ]
    result = analyze_temporal_divergence(primary, secondary)
    assert result["duration_difference_seconds"] > 0


def test_analyze_temporal_divergence_keys():
    now = datetime.now(timezone.utc)
    ev = [TraceEvent(session_id="s", timestamp=now)]
    result = analyze_temporal_divergence(ev, ev)
    assert "primary_duration_seconds" in result
    assert "secondary_duration_seconds" in result
    assert "duration_difference_seconds" in result
    assert "temporal_divergence_score" in result
    assert "timing_differences" in result


# ===========================================================================
# analyze_behavioral_divergence
# ===========================================================================


def test_analyze_behavioral_divergence_empty():
    result = analyze_behavioral_divergence([], [])
    assert result["primary_decision_count"] == 0
    assert result["secondary_decision_count"] == 0
    assert result["behavioral_divergence_score"] == 0.0


def test_analyze_behavioral_divergence_decision_count():
    decisions = [_make_event("s", EventType.DECISION) for _ in range(3)]
    tools = [_make_event("s", EventType.TOOL_CALL)]
    result = analyze_behavioral_divergence(decisions + tools, [])
    assert result["primary_decision_count"] == 3
    assert result["primary_tool_call_count"] == 1
    assert result["secondary_decision_count"] == 0


def test_analyze_behavioral_divergence_tool_divergence():
    primary_tools = [TraceEvent(session_id="p", event_type=EventType.TOOL_CALL)]
    setattr(primary_tools[0], "tool_name", "search")

    secondary_tools = [TraceEvent(session_id="s", event_type=EventType.TOOL_CALL)]
    setattr(secondary_tools[0], "tool_name", "calculator")

    result = analyze_behavioral_divergence(primary_tools, secondary_tools)
    assert len(result["tool_divergences"]) >= 1


def test_analyze_behavioral_divergence_keys():
    result = analyze_behavioral_divergence([], [])
    expected = {
        "primary_decision_count",
        "secondary_decision_count",
        "primary_tool_call_count",
        "secondary_tool_call_count",
        "decision_divergences",
        "tool_divergences",
        "behavioral_divergence_score",
    }
    assert expected.issubset(result.keys())


def test_analyze_behavioral_divergence_score_bounded():
    events = [_make_event("s", EventType.DECISION) for _ in range(20)]
    result = analyze_behavioral_divergence(events, [])
    assert 0.0 <= result["behavioral_divergence_score"] <= 1.0


# ===========================================================================
# SessionComparison.to_dict
# ===========================================================================


def test_session_comparison_to_dict():
    dp = DivergencePoint(
        divergence_type=DivergenceType.STRUCTURAL,
        severity=DivergenceSeverity.LOW,
    )
    sc = SessionComparison(
        primary_session_id="a",
        secondary_session_id="b",
        divergence_points=[dp],
        overall_divergence_score=0.2,
        structural_similarity=0.8,
        temporal_similarity=0.9,
        behavioral_similarity=0.95,
    )
    d = sc.to_dict()
    assert d["primary_session_id"] == "a"
    assert d["secondary_session_id"] == "b"
    assert len(d["divergence_points"]) == 1
    assert d["overall_divergence_score"] == 0.2
    assert d["structural_similarity"] == 0.8
