"""Event type registry for mapping EventType strings to concrete event classes."""

from __future__ import annotations

from .base import EventType, TraceEvent

# Simple registry for event type mappings.
# The registry is populated by __init__.py to ensure class identity consistency.
EVENT_TYPE_REGISTRY: dict[EventType, type[TraceEvent]] = {}
