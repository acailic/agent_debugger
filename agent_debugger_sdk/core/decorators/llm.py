"""LLM decorator for tracing LLM call functions.

This module provides the trace_llm decorator that wraps LLM call functions
to automatically collect execution traces.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from agent_debugger_sdk.core.context import TraceContext, get_current_context
from agent_debugger_sdk.core.decorators._utils import P, T
from agent_debugger_sdk.core.events import EventType, LLMRequestEvent, LLMResponseEvent

__all__ = ["trace_llm"]


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


def _extract_messages(args: tuple, kwargs: dict) -> list[dict[str, Any]]:
    """Extract messages from LLM call arguments.

    Looks for 'messages' in kwargs or first list argument.

    Args:
        args: Positional arguments.
        kwargs: Keyword arguments.

    Returns:
        A list of message dictionaries.
    """
    from agent_debugger_sdk.core.decorators._utils import _truncate_value

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
    from agent_debugger_sdk.core.decorators._utils import _truncate_value

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
    from agent_debugger_sdk.core.decorators._utils import _truncate_value

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
