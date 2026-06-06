"""Tests for FrameTracer and DivergenceDetector modules.

Covers agent_debugger_sdk/core/frame_tracer.py and
agent_debugger_sdk/core/divergence_detector.py which previously had zero
test coverage.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

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
    get_cost_breakdown,
    get_frame_by_id,
    get_frame_context,
    get_frames_at_depth,
    set_frame_context,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_event(
    session_id: str = "sess-a",
    event_type: EventType = EventType.LLM_RESPONSE,
    event_id: str | None = None,
    parent_id: str | None = None,
    timestamp: datetime | None = None,
    data: dict | None = None,
) -> TraceEvent:
    return TraceEvent(
        id=event_id or f"ev-{session_id}-{event_type}",
        session_id=session_id,
        event_type=event_type,
        name=str(event_type),
        timestamp=timestamp or datetime.now(timezone.utc),
        parent_id=parent_id,
        data=data or {},
    )


def make_frame(
    frame_id: str = "f1",
    function_name: str = "my_func",
    module_path: str = "my.module.my_func",
    depth: int = 0,
    duration_ms: float = 10.0,
    token_usage: TokenUsage | None = None,
    exception: ExceptionInfo | None = None,
    parent_frame_id: str | None = None,
) -> FrameEvent:
    now = time.time()
    return FrameEvent(
        frame_id=frame_id,
        function_name=function_name,
        module_path=module_path,
        depth=depth,
        duration_ms=duration_ms,
        token_usage=token_usage,
        exception=exception,
        parent_frame_id=parent_frame_id,
        start_time=now,
        end_time=now + duration_ms / 1000,
    )


# ===========================================================================
# TokenUsage
# ===========================================================================


class TestTokenUsage:
    def test_defaults_zero(self):
        u = TokenUsage()
        assert u.prompt_tokens == 0
        assert u.completion_tokens == 0
        assert u.total_tokens == 0

    def test_add_combines_values(self):
        a = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        b = TokenUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30)
        c = a + b
        assert c.prompt_tokens == 30
        assert c.completion_tokens == 15
        assert c.total_tokens == 45

    def test_to_dict_keys(self):
        u = TokenUsage(prompt_tokens=3, completion_tokens=7, total_tokens=10)
        d = u.to_dict()
        assert d == {"prompt_tokens": 3, "completion_tokens": 7, "total_tokens": 10}


# ===========================================================================
# ExceptionInfo
# ===========================================================================


class TestExceptionInfo:
    def test_to_dict_with_traceback(self):
        e = ExceptionInfo(exception_type="ValueError", message="bad input", traceback="tb")
        d = e.to_dict()
        assert d["exception_type"] == "ValueError"
        assert d["message"] == "bad input"
        assert d["traceback"] == "tb"

    def test_to_dict_without_traceback(self):
        e = ExceptionInfo(exception_type="KeyError", message="missing key")
        assert e.to_dict()["traceback"] is None


# ===========================================================================
# FrameEvent
# ===========================================================================


class TestFrameEvent:
    def test_to_dict_contains_all_fields(self):
        usage = TokenUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10)
        frame = make_frame(frame_id="f99", token_usage=usage)
        d = frame.to_dict()
        assert d["frame_id"] == "f99"
        assert d["function_name"] == "my_func"
        assert d["token_usage"] == usage.to_dict()
        assert d["exception"] is None

    def test_to_dict_with_exception(self):
        exc = ExceptionInfo(exception_type="RuntimeError", message="boom")
        frame = make_frame(exception=exc)
        d = frame.to_dict()
        assert d["exception"]["exception_type"] == "RuntimeError"

    def test_children_default_empty(self):
        frame = make_frame()
        assert frame.children == []


# ===========================================================================
# FrameLifetimeTrace
# ===========================================================================


class TestFrameLifetimeTrace:
    def test_to_dict_serializes_frames(self):
        f1 = make_frame("f1")
        f2 = make_frame("f2")
        trace = FrameLifetimeTrace(trace_id="t1", frames=[f1, f2], entry_point="start")
        d = trace.to_dict()
        assert d["trace_id"] == "t1"
        assert len(d["frames"]) == 2
        assert d["entry_point"] == "start"

    def test_empty_frames(self):
        trace = FrameLifetimeTrace(trace_id="empty")
        d = trace.to_dict()
        assert d["frames"] == []


# ===========================================================================
# build_frame_tree
# ===========================================================================


class TestBuildFrameTree:
    def test_empty_list_returns_empty_dict(self):
        assert build_frame_tree([]) == {}

    def test_single_root_frame(self):
        f = make_frame("root")
        tree = build_frame_tree([f])
        assert tree["frame"]["frame_id"] == "root"
        assert tree["children"] == []

    def test_parent_child_relationship(self):
        parent = make_frame("parent")
        child = make_frame("child", parent_frame_id="parent", depth=1)
        parent.children.append("child")
        tree = build_frame_tree([parent, child])
        assert tree["frame"]["frame_id"] == "parent"
        assert len(tree["children"]) == 1
        assert tree["children"][0]["frame"]["frame_id"] == "child"

    def test_multiple_roots_wrapped(self):
        f1 = make_frame("r1")
        f2 = make_frame("r2")
        tree = build_frame_tree([f1, f2])
        assert tree["frame"] is None
        assert len(tree["children"]) == 2


# ===========================================================================
# get_frame_by_id / get_frames_at_depth / filter_frames_by_name
# ===========================================================================


class TestFrameLookupHelpers:
    def setup_method(self):
        self.f1 = make_frame("f1", function_name="alpha", depth=0)
        self.f2 = make_frame("f2", function_name="beta", depth=1)
        self.f3 = make_frame("f3", function_name="alpha_helper", depth=1)
        self.trace = FrameLifetimeTrace(
            trace_id="t", frames=[self.f1, self.f2, self.f3]
        )

    def test_get_frame_by_id_found(self):
        assert get_frame_by_id(self.trace, "f2") is self.f2

    def test_get_frame_by_id_not_found(self):
        assert get_frame_by_id(self.trace, "missing") is None

    def test_get_frames_at_depth_zero(self):
        result = get_frames_at_depth(self.trace, 0)
        assert result == [self.f1]

    def test_get_frames_at_depth_one(self):
        result = get_frames_at_depth(self.trace, 1)
        assert self.f2 in result
        assert self.f3 in result

    def test_filter_frames_by_name_case_insensitive(self):
        result = filter_frames_by_name(self.trace, "ALPHA")
        assert self.f1 in result
        assert self.f3 in result
        assert self.f2 not in result


# ===========================================================================
# get_cost_breakdown
# ===========================================================================


class TestGetCostBreakdown:
    def test_cost_breakdown_groups_by_function(self):
        f1 = make_frame("f1", function_name="query", duration_ms=100.0,
                        token_usage=TokenUsage(total_tokens=50))
        f2 = make_frame("f2", function_name="query", duration_ms=200.0,
                        token_usage=TokenUsage(total_tokens=100))
        f3 = make_frame("f3", function_name="other", duration_ms=50.0)
        trace = FrameLifetimeTrace(trace_id="t", frames=[f1, f2, f3])

        breakdown = get_cost_breakdown(trace)
        assert "query" in breakdown
        assert "other" in breakdown

        q = breakdown["query"]
        assert q.total_calls == 2
        assert q.total_duration_ms == 300.0
        assert q.avg_duration_ms == 150.0
        assert q.total_tokens == 150
        assert q.avg_tokens == 75.0
        assert q.error_count == 0

    def test_error_count_counted(self):
        exc = ExceptionInfo(exception_type="E", message="err")
        f1 = make_frame("f1", function_name="risky", exception=exc)
        f2 = make_frame("f2", function_name="risky")
        trace = FrameLifetimeTrace(trace_id="t", frames=[f1, f2])
        breakdown = get_cost_breakdown(trace)
        assert breakdown["risky"].error_count == 1

    def test_empty_trace_returns_empty(self):
        trace = FrameLifetimeTrace(trace_id="empty")
        assert get_cost_breakdown(trace) == {}


# ===========================================================================
# FrameCaptureContext
# ===========================================================================


class TestFrameCaptureContext:
    def test_add_frame_appended(self):
        ctx = FrameCaptureContext(trace_id="t1")
        f = make_frame("f1")
        ctx.add_frame(f)
        assert f in ctx.frames

    def test_enter_exit_frame_updates_depth(self):
        ctx = FrameCaptureContext()
        ctx.enter_frame("f1")
        assert ctx._current_depth == 1
        ctx.exit_frame("f1")
        assert ctx._current_depth == 0

    def test_exit_ignores_mismatched_id(self):
        ctx = FrameCaptureContext()
        ctx.enter_frame("f1")
        ctx.exit_frame("wrong")
        assert ctx._current_depth == 1

    def test_build_trace_sums_duration(self):
        ctx = FrameCaptureContext(trace_id="t")
        ctx.add_frame(make_frame("a", duration_ms=100.0))
        ctx.add_frame(make_frame("b", duration_ms=200.0))
        trace = ctx.build_trace(entry_point="start")
        assert trace.total_duration_ms == 300.0
        assert trace.entry_point == "start"
        assert len(trace.frames) == 2

    def test_build_trace_sums_tokens(self):
        ctx = FrameCaptureContext(trace_id="t")
        ctx.add_frame(make_frame("a", token_usage=TokenUsage(total_tokens=30)))
        ctx.add_frame(make_frame("b", token_usage=TokenUsage(total_tokens=70)))
        trace = ctx.build_trace()
        assert trace.total_tokens == 100

    def test_to_dict_delegates_to_build_trace(self):
        ctx = FrameCaptureContext(trace_id="t")
        ctx.add_frame(make_frame("x"))
        d = ctx.to_dict()
        assert d["trace_id"] == "t"
        assert len(d["frames"]) == 1


# ===========================================================================
# set_frame_context / get_frame_context
# ===========================================================================


class TestFrameContextGlobal:
    def teardown_method(self):
        set_frame_context(None)

    def test_get_returns_none_by_default(self):
        set_frame_context(None)
        assert get_frame_context() is None

    def test_set_and_get_roundtrip(self):
        ctx = FrameCaptureContext(trace_id="global")
        set_frame_context(ctx)
        assert get_frame_context() is ctx


# ===========================================================================
# capture_function_call decorator
# ===========================================================================


class TestCaptureFunctionCall:
    def teardown_method(self):
        set_frame_context(None)

    def test_no_context_calls_through(self):
        set_frame_context(None)

        @capture_function_call
        def add(a, b):
            return a + b

        assert add(2, 3) == 5

    def test_captures_frame_when_context_active(self):
        ctx = FrameCaptureContext(trace_id="t")
        set_frame_context(ctx)

        @capture_function_call
        def multiply(x, y):
            return x * y

        result = multiply(3, 4)
        assert result == 12
        assert len(ctx.frames) == 1
        assert ctx.frames[0].function_name == "multiply"

    def test_captures_exception_and_reraises(self):
        ctx = FrameCaptureContext(trace_id="t")
        set_frame_context(ctx)

        @capture_function_call
        def broken():
            raise ValueError("oops")

        with pytest.raises(ValueError, match="oops"):
            broken()

        assert len(ctx.frames) == 1
        assert ctx.frames[0].exception is not None
        assert ctx.frames[0].exception.exception_type == "ValueError"

    def test_called_with_kwargs(self):
        @capture_function_call(capture_args=False)
        def noop():
            return "ok"

        assert noop() == "ok"


# ===========================================================================
# DivergenceType / DivergenceSeverity
# ===========================================================================


class TestDivergenceEnums:
    def test_divergence_type_values(self):
        assert str(DivergenceType.STRUCTURAL) == "structural"
        assert str(DivergenceType.TEMPORAL) == "temporal"
        assert str(DivergenceType.BEHAVIORAL) == "behavioral"
        assert str(DivergenceType.STATE) == "state"
        assert str(DivergenceType.ERROR) == "error"
        assert str(DivergenceType.PERFORMANCE) == "performance"

    def test_severity_values(self):
        assert str(DivergenceSeverity.CRITICAL) == "critical"
        assert str(DivergenceSeverity.HIGH) == "high"
        assert str(DivergenceSeverity.MEDIUM) == "medium"
        assert str(DivergenceSeverity.LOW) == "low"


# ===========================================================================
# DivergencePoint
# ===========================================================================


class TestDivergencePoint:
    def test_to_dict_minimal(self):
        dp = DivergencePoint(
            divergence_type=DivergenceType.STRUCTURAL,
            severity=DivergenceSeverity.LOW,
        )
        d = dp.to_dict()
        assert d["divergence_type"] == "structural"
        assert d["severity"] == "low"
        assert d["primary_event_id"] is None
        assert d["timestamp"] is None
        assert d["divergence_score"] == 0.0

    def test_to_dict_with_timestamp(self):
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        dp = DivergencePoint(
            divergence_type=DivergenceType.TEMPORAL,
            severity=DivergenceSeverity.HIGH,
            timestamp=ts,
            divergence_score=0.7,
        )
        d = dp.to_dict()
        assert d["timestamp"] == ts.isoformat()
        assert d["divergence_score"] == 0.7


# ===========================================================================
# SessionComparison
# ===========================================================================


class TestSessionComparison:
    def test_defaults(self):
        sc = SessionComparison(primary_session_id="a", secondary_session_id="b")
        assert sc.overall_divergence_score == 0.0
        assert sc.structural_similarity == 1.0
        assert sc.temporal_similarity == 1.0
        assert sc.behavioral_similarity == 1.0
        assert sc.divergence_points == []

    def test_to_dict(self):
        sc = SessionComparison(
            primary_session_id="a",
            secondary_session_id="b",
            overall_divergence_score=0.5,
        )
        d = sc.to_dict()
        assert d["primary_session_id"] == "a"
        assert d["overall_divergence_score"] == 0.5
        assert d["divergence_points"] == []


# ===========================================================================
# detect_divergences
# ===========================================================================


class TestDetectDivergences:
    def test_both_empty_returns_perfect_similarity(self):
        result = detect_divergences([], [])
        assert result.overall_divergence_score == 0.0
        assert result.structural_similarity == 1.0
        assert result.temporal_similarity == 1.0
        assert result.behavioral_similarity == 1.0

    def test_uses_session_id_from_first_event(self):
        events = [make_event(session_id="sess-x", event_id="e1")]
        result = detect_divergences(events, events)
        assert result.primary_session_id == "sess-x"

    def test_identical_traces_low_divergence(self):
        events = [
            make_event("s1", EventType.LLM_RESPONSE, "e1"),
            make_event("s1", EventType.TOOL_CALL, "e2"),
        ]
        result = detect_divergences(events, events)
        assert result.overall_divergence_score < 0.2

    def test_different_event_counts_produce_divergence(self):
        primary = [make_event("s1", EventType.LLM_RESPONSE, f"e{i}") for i in range(5)]
        secondary = [make_event("s2", EventType.LLM_RESPONSE, f"f{i}") for i in range(20)]
        result = detect_divergences(primary, secondary)
        assert result.overall_divergence_score > 0.0

    def test_summary_contains_expected_keys(self):
        events = [make_event("s", event_id="e1")]
        result = detect_divergences(events, events)
        assert "primary_event_count" in result.comparison_summary
        assert "total_divergences" in result.comparison_summary
        assert "critical_divergences" in result.comparison_summary

    def test_divergence_score_bounded(self):
        primary = [make_event("a", EventType.LLM_RESPONSE, f"e{i}") for i in range(30)]
        secondary = [make_event("b", EventType.DECISION, f"f{i}") for i in range(30)]
        result = detect_divergences(primary, secondary)
        assert 0.0 <= result.overall_divergence_score <= 1.0


# ===========================================================================
# compare_session_structures
# ===========================================================================


class TestCompareSessionStructures:
    def test_returns_expected_keys(self):
        events = [make_event("s", event_id="e1")]
        result = compare_session_structures(events, events)
        assert "primary_depth" in result
        assert "secondary_depth" in result
        assert "structural_similarity" in result
        assert "event_type_distribution_primary" in result

    def test_identical_events_high_similarity(self):
        events = [make_event("s", EventType.LLM_RESPONSE, f"e{i}") for i in range(5)]
        result = compare_session_structures(events, events)
        assert result["structural_similarity"] >= 0.9


# ===========================================================================
# analyze_temporal_divergence
# ===========================================================================


class TestAnalyzeTemporalDivergence:
    def test_empty_inputs_return_zeros(self):
        result = analyze_temporal_divergence([], [])
        assert result["primary_duration_seconds"] == 0.0
        assert result["secondary_duration_seconds"] == 0.0
        assert result["temporal_divergence_score"] == 0.0

    def test_same_timestamps_zero_divergence(self):
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        events = [make_event("s", timestamp=ts, event_id=f"e{i}") for i in range(3)]
        result = analyze_temporal_divergence(events, events)
        assert result["temporal_divergence_score"] == 0.0

    def test_duration_difference_calculated(self):
        from datetime import timedelta

        base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        primary = [
            make_event("p", timestamp=base, event_id="p1"),
            make_event("p", timestamp=base + timedelta(seconds=10), event_id="p2"),
        ]
        secondary = [
            make_event("s", timestamp=base, event_id="s1"),
            make_event("s", timestamp=base + timedelta(seconds=60), event_id="s2"),
        ]
        result = analyze_temporal_divergence(primary, secondary)
        assert result["duration_difference_seconds"] == pytest.approx(50.0, abs=0.1)

    def test_return_keys_present(self):
        events = [make_event("s", event_id="e1")]
        result = analyze_temporal_divergence(events, events)
        assert "primary_duration_seconds" in result
        assert "secondary_duration_seconds" in result
        assert "duration_difference_seconds" in result
        assert "temporal_divergence_score" in result
        assert "timing_differences" in result


# ===========================================================================
# analyze_behavioral_divergence
# ===========================================================================


class TestAnalyzeBehavioralDivergence:
    def test_empty_inputs(self):
        result = analyze_behavioral_divergence([], [])
        assert result["primary_decision_count"] == 0
        assert result["secondary_decision_count"] == 0
        assert result["behavioral_divergence_score"] == 0.0

    def test_counts_decision_events(self):
        primary = [
            make_event("a", EventType.DECISION, "d1"),
            make_event("a", EventType.DECISION, "d2"),
            make_event("a", EventType.LLM_RESPONSE, "r1"),
        ]
        secondary = [
            make_event("b", EventType.DECISION, "d3"),
        ]
        result = analyze_behavioral_divergence(primary, secondary)
        assert result["primary_decision_count"] == 2
        assert result["secondary_decision_count"] == 1

    def test_counts_tool_calls(self):
        primary = [make_event("a", EventType.TOOL_CALL, f"t{i}") for i in range(3)]
        secondary = [make_event("b", EventType.TOOL_CALL, f"u{i}") for i in range(1)]
        result = analyze_behavioral_divergence(primary, secondary)
        assert result["primary_tool_call_count"] == 3
        assert result["secondary_tool_call_count"] == 1

    def test_result_keys_present(self):
        result = analyze_behavioral_divergence([], [])
        expected_keys = {
            "primary_decision_count",
            "secondary_decision_count",
            "primary_tool_call_count",
            "secondary_tool_call_count",
            "decision_divergences",
            "tool_divergences",
            "behavioral_divergence_score",
        }
        assert expected_keys.issubset(result.keys())

    def test_divergence_score_bounded(self):
        primary = [make_event("a", EventType.DECISION, f"d{i}") for i in range(15)]
        secondary = [make_event("b", EventType.TOOL_CALL, f"t{i}") for i in range(15)]
        result = analyze_behavioral_divergence(primary, secondary)
        assert 0.0 <= result["behavioral_divergence_score"] <= 1.0
