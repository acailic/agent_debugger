"""Drift detection event emitted when replay diverges from original execution."""

from dataclasses import dataclass

from .base import EventType, TraceEvent

__all__ = ["DriftDetectedEvent"]


@dataclass(kw_only=True)
class DriftDetectedEvent(TraceEvent):
    """Event emitted when a replayed decision diverges from the original execution.

    Attributes:
        event_type: Always EventType.DRIFT
        description: Human-readable summary of what drifted
        original_value: The value from the original execution
        restored_value: The value from the restored/replayed execution
        drift_event_type: The event type where drift was detected (e.g. "decision")
        drift_index: Position in the original event sequence where drift occurred
        severity: "warning" or "critical"
    """

    event_type: EventType = EventType.DRIFT
    description: str = ""
    original_value: str = ""
    restored_value: str = ""
    drift_event_type: str = ""
    drift_index: int = 0
    severity: str = "warning"
