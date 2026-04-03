"""Event type registry for mapping EventType strings to concrete event classes."""

from __future__ import annotations

import threading
from types import MappingProxyType

from .base import EventType, TraceEvent

# Simple registry for event type mappings.
# The registry is populated by __init__.py to ensure class identity consistency.
# MappingProxyType makes the public registry read-only to prevent accidental modification.
_EVENT_TYPE_REGISTRY: dict[EventType, type[TraceEvent]] = {}
_EVENT_TYPE_REGISTRY_LOCK = threading.Lock()
EVENT_TYPE_REGISTRY = MappingProxyType(_EVENT_TYPE_REGISTRY)


def register_event_type(event_type: EventType, event_class: type[TraceEvent]) -> None:
    """Register an event type mapping.

    Thread-safe: uses internal lock to prevent race conditions during registration.
    """
    with _EVENT_TYPE_REGISTRY_LOCK:
        _EVENT_TYPE_REGISTRY[event_type] = event_class


def update_event_type_registry(mapping: dict[EventType, type[TraceEvent]]) -> None:
    """Bulk update event type mappings.

    Thread-safe: uses internal lock to prevent race conditions during bulk update.
    """
    with _EVENT_TYPE_REGISTRY_LOCK:
        _EVENT_TYPE_REGISTRY.update(mapping)


__all__ = ["EVENT_TYPE_REGISTRY", "register_event_type", "update_event_type_registry"]
