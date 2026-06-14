"""Unit tests for agent_debugger_sdk/core/frame_tracer.py."""

from __future__ import annotations

import pytest

from agent_debugger_sdk.core.frame_tracer import (
    ExceptionInfo,
    FrameCaptureContext,
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


def _frame(
    frame_id: str = "f1",
    function_name: str = "my_func",
    module_path: str = "mod.my_func",
    parent_frame_id: str | None = None,
    depth: int = 0,
    duration_ms: float = 10.0,
    token_usage: TokenUsage | None = None,
    exception: ExceptionInfo | None = None,
    children: list[str] | None = None,
) -> FrameEvent:
    return FrameEvent(
        frame_id=frame_id,
        function_name=function_name,
        module_path=module_path,
        parent_frame_id=parent_frame_id,
        depth=depth,
        duration_ms=duration_ms,
        token_usage=token_usage,
        exception=exception,
        children=children or [],
    )


def _trace(frames: list[FrameEvent] | None = None, trace_id: str = "t1") -> FrameLifetimeTrace:
    return FrameLifetimeTrace(trace_id=trace_id, frames=frames or [])


# ---------------------------------------------------------------------------
# TokenUsage
# ---------------------------------------------------------------------------


class TestTokenUsage:
    def test_add(self) -> None:
        a = TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        b = TokenUsage(prompt_tokens=5, completion_tokens=10, total_tokens=15)
        result = a + b
        assert result.prompt_tokens == 15
        assert result.completion_tokens == 30
        assert result.total_tokens == 45

    def test_to_dict(self) -> None:
        t = TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3)
        d = t.to_dict()
        assert d == {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}

    def test_default_values(self) -> None:
        t = TokenUsage()
        assert t.prompt_tokens == 0
        assert t.completion_tokens == 0
        assert t.total_tokens == 0


# ---------------------------------------------------------------------------
# ExceptionInfo
# ---------------------------------------------------------------------------


class TestExceptionInfo:
    def test_to_dict_with_traceback(self) -> None:
        e = ExceptionInfo(exception_type="ValueError", message="bad value", traceback="tb here")
        d = e.to_dict()
        assert d == {
            "exception_type": "ValueError",
            "message": "bad value",
            "traceback": "tb here",
        }

    def test_to_dict_no_traceback(self) -> None:
        e = ExceptionInfo(exception_type="RuntimeError", message="oops")
        d = e.to_dict()
        assert d["traceback"] is None


# ---------------------------------------------------------------------------
# FrameEvent
# ---------------------------------------------------------------------------


class TestFrameEvent:
    def test_to_dict_basic(self) -> None:
        f = _frame()
        d = f.to_dict()
        assert d["frame_id"] == "f1"
        assert d["function_name"] == "my_func"
        assert d["module_path"] == "mod.my_func"
        assert d["parent_frame_id"] is None
        assert d["exception"] is None
        assert d["token_usage"] is None
        assert d["children"] == []

    def test_to_dict_with_exception(self) -> None:
        exc = ExceptionInfo(exception_type="TypeError", message="type err")
        f = _frame(exception=exc)
        d = f.to_dict()
        assert d["exception"]["exception_type"] == "TypeError"

    def test_to_dict_with_token_usage(self) -> None:
        tu = TokenUsage(prompt_tokens=5, completion_tokens=10, total_tokens=15)
        f = _frame(token_usage=tu)
        d = f.to_dict()
        assert d["token_usage"]["total_tokens"] == 15

    def test_children_are_copied(self) -> None:
        f = _frame(children=["c1", "c2"])
        d = f.to_dict()
        assert d["children"] == ["c1", "c2"]
        d["children"].append("c3")
        assert f.children == ["c1", "c2"]


# ---------------------------------------------------------------------------
# build_frame_tree
# ---------------------------------------------------------------------------


class TestBuildFrameTree:
    def test_empty_frames_returns_empty_dict(self) -> None:
        assert build_frame_tree([]) == {}

    def test_single_root_frame(self) -> None:
        f = _frame(frame_id="root")
        tree = build_frame_tree([f])
        assert tree["frame"]["frame_id"] == "root"
        assert tree["children"] == []

    def test_parent_child_relationship(self) -> None:
        parent = _frame(frame_id="p", children=["c"])
        child = _frame(frame_id="c", parent_frame_id="p", depth=1)
        tree = build_frame_tree([parent, child])
        assert tree["frame"]["frame_id"] == "p"
        assert len(tree["children"]) == 1
        assert tree["children"][0]["frame"]["frame_id"] == "c"

    def test_multiple_roots_wrapped(self) -> None:
        f1 = _frame(frame_id="r1")
        f2 = _frame(frame_id="r2")
        tree = build_frame_tree([f1, f2])
        assert tree["frame"] is None
        assert len(tree["children"]) == 2


# ---------------------------------------------------------------------------
# get_frame_by_id
# ---------------------------------------------------------------------------


class TestGetFrameById:
    def test_returns_frame_when_found(self) -> None:
        f = _frame(frame_id="abc")
        trace = _trace([f])
        result = get_frame_by_id(trace, "abc")
        assert result is f

    def test_returns_none_when_not_found(self) -> None:
        trace = _trace([_frame(frame_id="x")])
        assert get_frame_by_id(trace, "missing") is None

    def test_returns_none_for_empty_trace(self) -> None:
        trace = _trace([])
        assert get_frame_by_id(trace, "any") is None


# ---------------------------------------------------------------------------
# get_frames_at_depth
# ---------------------------------------------------------------------------


class TestGetFramesAtDepth:
    def test_filters_by_depth(self) -> None:
        f0 = _frame(frame_id="a", depth=0)
        f1 = _frame(frame_id="b", depth=1)
        f2 = _frame(frame_id="c", depth=1)
        trace = _trace([f0, f1, f2])
        result = get_frames_at_depth(trace, 1)
        assert len(result) == 2
        ids = {f.frame_id for f in result}
        assert ids == {"b", "c"}

    def test_returns_empty_when_no_match(self) -> None:
        trace = _trace([_frame(depth=0)])
        assert get_frames_at_depth(trace, 5) == []

    def test_depth_zero(self) -> None:
        f = _frame(depth=0)
        trace = _trace([f])
        assert get_frames_at_depth(trace, 0) == [f]


# ---------------------------------------------------------------------------
# filter_frames_by_name
# ---------------------------------------------------------------------------


class TestFilterFramesByName:
    def test_case_insensitive_match(self) -> None:
        f1 = _frame(frame_id="1", function_name="FetchData")
        f2 = _frame(frame_id="2", function_name="process")
        trace = _trace([f1, f2])
        result = filter_frames_by_name(trace, "fetch")
        assert result == [f1]

    def test_substring_match(self) -> None:
        f = _frame(function_name="get_user_profile")
        trace = _trace([f])
        assert filter_frames_by_name(trace, "user") == [f]

    def test_no_match_returns_empty(self) -> None:
        trace = _trace([_frame(function_name="alpha")])
        assert filter_frames_by_name(trace, "beta") == []

    def test_matches_multiple(self) -> None:
        f1 = _frame(frame_id="1", function_name="load_data")
        f2 = _frame(frame_id="2", function_name="save_data")
        trace = _trace([f1, f2])
        assert len(filter_frames_by_name(trace, "data")) == 2


# ---------------------------------------------------------------------------
# get_cost_breakdown
# ---------------------------------------------------------------------------


class TestGetCostBreakdown:
    def test_empty_trace(self) -> None:
        trace = _trace([])
        assert get_cost_breakdown(trace) == {}

    def test_single_function(self) -> None:
        f = _frame(function_name="fn", duration_ms=50.0)
        trace = _trace([f])
        breakdown = get_cost_breakdown(trace)
        assert "fn" in breakdown
        cost = breakdown["fn"]
        assert cost.total_calls == 1
        assert cost.total_duration_ms == 50.0
        assert cost.avg_duration_ms == 50.0
        assert cost.error_count == 0

    def test_aggregates_multiple_calls(self) -> None:
        f1 = _frame(frame_id="1", function_name="fn", duration_ms=20.0)
        f2 = _frame(frame_id="2", function_name="fn", duration_ms=40.0)
        trace = _trace([f1, f2])
        cost = get_cost_breakdown(trace)["fn"]
        assert cost.total_calls == 2
        assert cost.total_duration_ms == 60.0
        assert cost.avg_duration_ms == 30.0

    def test_counts_errors(self) -> None:
        exc = ExceptionInfo(exception_type="Err", message="msg")
        f1 = _frame(frame_id="1", function_name="fn")
        f2 = _frame(frame_id="2", function_name="fn", exception=exc)
        trace = _trace([f1, f2])
        assert get_cost_breakdown(trace)["fn"].error_count == 1

    def test_aggregates_tokens(self) -> None:
        tu = TokenUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10)
        f = _frame(function_name="fn", token_usage=tu)
        trace = _trace([f])
        assert get_cost_breakdown(trace)["fn"].total_tokens == 10

    def test_frame_cost_to_dict(self) -> None:
        f = _frame(function_name="fn", duration_ms=100.0)
        cost = get_cost_breakdown(_trace([f]))["fn"]
        d = cost.to_dict()
        assert d["function_name"] == "fn"
        assert d["total_calls"] == 1


# ---------------------------------------------------------------------------
# FrameCaptureContext
# ---------------------------------------------------------------------------


class TestFrameCaptureContext:
    def test_custom_trace_id(self) -> None:
        ctx = FrameCaptureContext(trace_id="my-id")
        assert ctx.trace_id == "my-id"

    def test_auto_trace_id(self) -> None:
        ctx = FrameCaptureContext()
        assert ctx.trace_id  # non-empty

    def test_add_frame_appends(self) -> None:
        ctx = FrameCaptureContext()
        f = _frame()
        ctx.add_frame(f)
        assert f in ctx.frames

    def test_enter_exit_frame_stack(self) -> None:
        ctx = FrameCaptureContext()
        ctx.enter_frame("f1")
        assert ctx._parent_stack == ["f1"]
        assert ctx._current_depth == 1
        ctx.exit_frame("f1")
        assert ctx._parent_stack == []
        assert ctx._current_depth == 0

    def test_exit_wrong_frame_is_noop(self) -> None:
        ctx = FrameCaptureContext()
        ctx.enter_frame("f1")
        ctx.exit_frame("wrong")
        assert ctx._parent_stack == ["f1"]

    def test_add_frame_sets_parent_and_depth(self) -> None:
        ctx = FrameCaptureContext(trace_id="t")
        parent = _frame(frame_id="p")
        ctx.add_frame(parent)
        ctx.enter_frame("p")

        child = _frame(frame_id="c")
        ctx.add_frame(child)

        assert child.parent_frame_id == "p"
        assert child.depth == 1
        assert "c" in parent.children

    def test_build_trace_aggregates(self) -> None:
        ctx = FrameCaptureContext(trace_id="t")
        f1 = _frame(frame_id="1", duration_ms=30.0)
        f2 = _frame(frame_id="2", duration_ms=70.0)
        ctx.add_frame(f1)
        ctx.add_frame(f2)
        trace = ctx.build_trace(entry_point="root")
        assert trace.total_duration_ms == 100.0
        assert trace.entry_point == "root"
        assert len(trace.frames) == 2

    def test_build_trace_totals_tokens(self) -> None:
        ctx = FrameCaptureContext()
        tu = TokenUsage(total_tokens=50)
        f = _frame(token_usage=tu)
        ctx.add_frame(f)
        trace = ctx.build_trace()
        assert trace.total_tokens == 50

    def test_to_dict(self) -> None:
        ctx = FrameCaptureContext(trace_id="t")
        ctx.add_frame(_frame())
        d = ctx.to_dict()
        assert d["trace_id"] == "t"
        assert isinstance(d["frames"], list)


# ---------------------------------------------------------------------------
# Global frame context helpers
# ---------------------------------------------------------------------------


class TestFrameContextHelpers:
    def setup_method(self) -> None:
        set_frame_context(None)

    def teardown_method(self) -> None:
        set_frame_context(None)

    def test_set_and_get_context(self) -> None:
        ctx = FrameCaptureContext()
        set_frame_context(ctx)
        assert get_frame_context() is ctx

    def test_set_none_clears_context(self) -> None:
        set_frame_context(FrameCaptureContext())
        set_frame_context(None)
        assert get_frame_context() is None


# ---------------------------------------------------------------------------
# capture_function_call decorator
# ---------------------------------------------------------------------------


class TestCaptureFunctionCall:
    def setup_method(self) -> None:
        set_frame_context(None)

    def teardown_method(self) -> None:
        set_frame_context(None)

    def test_no_context_calls_function_normally(self) -> None:
        @capture_function_call
        def add(a: int, b: int) -> int:
            return a + b

        assert add(2, 3) == 5

    def test_captures_frame_in_context(self) -> None:
        ctx = FrameCaptureContext()
        set_frame_context(ctx)

        @capture_function_call
        def greet(name: str) -> str:
            return f"hi {name}"

        result = greet("world")
        assert result == "hi world"
        assert len(ctx.frames) == 1
        frame = ctx.frames[0]
        assert frame.function_name == "greet"
        assert frame.duration_ms >= 0

    def test_captures_args(self) -> None:
        ctx = FrameCaptureContext()
        set_frame_context(ctx)

        @capture_function_call
        def fn(x: int, y: int = 0) -> int:
            return x + y

        fn(10, y=5)
        assert ctx.frames[0].call_args.get("x") == 10

    def test_captures_exception_info(self) -> None:
        ctx = FrameCaptureContext()
        set_frame_context(ctx)

        @capture_function_call
        def boom() -> None:
            raise ValueError("kaboom")

        with pytest.raises(ValueError):
            boom()

        assert len(ctx.frames) == 1
        exc = ctx.frames[0].exception
        assert exc is not None
        assert exc.exception_type == "ValueError"
        assert "kaboom" in exc.message

    def test_called_with_kwargs(self) -> None:
        ctx = FrameCaptureContext()
        set_frame_context(ctx)

        @capture_function_call(capture_args=False, capture_return=False)
        def fn() -> str:
            return "ok"

        result = fn()
        assert result == "ok"
        assert ctx.frames[0].call_args == {}

    def test_nested_frames_have_parent_child(self) -> None:
        ctx = FrameCaptureContext()
        set_frame_context(ctx)

        @capture_function_call
        def inner() -> None:
            pass

        @capture_function_call
        def outer() -> None:
            inner()

        outer()
        assert len(ctx.frames) == 2
        # outer is added before inner exits (check depths)
        depths = {f.function_name: f.depth for f in ctx.frames}
        assert depths["outer"] < depths["inner"] or depths["inner"] > 0


# ---------------------------------------------------------------------------
# _serialize_value
# ---------------------------------------------------------------------------


class TestSerializeValue:
    def test_none(self) -> None:
        assert _serialize_value(None) is None

    def test_primitives(self) -> None:
        assert _serialize_value(42) == 42
        assert _serialize_value(3.14) == 3.14
        assert _serialize_value(True) is True
        assert _serialize_value("hello") == "hello"

    def test_list(self) -> None:
        assert _serialize_value([1, 2, 3]) == [1, 2, 3]

    def test_tuple_becomes_list(self) -> None:
        assert _serialize_value((1, 2)) == [1, 2]

    def test_dict(self) -> None:
        assert _serialize_value({"a": 1}) == {"a": 1}

    def test_custom_object_stringified(self) -> None:
        class Foo:
            def __str__(self) -> str:
                return "foo_str"

        result = _serialize_value(Foo())
        assert result == "foo_str"

    def test_nested_structure(self) -> None:
        result = _serialize_value({"key": [1, None, "x"]})
        assert result == {"key": [1, None, "x"]}


# ---------------------------------------------------------------------------
# to_dict / from_dict round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_empty_trace(self) -> None:
        trace = FrameLifetimeTrace(trace_id="rt1")
        d = to_dict(trace)
        restored = from_dict(d)
        assert restored.trace_id == "rt1"
        assert restored.frames == []

    def test_trace_with_frames(self) -> None:
        tu = TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3)
        exc = ExceptionInfo(exception_type="E", message="m", traceback="tb")
        f = FrameEvent(
            frame_id="fx",
            function_name="fn",
            module_path="mod.fn",
            duration_ms=42.0,
            depth=1,
            token_usage=tu,
            exception=exc,
        )
        trace = FrameLifetimeTrace(
            trace_id="rt2",
            frames=[f],
            entry_point="fn",
            total_duration_ms=42.0,
            total_tokens=3,
        )
        d = to_dict(trace)
        restored = from_dict(d)
        assert restored.trace_id == "rt2"
        assert len(restored.frames) == 1
        rf = restored.frames[0]
        assert rf.frame_id == "fx"
        assert rf.token_usage is not None
        assert rf.token_usage.total_tokens == 3
        assert rf.exception is not None
        assert rf.exception.exception_type == "E"

    def test_to_dict_fields(self) -> None:
        trace = FrameLifetimeTrace(trace_id="t", entry_point="ep", total_duration_ms=5.0, total_tokens=10)
        d = to_dict(trace)
        assert d["trace_id"] == "t"
        assert d["entry_point"] == "ep"
        assert d["total_duration_ms"] == 5.0
        assert d["total_tokens"] == 10
