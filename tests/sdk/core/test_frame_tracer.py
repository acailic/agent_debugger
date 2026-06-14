"""Unit tests for agent_debugger_sdk.core.frame_tracer."""

from __future__ import annotations

import uuid

import pytest

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


def make_frame(
    frame_id: str | None = None,
    function_name: str = "test_func",
    module_path: str = "test_module.test_func",
    depth: int = 0,
    duration_ms: float = 10.0,
    parent_frame_id: str | None = None,
    token_usage: TokenUsage | None = None,
    exception: ExceptionInfo | None = None,
) -> FrameEvent:
    return FrameEvent(
        frame_id=frame_id or str(uuid.uuid4()),
        function_name=function_name,
        module_path=module_path,
        depth=depth,
        duration_ms=duration_ms,
        parent_frame_id=parent_frame_id,
        token_usage=token_usage,
        exception=exception,
    )


# ── TokenUsage ───────────────────────────────────────────────────────────────

class TestTokenUsage:
    def test_to_dict(self):
        tu = TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        assert tu.to_dict() == {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        }

    def test_add(self):
        a = TokenUsage(prompt_tokens=5, completion_tokens=10, total_tokens=15)
        b = TokenUsage(prompt_tokens=3, completion_tokens=7, total_tokens=10)
        result = a + b
        assert result.prompt_tokens == 8
        assert result.completion_tokens == 17
        assert result.total_tokens == 25

    def test_add_zeros(self):
        a = TokenUsage()
        b = TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3)
        assert (a + b).total_tokens == 3

    def test_defaults_are_zero(self):
        tu = TokenUsage()
        assert tu.prompt_tokens == 0
        assert tu.completion_tokens == 0
        assert tu.total_tokens == 0


# ── ExceptionInfo ────────────────────────────────────────────────────────────

class TestExceptionInfo:
    def test_to_dict_with_traceback(self):
        ei = ExceptionInfo(exception_type="ValueError", message="bad", traceback="tb")
        d = ei.to_dict()
        assert d["exception_type"] == "ValueError"
        assert d["message"] == "bad"
        assert d["traceback"] == "tb"

    def test_to_dict_without_traceback(self):
        ei = ExceptionInfo(exception_type="RuntimeError", message="oops")
        assert ei.to_dict()["traceback"] is None


# ── FrameEvent ───────────────────────────────────────────────────────────────

class TestFrameEvent:
    def test_to_dict_minimal(self):
        fid = str(uuid.uuid4())
        frame = FrameEvent(frame_id=fid, function_name="f", module_path="m.f")
        d = frame.to_dict()
        assert d["frame_id"] == fid
        assert d["function_name"] == "f"
        assert d["module_path"] == "m.f"
        assert d["exception"] is None
        assert d["token_usage"] is None
        assert d["children"] == []

    def test_to_dict_with_token_usage(self):
        tu = TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3)
        frame = make_frame(token_usage=tu)
        d = frame.to_dict()
        assert d["token_usage"]["total_tokens"] == 3

    def test_to_dict_with_exception(self):
        ei = ExceptionInfo(exception_type="TypeError", message="bad type")
        frame = make_frame(exception=ei)
        d = frame.to_dict()
        assert d["exception"]["exception_type"] == "TypeError"

    def test_children_serialized(self):
        frame = make_frame()
        child_id = str(uuid.uuid4())
        frame.children.append(child_id)
        assert frame.to_dict()["children"] == [child_id]


# ── FrameCost ────────────────────────────────────────────────────────────────

class TestFrameCost:
    def test_to_dict(self):
        fc = FrameCost(
            function_name="my_func",
            total_calls=5,
            total_duration_ms=100.0,
            avg_duration_ms=20.0,
            total_tokens=50,
            avg_tokens=10.0,
            error_count=1,
        )
        d = fc.to_dict()
        assert d["function_name"] == "my_func"
        assert d["total_calls"] == 5
        assert d["error_count"] == 1


# ── FrameLifetimeTrace ───────────────────────────────────────────────────────

class TestFrameLifetimeTrace:
    def test_to_dict_empty(self):
        trace = FrameLifetimeTrace(trace_id="t1")
        d = trace.to_dict()
        assert d["trace_id"] == "t1"
        assert d["frames"] == []
        assert d["total_tokens"] == 0

    def test_to_dict_with_frames(self):
        frame = make_frame()
        trace = FrameLifetimeTrace(trace_id="t2", frames=[frame])
        d = trace.to_dict()
        assert len(d["frames"]) == 1


# ── build_frame_tree ─────────────────────────────────────────────────────────

class TestBuildFrameTree:
    def test_empty(self):
        assert build_frame_tree([]) == {}

    def test_single_root(self):
        frame = make_frame(frame_id="root")
        tree = build_frame_tree([frame])
        assert tree["frame"]["frame_id"] == "root"
        assert tree["children"] == []

    def test_parent_child(self):
        parent = make_frame(frame_id="p")
        child = make_frame(frame_id="c", parent_frame_id="p")
        parent.children.append("c")
        tree = build_frame_tree([parent, child])
        assert tree["frame"]["frame_id"] == "p"
        assert len(tree["children"]) == 1
        assert tree["children"][0]["frame"]["frame_id"] == "c"

    def test_multiple_roots(self):
        r1 = make_frame(frame_id="r1")
        r2 = make_frame(frame_id="r2")
        tree = build_frame_tree([r1, r2])
        # Virtual root wraps multiple roots
        assert tree["frame"] is None
        assert len(tree["children"]) == 2


# ── get_frame_by_id ──────────────────────────────────────────────────────────

class TestGetFrameById:
    def test_found(self):
        frame = make_frame(frame_id="abc")
        trace = FrameLifetimeTrace(trace_id="t", frames=[frame])
        assert get_frame_by_id(trace, "abc") is frame

    def test_not_found(self):
        trace = FrameLifetimeTrace(trace_id="t", frames=[])
        assert get_frame_by_id(trace, "missing") is None


# ── get_frames_at_depth ──────────────────────────────────────────────────────

class TestGetFramesAtDepth:
    def test_filter_by_depth(self):
        f0 = make_frame(depth=0)
        f1a = make_frame(depth=1)
        f1b = make_frame(depth=1)
        f2 = make_frame(depth=2)
        trace = FrameLifetimeTrace(trace_id="t", frames=[f0, f1a, f1b, f2])
        assert get_frames_at_depth(trace, 1) == [f1a, f1b]

    def test_no_match(self):
        f0 = make_frame(depth=0)
        trace = FrameLifetimeTrace(trace_id="t", frames=[f0])
        assert get_frames_at_depth(trace, 5) == []


# ── filter_frames_by_name ────────────────────────────────────────────────────

class TestFilterFramesByName:
    def test_case_insensitive_match(self):
        f1 = make_frame(function_name="MyAgent")
        f2 = make_frame(function_name="other")
        trace = FrameLifetimeTrace(trace_id="t", frames=[f1, f2])
        result = filter_frames_by_name(trace, "myagent")
        assert f1 in result
        assert f2 not in result

    def test_substring_match(self):
        f = make_frame(function_name="process_request")
        trace = FrameLifetimeTrace(trace_id="t", frames=[f])
        assert filter_frames_by_name(trace, "request") == [f]

    def test_no_match(self):
        trace = FrameLifetimeTrace(trace_id="t", frames=[make_frame(function_name="foo")])
        assert filter_frames_by_name(trace, "bar") == []


# ── get_cost_breakdown ───────────────────────────────────────────────────────

class TestGetCostBreakdown:
    def test_single_function(self):
        f = make_frame(function_name="fn", duration_ms=100.0)
        trace = FrameLifetimeTrace(trace_id="t", frames=[f])
        breakdown = get_cost_breakdown(trace)
        assert "fn" in breakdown
        cost = breakdown["fn"]
        assert cost.total_calls == 1
        assert cost.total_duration_ms == 100.0
        assert cost.avg_duration_ms == 100.0
        assert cost.error_count == 0

    def test_multiple_calls_same_function(self):
        frames = [make_frame(function_name="fn", duration_ms=10.0) for _ in range(3)]
        trace = FrameLifetimeTrace(trace_id="t", frames=frames)
        cost = get_cost_breakdown(trace)["fn"]
        assert cost.total_calls == 3
        assert cost.total_duration_ms == 30.0
        assert cost.avg_duration_ms == 10.0

    def test_error_count(self):
        ei = ExceptionInfo(exception_type="ValueError", message="err")
        f1 = make_frame(function_name="fn", exception=ei)
        f2 = make_frame(function_name="fn")
        trace = FrameLifetimeTrace(trace_id="t", frames=[f1, f2])
        assert get_cost_breakdown(trace)["fn"].error_count == 1

    def test_token_aggregation(self):
        tu = TokenUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10)
        f1 = make_frame(function_name="fn", token_usage=tu)
        f2 = make_frame(function_name="fn", token_usage=tu)
        trace = FrameLifetimeTrace(trace_id="t", frames=[f1, f2])
        cost = get_cost_breakdown(trace)["fn"]
        assert cost.total_tokens == 20
        assert cost.avg_tokens == 10.0

    def test_empty_trace(self):
        trace = FrameLifetimeTrace(trace_id="t", frames=[])
        assert get_cost_breakdown(trace) == {}


# ── FrameCaptureContext ───────────────────────────────────────────────────────

class TestFrameCaptureContext:
    def test_initial_state(self):
        ctx = FrameCaptureContext(trace_id="t1")
        assert ctx.trace_id == "t1"
        assert ctx.frames == []
        assert ctx._current_depth == 0

    def test_auto_trace_id(self):
        ctx = FrameCaptureContext()
        assert ctx.trace_id  # non-empty UUID

    def test_enter_exit_frame(self):
        ctx = FrameCaptureContext()
        ctx.enter_frame("f1")
        assert ctx._current_depth == 1
        ctx.exit_frame("f1")
        assert ctx._current_depth == 0

    def test_exit_wrong_frame_no_crash(self):
        ctx = FrameCaptureContext()
        ctx.enter_frame("f1")
        ctx.exit_frame("wrong")  # Should not pop
        assert ctx._current_depth == 1

    def test_add_frame_sets_parent(self):
        ctx = FrameCaptureContext()
        parent = make_frame(frame_id="parent")
        ctx.frames.append(parent)
        ctx._parent_stack.append("parent")

        child = make_frame(frame_id="child")
        ctx.add_frame(child)

        assert child.parent_frame_id == "parent"
        assert child.depth == 1
        assert "child" in parent.children

    def test_build_trace(self):
        ctx = FrameCaptureContext(trace_id="trace1")
        f = make_frame(duration_ms=50.0)
        ctx.frames.append(f)
        tu = TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3)
        f.token_usage = tu
        trace = ctx.build_trace(entry_point="main")
        assert trace.trace_id == "trace1"
        assert trace.entry_point == "main"
        assert trace.total_duration_ms == 50.0
        assert trace.total_tokens == 3
        assert len(trace.frames) == 1

    def test_to_dict(self):
        ctx = FrameCaptureContext(trace_id="t")
        d = ctx.to_dict()
        assert d["trace_id"] == "t"
        assert d["frames"] == []


# ── capture_function_call decorator ─────────────────────────────────────────

class TestCaptureFunctionCall:
    def setup_method(self):
        self.ctx = FrameCaptureContext(trace_id="test")
        set_frame_context(self.ctx)

    def teardown_method(self):
        set_frame_context(None)

    def test_captures_basic_call(self):
        @capture_function_call
        def add(a: int, b: int) -> int:
            return a + b

        result = add(2, 3)
        assert result == 5
        assert len(self.ctx.frames) == 1
        frame = self.ctx.frames[0]
        assert frame.function_name == "add"
        assert frame.duration_ms >= 0

    def test_captures_args(self):
        @capture_function_call
        def greet(name: str) -> str:
            return f"hello {name}"

        greet("world")
        frame = self.ctx.frames[0]
        assert frame.call_args.get("name") == "world"

    def test_captures_return_value(self):
        @capture_function_call
        def get_value() -> int:
            return 42

        get_value()
        assert self.ctx.frames[0].return_value == 42

    def test_captures_exception(self):
        @capture_function_call
        def fail() -> None:
            raise ValueError("boom")

        with pytest.raises(ValueError):
            fail()

        frame = self.ctx.frames[0]
        assert frame.exception is not None
        assert frame.exception.exception_type == "ValueError"
        assert frame.exception.message == "boom"

    def test_no_context_passthrough(self):
        set_frame_context(None)

        @capture_function_call
        def noop() -> str:
            return "ok"

        assert noop() == "ok"

    def test_decorator_with_options(self):
        @capture_function_call(capture_args=False, capture_return=False)
        def process(x: int) -> int:
            return x * 2

        process(5)
        frame = self.ctx.frames[0]
        assert frame.call_args == {}
        assert frame.return_value is None

    def test_nested_calls_depth(self):
        @capture_function_call
        def inner() -> str:
            return "inner"

        @capture_function_call
        def outer() -> str:
            return inner()

        outer()
        depths = {f.function_name: f.depth for f in self.ctx.frames}
        assert depths["outer"] < depths["inner"]


# ── _serialize_value ─────────────────────────────────────────────────────────

class TestSerializeValue:
    def test_primitives(self):
        assert _serialize_value(None) is None
        assert _serialize_value(42) == 42
        assert _serialize_value(3.14) == 3.14
        assert _serialize_value(True) is True
        assert _serialize_value("hello") == "hello"

    def test_list(self):
        assert _serialize_value([1, 2, 3]) == [1, 2, 3]

    def test_tuple_becomes_list(self):
        result = _serialize_value((1, 2))
        assert result == [1, 2]

    def test_dict(self):
        assert _serialize_value({"k": "v"}) == {"k": "v"}

    def test_unknown_type_uses_str(self):
        class Custom:
            def __str__(self) -> str:
                return "custom_repr"

        assert _serialize_value(Custom()) == "custom_repr"

    def test_nested(self):
        result = _serialize_value({"items": [1, (2, 3)]})
        assert result == {"items": [1, [2, 3]]}


# ── to_dict / from_dict round-trip ───────────────────────────────────────────

class TestRoundTrip:
    def test_round_trip_minimal(self):
        trace = FrameLifetimeTrace(trace_id="rt1")
        d = to_dict(trace)
        restored = from_dict(d)
        assert restored.trace_id == "rt1"
        assert restored.frames == []

    def test_round_trip_with_frame(self):
        fid = str(uuid.uuid4())
        frame = FrameEvent(
            frame_id=fid,
            function_name="fn",
            module_path="mod.fn",
            depth=1,
            duration_ms=25.5,
            start_time=1000.0,
            end_time=1000.0255,
        )
        trace = FrameLifetimeTrace(trace_id="rt2", frames=[frame])
        restored = from_dict(to_dict(trace))
        assert len(restored.frames) == 1
        rf = restored.frames[0]
        assert rf.frame_id == fid
        assert rf.function_name == "fn"
        assert rf.duration_ms == 25.5

    def test_round_trip_with_exception(self):
        ei = ExceptionInfo(exception_type="TypeError", message="bad", traceback="tb")
        frame = make_frame(exception=ei)
        trace = FrameLifetimeTrace(trace_id="rt3", frames=[frame])
        restored = from_dict(to_dict(trace))
        assert restored.frames[0].exception is not None
        assert restored.frames[0].exception.exception_type == "TypeError"

    def test_round_trip_with_token_usage(self):
        tu = TokenUsage(prompt_tokens=5, completion_tokens=10, total_tokens=15)
        frame = make_frame(token_usage=tu)
        trace = FrameLifetimeTrace(trace_id="rt4", frames=[frame])
        restored = from_dict(to_dict(trace))
        rt = restored.frames[0].token_usage
        assert rt is not None
        assert rt.total_tokens == 15


# ── get_frame_context / set_frame_context ────────────────────────────────────

class TestFrameContextGlobalState:
    def teardown_method(self):
        set_frame_context(None)

    def test_default_none(self):
        set_frame_context(None)
        assert get_frame_context() is None

    def test_set_and_get(self):
        ctx = FrameCaptureContext()
        set_frame_context(ctx)
        assert get_frame_context() is ctx

    def test_replace(self):
        ctx1 = FrameCaptureContext()
        ctx2 = FrameCaptureContext()
        set_frame_context(ctx1)
        set_frame_context(ctx2)
        assert get_frame_context() is ctx2
