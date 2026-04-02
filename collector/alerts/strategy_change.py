"""Strategy change detection alerter."""

from __future__ import annotations

from typing import Any

from agent_debugger_sdk.core.events import EventType, TraceEvent

from ..causal_analysis import _event_value
from .base import AlertDeriver


class StrategyChangeAlerter(AlertDeriver):
    """Detects when chosen_action shifts between consecutive decisions."""

    def derive(self, events: list[TraceEvent]) -> list[dict[str, Any]]:
        """Derive strategy change alerts from events.

        Args:
            events: List of trace events to analyze

        Returns:
            List of alert dictionaries for detected strategy changes
        """
        alerts: list[dict[str, Any]] = []

        recent_decisions = [event for event in events if event.event_type == EventType.DECISION]
        last_two_decisions = recent_decisions[-2:]

        if len(last_two_decisions) == 2:
            previous_action = _event_value(last_two_decisions[0], "chosen_action", last_two_decisions[0].name)
            latest_action = _event_value(last_two_decisions[1], "chosen_action", last_two_decisions[1].name)

            if previous_action != latest_action:
                alerts.append(
                    {
                        "alert_type": "strategy_change",
                        "severity": "medium",
                        "signal": f'Decision shifted from "{previous_action}" to "{latest_action}"',
                        "event_id": last_two_decisions[-1].id,
                        "source": "derived",
                    }
                )

        return alerts
