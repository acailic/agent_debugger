"""Agent decorator for tracing agent functions.

This module provides the trace_agent decorator that wraps agent functions
to automatically collect execution traces.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps

from agent_debugger_sdk.core.context import TraceContext
from agent_debugger_sdk.core.decorators._utils import P, T

__all__ = ["trace_agent"]


def trace_agent(
    name: str,
    framework: str = "unknown",
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator to trace an async agent function.

    Creates a new trace session on entry, records AGENT_START and AGENT_END
    events, and captures any exceptions as ERROR events.

    Args:
        name: Human-readable name for the agent.
        framework: The agent framework being used (pydantic_ai, langchain, autogen).

    Returns:
        A decorator function that wraps async agent functions.

    Example:
        @trace_agent(name="research_agent", framework="pydantic_ai")
        async def research_agent(query: str) -> str:
            results = await search_tool(query)
            return summarize(results)

    Note:
        The decorated function must be async. For sync functions, wrap them
        in an async wrapper or use asyncio.run() at the call site.
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            ctx = TraceContext(
                agent_name=name,
                framework=framework,
            )

            async with ctx:
                # Use the session start event's ID as the parent for child events
                if ctx._session_start_event:
                    ctx.set_parent(ctx._session_start_event.id)

                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception:
                    # Error is already recorded by TraceContext.__aexit__
                    raise

        return async_wrapper

    return decorator
