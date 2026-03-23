"""Collector module for agent debugging.

This module provides trace collection, scoring, buffering, and persistence
for agent execution events.
"""

from .buffer import EventBuffer
from .buffer import get_event_buffer
from .buffer_base import BufferBase
from .intelligence import TraceIntelligence
from .persistence import PersistenceManager
from .scorer import ImportanceScorer
from .scorer import get_importance_scorer

__all__ = [
    "EventBuffer",
    "get_event_buffer",
    "BufferBase",
    "create_buffer",
    "ImportanceScorer",
    "get_importance_scorer",
    "TraceIntelligence",
    "PersistenceManager",
]


def create_buffer(backend: str = "memory", **kwargs) -> BufferBase:
    """Create a buffer instance.

    Factory function to create buffer implementations. Currently supports
    in-memory and Redis-backed buffers.

    Args:
        backend: Buffer backend type ("memory" or "redis")
        **kwargs: Additional arguments passed to buffer constructor

    Returns:
        BufferBase instance

    Raises:
        ValueError: If backend is not supported

    Example:
        >>> memory_buf = create_buffer(backend="memory")
        >>> redis_buf = create_buffer(backend="redis", host="localhost", port=6379)
    """
    if backend == "memory":
        return EventBuffer(**kwargs)
    if backend == "redis":
        from .buffer_redis import RedisEventBuffer

        return RedisEventBuffer(**kwargs)
    raise ValueError(f"Unknown buffer backend: {backend}")
