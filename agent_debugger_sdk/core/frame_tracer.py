"""Frame Lifetime Trace module for function-level tracing.

Based on the ADI paper (FSE 2026), this module provides fine-grained function-level
tracing capabilities for agent execution analysis. It captures individual function
calls, their relationships, execution metrics, and token usage patterns.
"""

from __future__ import annotations

import functools
import inspect
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(kw_only=True)
class TokenUsage:
    """Token usage information for a function call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        """Combine two TokenUsage instances."""
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )

    def to_dict(self) -> dict[str, int]:
        """Serialize to dictionary."""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(kw_only=True)
class ExceptionInfo:
    """Serialized exception information."""

    exception_type: str
    message: str
    traceback: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Serialize to dictionary."""
        return {
            "exception_type": self.exception_type,
            "message": self.message,
            "traceback": self.traceback,
        }


@dataclass(kw_only=True)
class FrameEvent:
    """A single function call frame event.

    Captures the execution of a single function call including its inputs,
    outputs, timing, and relationships to other function calls.

    Attributes:
        frame_id: Unique identifier for this frame
        function_name: The function being traced
        module_path: Module/class the function belongs to
        parent_frame_id: Parent frame for nested calls
        call_args: Serialized function arguments
        return_value: Serialized return value
        exception: If the function raised an exception
        start_time: Timestamp of call start
        end_time: Timestamp of call end
        duration_ms: Execution duration in milliseconds
        token_usage: If the function made LLM calls
        depth: Call stack depth
        children: Child frame IDs (nested calls)
    """

    frame_id: str
    function_name: str
    module_path: str
    parent_frame_id: str | None = None
    call_args: dict[str, Any] = field(default_factory=dict)
    return_value: Any = None
    exception: ExceptionInfo | None = None
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0
    token_usage: TokenUsage | None = None
    depth: int = 0
    children: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "frame_id": self.frame_id,
            "function_name": self.function_name,
            "module_path": self.module_path,
            "parent_frame_id": self.parent_frame_id,
            "call_args": self.call_args,
            "return_value": self.return_value,
            "exception": self.exception.to_dict() if self.exception else None,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "token_usage": self.token_usage.to_dict() if self.token_usage else None,
            "depth": self.depth,
            "children": list(self.children),
        }


@dataclass(kw_only=True)
class FrameCost:
    """Cost breakdown for a function or set of frames."""

    function_name: str
    total_calls: int
    total_duration_ms: float
    avg_duration_ms: float
    total_tokens: int
    avg_tokens: float
    error_count: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "function_name": self.function_name,
            "total_calls": self.total_calls,
            "total_duration_ms": self.total_duration_ms,
            "avg_duration_ms": self.avg_duration_ms,
            "total_tokens": self.total_tokens,
            "avg_tokens": self.avg_tokens,
            "error_count": self.error_count,
        }


@dataclass(kw_only=True)
class FrameLifetimeTrace:
    """Complete function-level trace for an agent session.

    A FrameLifetimeTrace captures all function calls during an agent's execution,
    organized hierarchically to show call relationships and patterns.

    Attributes:
        trace_id: Links to session
        frames: All captured frames
        entry_point: The top-level function
        total_duration_ms: Total execution time
        total_tokens: Total tokens used
        frame_tree: Hierarchical structure of frames
    """

    trace_id: str
    frames: list[FrameEvent] = field(default_factory=list)
    entry_point: str = ""
    total_duration_ms: float = 0.0
    total_tokens: int = 0
    frame_tree: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "trace_id": self.trace_id,
            "frames": [frame.to_dict() for frame in self.frames],
            "entry_point": self.entry_point,
            "total_duration_ms": self.total_duration_ms,
            "total_tokens": self.total_tokens,
            "frame_tree": dict(self.frame_tree),
        }


def build_frame_tree(frames: list[FrameEvent]) -> dict[str, Any]:
    """Build hierarchical tree from flat frame list.

    Args:
        frames: List of frame events to organize

    Returns:
        Hierarchical dictionary structure of frames
    """
    if not frames:
        return {}

    # Create a map of frame_id -> frame
    frame_map = {frame.frame_id: frame for frame in frames}

    # Find root frames (no parent or parent not in our frames)
    root_frames = [
        frame for frame in frames
        if frame.parent_frame_id is None or frame.parent_frame_id not in frame_map
    ]

    def build_subtree(frame: FrameEvent) -> dict[str, Any]:
        """Recursively build subtree for a frame."""
        children_data = []
        for child_id in frame.children:
            if child_id in frame_map:
                children_data.append(build_subtree(frame_map[child_id]))

        return {
            "frame": frame.to_dict(),
            "children": children_data,
        }

    # Build tree for each root frame
    if len(root_frames) == 1:
        return build_subtree(root_frames[0])
    else:
        # Multiple root frames - wrap in a virtual root
        return {
            "frame": None,
            "children": [build_subtree(root) for root in root_frames],
        }


def get_frame_by_id(trace: FrameLifetimeTrace, frame_id: str) -> FrameEvent | None:
    """Get a frame by its ID.

    Args:
        trace: The frame lifetime trace to search
        frame_id: The frame ID to find

    Returns:
        The FrameEvent if found, None otherwise
    """
    for frame in trace.frames:
        if frame.frame_id == frame_id:
            return frame
    return None


def get_frames_at_depth(trace: FrameLifetimeTrace, depth: int) -> list[FrameEvent]:
    """Get all frames at a specific call stack depth.

    Args:
        trace: The frame lifetime trace to search
        depth: The depth to filter by (0 = top-level)

    Returns:
        List of frames at the specified depth
    """
    return [frame for frame in trace.frames if frame.depth == depth]


def filter_frames_by_name(trace: FrameLifetimeTrace, name_pattern: str) -> list[FrameEvent]:
    """Filter frames by function name pattern.

    Args:
        trace: The frame lifetime trace to search
        name_pattern: Pattern to match (supports substring matching)

    Returns:
        List of frames matching the name pattern
    """
    pattern_lower = name_pattern.lower()
    return [
        frame for frame in trace.frames
        if pattern_lower in frame.function_name.lower()
    ]


def get_cost_breakdown(trace: FrameLifetimeTrace) -> dict[str, FrameCost]:
    """Calculate per-function token/latency costs.

    Args:
        trace: The frame lifetime trace to analyze

    Returns:
        Dictionary mapping function names to cost breakdowns
    """
    from collections import defaultdict

    # Group by function name
    frames_by_function: dict[str, list[FrameEvent]] = defaultdict(list)
    for frame in trace.frames:
        frames_by_function[frame.function_name].append(frame)

    # Calculate cost breakdown for each function
    cost_breakdown: dict[str, FrameCost] = {}
    for function_name, frames in frames_by_function.items():
        total_duration = sum(frame.duration_ms for frame in frames)
        total_tokens = sum(
            frame.token_usage.total_tokens if frame.token_usage else 0
            for frame in frames
        )
        error_count = sum(1 for frame in frames if frame.exception)

        cost_breakdown[function_name] = FrameCost(
            function_name=function_name,
            total_calls=len(frames),
            total_duration_ms=total_duration,
            avg_duration_ms=total_duration / len(frames) if frames else 0.0,
            total_tokens=total_tokens,
            avg_tokens=total_tokens / len(frames) if frames else 0.0,
            error_count=error_count,
        )

    return cost_breakdown


class FrameCaptureContext:
    """Context manager for capturing frame-level traces."""

    def __init__(self, trace_id: str | None = None) -> None:
        """Initialize the frame capture context.

        Args:
            trace_id: Optional trace ID to link to session
        """
        self.trace_id = trace_id or str(uuid.uuid4())
        self.frames: list[FrameEvent] = []
        self._current_depth = 0
        self._parent_stack: list[str] = []

    def add_frame(self, frame: FrameEvent) -> None:
        """Add a frame to the trace.

        Args:
            frame: The frame event to add
        """
        self.frames.append(frame)

        # Update parent-child relationships
        if self._parent_stack:
            parent_id = self._parent_stack[-1]
            frame.parent_frame_id = parent_id
            frame.depth = len(self._parent_stack)

            # Add this frame as child of parent
            parent_frame = get_frame_by_id(
                FrameLifetimeTrace(trace_id=self.trace_id, frames=self.frames),
                parent_id
            )
            if parent_frame:
                parent_frame.children.append(frame.frame_id)

    def enter_frame(self, frame_id: str) -> None:
        """Enter a new frame (push onto stack).

        Args:
            frame_id: The ID of the frame being entered
        """
        self._parent_stack.append(frame_id)
        self._current_depth = len(self._parent_stack)

    def exit_frame(self, frame_id: str) -> None:
        """Exit a frame (pop from stack).

        Args:
            frame_id: The ID of the frame being exited
        """
        if self._parent_stack and self._parent_stack[-1] == frame_id:
            self._parent_stack.pop()
            self._current_depth = len(self._parent_stack)

    def build_trace(self, entry_point: str = "") -> FrameLifetimeTrace:
        """Build the complete frame lifetime trace.

        Args:
            entry_point: Optional entry point function name

        Returns:
            Complete FrameLifetimeTrace
        """
        total_duration = sum(frame.duration_ms for frame in self.frames)
        total_tokens = sum(
            frame.token_usage.total_tokens if frame.token_usage else 0
            for frame in self.frames
        )

        trace = FrameLifetimeTrace(
            trace_id=self.trace_id,
            frames=list(self.frames),
            entry_point=entry_point,
            total_duration_ms=total_duration,
            total_tokens=total_tokens,
        )
        trace.frame_tree = build_frame_tree(self.frames)
        return trace

    def to_dict(self) -> dict[str, Any]:
        """Serialize the current state to dictionary."""
        trace = self.build_trace()
        return trace.to_dict()


# Global frame capture context (can be overridden per session)
_current_frame_context: FrameCaptureContext | None = None


def get_frame_context() -> FrameCaptureContext | None:
    """Get the current frame capture context."""
    return _current_frame_context


def set_frame_context(context: FrameCaptureContext | None) -> None:
    """Set the current frame capture context.

    Args:
        context: The frame capture context to set
    """
    global _current_frame_context
    _current_frame_context = context


def capture_function_call(
    func: Callable | None = None,
    *,
    capture_args: bool = True,
    capture_return: bool = True,
    capture_exception: bool = True,
) -> Callable:
    """Decorator that captures a function's execution as a FrameEvent.

    Args:
        func: The function to decorate (used when called as @capture_function_call)
        capture_args: Whether to capture function arguments
        capture_return: Whether to capture return value
        capture_exception: Whether to capture exception information

    Returns:
        Decorated function that captures frame events

    Example:
        @capture_function_call
        def my_function(arg1, arg2):
            return arg1 + arg2
    """
    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            frame_context = get_frame_context()
            if not frame_context:
                # No frame capture active, just call the function
                return f(*args, **kwargs)

            frame_id = str(uuid.uuid4())
            frame_context.enter_frame(frame_id)

            # Get function metadata
            function_name = f.__name__
            module_path = f.__qualname__
            if hasattr(f, "__module__"):
                module_path = f"{f.__module__}.{f.__qualname__}"

            start_time = time.time()
            exception_info = None
            return_value = None

            try:
                return_value = f(*args, **kwargs)
                return return_value
            except Exception as e:
                if capture_exception:
                    import traceback
                    exception_info = ExceptionInfo(
                        exception_type=type(e).__name__,
                        message=str(e),
                        traceback=traceback.format_exc(),
                    )
                raise
            finally:
                end_time = time.time()
                duration_ms = (end_time - start_time) * 1000

                # Serialize arguments if requested
                call_args = {}
                if capture_args:
                    try:
                        sig = inspect.signature(f)
                        bound_args = sig.bind(*args, **kwargs)
                        bound_args.apply_defaults()
                        for name, value in bound_args.arguments.items():
                            call_args[name] = _serialize_value(value)
                    except Exception:
                        # Fallback to simple representation
                        call_args = {"args": str(args), "kwargs": str(kwargs)}

                # Serialize return value if requested
                serialized_return = None
                if capture_return and return_value is not None:
                    serialized_return = _serialize_value(return_value)

                frame = FrameEvent(
                    frame_id=frame_id,
                    function_name=function_name,
                    module_path=module_path,
                    call_args=call_args,
                    return_value=serialized_return,
                    exception=exception_info,
                    start_time=start_time,
                    end_time=end_time,
                    duration_ms=duration_ms,
                    depth=frame_context._current_depth,
                )

                frame_context.add_frame(frame)
                frame_context.exit_frame(frame_id)

        return wrapper

    if func is None:
        # Called with arguments: @capture_function_call(capture_args=False)
        return decorator
    else:
        # Called without arguments: @capture_function_call
        return decorator(func)


def _serialize_value(value: Any) -> Any:
    """Safely serialize a value for storage.

    Args:
        value: The value to serialize

    Returns:
        Serialized representation of the value
    """
    try:
        # Try JSON-serializable types
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (list, tuple)):
            return [_serialize_value(v) for v in value]
        if isinstance(value, dict):
            return {k: _serialize_value(v) for k, v in value.items()}

        # For other types, try string representation
        return str(value)
    except Exception:
        return "<unserializable>"


def to_dict(trace: FrameLifetimeTrace) -> dict[str, Any]:
    """Serialize a FrameLifetimeTrace to dictionary.

    Args:
        trace: The trace to serialize

    Returns:
        Dictionary representation of the trace
    """
    return trace.to_dict()


def from_dict(data: dict[str, Any]) -> FrameLifetimeTrace:
    """Deserialize a dictionary to FrameLifetimeTrace.

    Args:
        data: Dictionary data to deserialize

    Returns:
        Reconstructed FrameLifetimeTrace
    """
    frames = [
        FrameEvent(
            frame_id=f["frame_id"],
            function_name=f["function_name"],
            module_path=f["module_path"],
            parent_frame_id=f.get("parent_frame_id"),
            call_args=f.get("call_args", {}),
            return_value=f.get("return_value"),
            exception=_deserialize_exception(f.get("exception")) if f.get("exception") else None,
            start_time=f.get("start_time", 0.0),
            end_time=f.get("end_time", 0.0),
            duration_ms=f.get("duration_ms", 0.0),
            token_usage=_deserialize_token_usage(f.get("token_usage")) if f.get("token_usage") else None,
            depth=f.get("depth", 0),
            children=f.get("children", []),
        )
        for f in data.get("frames", [])
    ]

    trace = FrameLifetimeTrace(
        trace_id=data["trace_id"],
        frames=frames,
        entry_point=data.get("entry_point", ""),
        total_duration_ms=data.get("total_duration_ms", 0.0),
        total_tokens=data.get("total_tokens", 0),
        frame_tree=data.get("frame_tree", {}),
    )
    return trace


def _deserialize_exception(data: dict[str, str | None]) -> ExceptionInfo:
    """Deserialize exception info from dictionary."""
    return ExceptionInfo(
        exception_type=data["exception_type"],
        message=data["message"],
        traceback=data.get("traceback"),
    )


def _deserialize_token_usage(data: dict[str, int]) -> TokenUsage:
    """Deserialize token usage from dictionary."""
    return TokenUsage(
        prompt_tokens=data["prompt_tokens"],
        completion_tokens=data["completion_tokens"],
        total_tokens=data["total_tokens"],
    )