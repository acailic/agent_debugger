"""Shared utilities for decorators.

This module provides common type definitions and helper functions
used across the agent, tool, and LLM decorators.
"""

from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")

__all__ = ["P", "T", "_truncate_value", "_sanitize_arguments", "_sanitize_result"]


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
