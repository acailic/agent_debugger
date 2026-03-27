"""Shared utility functions for LangChain adapters.

This module provides common utilities used by both the async
LangChainTracingHandler and the sync auto-patch LangChainAdapter.
"""

from __future__ import annotations

from typing import Any


def normalize_tool_calls(raw_tool_calls: Any) -> list[dict[str, Any]]:
    """Return a stable tool-call payload from LangChain response objects.

    Handles both dict-style and object-style tool call representations
    from LangChain responses.

    Args:
        raw_tool_calls: Raw tool calls from a LangChain response (may be
            list, tuple, or None).

    Returns:
        List of normalized tool call dicts with 'id', 'name', and 'arguments'.
    """
    normalized: list[dict[str, Any]] = []

    if not isinstance(raw_tool_calls, (list, tuple)):
        raw_tool_calls = []

    for tool_call in raw_tool_calls or []:
        if isinstance(tool_call, dict):
            function = tool_call.get("function") or {}
            name = tool_call.get("name") or function.get("name", "")
            arguments = tool_call.get("args")
            if arguments is None:
                arguments = tool_call.get("arguments", function.get("arguments", {}))
            normalized.append(
                {
                    "id": tool_call.get("id", ""),
                    "name": name,
                    "arguments": arguments if arguments is not None else {},
                }
            )
            continue

        function = getattr(tool_call, "function", None)
        arguments = getattr(tool_call, "args", None)
        if arguments is None and function is not None:
            arguments = getattr(function, "arguments", None)
        if arguments is None:
            arguments = getattr(tool_call, "arguments", {})

        normalized.append(
            {
                "id": getattr(tool_call, "id", ""),
                "name": getattr(function, "name", "") if function is not None else getattr(tool_call, "name", ""),
                "arguments": arguments if arguments is not None else {},
            }
        )

    return normalized


def extract_response_content_and_tool_calls(
    response: Any,
    capture_content: bool = True,
) -> tuple[str, list[dict[str, Any]]]:
    """Extract content and tool calls from a LangChain LLMResult.

    Args:
        response: The LangChain LLMResult or response object.
        capture_content: Whether to capture the text content. Set to False
            for lightweight tracing that omits prompt/response text.

    Returns:
        Tuple of (content string, list of normalized tool call dicts).
    """
    content = ""
    tool_calls: list[dict[str, Any]] = []

    if not getattr(response, "generations", None) or not response.generations:
        return content, tool_calls

    first = response.generations[0]
    if not first:
        return content, tool_calls

    generation = first[0]
    message = getattr(generation, "message", None)

    if capture_content:
        content = getattr(generation, "text", "")
        if not content and message is not None:
            message_content = getattr(message, "content", "")
            content = message_content if isinstance(message_content, str) else str(message_content)

    if message is not None:
        tool_calls = normalize_tool_calls(getattr(message, "tool_calls", []))
    if not tool_calls:
        tool_calls = normalize_tool_calls(getattr(generation, "tool_calls", []))

    return content, tool_calls


def extract_invocation_settings(invocation_params: dict[str, Any]) -> dict[str, Any]:
    """Normalize LangChain invocation settings into stable trace fields.

    Args:
        invocation_params: LangChain invocation parameters dict.

    Returns:
        Dict with normalized settings (temperature, max_tokens, top_p).
    """
    max_tokens = invocation_params.get("max_tokens", invocation_params.get("max_completion_tokens"))
    return {
        k: v
        for k, v in {
            "temperature": invocation_params.get("temperature"),
            "max_tokens": max_tokens,
            "top_p": invocation_params.get("top_p"),
        }.items()
        if v is not None
    }
