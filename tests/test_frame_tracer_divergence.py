"""Unit tests for FrameTracer and DivergenceDetector (issue #208)."""

from __future__ import annotations

import uuid
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
# Helpers
# ===========================================================================


def _make_event(
    session_id: str = "sess-a",
    event_type: EventType = EventType.AGENT_START,
    timestamp: datetime | None = None,
    parent_id: str | None = None,
    **kwargs,
) -> TraceEvent:
    return TraceEvent(
        id=str(uuid.uuid4()),
        session_id=session_id,
        event_type=event_type,
        timestamp=timestamp or datetime.now(timezone.utc),
        parent_id=parent_id,
        **kwargs,
    )


def _make_frame(
    function_name: str = "fn",
    module_path: str = "mod.fn",
    duration_ms: float = 10.0,
    depth: int = 0,
    parent_frame_id: str | None = None,
) -> FrameEvent:
    return FrameEvent(
        frame_id=str(uuid.uuid4()),
        function_name=function_name,
        module_path=module_path,
        duration_ms=duration_ms,
        depth=depth,
        parent_frame_id=parent_frame_id,
    )


# ===========================================================================
# TokenUsage
# ===========================================================================


class TestTokenUsage:
    def test_default_fields_are_zero(self):
        tu = TokenUsage()
        assert tu.prompt_tokens == 0
        assert tu.completion_tokens == 0
        assert tu.total_tokens == 0

    def test_add(self):
        a = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        b = TokenUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30)
        result = a + b
        assert result.prompt_tokens == 30
        assert result.completion_tokens == 15
        assert result.total_tokens == 45

    def test_add_identity(self):
        a = TokenUsage(prompt_tokens=7, completion_tokens=3, total_tokens=10)
        zero = TokenUsage()
        assert (a + zero).total_tokens == 10
        assert (zero + a).total_tokens == 10

    def test_to_dict(self):
        tu = TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3)
        d = tu.to_dict()
        assert d == {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}

    def test_to_dict_keys_complete(self):
        d = TokenUsage().to_dict()
        assert set(d.keys()) == {"prompt_tokens", "completion_tokens", "total_tokens"}


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
    def test_construction_defaults(self):
        fe = FrameEvent(frame_id="fid", function_name="fn", module_path="m.fn")
        assert fe.parent_frame_id is None
        assert fe.exception is None
        assert fe.token_usage is None
        assert fe.depth == 0
        assert fe.children == []

    def test_to_dict_basic(self):
        fe = FrameEvent(
            frame_id="fid",
            function_name="my_func",
            module_path="mymod.my_func",
            start_time=1.0,
            end_time=1.1,
            duration_ms=100.0,
        )
        d = fe.to_dict()
        assert d["frame_id"] == "fid"
        assert d["function_name"] == "my_func"
        assert d["module_path"] == "mymod.my_func"
        assert d["duration_ms"] == 100.0
        assert d["exception"] is None
        assert d["token_usage"] is None

    def test_to_dict_with_token_usage(self):
        tu = TokenUsage(prompt_tokens=5, completion_tokens=3, total_tokens=8)
        fe = FrameEvent(frame_id="f1", function_name="fn", module_path="m", token_usage=tu)
        d = fe.to_dict()
        assert d["token_usage"] == {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}

    def test_to_dict_with_exception(self):
        ei = ExceptionInfo(exception_type="ValueError", message="err")
        fe = FrameEvent(frame_id="f1", function_name="fn", module_path="m", exception=ei)
        d = fe.to_dict()
        assert d["exception"]["exception_type"] == "ValueError"

    def test_to_dict_children_copied(self):
        fe = FrameEvent(frame_id="f1", function_name="fn", module_path="m", children=["c1", "c2"])
        d = fe.to_dict()
        assert d["children"] == ["c1", "c2"]


# ===========================================================================
# FrameLifetimeTrace
# ===========================================================================


class TestFrameLifetimeTrace:
    def test_construction(self):
        trace = FrameLifetimeTrace(trace_id="t1")
        assert trace.frames == []
        assert trace.entry_point == ""
        assert trace.total_duration_ms == 0.0
        assert trace.total_tokens == 0

    def test_to_dict_empty(self):
        trace = FrameLifetimeTrace(trace_id="t1")
        d = trace.to_dict()
        assert d["trace_id"] == "t1"
        assert d["frames"] == []
        assert d["total_tokens"] == 0

    def test_to_dict_with_frames(self):
        fe = _make_frame()
        trace = FrameLifetimeTrace(trace_id="t1", frames=[fe], total_duration_ms=50.0, total_tokens=10)
        d = trace.to_dict()
        assert len(d["frames"]) == 1
        assert d["total_duration_ms"] == 50.0
        assert d["total_tokens"] == 10


# ===========================================================================
# build_frame_tree
# ===========================================================================


class TestBuildFrameTree:
    def test_empty(self):
        assert build_frame_tree([]) == {}

    def test_single_root(self):
        fe = FrameEvent(frame_id="root", function_name="main", module_path="mod")
        tree = build_frame_tree([fe])
        assert tree["frame"]["frame_id"] == "root"
        assert tree["children"] == []

    def test_parent_child(self):
        parent = FrameEvent(frame_id="p", function_name="parent", module_path="m")
        child = FrameEvent(
            frame_id="c",
            function_name="child",
            module_path="m",
            parent_frame_id="p",
        )
        parent.children.append("c")
        tree = build_frame_tree([parent, child])
        assert tree["frame"]["frame_id"] == "p"
        assert len(tree["children"]) == 1
        assert tree["children"][0]["frame"]["frame_id"] == "c"

    def test_multiple_roots_wrapped(self):
        a = FrameEvent(frame_id="a", function_name="a", module_path="m")
        b = FrameEvent(frame_id="b", function_name="b", module_path="m")
        tree = build_frame_tree([a, b])
        assert tree["frame"] is None
        assert len(tree["children"]) == 2


# ===========================================================================
# get_frame_by_id
# ===========================================================================


class TestGetFrameById:
    def test_found(self):
        fe = _make_frame(function_name="fn")
        trace = FrameLifetimeTrace(trace_id="t", frames=[fe])
        assert get_frame_by_id(trace, fe.frame_id) is fe

    def test_not_found(self):
        trace = FrameLifetimeTrace(trace_id="t", frames=[])
        assert get_frame_by_id(trace, "missing") is None


# ===========================================================================
# get_frames_at_depth
# ===========================================================================


class TestGetFramesAtDepth:
    def test_filters_by_depth(self):
        f0 = _make_frame(depth=0)
        f1 = _make_frame(depth=1)
        f1b = _make_frame(depth=1)
        trace = FrameLifetimeTrace(trace_id="t", frames=[f0, f1, f1b])
        result = get_frames_at_depth(trace, 1)
        assert len(result) == 2
        assert f0 not in result

    def test_empty_trace(self):
        trace = FrameLifetimeTrace(trace_id="t")
        assert get_frames_at_depth(trace, 0) == []


# ===========================================================================
# filter_frames_by_name
# ===========================================================================


class TestFilterFramesByName:
    def test_matches_substring(self):
        f1 = _make_frame(function_name="process_data")
        f2 = _make_frame(function_name="load_config")
        trace = FrameLifetimeTrace(trace_id="t", frames=[f1, f2])
        result = filter_frames_by_name(trace, "process")
        assert result == [f1]

    def test_case_insensitive(self):
        f = _make_frame(function_name="ProcessData")
        trace = FrameLifetimeTrace(trace_id="t", frames=[f])
        assert filter_frames_by_name(trace, "processdata") == [f]

    def test_no_match(self):
        f = _make_frame(function_name="something_else")
        trace = FrameLifetimeTrace(trace_id="t", frames=[f])
        assert filter_frames_by_name(trace, "xyz") == []


# ===========================================================================
# get_cost_breakdown
# ===========================================================================


class TestGetCostBreakdown:
    def test_single_function(self):
        f1 = _make_frame(function_name="fn", duration_ms=20.0)
        f2 = _make_frame(function_name="fn", duration_ms=30.0)
        trace = FrameLifetimeTrace(trace_id="t", frames=[f1, f2])
        breakdown = get_cost_breakdown(trace)
        assert "fn" in breakdown
        cost = breakdown["fn"]
        assert cost.total_calls == 2
        assert cost.total_duration_ms == 50.0
        assert cost.avg_duration_ms == 25.0
        assert cost.error_count == 0

    def test_counts_errors(self):
        ei = ExceptionInfo(exception_type="ValueError", message="err")
        f = _make_frame(function_name="bad_fn")
        f.exception = ei
        trace = FrameLifetimeTrace(trace_id="t", frames=[f])
        breakdown = get_cost_breakdown(trace)
        assert breakdown["bad_fn"].error_count == 1

    def test_token_aggregation(self):
        f = _make_frame(function_name="llm_call")
        f.token_usage = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        trace = FrameLifetimeTrace(trace_id="t", frames=[f])
        breakdown = get_cost_breakdown(trace)
        assert breakdown["llm_call"].total_tokens == 15
        assert breakdown["llm_call"].avg_tokens == 15.0

    def test_empty_trace(self):
        trace = FrameLifetimeTrace(trace_id="t")
        assert get_cost_breakdown(trace) == {}

    def test_multiple_functions(self):
        f1 = _make_frame(function_name="a")
        f2 = _make_frame(function_name="b")
        trace = FrameLifetimeTrace(trace_id="t", frames=[f1, f2])
        breakdown = get_cost_breakdown(trace)
        assert set(breakdown.keys()) == {"a", "b"}


# ===========================================================================
# FrameCaptureContext
# ===========================================================================


class TestFrameCaptureContext:
    def test_default_trace_id_generated(self):
        ctx = FrameCaptureContext()
        assert ctx.trace_id  # not empty

    def test_custom_trace_id(self):
        ctx = FrameCaptureContext(trace_id="my-trace")
        assert ctx.trace_id == "my-trace"

    def test_add_frame(self):
        ctx = FrameCaptureContext(trace_id="t")
        fe = FrameEvent(frame_id="f1", function_name="fn", module_path="m")
        ctx.add_frame(fe)
        assert fe in ctx.frames

    def test_enter_exit_frame_updates_depth(self):
        ctx = FrameCaptureContext(trace_id="t")
        ctx.enter_frame("f1")
        assert ctx._current_depth == 1
        ctx.exit_frame("f1")
        assert ctx._current_depth == 0

    def test_exit_wrong_frame_is_noop(self):
        ctx = FrameCaptureContext(trace_id="t")
        ctx.enter_frame("f1")
        ctx.exit_frame("not-f1")  # should not pop
        assert ctx._current_depth == 1

    def test_build_trace_aggregates_totals(self):
        ctx = FrameCaptureContext(trace_id="t")
        f1 = FrameEvent(
            frame_id="f1",
            function_name="fn",
            module_path="m",
            duration_ms=40.0,
            token_usage=TokenUsage(total_tokens=10),
        )
        f2 = FrameEvent(
            frame_id="f2",
            function_name="fn2",
            module_path="m",
            duration_ms=60.0,
        )
        ctx.add_frame(f1)
        ctx.add_frame(f2)
        trace = ctx.build_trace(entry_point="fn")
        assert trace.total_duration_ms == 100.0
        assert trace.total_tokens == 10
        assert trace.entry_point == "fn"
        assert len(trace.frames) == 2

    def test_parent_child_linking_via_enter(self):
        ctx = FrameCaptureContext(trace_id="t")
        parent = FrameEvent(frame_id="p", function_name="parent", module_path="m")
        ctx.add_frame(parent)
        ctx.enter_frame("p")
        child = FrameEvent(frame_id="c", function_name="child", module_path="m")
        ctx.add_frame(child)
        ctx.exit_frame("p")
        assert child.parent_frame_id == "p"
        assert "c" in parent.children

    def test_to_dict(self):
        ctx = FrameCaptureContext(trace_id="t")
        d = ctx.to_dict()
        assert d["trace_id"] == "t"
        assert d["frames"] == []


# ===========================================================================
# Global frame context
# ===========================================================================


class TestGlobalFrameContext:
    def teardown_method(self):
        set_frame_context(None)

    def test_set_and_get(self):
        ctx = FrameCaptureContext(trace_id="global")
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
    def teardown_method(self):
        set_frame_context(None)

    def test_no_context_passthrough(self):
        @capture_function_call
        def add(x, y):
            return x + y

        assert add(2, 3) == 5

    def test_captures_frame_with_context(self):
        ctx = FrameCaptureContext(trace_id="t")
        set_frame_context(ctx)

        @capture_function_call
        def multiply(x, y):
            return x * y

        result = multiply(3, 4)
        assert result == 12
        assert len(ctx.frames) == 1
        frame = ctx.frames[0]
        assert frame.function_name == "multiply"
        assert frame.duration_ms >= 0.0

    def test_captures_args(self):
        ctx = FrameCaptureContext(trace_id="t")
        set_frame_context(ctx)

        @capture_function_call
        def greet(name):
            return f"hello {name}"

        greet("world")
        assert ctx.frames[0].call_args.get("name") == "world"

    def test_captures_exception_info(self):
        ctx = FrameCaptureContext(trace_id="t")
        set_frame_context(ctx)

        @capture_function_call
        def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            fail()

        assert ctx.frames[0].exception is not None
        assert ctx.frames[0].exception.exception_type == "ValueError"
        assert ctx.frames[0].exception.message == "boom"

    def test_with_kwargs(self):
        ctx = FrameCaptureContext(trace_id="t")
        set_frame_context(ctx)

        @capture_function_call(capture_args=False, capture_return=False)
        def noop(x):
            return x

        noop(42)
        frame = ctx.frames[0]
        assert frame.call_args == {}
        assert frame.return_value is None

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
        names = {f.function_name for f in ctx.frames}
        assert "outer" in names
        assert "inner" in names
        assert len(ctx.frames) == 2


# ===========================================================================
# to_dict / from_dict round-trip
# ===========================================================================


class TestRoundTrip:
    def test_round_trip_empty_trace(self):
        original = FrameLifetimeTrace(trace_id="rt1")
        restored = from_dict(to_dict(original))
        assert restored.trace_id == "rt1"
        assert restored.frames == []

    def test_round_trip_with_frame(self):
        fe = FrameEvent(
            frame_id="f1",
            function_name="my_func",
            module_path="mymod.my_func",
            duration_ms=25.0,
            token_usage=TokenUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
        )
        original = FrameLifetimeTrace(trace_id="rt2", frames=[fe], total_tokens=5)
        restored = from_dict(to_dict(original))
        assert len(restored.frames) == 1
        rf = restored.frames[0]
        assert rf.frame_id == "f1"
        assert rf.function_name == "my_func"
        assert rf.token_usage is not None
        assert rf.token_usage.total_tokens == 5

    def test_round_trip_with_exception(self):
        ei = ExceptionInfo(exception_type="TypeError", message="type err", traceback="tb")
        fe = FrameEvent(frame_id="f1", function_name="fn", module_path="m", exception=ei)
        original = FrameLifetimeTrace(trace_id="rt3", frames=[fe])
        restored = from_dict(to_dict(original))
        assert restored.frames[0].exception.exception_type == "TypeError"


# ===========================================================================
# DivergenceType and DivergenceSeverity enums
# ===========================================================================


class TestDivergenceEnums:
    def test_divergence_type_values(self):
        assert str(DivergenceType.STRUCTURAL) == "structural"
        assert str(DivergenceType.TEMPORAL) == "temporal"
        assert str(DivergenceType.BEHAVIORAL) == "behavioral"
        assert str(DivergenceType.STATE) == "state"
        assert str(DivergenceType.ERROR) == "error"
        assert str(DivergenceType.PERFORMANCE) == "performance"

    def test_divergence_severity_values(self):
        assert str(DivergenceSeverity.CRITICAL) == "critical"
        assert str(DivergenceSeverity.HIGH) == "high"
        assert str(DivergenceSeverity.MEDIUM) == "medium"
        assert str(DivergenceSeverity.LOW) == "low"

    def test_enum_membership(self):
        assert DivergenceType("structural") == DivergenceType.STRUCTURAL
        assert DivergenceSeverity("high") == DivergenceSeverity.HIGH


# ===========================================================================
# DivergencePoint
# ===========================================================================


class TestDivergencePoint:
    def test_to_dict_basic(self):
        dp = DivergencePoint(
            divergence_type=DivergenceType.BEHAVIORAL,
            severity=DivergenceSeverity.HIGH,
            description="test",
            divergence_score=0.7,
        )
        d = dp.to_dict()
        assert d["divergence_type"] == "behavioral"
        assert d["severity"] == "high"
        assert d["description"] == "test"
        assert d["divergence_score"] == 0.7
        assert d["timestamp"] is None

    def test_to_dict_with_timestamp(self):
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        dp = DivergencePoint(
            divergence_type=DivergenceType.TEMPORAL,
            severity=DivergenceSeverity.LOW,
            timestamp=ts,
        )
        d = dp.to_dict()
        assert "2024-01-01" in d["timestamp"]

    def test_to_dict_with_metadata(self):
        dp = DivergencePoint(
            divergence_type=DivergenceType.STATE,
            severity=DivergenceSeverity.MEDIUM,
            metadata={"key": "value"},
        )
        d = dp.to_dict()
        assert d["metadata"] == {"key": "value"}

    def test_to_dict_event_ids(self):
        dp = DivergencePoint(
            divergence_type=DivergenceType.STRUCTURAL,
            severity=DivergenceSeverity.CRITICAL,
            primary_event_id="e1",
            secondary_event_id="e2",
        )
        d = dp.to_dict()
        assert d["primary_event_id"] == "e1"
        assert d["secondary_event_id"] == "e2"


# ===========================================================================
# SessionComparison
# ===========================================================================


class TestSessionComparison:
    def test_defaults(self):
        sc = SessionComparison(primary_session_id="a", secondary_session_id="b")
        assert sc.divergence_points == []
        assert sc.overall_divergence_score == 0.0
        assert sc.structural_similarity == 1.0
        assert sc.temporal_similarity == 1.0
        assert sc.behavioral_similarity == 1.0

    def test_to_dict(self):
        dp = DivergencePoint(
            divergence_type=DivergenceType.STRUCTURAL,
            severity=DivergenceSeverity.LOW,
        )
        sc = SessionComparison(
            primary_session_id="a",
            secondary_session_id="b",
            divergence_points=[dp],
            overall_divergence_score=0.1,
        )
        d = sc.to_dict()
        assert d["primary_session_id"] == "a"
        assert d["secondary_session_id"] == "b"
        assert len(d["divergence_points"]) == 1
        assert d["overall_divergence_score"] == 0.1


# ===========================================================================
# detect_divergences
# ===========================================================================


class TestDetectDivergences:
    def test_both_empty(self):
        result = detect_divergences([], [])
        assert result.overall_divergence_score == 0.0
        assert result.structural_similarity == 1.0
        assert result.temporal_similarity == 1.0
        assert result.behavioral_similarity == 1.0
        assert result.divergence_points == []

    def test_session_ids_extracted(self):
        e1 = _make_event(session_id="sess-1")
        e2 = _make_event(session_id="sess-2")
        result = detect_divergences([e1], [e2])
        assert result.primary_session_id == "sess-1"
        assert result.secondary_session_id == "sess-2"

    def test_identical_sessions_low_divergence(self):
        events = [_make_event(session_id="s", event_type=EventType.AGENT_START)]
        result = detect_divergences(events, events)
        assert result.overall_divergence_score == 0.0
        assert result.structural_similarity == 1.0

    def test_different_event_counts_creates_structural_divergences(self):
        primary = [_make_event(session_id="a") for _ in range(3)]
        secondary = [_make_event(session_id="b") for _ in range(10)]
        result = detect_divergences(primary, secondary)
        structural_divs = [
            d for d in result.divergence_points
            if d.divergence_type == DivergenceType.STRUCTURAL
        ]
        assert len(structural_divs) > 0

    def test_summary_contains_counts(self):
        e1 = _make_event(session_id="a")
        e2 = _make_event(session_id="b")
        result = detect_divergences([e1], [e2])
        assert result.comparison_summary["primary_event_count"] == 1
        assert result.comparison_summary["secondary_event_count"] == 1
        assert "total_divergences" in result.comparison_summary

    def test_overall_score_bounded(self):
        primary = [_make_event(session_id="a") for _ in range(50)]
        secondary = [_make_event(session_id="b") for _ in range(1)]
        result = detect_divergences(primary, secondary)
        assert 0.0 <= result.overall_divergence_score <= 1.0

    def test_one_empty_session(self):
        events = [_make_event(session_id="a") for _ in range(5)]
        result = detect_divergences(events, [])
        assert result.primary_session_id == "a"
        assert result.secondary_session_id == ""

    def test_to_dict_serializable(self):
        import json
        e1 = _make_event(session_id="a")
        e2 = _make_event(session_id="b")
        result = detect_divergences([e1], [e2])
        d = result.to_dict()
        # Should be JSON-serializable
        json.dumps(d)


# ===========================================================================
# compare_session_structures
# ===========================================================================


class TestCompareSessionStructures:
    def test_returns_expected_keys(self):
        e = _make_event(session_id="a")
        result = compare_session_structures([e], [e])
        assert "primary_depth" in result
        assert "secondary_depth" in result
        assert "structural_similarity" in result
        assert "event_type_distribution_primary" in result
        assert "event_type_distribution_secondary" in result

    def test_same_events_full_similarity(self):
        events = [_make_event(session_id="s")]
        result = compare_session_structures(events, events)
        assert result["structural_similarity"] == 1.0

    def test_empty_vs_empty(self):
        result = compare_session_structures([], [])
        assert result["structural_similarity"] == 1.0
        assert result["primary_depth"] == 0

    def test_empty_vs_nonempty(self):
        events = [_make_event(session_id="a")]
        result = compare_session_structures([], events)
        assert result["structural_similarity"] == 0.0

    def test_event_distribution_counts(self):
        events = [
            _make_event(session_id="s", event_type=EventType.TOOL_CALL),
            _make_event(session_id="s", event_type=EventType.TOOL_CALL),
            _make_event(session_id="s", event_type=EventType.LLM_REQUEST),
        ]
        result = compare_session_structures(events, [])
        dist = result["event_type_distribution_primary"]
        assert dist.get("tool_call") == 2
        assert dist.get("llm_request") == 1


# ===========================================================================
# analyze_temporal_divergence
# ===========================================================================


class TestAnalyzeTemporalDivergence:
    def test_empty_returns_zero(self):
        result = analyze_temporal_divergence([], [])
        assert result["temporal_divergence_score"] == 0.0
        assert result["primary_duration_seconds"] == 0.0

    def test_one_empty_returns_zero(self):
        events = [_make_event(session_id="a")]
        result = analyze_temporal_divergence(events, [])
        assert result["temporal_divergence_score"] == 0.0

    def test_same_timing_no_divergence(self):
        ts = datetime.now(timezone.utc)
        events = [_make_event(session_id="a", timestamp=ts)]
        result = analyze_temporal_divergence(events, events)
        assert result["temporal_divergence_score"] == 0.0

    def test_detects_duration_difference(self):
        base = datetime.now(timezone.utc)
        primary = [
            _make_event(session_id="a", timestamp=base),
            _make_event(session_id="a", timestamp=base + timedelta(seconds=10)),
        ]
        secondary = [
            _make_event(session_id="b", timestamp=base),
            _make_event(session_id="b", timestamp=base + timedelta(seconds=100)),
        ]
        result = analyze_temporal_divergence(primary, secondary)
        assert result["duration_difference_seconds"] == pytest.approx(90.0, abs=1.0)

    def test_result_has_expected_keys(self):
        e = _make_event(session_id="a")
        result = analyze_temporal_divergence([e], [e])
        assert "primary_duration_seconds" in result
        assert "secondary_duration_seconds" in result
        assert "temporal_divergence_score" in result
        assert "timing_differences" in result


# ===========================================================================
# analyze_behavioral_divergence
# ===========================================================================


class TestAnalyzeBehavioralDivergence:
    def test_empty_sessions(self):
        result = analyze_behavioral_divergence([], [])
        assert result["primary_decision_count"] == 0
        assert result["secondary_decision_count"] == 0
        assert result["behavioral_divergence_score"] == 0.0

    def test_counts_decisions_and_tools(self):
        events = [
            _make_event(session_id="a", event_type=EventType.DECISION),
            _make_event(session_id="a", event_type=EventType.DECISION),
            _make_event(session_id="a", event_type=EventType.TOOL_CALL),
        ]
        result = analyze_behavioral_divergence(events, [])
        assert result["primary_decision_count"] == 2
        assert result["primary_tool_call_count"] == 1
        assert result["secondary_decision_count"] == 0

    def test_same_behavior_low_divergence(self):
        events = [_make_event(session_id="a", event_type=EventType.DECISION)]
        result = analyze_behavioral_divergence(events, events)
        assert result["behavioral_divergence_score"] == 0.0

    def test_result_has_expected_keys(self):
        result = analyze_behavioral_divergence([], [])
        assert "primary_decision_count" in result
        assert "secondary_decision_count" in result
        assert "primary_tool_call_count" in result
        assert "secondary_tool_call_count" in result
        assert "decision_divergences" in result
        assert "tool_divergences" in result
        assert "behavioral_divergence_score" in result

    def test_tool_divergence_detected(self):
        from agent_debugger_sdk.core.events import ToolCallEvent

        primary = [
            ToolCallEvent(session_id="a", tool_name="search"),
        ]
        secondary = [
            ToolCallEvent(session_id="b", tool_name="write_file"),
        ]
        result = analyze_behavioral_divergence(primary, secondary)
        assert result["behavioral_divergence_score"] > 0.0
        assert len(result["tool_divergences"]) > 0
