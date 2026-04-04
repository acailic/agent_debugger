"""State-drift detection for comparing restored vs original execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


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
        orig_data = original.get("data") or {}
        new_data = new_event.get("data") or {}

        orig_type = original.get("event_type")
        new_type = new_event.get("event_type")

        # Decision drift: chosen_action or action
        if orig_type == "decision" or new_type == "decision":
            for action_field in ("chosen_action", "action"):
                orig_val = orig_data.get(action_field)
                new_val = new_data.get(action_field)
                if orig_val is not None and new_val is not None and orig_val != new_val:
                    return DriftEvent(
                        severity=DriftSeverity.WARNING,
                        description=f"Decision action drifted: {orig_val!r} -> {new_val!r}",
                        original_value=orig_val,
                        restored_value=new_val,
                        event_index=index,
                        field=action_field,
                    )

            # Confidence drift
            orig_conf = orig_data.get("confidence")
            new_conf = new_data.get("confidence")
            if orig_conf is not None and new_conf is not None:
                delta = abs(float(orig_conf) - float(new_conf))
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

        # Tool call drift: tool_name
        if orig_type == "tool_call" or new_type == "tool_call":
            orig_tool = orig_data.get("tool_name")
            new_tool = new_data.get("tool_name")
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
