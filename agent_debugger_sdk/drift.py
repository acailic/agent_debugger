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

    @staticmethod
    def _get_field(event: dict[str, Any], *keys: str) -> Any:
        """Get a field from an event, checking top-level keys first then nested data.

        Handles both real SDK events (where typed fields like chosen_action, tool_name,
        confidence are top-level keys placed by TraceEvent.to_dict()) and legacy
        nested payloads (where fields are inside event['data']).

        Args:
            event: The event dict to extract from.
            *keys: Keys to try, in order. Returns the first match found.

        Returns:
            The field value if found, None otherwise.
        """
        for key in keys:
            # Check top-level first (where TraceEvent.to_dict() puts typed fields)
            if key in event:
                return event[key]
            # Fall back to nested data dict
            data = event.get("data") or {}
            if key in data:
                return data[key]
        return None

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

        # --- event type mismatch check (CRITICAL) ---
        orig_type = self._get_field(original, "event_type")
        new_type = self._get_field(new_event, "event_type")
        if orig_type is not None and new_type is not None and orig_type != new_type:
            return DriftEvent(
                severity=DriftSeverity.CRITICAL,
                description=f"Event type mismatch: expected {orig_type!r}, got {new_type!r}",
                original_value=orig_type,
                restored_value=new_type,
                event_index=index,
            )

        # --- chosen_action / action drift ---
        # Use _get_field for each side to handle mixed payload structures
        orig_action = self._get_field(original, "chosen_action", "action")
        new_action = self._get_field(new_event, "chosen_action", "action")
        if orig_action is not None and new_action is not None and orig_action != new_action:
            return DriftEvent(
                severity=DriftSeverity.CRITICAL,
                description=f"Action drift: expected {orig_action!r}, got {new_action!r}",
                original_value=orig_action,
                restored_value=new_action,
                event_index=index,
            )

        # --- tool_name drift ---
        orig_tool = self._get_field(original, "tool_name")
        new_tool = self._get_field(new_event, "tool_name")
        if orig_tool is not None and new_tool is not None and orig_tool != new_tool:
            return DriftEvent(
                severity=DriftSeverity.WARNING,
                description=f"Tool call drift: expected {orig_tool!r}, got {new_tool!r}",
                original_value=orig_tool,
                restored_value=new_tool,
                event_index=index,
            )

        # --- confidence drift (with guarded conversion) ---
        orig_conf = self._get_field(original, "confidence")
        new_conf = self._get_field(new_event, "confidence")
        if orig_conf is not None and new_conf is not None:
            try:
                orig_conf_val = float(orig_conf)
                new_conf_val = float(new_conf)
                delta = abs(orig_conf_val - new_conf_val)
                if delta >= _CONFIDENCE_DRIFT_THRESHOLD:
                    return DriftEvent(
                        severity=DriftSeverity.WARNING,
                        description=(
                            f"Confidence drift: {orig_conf_val:.2f} \u2192 {new_conf_val:.2f} (\u0394{delta:.2f})"
                        ),
                        original_value=orig_conf,
                        restored_value=new_conf,
                        event_index=index,
                    )
            except (ValueError, TypeError):
                # Confidence values are not comparable as floats; skip this check
                pass

        return None
