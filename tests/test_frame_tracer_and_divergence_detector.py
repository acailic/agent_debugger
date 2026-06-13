"""Unit tests for frame_tracer and divergence_detector — closes #208."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.divergence_detector import (
    DivergencePoint,
    DivergenceSeverity,
    DivergenceType,
    SessionComparison,
    _analyze_behavioral_divergence,
    _analyze_structural_divergence,
    _analyze_temporal_divergence,
    _avg_branching_factor,
    _build_event_tree,
    _calculate_behavioral_divergence_score,
    _calculate_session_duration,
    _calculate_structural_similarity,
    _calculate_temporal_divergence_score,
    _compare_timing_patterns,
    _compare_tool_usage,
    _count_divergences_by_type,
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
from agent_debugger_sdk.core.frame_tracer import (
    ExceptionInfo,
    FrameCaptureContext,
    FrameCost,
    FrameEvent,
    FrameLifetimeTrace,
    TokenUsage,
    _serialize_value,
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    session_id: str = "s1",
    event_type: EventType = EventType.AGENT_START,
    parent_id: str | None = None,
    timestamp: datetime | None = None,
) -> TraceEvent:
    return TraceEvent(
        session_id=session_id,
        event_type=event_type,
        parent_id=parent_id,
        timestamp=timestamp or datetime.now(timezone.utc),
    )


def _make_frame(
    function_name: str = "fn",
    module_path: str = "mod.fn",
    duration_ms: float = 10.0,
    depth: int = 0,
    token_usage: TokenUsage | None = None,
    exception: ExceptionInfo | None = None,
) -> FrameEvent:
    return FrameEvent(
        frame_id=f"frame-{function_name}-{id(object())}",
        function_name=function_name,
        module_path=module_path,
        duration_ms=duration_ms,
        depth=depth,
        token_usage=token_usage,
        exception=exception,
    )


# ===========================================================================
# TokenUsage
# ===========================================================================


class TestTokenUsage:
    def test_to_dict_keys(self):
        tu = TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3)
        d = tu.to_dict()
        assert d == {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}

    def test_add(self):
        a = TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3)
        b = TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        result = a + b
        assert result.prompt_tokens == 11
        assert result.completion_tokens == 22
        assert result.total_tokens == 33

    def test_add_zeros(self):
        a = TokenUsage()
        b = TokenUsage()
        assert (a + b).total_tokens == 0


# ===========================================================================
# ExceptionInfo
# ===========================================================================


class TestExceptionInfo:
    def test_to_dict_with_traceback(self):
        ei = ExceptionInfo(exception_type="ValueError", message="bad", traceback="tb")
        d = ei.to_dict()
        assert d["exception_type"] == "ValueError"
        assert d["message"] == "bad"
        assert d["traceback"] == "tb"

    def test_to_dict_without_traceback(self):
        ei = ExceptionInfo(exception_type="RuntimeError", message="oops")
        d = ei.to_dict()
        assert d["traceback"] is None


# ===========================================================================
# FrameEvent
# ===========================================================================


class TestFrameEvent:
    def test_to_dict_round_trip_basic(self):
        frame = _make_frame()
        d = frame.to_dict()
        assert d["function_name"] == "fn"
        assert d["module_path"] == "mod.fn"
        assert d["exception"] is None
        assert d["token_usage"] is None
        assert isinstance(d["children"], list)

    def test_to_dict_with_token_usage(self):
        tu = TokenUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10)
        frame = _make_frame(token_usage=tu)
        d = frame.to_dict()
        assert d["token_usage"]["total_tokens"] == 10

    def test_to_dict_with_exception(self):
        ei = ExceptionInfo(exception_type="KeyError", message="missing key")
        frame = _make_frame(exception=ei)
        d = frame.to_dict()
        assert d["exception"]["exception_type"] == "KeyError"


# ===========================================================================
# FrameCost
# ===========================================================================


class TestFrameCost:
    def test_to_dict(self):
        fc = FrameCost(
            function_name="foo",
            total_calls=3,
            total_duration_ms=90.0,
            avg_duration_ms=30.0,
            total_tokens=300,
            avg_tokens=100.0,
            error_count=1,
        )
        d = fc.to_dict()
        assert d["function_name"] == "foo"
        assert d["total_calls"] == 3
        assert d["error_count"] == 1


# ===========================================================================
# FrameLifetimeTrace
# ===========================================================================


class TestFrameLifetimeTrace:
    def test_to_dict_empty(self):
        trace = FrameLifetimeTrace(trace_id="t1")
        d = trace.to_dict()
        assert d["trace_id"] == "t1"
        assert d["frames"] == []
        assert d["total_tokens"] == 0

    def test_to_dict_with_frames(self):
        trace = FrameLifetimeTrace(
            trace_id="t2",
            frames=[_make_frame("a"), _make_frame("b")],
            total_duration_ms=20.0,
            total_tokens=5,
        )
        d = trace.to_dict()
        assert len(d["frames"]) == 2
        assert d["total_duration_ms"] == 20.0


# ===========================================================================
# build_frame_tree
# ===========================================================================


class TestBuildFrameTree:
    def test_empty(self):
        assert build_frame_tree([]) == {}

    def test_single_root(self):
        frame = _make_frame("root")
        tree = build_frame_tree([frame])
        assert tree["frame"]["function_name"] == "root"
        assert tree["children"] == []

    def test_parent_child(self):
        root = FrameEvent(
            frame_id="root-id",
            function_name="root",
            module_path="m.root",
        )
        child = FrameEvent(
            frame_id="child-id",
            function_name="child",
            module_path="m.child",
            parent_frame_id="root-id",
        )
        root.children.append("child-id")
        tree = build_frame_tree([root, child])
        assert tree["frame"]["function_name"] == "root"
        assert len(tree["children"]) == 1
        assert tree["children"][0]["frame"]["function_name"] == "child"

    def test_multiple_roots(self):
        a = _make_frame("a")
        b = _make_frame("b")
        tree = build_frame_tree([a, b])
        assert tree["frame"] is None
        assert len(tree["children"]) == 2


# ===========================================================================
# get_frame_by_id
# ===========================================================================


class TestGetFrameById:
    def test_found(self):
        frame = FrameEvent(frame_id="x", function_name="f", module_path="m")
        trace = FrameLifetimeTrace(trace_id="t", frames=[frame])
        assert get_frame_by_id(trace, "x") is frame

    def test_not_found(self):
        trace = FrameLifetimeTrace(trace_id="t", frames=[])
        assert get_frame_by_id(trace, "missing") is None


# ===========================================================================
# get_frames_at_depth
# ===========================================================================


class TestGetFramesAtDepth:
    def test_depth_filter(self):
        f0 = _make_frame("root", depth=0)
        f1a = _make_frame("child_a", depth=1)
        f1b = _make_frame("child_b", depth=1)
        f2 = _make_frame("grandchild", depth=2)
        trace = FrameLifetimeTrace(trace_id="t", frames=[f0, f1a, f1b, f2])
        assert get_frames_at_depth(trace, 0) == [f0]
        depth1 = get_frames_at_depth(trace, 1)
        assert len(depth1) == 2
        assert f1a in depth1
        assert f1b in depth1
        assert get_frames_at_depth(trace, 2) == [f2]
        assert get_frames_at_depth(trace, 99) == []


# ===========================================================================
# filter_frames_by_name
# ===========================================================================


class TestFilterFramesByName:
    def test_case_insensitive_match(self):
        frames = [_make_frame("ProcessData"), _make_frame("sendRequest"), _make_frame("cleanup")]
        trace = FrameLifetimeTrace(trace_id="t", frames=frames)
        result = filter_frames_by_name(trace, "process")
        assert len(result) == 1
        assert result[0].function_name == "ProcessData"

    def test_no_match(self):
        trace = FrameLifetimeTrace(trace_id="t", frames=[_make_frame("foo")])
        assert filter_frames_by_name(trace, "xyz") == []

    def test_multiple_matches(self):
        frames = [_make_frame("call_api"), _make_frame("call_db"), _make_frame("render")]
        trace = FrameLifetimeTrace(trace_id="t", frames=frames)
        assert len(filter_frames_by_name(trace, "call")) == 2


# ===========================================================================
# get_cost_breakdown
# ===========================================================================


class TestGetCostBreakdown:
    def test_basic_breakdown(self):
        tu = TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20)
        frames = [
            _make_frame("call_llm", duration_ms=100.0, token_usage=tu),
            _make_frame("call_llm", duration_ms=200.0, token_usage=tu),
            _make_frame("other", duration_ms=50.0),
        ]
        trace = FrameLifetimeTrace(trace_id="t", frames=frames)
        breakdown = get_cost_breakdown(trace)
        assert "call_llm" in breakdown
        llm = breakdown["call_llm"]
        assert llm.total_calls == 2
        assert llm.total_duration_ms == 300.0
        assert llm.avg_duration_ms == 150.0
        assert llm.total_tokens == 40
        assert llm.error_count == 0

    def test_error_count(self):
        ei = ExceptionInfo(exception_type="Error", message="e")
        frames = [
            _make_frame("risky", exception=ei),
            _make_frame("risky"),
        ]
        trace = FrameLifetimeTrace(trace_id="t", frames=frames)
        breakdown = get_cost_breakdown(trace)
        assert breakdown["risky"].error_count == 1

    def test_empty_trace(self):
        trace = FrameLifetimeTrace(trace_id="t")
        assert get_cost_breakdown(trace) == {}


# ===========================================================================
# FrameCaptureContext
# ===========================================================================


class TestFrameCaptureContext:
    def test_build_trace_empty(self):
        ctx = FrameCaptureContext(trace_id="t1")
        trace = ctx.build_trace("main")
        assert trace.trace_id == "t1"
        assert trace.entry_point == "main"
        assert trace.frames == []

    def test_add_frame_no_parent_stack(self):
        ctx = FrameCaptureContext(trace_id="t")
        frame = FrameEvent(frame_id="f", function_name="fn", module_path="m")
        ctx.add_frame(frame)
        # empty stack → no parent assigned
        assert frame.parent_frame_id is None
        assert frame.depth == 0

    def test_add_frame_sets_parent_from_stack(self):
        ctx = FrameCaptureContext(trace_id="t")
        ctx.enter_frame("outer-id")
        frame = FrameEvent(frame_id="inner-id", function_name="inner", module_path="m")
        ctx.add_frame(frame)
        # top of stack is "outer-id" → assigned as parent
        assert frame.parent_frame_id == "outer-id"
        assert frame.depth == 1

    def test_exit_frame_unknown_id_safe(self):
        ctx = FrameCaptureContext(trace_id="t")
        ctx.exit_frame("nonexistent")  # should not raise

    def test_build_trace_totals(self):
        tu = TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=15)
        ctx = FrameCaptureContext(trace_id="t")
        ctx.frames.append(_make_frame("a", duration_ms=10.0, token_usage=tu))
        ctx.frames.append(_make_frame("b", duration_ms=20.0))
        trace = ctx.build_trace()
        assert trace.total_duration_ms == 30.0
        assert trace.total_tokens == 15

    def test_to_dict(self):
        ctx = FrameCaptureContext(trace_id="t")
        d = ctx.to_dict()
        assert d["trace_id"] == "t"


# ===========================================================================
# set_frame_context / get_frame_context
# ===========================================================================


class TestFrameContext:
    def setup_method(self):
        set_frame_context(None)

    def teardown_method(self):
        set_frame_context(None)

    def test_set_and_get(self):
        ctx = FrameCaptureContext(trace_id="ctx-1")
        set_frame_context(ctx)
        assert get_frame_context() is ctx

    def test_clear(self):
        set_frame_context(FrameCaptureContext())
        set_frame_context(None)
        assert get_frame_context() is None


# ===========================================================================
# capture_function_call decorator
# ===========================================================================


class TestCaptureFunctionCall:
    def setup_method(self):
        set_frame_context(None)

    def teardown_method(self):
        set_frame_context(None)

    def test_no_context_passthrough(self):
        @capture_function_call
        def add(a, b):
            return a + b

        assert add(2, 3) == 5

    def test_with_context_captures_frame(self):
        ctx = FrameCaptureContext(trace_id="t")
        set_frame_context(ctx)

        @capture_function_call
        def greet(name):
            return f"hello {name}"

        result = greet("world")
        assert result == "hello world"
        assert len(ctx.frames) == 1
        assert ctx.frames[0].function_name == "greet"

    def test_exception_captured_and_reraised(self):
        ctx = FrameCaptureContext(trace_id="t")
        set_frame_context(ctx)

        @capture_function_call
        def boom():
            raise ValueError("kaboom")

        with pytest.raises(ValueError, match="kaboom"):
            boom()

        assert len(ctx.frames) == 1
        assert ctx.frames[0].exception is not None
        assert ctx.frames[0].exception.exception_type == "ValueError"

    def test_with_args_decorator(self):
        ctx = FrameCaptureContext(trace_id="t")
        set_frame_context(ctx)

        @capture_function_call(capture_args=False, capture_return=False)
        def compute(x):
            return x * 2

        result = compute(5)
        assert result == 10
        assert len(ctx.frames) == 1
        assert ctx.frames[0].call_args == {}

    def test_nested_calls_both_captured(self):
        ctx = FrameCaptureContext(trace_id="t")
        set_frame_context(ctx)

        @capture_function_call
        def inner():
            return 1

        @capture_function_call
        def outer():
            return inner()

        outer()
        assert len(ctx.frames) == 2
        names = {f.function_name for f in ctx.frames}
        assert "inner" in names
        assert "outer" in names
        # inner executes deeper in the stack so has higher depth
        inner_frame = next(f for f in ctx.frames if f.function_name == "inner")
        outer_frame = next(f for f in ctx.frames if f.function_name == "outer")
        assert inner_frame.depth > outer_frame.depth


# ===========================================================================
# _serialize_value
# ===========================================================================


class TestSerializeValue:
    def test_primitives(self):
        assert _serialize_value(None) is None
        assert _serialize_value(42) == 42
        assert _serialize_value(3.14) == 3.14
        assert _serialize_value(True) is True
        assert _serialize_value("hello") == "hello"

    def test_list_and_tuple(self):
        assert _serialize_value([1, 2, 3]) == [1, 2, 3]
        assert _serialize_value((4, 5)) == [4, 5]

    def test_dict(self):
        assert _serialize_value({"a": 1, "b": [2, 3]}) == {"a": 1, "b": [2, 3]}

    def test_custom_object_stringified(self):
        class Weird:
            def __str__(self):
                return "weird_obj"

        assert _serialize_value(Weird()) == "weird_obj"


# ===========================================================================
# to_dict / from_dict round-trip
# ===========================================================================


class TestRoundTrip:
    def test_to_dict_from_dict(self):
        frame = FrameEvent(
            frame_id="f1",
            function_name="fn",
            module_path="mod.fn",
            duration_ms=42.0,
            token_usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )
        trace = FrameLifetimeTrace(trace_id="t", frames=[frame])
        d = to_dict(trace)
        restored = from_dict(d)
        assert restored.trace_id == "t"
        assert len(restored.frames) == 1
        assert restored.frames[0].function_name == "fn"
        assert restored.frames[0].token_usage is not None
        assert restored.frames[0].token_usage.total_tokens == 2

    def test_from_dict_with_exception(self):
        d = {
            "trace_id": "t2",
            "frames": [
                {
                    "frame_id": "f2",
                    "function_name": "boom",
                    "module_path": "m",
                    "exception": {
                        "exception_type": "ValueError",
                        "message": "err",
                        "traceback": None,
                    },
                    "start_time": 0.0,
                    "end_time": 0.0,
                    "duration_ms": 0.0,
                    "depth": 0,
                    "children": [],
                    "parent_frame_id": None,
                    "call_args": {},
                    "return_value": None,
                    "token_usage": None,
                }
            ],
            "entry_point": "",
            "total_duration_ms": 0.0,
            "total_tokens": 0,
            "frame_tree": {},
        }
        restored = from_dict(d)
        assert restored.frames[0].exception.exception_type == "ValueError"


# ===========================================================================
# DivergencePoint
# ===========================================================================


class TestDivergencePoint:
    def test_to_dict(self):
        dp = DivergencePoint(
            divergence_type=DivergenceType.STRUCTURAL,
            severity=DivergenceSeverity.HIGH,
            description="some diff",
            divergence_score=0.8,
        )
        d = dp.to_dict()
        assert d["divergence_type"] == "structural"
        assert d["severity"] == "high"
        assert d["divergence_score"] == 0.8
        assert d["timestamp"] is None

    def test_to_dict_with_timestamp(self):
        ts = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
        dp = DivergencePoint(
            divergence_type=DivergenceType.TEMPORAL,
            severity=DivergenceSeverity.LOW,
            timestamp=ts,
        )
        d = dp.to_dict()
        assert "2025-01-01" in d["timestamp"]


# ===========================================================================
# SessionComparison
# ===========================================================================


class TestSessionComparison:
    def test_to_dict(self):
        sc = SessionComparison(
            primary_session_id="a",
            secondary_session_id="b",
            overall_divergence_score=0.3,
        )
        d = sc.to_dict()
        assert d["primary_session_id"] == "a"
        assert d["secondary_session_id"] == "b"
        assert d["divergence_points"] == []


# ===========================================================================
# detect_divergences
# ===========================================================================


class TestDetectDivergences:
    def test_both_empty(self):
        result = detect_divergences([], [])
        assert result.overall_divergence_score == 0.0
        assert result.structural_similarity == 1.0

    def test_same_events(self):
        events = [_make_event("s1", EventType.AGENT_START)]
        result = detect_divergences(events, events[:])
        assert result.primary_session_id == "s1"
        assert result.secondary_session_id == "s1"
        # Same events → no structural divergence from count diff
        assert result.overall_divergence_score == 0.0

    def test_different_counts(self):
        primary = [_make_event("p"), _make_event("p"), _make_event("p")]
        secondary = [_make_event("s")]
        result = detect_divergences(primary, secondary)
        assert result.overall_divergence_score > 0.0
        assert result.structural_similarity < 1.0

    def test_session_ids_extracted(self):
        primary = [_make_event("primary-sess")]
        secondary = [_make_event("secondary-sess")]
        result = detect_divergences(primary, secondary)
        assert result.primary_session_id == "primary-sess"
        assert result.secondary_session_id == "secondary-sess"

    def test_comparison_summary_populated(self):
        primary = [_make_event() for _ in range(3)]
        secondary = [_make_event() for _ in range(5)]
        result = detect_divergences(primary, secondary)
        assert result.comparison_summary["primary_event_count"] == 3
        assert result.comparison_summary["secondary_event_count"] == 5


# ===========================================================================
# compare_session_structures
# ===========================================================================


class TestCompareSessionStructures:
    def test_empty(self):
        result = compare_session_structures([], [])
        assert result["primary_depth"] == 0
        assert result["secondary_depth"] == 0

    def test_with_events(self):
        events = [_make_event("s", EventType.AGENT_START), _make_event("s", EventType.TOOL_CALL)]
        result = compare_session_structures(events, events[:])
        assert result["structural_similarity"] == 1.0


# ===========================================================================
# analyze_temporal_divergence
# ===========================================================================


class TestAnalyzeTemporalDivergence:
    def test_empty(self):
        result = analyze_temporal_divergence([], [])
        assert result["temporal_divergence_score"] == 0.0
        assert result["primary_duration_seconds"] == 0.0

    def test_same_timing(self):
        ts = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        events = [TraceEvent(session_id="s", event_type=EventType.AGENT_START, timestamp=ts)]
        result = analyze_temporal_divergence(events, events[:])
        assert result["duration_difference_seconds"] == 0.0


# ===========================================================================
# analyze_behavioral_divergence
# ===========================================================================


class TestAnalyzeBehavioralDivergence:
    def test_no_decisions_no_tools(self):
        events = [_make_event("s", EventType.AGENT_START)]
        result = analyze_behavioral_divergence(events, events[:])
        assert result["primary_decision_count"] == 0
        assert result["primary_tool_call_count"] == 0
        assert result["behavioral_divergence_score"] == 0.0

    def test_different_tool_counts(self):
        primary = [_make_event("s", EventType.TOOL_CALL), _make_event("s", EventType.TOOL_CALL)]
        secondary = [_make_event("s", EventType.TOOL_CALL)]
        result = analyze_behavioral_divergence(primary, secondary)
        assert result["primary_tool_call_count"] == 2
        assert result["secondary_tool_call_count"] == 1


# ===========================================================================
# Internal helpers — divergence_detector
# ===========================================================================


class TestDivergenceHelpers:
    def test_severity_for_count_difference(self):
        assert _severity_for_count_difference(1) == DivergenceSeverity.LOW
        assert _severity_for_count_difference(6) == DivergenceSeverity.MEDIUM
        assert _severity_for_count_difference(11) == DivergenceSeverity.HIGH
        assert _severity_for_count_difference(21) == DivergenceSeverity.CRITICAL

    def test_severity_for_timing_difference(self):
        assert _severity_for_timing_difference(10.0) == DivergenceSeverity.LOW
        assert _severity_for_timing_difference(35.0) == DivergenceSeverity.MEDIUM
        assert _severity_for_timing_difference(65.0) == DivergenceSeverity.HIGH

    def test_count_divergences_by_type(self):
        points = [
            DivergencePoint(divergence_type=DivergenceType.STRUCTURAL, severity=DivergenceSeverity.LOW),
            DivergencePoint(divergence_type=DivergenceType.STRUCTURAL, severity=DivergenceSeverity.HIGH),
            DivergencePoint(divergence_type=DivergenceType.TEMPORAL, severity=DivergenceSeverity.LOW),
        ]
        counts = _count_divergences_by_type(points)
        assert counts["structural"] == 2
        assert counts["temporal"] == 1

    def test_build_event_tree(self):
        parent = _make_event("s")
        child = _make_event("s")
        child.parent_id = parent.id
        tree = _build_event_tree([parent, child])
        assert parent.id in tree

    def test_max_tree_depth_empty(self):
        assert _max_tree_depth({}) == 0

    def test_max_tree_depth_chain(self):
        # a -> b -> c
        tree = {"a": ["b"], "b": ["c"], "c": []}
        assert _max_tree_depth(tree) == 2

    def test_avg_branching_factor_empty(self):
        assert _avg_branching_factor({}) == 0.0

    def test_avg_branching_factor(self):
        tree = {"root": ["a", "b", "c"], "a": [], "b": [], "c": []}
        bf = _avg_branching_factor(tree)
        assert bf == pytest.approx(3 / 4)

    def test_get_event_distribution(self):
        events = [
            _make_event(event_type=EventType.AGENT_START),
            _make_event(event_type=EventType.TOOL_CALL),
            _make_event(event_type=EventType.TOOL_CALL),
        ]
        dist = _get_event_distribution(events)
        assert dist["agent_start"] == 1
        assert dist["tool_call"] == 2

    def test_calculate_structural_similarity_both_empty(self):
        assert _calculate_structural_similarity({}, {}) == 1.0

    def test_calculate_structural_similarity_one_empty(self):
        assert _calculate_structural_similarity({"a": []}, {}) == 0.0

    def test_calculate_session_duration_no_timestamps(self):
        # TraceEvent requires datetime; pass empty list to cover the no-events branch
        assert _calculate_session_duration([]) == 0.0

    def test_calculate_session_duration(self):
        from datetime import timedelta

        t1 = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(seconds=30)
        events = [
            TraceEvent(session_id="s", event_type=EventType.AGENT_START, timestamp=t1),
            TraceEvent(session_id="s", event_type=EventType.AGENT_END, timestamp=t2),
        ]
        assert _calculate_session_duration(events) == pytest.approx(30.0)

    def test_compare_timing_patterns_empty(self):
        assert _compare_timing_patterns([], []) == []

    def test_calculate_temporal_divergence_score_empty(self):
        assert _calculate_temporal_divergence_score([]) == 0.0

    def test_calculate_temporal_divergence_score_capped(self):
        diffs = [{"time_difference_seconds": 120.0}]
        score = _calculate_temporal_divergence_score(diffs)
        assert score == 1.0

    def test_compare_tool_usage_only_in_one(self):
        class ToolEvent(TraceEvent):
            pass

        e1 = _make_event("s", EventType.TOOL_CALL)
        e1.tool_name = "search"  # type: ignore[attr-defined]
        e2 = _make_event("s", EventType.TOOL_CALL)
        e2.tool_name = "calculator"  # type: ignore[attr-defined]

        diffs = _compare_tool_usage([e1], [e2])
        tool_names = {d["tool_name"] for d in diffs}
        assert "search" in tool_names
        assert "calculator" in tool_names
        assert all(d["tool_only_in_one"] for d in diffs)

    def test_calculate_behavioral_divergence_score_zero(self):
        assert _calculate_behavioral_divergence_score([], []) == 0.0

    def test_calculate_behavioral_divergence_score_capped(self):
        decision_diffs = [{}] * 10
        tool_diffs = [{}] * 10
        score = _calculate_behavioral_divergence_score(decision_diffs, tool_diffs)
        assert score == 1.0

    def test_analyze_structural_divergence_same(self):
        events = [_make_event("s", EventType.AGENT_START)]
        result = _analyze_structural_divergence(events, events[:])
        assert result["divergence_score"] == 0.0

    def test_analyze_temporal_divergence_no_events(self):
        result = _analyze_temporal_divergence([], [])
        assert result["divergence_score"] == 0.0

    def test_analyze_behavioral_divergence_no_events(self):
        result = _analyze_behavioral_divergence([], [])
        assert result["divergence_score"] == 0.0
