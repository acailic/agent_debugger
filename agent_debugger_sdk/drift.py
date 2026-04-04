"""State-drift detection for comparing restored vs original execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


def _get_field(event: dict[str, Any], *keys: str) -> Any:
    """Return the first matching key found at the top level, then within 'data'.

    Real SDK events serialized via ``to_dict()`` place typed fields (e.g.
    ``chosen_action``, ``tool_name``) at the top level as dataclass fields.
    Raw/legacy events may nest them under ``data``. This helper checks both
    locations so drift detection works regardless of serialization path.
    """
    data = event.get("data") or {}
    for key in keys:
        val = event.get(key)
        if val is not None:
            return val
        val = data.get(key)
        if val is not None:
            return val
    return None


class DriftSeverity(Enum):
    """Severity levels for detected state drift."""

    MINOR = "minor"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class DriftEvent:
    """Represents a detected divergence between original and restored execution.

    Attributes:
        severity: How significant the drift is.
        description: Human-readable description of the drift.
        original_value: The value from the original execution.
        restored_value: The value from the restored execution.
        event_index: Index in the original event sequence where drift occurred.
        field: The field or dimension where drift was detected.
    """

    severity: DriftSeverity
    description: str
    original_value: Any
    restored_value: Any
    event_index: int = 0
    field: str = ""

    # Aliases for test compatibility
    @property
    def expected(self) -> Any:
        return self.original_value

    @property
    def actual(self) -> Any:
        return self.restored_value


# Threshold for confidence drift to be considered WARNING
_CONFIDENCE_DRIFT_THRESHOLD = 0.25


class DriftDetector:
    """Detects divergence between original events and a new (restored) execution.

    Initialized with the original event sequence. Call compare() for each
    new event to check whether the execution is drifting from the original.

    Args:
        original_events: The events from the original execution run.

    Example:
        detector = DriftDetector(original_events)
        drift = detector.compare(new_event, index=0)
        if drift:
            print(f"Drift detected: {drift.description}")
    """

    def __init__(self, original_events: list[dict[str, Any]]) -> None:
        self._original_events = original_events

    def compare(self, new_event: dict[str, Any], index: int) -> DriftEvent | None:
        """Compare a new event against the original event at the same index.

        Args:
            new_event: The event from the restored execution.
            index: The position in the original sequence to compare against.

        Returns:
            DriftEvent if drift is detected, None if events match or comparison
            is not possible (e.g. missing fields, out-of-bounds index).
        """
        if index >= len(self._original_events):
            return None

        original = self._original_events[index]

        orig_type = original.get("event_type")
        new_type = new_event.get("event_type")

        # Event type mismatch is itself a critical drift
        if orig_type and new_type and orig_type != new_type:
            return DriftEvent(
                severity=DriftSeverity.CRITICAL,
                description=f"Event type mismatch: expected '{orig_type}', got '{new_type}'",
                original_value=orig_type,
                restored_value=new_type,
                event_index=index,
                field="event_type",
            )

        # Decision drift: resolve action from chosen_action OR action alias so
        # that mixed/legacy payloads (one side uses chosen_action, the other
        # uses action) are still compared correctly.
        if orig_type == "decision" or new_type == "decision":
            orig_action = _get_field(original, "chosen_action", "action")
            new_action = _get_field(new_event, "chosen_action", "action")
            if orig_action is not None and new_action is not None and orig_action != new_action:
                return DriftEvent(
                    severity=DriftSeverity.WARNING,
                    description=f"Decision action drifted: {orig_action!r} -> {new_action!r}",
                    original_value=orig_action,
                    restored_value=new_action,
                    event_index=index,
                    field="chosen_action",
                )

            # Confidence drift
            orig_conf = _get_field(original, "confidence")
            new_conf = _get_field(new_event, "confidence")
            if orig_conf is not None and new_conf is not None:
                try:
                    delta = abs(float(orig_conf) - float(new_conf))
                except (ValueError, TypeError):
                    delta = 0.0
                if delta >= _CONFIDENCE_DRIFT_THRESHOLD:
                    severity = DriftSeverity.CRITICAL if delta >= 0.5 else DriftSeverity.WARNING
                    return DriftEvent(
                        severity=severity,
                        description=f"Decision confidence drifted: {orig_conf} -> {new_conf} (delta={delta:.2f})",
                        original_value=orig_conf,
                        restored_value=new_conf,
                        event_index=index,
                        field="confidence",
                    )

        # Tool call drift: resolve tool from tool_name OR tool alias.
        if orig_type == "tool_call" or new_type == "tool_call":
            orig_tool = _get_field(original, "tool_name", "tool")
            new_tool = _get_field(new_event, "tool_name", "tool")
            if orig_tool is not None and new_tool is not None and orig_tool != new_tool:
                return DriftEvent(
                    severity=DriftSeverity.WARNING,
                    description=f"Tool call drifted: {orig_tool!r} -> {new_tool!r}",
                    original_value=orig_tool,
                    restored_value=new_tool,
                    event_index=index,
                    field="tool_name",
                )

        return None
