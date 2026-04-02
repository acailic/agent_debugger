"""Simplified high-level API for Peaky Peek.

Provides two entry points for minimal-friction tracing:

- ``@trace`` — decorator that auto-names and auto-initializes
- ``trace_session()`` — context manager that combines init + TraceContext

Both call ``init()`` automatically so users never need an explicit setup step.

Example (decorator)::

    from agent_debugger_sdk import trace

    @trace
    async def my_agent(prompt: str) -> str:
        return await llm_call(prompt)

Example (context manager)::

    from agent_debugger_sdk import trace_session

    async with trace_session("my_agent") as ctx:
        await ctx.record_decision(reasoning="...", confidence=0.9, chosen_action="call_tool")
        result = await some_tool()
        await ctx.record_tool_result("some_tool", result)

Example (zero-config auto-patch)::

    # Set env var before importing your framework:
    # PEAKY_PEEK_AUTO_PATCH=true python my_agent.py

    import agent_debugger_sdk.auto_patch  # activates on import
    # ... run your agent normally, traces are captured automatically
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any

from agent_debugger_sdk.config import init

__all__ = ["trace", "trace_session"]


# ---------------------------------------------------------------------------
# @trace decorator
# ---------------------------------------------------------------------------


def trace(
    func: Callable[..., Awaitable[Any]] | None = None,
    *,
    name: str | None = None,
    framework: str = "custom",
) -> Any:
    """Decorator that traces an async agent function with zero setup.

    Automatically calls ``init()`` on first use so the user never needs an
    explicit initialization step.  Derives the agent name from the decorated
    function when *name* is not provided.

    Args:
        func: The async function to decorate (when used without arguments).
        name: Optional agent name. Defaults to the function's ``__qualname__``.
        framework: Framework identifier (default ``"custom"``).

    Returns:
        A decorator or the decorated function, depending on call style.

    Examples::

        # Style 1 — bare decorator
        @trace
        async def my_agent(prompt: str) -> str:
            ...

        # Style 2 — with options
        @trace(name="research_agent", framework="langchain")
        async def my_agent(prompt: str) -> str:
            ...
    """
    _ensure_initialized()

    def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        from agent_debugger_sdk.core.context import TraceContext

        agent_name = name or fn.__qualname__

        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = TraceContext(agent_name=agent_name, framework=framework)
            async with ctx:
                if ctx._session_start_event:
                    ctx.set_parent(ctx._session_start_event.id)
                return await fn(*args, **kwargs)

        return wrapper

    if func is not None:
        # Called as @trace without parentheses
        return decorator(func)
    # Called as @trace(...) with arguments
    return decorator


# ---------------------------------------------------------------------------
# trace_session() context manager
# ---------------------------------------------------------------------------


@asynccontextmanager
async def trace_session(
    agent_name: str = "agent",
    *,
    framework: str = "custom",
    session_id: str | None = None,
    tags: list[str] | None = None,
) -> Any:
    """Async context manager that creates a tracing session with zero setup.

    Combines ``init()`` + ``TraceContext`` so the user only needs one import.

    Args:
        agent_name: Name for the agent being traced.
        framework: Framework identifier (default ``"custom"``).
        session_id: Optional session ID (auto-generated UUID if None).
        tags: Optional tags for categorizing the session.

    Yields:
        A ``TraceContext`` instance for recording events.

    Example::

        from agent_debugger_sdk import trace_session

        async with trace_session("weather_agent") as ctx:
            await ctx.record_decision(
                reasoning="User asked for weather",
                confidence=0.9,
                chosen_action="call_weather_api",
            )
            await ctx.record_tool_call("weather_api", {"city": "Seattle"})
            await ctx.record_tool_result("weather_api", result={"temp": 52})
    """
    _ensure_initialized()

    from agent_debugger_sdk.core.context import TraceContext

    ctx = TraceContext(
        agent_name=agent_name,
        framework=framework,
        session_id=session_id,
        tags=tags,
    )

    async with ctx:
        if ctx._session_start_event:
            ctx.set_parent(ctx._session_start_event.id)
        yield ctx


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_initialized = False


def _ensure_initialized() -> None:
    """Call ``init()`` once so the SDK is ready for tracing."""
    global _initialized
    if not _initialized:
        init()
        _initialized = True
