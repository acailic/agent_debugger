"""State-drift detection for replay comparison.

DriftDetector compares events produced during a restored execution against
the originally recorded events and reports divergences as DriftEvents.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any


class DriftSeverity(enum.Enum):
    """Severity levels for detected drift."""

    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class DriftEvent:
    """Represents a detected divergence between original and restored execution.

    Attributes:
        severity: How severe the drift is.
        description: Human-readable description of what drifted.
        original_value: The value from the original execution.
        restored_value: The value from the restored execution.
        event_index: Index of the event where drift was detected.
    """

    severity: DriftSeverity
    description: str
    original_value: Any
    restored_value: Any
    event_index: int = 0

    @property
    def expected(self) -> Any:
        """Alias for original_value."""
        return self.original_value

    @property
    def actual(self) -> Any:
        """Alias for restored_value."""
        return self.restored_value


_CONFIDENCE_DRIFT_THRESHOLD = 0.2


class DriftDetector:
    """Compares replayed events against original events to detect state drift.

    Args:
        original_events: The events recorded during the original execution.
    """

    def __init__(self, original_events: list[dict[str, Any]]) -> None:
        self.original_events = list(original_events)

    def compare(self, new_event: dict[str, Any], *, index: int) -> DriftEvent | None:
        """Compare a new event against the original event at the given index.

        Checks for action drift, tool drift, and confidence drift.

        Args:
            new_event: Event from the restored execution.
            index: Index into original_events to compare against.

        Returns:
            DriftEvent if drift was detected, None if events match or
            comparison is not possible.
        """
        if index >= len(self.original_events):
            return None

        original = self.original_events[index]
        orig_data: dict[str, Any] = original.get("data") or {}
        new_data: dict[str, Any] = new_event.get("data") or {}

        # --- chosen_action / action drift ---
        for key in ("chosen_action", "action"):
            orig_val = orig_data.get(key)
            new_val = new_data.get(key)
            if orig_val is not None and new_val is not None and orig_val != new_val:
                return DriftEvent(
                    severity=DriftSeverity.CRITICAL,
                    description=f"Action drift: expected {orig_val!r}, got {new_val!r}",
                    original_value=orig_val,
                    restored_value=new_val,
                    event_index=index,
                )

        # --- tool_name drift ---
        orig_tool = orig_data.get("tool_name")
        new_tool = new_data.get("tool_name")
        if orig_tool is not None and new_tool is not None and orig_tool != new_tool:
            return DriftEvent(
                severity=DriftSeverity.WARNING,
                description=f"Tool call drift: expected {orig_tool!r}, got {new_tool!r}",
                original_value=orig_tool,
                restored_value=new_tool,
                event_index=index,
            )

        # --- confidence drift ---
        orig_conf = orig_data.get("confidence")
        new_conf = new_data.get("confidence")
        if orig_conf is not None and new_conf is not None:
            delta = abs(float(orig_conf) - float(new_conf))
            if delta >= _CONFIDENCE_DRIFT_THRESHOLD:
                return DriftEvent(
                    severity=DriftSeverity.WARNING,
                    description=(
                        f"Confidence drift: {orig_conf:.2f} \u2192 {new_conf:.2f} (\u0394{delta:.2f})"
                    ),
                    original_value=orig_conf,
                    restored_value=new_conf,
                    event_index=index,
                )

        return None
