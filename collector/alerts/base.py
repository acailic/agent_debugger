"""Base protocol for alert derivation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agent_debugger_sdk.core.events import TraceEvent


class AlertDeriver(ABC):
    """Protocol for deriving alerts from events."""

    @abstractmethod
    def derive(self, events: list[TraceEvent]) -> list[dict[str, Any]]:
        """Derive alerts from a list of events.

        Args:
            events: List of trace events to analyze

        Returns:
            List of alert dictionaries with keys: alert_type, severity, signal, event_id, source
        """
        ...
