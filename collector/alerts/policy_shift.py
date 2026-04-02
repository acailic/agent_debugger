"""Policy shift detection alerter."""

from __future__ import annotations

from typing import Any

from agent_debugger_sdk.core.events import EventType, TraceEvent

from ..causal_analysis import _event_value
from .base import AlertDeriver


class PolicyShiftAlerter(AlertDeriver):
    """Detects 2+ unique policies active in recent window."""

    def derive(self, events: list[TraceEvent]) -> list[dict[str, Any]]:
        """Derive policy shift alerts from events.

        Args:
            events: List of trace events to analyze

        Returns:
            List of alert dictionaries for detected policy shifts
        """
        alerts: list[dict[str, Any]] = []

        recent_policies = [event for event in events if event.event_type == EventType.PROMPT_POLICY]
        unique_policies = {
            _event_value(event, "template_id", event.name)
            for event in recent_policies
            if _event_value(event, "template_id", event.name)
        }

        if len(unique_policies) >= 2:
            alerts.append(
                {
                    "alert_type": "policy_shift",
                    "severity": "medium",
                    "signal": f"{len(unique_policies)} prompt policies active in the recent window",
                    "event_id": recent_policies[-1].id,
                    "source": "derived",
                }
            )

        return alerts
