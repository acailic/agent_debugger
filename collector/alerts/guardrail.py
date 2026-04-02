"""Guardrail pressure detection alerter."""

from __future__ import annotations

from typing import Any

from agent_debugger_sdk.core.events import EventType, TraceEvent

from ..causal_analysis import _event_value
from .base import AlertDeriver


class GuardrailPressureAlerter(AlertDeriver):
    """Detects 2+ guardrails triggered in recent window."""

    def derive(self, events: list[TraceEvent]) -> list[dict[str, Any]]:
        """Derive guardrail pressure alerts from events.

        Args:
            events: List of trace events to analyze

        Returns:
            List of alert dictionaries for detected guardrail pressure
        """
        alerts: list[dict[str, Any]] = []

        recent_guardrails = [
            event
            for event in events
            if (
                event.event_type == EventType.REFUSAL
                or event.event_type == EventType.POLICY_VIOLATION
                or (event.event_type == EventType.SAFETY_CHECK and _event_value(event, "outcome", "pass") != "pass")
            )
        ]

        if len(recent_guardrails) >= 2:
            alerts.append(
                {
                    "alert_type": "guardrail_pressure",
                    "severity": "high" if len(recent_guardrails) >= 3 else "medium",
                    "signal": f"{len(recent_guardrails)} recent blocked or warned actions",
                    "event_id": recent_guardrails[-1].id,
                    "source": "derived",
                }
            )

        return alerts
