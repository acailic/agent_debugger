"""State-drift detection for replay sessions.

Compares events recorded during a restored replay against the original
execution. Emits DriftEvent values when execution paths diverge.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class DriftSeverity(str, Enum):
    """Severity levels for detected state drift."""

    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class DriftEvent:
    """Describes a single point of divergence between original and restored execution.

    Attributes:
        severity: How significant the drift is.
        description: Human-readable explanation of what changed.
        original_value: The value recorded in the original run.
        restored_value: The value observed in the restored run.
    """

    severity: DriftSeverity
    description: str
    original_value: Any = None
    restored_value: Any = None

    # Aliases so tests can use either naming convention.
    @property
    def expected(self) -> Any:
        return self.original_value

    @property
    def actual(self) -> Any:
        return self.restored_value


class DriftDetector:
    """Compares a restored replay against the original recorded events.

    Usage::

        detector = DriftDetector(original_events)
        drift = detector.compare(new_event, index=0)
        if drift:
            print(drift.severity, drift.description)
    """

    # Confidence delta that triggers a WARNING.
    _CONFIDENCE_THRESHOLD = 0.4

    def __init__(self, original_events: list[dict[str, Any]]) -> None:
        self._original = original_events

    def compare(self, new_event: dict[str, Any], index: int) -> DriftEvent | None:
        """Compare *new_event* at *index* against the original event at that position.

        Returns a DriftEvent if drift is detected, or None if execution matches.
        Missing fields in either event are handled gracefully (no false positives).
        """
        if index < 0 or index >= len(self._original):
            return None

        original = self._original[index]
        orig_data: dict[str, Any] = original.get("data") or {}
        new_data: dict[str, Any] = new_event.get("data") or {}

        orig_type = original.get("event_type")
        new_type = new_event.get("event_type")

        # --- Decision / action drift ---
        if orig_type == "decision" or new_type == "decision":
            orig_action = orig_data.get("chosen_action") or orig_data.get("action")
            new_action = new_data.get("chosen_action") or new_data.get("action")
            if orig_action is not None and new_action is not None and orig_action != new_action:
                return DriftEvent(
                    severity=DriftSeverity.CRITICAL,
                    description=f"Action drift: expected '{orig_action}', got '{new_action}'",
                    original_value=orig_action,
                    restored_value=new_action,
                )

            # Confidence drift (only when both values present)
            orig_conf = orig_data.get("confidence")
            new_conf = new_data.get("confidence")
            if orig_conf is not None and new_conf is not None:
                if abs(float(orig_conf) - float(new_conf)) > self._CONFIDENCE_THRESHOLD:
                    return DriftEvent(
                        severity=DriftSeverity.WARNING,
                        description=(
                            f"Confidence drift: expected {orig_conf}, got {new_conf}"
                        ),
                        original_value=orig_conf,
                        restored_value=new_conf,
                    )

        # --- Tool call drift ---
        if orig_type == "tool_call" or new_type == "tool_call":
            orig_tool = orig_data.get("tool_name") or orig_data.get("tool")
            new_tool = new_data.get("tool_name") or new_data.get("tool")
            if orig_tool is not None and new_tool is not None and orig_tool != new_tool:
                return DriftEvent(
                    severity=DriftSeverity.WARNING,
                    description=f"Tool call drift: expected '{orig_tool}', got '{new_tool}'",
                    original_value=orig_tool,
                    restored_value=new_tool,
                )

        return None
