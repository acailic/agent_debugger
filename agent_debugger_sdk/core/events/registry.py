"""Event type registry for mapping EventType strings to concrete event classes."""

from __future__ import annotations

from types import MappingProxyType
from typing import final

from .base import EventType, TraceEvent

# Simple registry for event type mappings.
# The registry is populated by __init__.py to ensure class identity consistency.
# MappingProxyType makes the public registry read-only to prevent accidental modification.
_EVENT_TYPE_REGISTRY: dict[EventType, type[TraceEvent]] = {}
EVENT_TYPE_REGISTRY = MappingProxyType(_EVENT_TYPE_REGISTRY)


@final
def register_event_type(event_type: EventType, event_class: type[TraceEvent]) -> None:
    """Register an event type mapping.

    Args:
        event_type: The EventType enum value
        event_class: The TraceEvent subclass to register
    """
    _EVENT_TYPE_REGISTRY[event_type] = event_class


@final
def update_event_type_registry(mapping: dict[EventType, type[TraceEvent]]) -> None:
    """Bulk update event type mappings.

    Args:
        mapping: Dictionary of EventType to TraceEvent class mappings
    """
    _EVENT_TYPE_REGISTRY.update(mapping)


__all__ = ["EVENT_TYPE_REGISTRY", "register_event_type", "update_event_type_registry"]
