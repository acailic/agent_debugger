"""Base protocol for alert derivation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agent_debugger_sdk.core.events import TraceEvent


class AlertDeriver(ABC):
    """Protocol for deriving alerts from events."""

    def __init__(self, policy_getter: Any | None = None):
        """Initialize the alerter with an optional policy getter.

        Args:
            policy_getter: Optional callable that retrieves alert policies.
                          Should have signature: (alert_type: str, agent_name: str | None) -> dict | None
        """
        self.policy_getter = policy_getter

    def get_threshold(self, alert_type: str, agent_name: str | None = None, default_threshold: float = 0.0) -> float:
        """Get the threshold value for an alert type from policy or use default.

        Args:
            alert_type: Type of alert to get threshold for
            agent_name: Optional agent name for agent-specific policies
            default_threshold: Default threshold if no policy found

        Returns:
            Threshold value to use
        """
        if self.policy_getter:
            policy = self.policy_getter(alert_type, agent_name)
            if policy and policy.get("enabled", True):
                return policy.get("threshold_value", default_threshold)
        return default_threshold

    @abstractmethod
    def derive(self, events: list[TraceEvent]) -> list[dict[str, Any]]:
        """Derive alerts from a list of events.

        Args:
            events: List of trace events to analyze

        Returns:
            List of alert dictionaries with keys: alert_type, severity, signal, event_id, source
        """
        ...
