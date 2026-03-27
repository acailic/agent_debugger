"""Tool loop detection alerter."""
from __future__ import annotations

from typing import Any

from agent_debugger_sdk.core.events import EventType, TraceEvent

from ..causal_analysis import _event_value
from .base import AlertDeriver


class ToolLoopAlerter(AlertDeriver):
    """Detects 3+ consecutive calls to the same tool."""

    def derive(self, events: list[TraceEvent]) -> list[dict[str, Any]]:
        """Derive tool loop alerts from events.

        Args:
            events: List of trace events to analyze

        Returns:
            List of alert dictionaries for detected tool loops
        """
        alerts: list[dict[str, Any]] = []

        recent_tool_calls = [event for event in events if event.event_type == EventType.TOOL_CALL]
        last_three_tool_calls = recent_tool_calls[-3:]

        if len(last_three_tool_calls) == 3:
            tool_name = _event_value(last_three_tool_calls[-1], "tool_name", "")
            if tool_name and all(
                _event_value(event, "tool_name", "") == tool_name for event in last_three_tool_calls
            ):
                alerts.append(
                    {
                        "alert_type": "tool_loop",
                        "severity": "high",
                        "signal": f"Three consecutive calls to {tool_name}",
                        "event_id": last_three_tool_calls[-1].id,
                        "source": "derived",
                    }
                )

        return alerts
