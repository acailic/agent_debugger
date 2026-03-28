"""Utility functions for PydanticAI adapter.

This module contains helper functions for model name resolution, message conversion,
and data extraction from PydanticAI objects.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

try:
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        RetryPromptPart,
        SystemPromptPart,
        ToolReturnPart,
        UserPromptPart,
    )
    from pydantic_ai.models import Model

    PYDANTIC_AI_AVAILABLE = True
except ImportError:
    PYDANTIC_AI_AVAILABLE = False
    Model = Any
    ModelResponse = Any
    ModelRequest = Any
    UserPromptPart = Any
    SystemPromptPart = Any
    ToolReturnPart = Any
    RetryPromptPart = Any


def resolve_model_name(agent: Any, requested_model: Model | str | None) -> str:
    """Resolve the active model name from explicit or agent-level configuration.

    Args:
        agent: The PydanticAI Agent instance.
        requested_model: Explicitly requested model, if any.

    Returns:
        Resolved model name as string.
    """
    if isinstance(requested_model, str):
        return requested_model
    if requested_model is not None:
        name = getattr(requested_model, "model_name", None) or getattr(requested_model, "name", None)
        if name:
            return str(name)

    for attr in ("model", "_model", "model_name", "name"):
        value = getattr(agent, attr, None)
        if isinstance(value, str) and value:
            return value
        name = getattr(value, "model_name", None) or getattr(value, "name", None)
        if name:
            return str(name)

    return "unknown"


def request_messages_from_parts(parts: list[Any] | Any) -> list[dict[str, Any]]:
    """Convert PydanticAI request parts into our LLM-request message shape.

    Args:
        parts: Message parts from a ModelRequest.

    Returns:
        List of message dictionaries with role and content.
    """
    messages: list[dict[str, Any]] = []

    for part in parts:
        if isinstance(part, UserPromptPart):
            messages.append({"role": "user", "content": stringify_content(part.content)})
        elif isinstance(part, SystemPromptPart):
            messages.append({"role": "system", "content": stringify_content(part.content)})
        elif isinstance(part, ToolReturnPart):
            messages.append(
                {
                    "role": "tool",
                    "name": part.tool_name,
                    "content": part.model_response_str(),
                }
            )
        elif isinstance(part, RetryPromptPart):
            role = "tool" if part.tool_name else "user"
            item = {"role": role, "content": part.model_response()}
            if part.tool_name:
                item["name"] = part.tool_name
            messages.append(item)

    return messages


def stringify_content(content: Any) -> str:
    """Render simple request content into a stable string for event payloads.

    Args:
        content: Content to stringify.

    Returns:
        String representation of content.
    """
    if isinstance(content, str):
        return content
    return str(content)


def usage_from_message(message: ModelResponse) -> dict[str, int]:
    """Extract token usage from a model response message.

    Args:
        message: A ModelResponse instance.

    Returns:
        Dictionary with input_tokens and output_tokens.
    """
    usage = getattr(message, "usage", None)
    if usage is None:
        return {"input_tokens": 0, "output_tokens": 0}
    return {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
    }


def response_duration_ms(
    *,
    request_timestamp: datetime | None,
    response_timestamp: datetime | None,
    fallback_ms: float,
) -> float:
    """Calculate response duration based on timestamps with fallback.

    Args:
        request_timestamp: When the request was made.
        response_timestamp: When the response was received.
        fallback_ms: Fallback duration in milliseconds.

    Returns:
        Duration in milliseconds.
    """
    if request_timestamp and response_timestamp:
        duration_ms = (response_timestamp - request_timestamp).total_seconds() * 1000
        if duration_ms > 0:
            return duration_ms
    return fallback_ms if fallback_ms > 0 else 1.0
