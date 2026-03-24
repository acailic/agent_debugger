"""Tool decorator for tracing tool functions.

This module provides the trace_tool decorator that wraps tool functions
to automatically collect execution traces.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from functools import wraps

from agent_debugger_sdk.core.context import TraceContext, get_current_context
from agent_debugger_sdk.core.decorators._utils import P, T
from agent_debugger_sdk.core.events import EventType, ToolCallEvent, ToolResultEvent

__all__ = ["trace_tool"]


def trace_tool(
    name: str,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator to trace a tool function.

    Records TOOL_CALL before execution and TOOL_RESULT after execution,
    including duration and any errors.

    Args:
        name: Human-readable name for the tool.

    Returns:
        A decorator function that wraps async tool functions.

    Example:
        @trace_tool(name="web_search")
        async def web_search(query: str) -> list[str]:
            results = await search_api(query)
            return results

    Note:
        Works both inside a trace_agent context (uses existing session)
        or standalone (creates a temporary context).
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            from agent_debugger_sdk.core.decorators._utils import _sanitize_arguments, _sanitize_result

            ctx = get_current_context()
            own_context = ctx is None

            if own_context:
                ctx = TraceContext(
                    agent_name="tool_runner",
                    framework="unknown",
                )
                await ctx.__aenter__()

            if ctx is None:
                raise RuntimeError("TraceContext is None - this should not happen")  # pragma: no cover

            tool_call_event = ToolCallEvent(
                session_id=ctx.session_id,
                parent_id=ctx.get_current_parent(),
                event_type=EventType.TOOL_CALL,
                name=f"{name}_call",
                tool_name=name,
                arguments=_sanitize_arguments(args, kwargs),
                importance=0.4,
            )
            await ctx._emit_event(tool_call_event)

            start_time = time.perf_counter()
            error: Exception | None = None
            result: T | None = None

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                error = e
                raise
            finally:
                end_time = time.perf_counter()
                duration_ms = (end_time - start_time) * 1000

                tool_result_event = ToolResultEvent(
                    session_id=ctx.session_id,
                    parent_id=tool_call_event.id,
                    event_type=EventType.TOOL_RESULT,
                    name=f"{name}_result",
                    tool_name=name,
                    result=_sanitize_result(result) if error is None else None,
                    error=str(error) if error else None,
                    duration_ms=duration_ms,
                    importance=0.9 if error else 0.5,
                )
                await ctx._emit_event(tool_result_event)

                if own_context:
                    # Pass actual exception info to __aexit__ when error occurred
                    if error is not None:
                        await ctx.__aexit__(type(error), error, error.__traceback__)
                    else:
                        await ctx.__aexit__(None, None, None)

        return async_wrapper

    return decorator
