"""Decorators for instrumenting agent code with trace collection.

This module provides decorators that wrap agent functions, tool calls,
and LLM interactions to automatically collect execution traces.

Example:
    from agent_debugger_sdk import trace_agent, trace_tool, trace_llm

    @trace_agent(name="my_agent", framework="pydantic_ai")
    async def my_agent(prompt: str) -> str:
        result = await call_llm([{"role": "user", "content": prompt}])
        return result

    @trace_tool(name="search_web")
    async def search_web(query: str) -> list[str]:
        return ["result1", "result2"]

    @trace_llm(model="gpt-4o")
    async def call_llm(messages: list) -> str:
        return "Hello!"
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Awaitable
from collections.abc import Callable
from functools import wraps
from typing import Any
from typing import ParamSpec
from typing import TypeVar

from agent_debugger_sdk.core.context import TraceContext
from agent_debugger_sdk.core.context import get_current_context
from agent_debugger_sdk.core.events import EventType
from agent_debugger_sdk.core.events import LLMRequestEvent
from agent_debugger_sdk.core.events import LLMResponseEvent
from agent_debugger_sdk.core.events import ToolCallEvent
from agent_debugger_sdk.core.events import ToolResultEvent

P = ParamSpec("P")
T = TypeVar("T")

__all__ = ["trace_agent", "trace_tool", "trace_llm"]


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
                    result=_sanitize_result(result) if result else None,
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


def trace_llm(
    model: str,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator to trace an LLM call function.

    Records LLM_REQUEST before the call and LLM_RESPONSE after, including
    token usage, cost, and duration.

    Args:
        model: The model identifier (e.g., "gpt-4o", "claude-3-opus").

    Returns:
        A decorator function that wraps async LLM call functions.

    Example:
        @trace_llm(model="gpt-4o")
        async def call_gpt(messages: list[dict]) -> str:
            response = await openai.chat.completions.create(
                model="gpt-4o",
                messages=messages
            )
            return response.choices[0].message.content

    Note:
        The decorated function should return either:
        - A string (content only)
        - A dict with 'content', 'usage', 'cost_usd' keys
        - An object with these as attributes

        Works both inside a trace_agent context or standalone.
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            ctx = get_current_context()
            own_context = ctx is None

            if own_context:
                ctx = TraceContext(
                    agent_name="llm_runner",
                    framework="unknown",
                )
                await ctx.__aenter__()

            if ctx is None:
                raise RuntimeError("TraceContext is None - this should not happen")  # pragma: no cover

            messages = _extract_messages(args, kwargs)

            llm_request_event = LLMRequestEvent(
                session_id=ctx.session_id,
                parent_id=ctx.get_current_parent(),
                event_type=EventType.LLM_REQUEST,
                name=f"llm_call_{model}",
                model=model,
                messages=messages,
                tools=_extract_tools(args, kwargs),
                settings=_extract_settings(args, kwargs),
                importance=0.3,
            )
            await ctx._emit_event(llm_request_event)

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

                content = ""
                usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
                cost_usd = 0.0
                tool_calls: list[dict[str, Any]] = []

                if result is not None and error is None:
                    content, usage, cost_usd, tool_calls = _extract_llm_response(result)

                llm_response_event = LLMResponseEvent(
                    session_id=ctx.session_id,
                    parent_id=llm_request_event.id,
                    event_type=EventType.LLM_RESPONSE,
                    name=f"llm_response_{model}",
                    model=model,
                    content=content,
                    tool_calls=tool_calls,
                    usage=usage,
                    cost_usd=cost_usd,
                    duration_ms=duration_ms,
                    importance=0.9 if error else 0.5,
                )
                await ctx._emit_event(llm_response_event)

                if own_context:
                    # Pass actual exception info to __aexit__ when error occurred
                    if error is not None:
                        await ctx.__aexit__(type(error), error, error.__traceback__)
                    else:
                        await ctx.__aexit__(None, None, None)

        return async_wrapper

    return decorator


def _sanitize_arguments(args: tuple, kwargs: dict) -> dict[str, Any]:
    """Sanitize function arguments for trace storage.

    Converts positional and keyword arguments to a dictionary,
    truncating large values.

    Args:
        args: Positional arguments.
        kwargs: Keyword arguments.

    Returns:
        A dictionary of sanitized arguments.
    """
    sanitized: dict[str, Any] = {}

    for i, arg in enumerate(args):
        key = f"arg_{i}"
        sanitized[key] = _truncate_value(arg)

    for key, value in kwargs.items():
        sanitized[key] = _truncate_value(value)

    return sanitized


def _truncate_value(value: Any, max_length: int = 1000) -> Any:
    """Truncate a value if it's too large for trace storage.

    Args:
        value: The value to potentially truncate.
        max_length: Maximum string length before truncation.

    Returns:
        The value, possibly truncated.
    """
    if isinstance(value, str):
        if len(value) > max_length:
            return value[:max_length] + "...[truncated]"
        return value

    if isinstance(value, list | tuple):
        if len(value) > 100:
            return [_truncate_value(v, max_length) for v in value[:10]] + [f"...[{len(value) - 10} more items]"]
        return [_truncate_value(v, max_length) for v in value]

    if isinstance(value, dict):
        if len(value) > 50:
            truncated = {}
            for i, (k, v) in enumerate(value.items()):
                if i >= 20:
                    truncated["__truncated__"] = f"{len(value) - 20} more keys"
                    break
                truncated[k] = _truncate_value(v, max_length)
            return truncated
        return {k: _truncate_value(v, max_length) for k, v in value.items()}

    return value


def _sanitize_result(result: Any) -> Any:
    """Sanitize a function result for trace storage.

    Args:
        result: The result to sanitize.

    Returns:
        A sanitized version of the result.
    """
    return _truncate_value(result, max_length=5000)


def _extract_messages(args: tuple, kwargs: dict) -> list[dict[str, Any]]:
    """Extract messages from LLM call arguments.

    Looks for 'messages' in kwargs or first list argument.

    Args:
        args: Positional arguments.
        kwargs: Keyword arguments.

    Returns:
        A list of message dictionaries.
    """
    if "messages" in kwargs:
        messages = kwargs["messages"]
        if isinstance(messages, list):
            return _truncate_value(messages)
        return [{"role": "unknown", "content": str(messages)}]

    for arg in args:
        if (
            isinstance(arg, list)
            and len(arg) > 0
            and isinstance(arg[0], dict)
            and ("role" in arg[0] or "content" in arg[0])
        ):
            return _truncate_value(arg)

    return []


def _extract_tools(args: tuple, kwargs: dict) -> list[dict[str, Any]]:
    """Extract tool definitions from LLM call arguments.

    Args:
        args: Positional arguments.
        kwargs: Keyword arguments.

    Returns:
        A list of tool definition dictionaries.
    """
    if "tools" in kwargs:
        return _truncate_value(kwargs["tools"])
    return []


def _extract_settings(args: tuple, kwargs: dict) -> dict[str, Any]:
    """Extract model settings from LLM call arguments.

    Args:
        args: Positional arguments.
        kwargs: Keyword arguments.

    Returns:
        A dictionary of settings.
    """
    settings: dict[str, Any] = {}

    for key in ["temperature", "max_tokens", "top_p", "frequency_penalty", "presence_penalty"]:
        if key in kwargs:
            settings[key] = kwargs[key]

    return settings


def _extract_llm_response(result: Any) -> tuple[str, dict[str, int], float, list[dict[str, Any]]]:
    """Extract content, usage, cost, and tool calls from an LLM response.

    Handles various response formats (dict, object with attributes).

    Args:
        result: The LLM response to extract from.

    Returns:
        A tuple of (content, usage, cost_usd, tool_calls).
    """
    content = ""
    usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
    cost_usd = 0.0
    tool_calls: list[dict[str, Any]] = []

    if isinstance(result, str):
        content = result
    elif isinstance(result, dict):
        content = result.get("content", "")
        if "usage" in result:
            usage = result["usage"]
        if "cost_usd" in result:
            cost_usd = result["cost_usd"]
        if "tool_calls" in result:
            tool_calls = result["tool_calls"]
    else:
        if hasattr(result, "content"):
            content = str(result.content)
        elif hasattr(result, "choices"):
            try:
                content = result.choices[0].message.content
            except (AttributeError, IndexError, KeyError):
                content = str(result)

        if hasattr(result, "usage"):
            with contextlib.suppress(AttributeError):
                usage = {
                    "input_tokens": getattr(result.usage, "prompt_tokens", 0)
                    or getattr(result.usage, "input_tokens", 0),
                    "output_tokens": getattr(result.usage, "completion_tokens", 0)
                    or getattr(result.usage, "output_tokens", 0),
                }

        if hasattr(result, "tool_calls"):
            with contextlib.suppress(AttributeError):
                for tc in result.tool_calls or []:
                    tool_calls.append(
                        {
                            "id": getattr(tc, "id", ""),
                            "name": getattr(tc.function, "name", "")
                            if hasattr(tc, "function")
                            else getattr(tc, "name", ""),
                            "arguments": getattr(tc.function, "arguments", "")
                            if hasattr(tc, "function")
                            else getattr(tc, "arguments", {}),
                        }
                    )

    content = _truncate_value(content, max_length=5000) if isinstance(content, str) else str(content)

    return content, usage, cost_usd, tool_calls
