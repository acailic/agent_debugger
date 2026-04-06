"""State-drift detection for comparing restored vs original agent execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class DriftSeverity(Enum):
    """Severity levels for detected state drift."""

    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class DriftEvent:
    """Represents a detected divergence between original and restored execution.

    Attributes:
        severity: How significant the drift is (WARNING or CRITICAL).
        description: Human-readable summary of what drifted.
        original_value: The value from the original execution.
        restored_value: The value from the restored execution.
        event_type: The type of event where drift was detected.
        index: The position in the event sequence where drift was detected.
    """

    severity: DriftSeverity
    description: str
    original_value: Any
    restored_value: Any
    event_type: str = ""
    index: int = 0

    # Aliases for test compatibility
    @property
    def expected(self) -> Any:
        return self.original_value

    @property
    def actual(self) -> Any:
        return self.restored_value


# Threshold at which a confidence delta is considered significant enough to flag
_CONFIDENCE_DRIFT_THRESHOLD = 0.4


class DriftDetector:
    """Detects divergence between original and restored agent execution.

    Compares new (restored) events against a reference list of original events,
    field by field. Returns a :class:`DriftEvent` when drift is found, or ``None``
    when events match.

    Args:
        original_events: Ordered list of events from the original execution.
    """

    def __init__(self, original_events: list[dict[str, Any]]) -> None:
        self.original_events = original_events

    def compare(self, new_event: dict[str, Any], index: int = 0) -> DriftEvent | None:
        """Compare a restored event against the original event at *index*.

        Checks for differences in:
        - ``chosen_action`` / ``action`` inside ``data``
        - ``tool_name`` inside ``data``
        - ``confidence`` inside ``data`` (flags when delta exceeds threshold)

        Returns ``None`` when no drift is detected or when fields are absent.

        Args:
            new_event: The event produced during the restored execution.
            index: Position in ``original_events`` to compare against.

        Returns:
            A :class:`DriftEvent` if drift is detected, otherwise ``None``.
        """
        if index >= len(self.original_events):
            return None

        original = self.original_events[index]
        orig_data: dict[str, Any] = original.get("data") or {}
        new_data: dict[str, Any] = new_event.get("data") or {}
        event_type = new_event.get("event_type", original.get("event_type", ""))

        # Check chosen_action / action drift
        for key in ("chosen_action", "action"):
            if key in orig_data and key in new_data:
                if orig_data[key] != new_data[key]:
                    return DriftEvent(
                        severity=DriftSeverity.CRITICAL,
                        description=(
                            f"Action drift at index {index}: "
                            f"expected {orig_data[key]!r}, got {new_data[key]!r}"
                        ),
                        original_value=orig_data[key],
                        restored_value=new_data[key],
                        event_type=event_type,
                        index=index,
                    )

        # Check tool_name / tool drift (some payloads use 'tool' instead of 'tool_name')
        orig_tool = orig_data.get("tool_name") or orig_data.get("tool")
        new_tool = new_data.get("tool_name") or new_data.get("tool")
        if orig_tool is not None and new_tool is not None and orig_tool != new_tool:
            return DriftEvent(
                severity=DriftSeverity.WARNING,
                description=(
                    f"Tool call drift at index {index}: "
                    f"expected tool {orig_tool!r}, "
                    f"got {new_tool!r}"
                ),
                original_value=orig_tool,
                restored_value=new_tool,
                event_type=event_type,
                index=index,
            )

        # Check confidence drift (with guarded float conversion)
        if "confidence" in orig_data and "confidence" in new_data:
            try:
                delta = abs(float(orig_data["confidence"]) - float(new_data["confidence"]))
                if delta >= _CONFIDENCE_DRIFT_THRESHOLD:
                    severity = DriftSeverity.CRITICAL if delta >= 0.5 else DriftSeverity.WARNING
                    return DriftEvent(
                        severity=severity,
                        description=(
                            f"Confidence drift at index {index}: "
                            f"expected {orig_data['confidence']}, got {new_data['confidence']} "
                            f"(delta={delta:.2f})"
                        ),
                        original_value=orig_data["confidence"],
                        restored_value=new_data["confidence"],
                        event_type=event_type,
                        index=index,
                    )
            except (ValueError, TypeError):
                # Confidence values are not comparable as floats; skip this check
                pass

        return None
