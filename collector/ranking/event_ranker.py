"""Event ranking service for computing replay value and severity."""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from agent_debugger_sdk.core.events import EventType, TraceEvent


def _event_value(event: TraceEvent | None, key: str, default: Any = None) -> Any:
    """Extract a value from an event's attributes or data dict."""
    if event is None:
        return default
    if hasattr(event, key):
        return getattr(event, key)
    return event.data.get(key, default)


class EventRankingService:
    """Compute event rankings for replay value and severity."""

    def __init__(
        self,
        causal_analyzer: Any,
        fingerprint_fn: Callable[[TraceEvent], str],
        severity_fn: Callable[[TraceEvent], float],
    ) -> None:
        """Initialize the event ranking service.

        Args:
            causal_analyzer: CausalAnalyzer instance for computing severity.
            fingerprint_fn: Function to compute event fingerprints.
            severity_fn: Function to compute event severity.
        """
        self._causal = causal_analyzer
        self._fingerprint = fingerprint_fn
        self._severity = severity_fn

    def rank_events(
        self,
        events: list[TraceEvent],
        checkpoint_event_ids: set[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Compute rankings for all events.

        Args:
            events: List of trace events to rank.
            checkpoint_event_ids: Set of event IDs that are associated with checkpoints.

        Returns:
            Tuple of:
            - List of ranking dicts with:
              - event_id, event_type, fingerprint
              - severity, novelty, recurrence, replay_value, composite
            - List of behavior_alerts (tool loop detection)
        """
        if not events:
            return [], []

        fingerprints = [self._fingerprint(event) for event in events]
        counts = Counter(fingerprints)
        event_rankings: list[dict[str, Any]] = []

        consecutive_tool_loop = 0
        previous_tool_name: str | None = None
        behavior_alerts: list[dict[str, Any]] = []

        for index, event in enumerate(events):
            fingerprint = fingerprints[index]
            severity = self._severity(event)
            recurrence_count = counts[fingerprint]
            recurrence = min((recurrence_count - 1) / max(len(events), 1), 1.0)
            novelty = 1.0 / recurrence_count
            replay_value = severity * 0.55
            replay_value += 0.15 if event.id in checkpoint_event_ids else 0.0
            replay_value += (
                0.1 if event.event_type in {EventType.DECISION, EventType.REFUSAL, EventType.POLICY_VIOLATION} else 0.0
            )
            replay_value += (
                0.1
                if bool(_event_value(event, "upstream_event_ids", getattr(event, "upstream_event_ids", [])))
                else 0.0
            )
            replay_value += 0.1 if bool(_event_value(event, "evidence_event_ids", [])) else 0.0
            composite = min(1.0, severity * 0.45 + novelty * 0.2 + recurrence * 0.15 + replay_value * 0.2)

            event_rankings.append(
                {
                    "event_id": event.id,
                    "event_type": str(event.event_type),
                    "fingerprint": fingerprint,
                    "severity": round(severity, 4),
                    "novelty": round(novelty, 4),
                    "recurrence": round(recurrence, 4),
                    "replay_value": round(min(replay_value, 1.0), 4),
                    "composite": round(composite, 4),
                }
            )

            # Tool loop detection for behavior_alerts
            if event.event_type == EventType.TOOL_CALL:
                tool_name = _event_value(event, "tool_name", "")
                if tool_name and tool_name == previous_tool_name:
                    consecutive_tool_loop += 1
                else:
                    consecutive_tool_loop = 1
                previous_tool_name = tool_name
                if consecutive_tool_loop >= 3:
                    behavior_alerts.append(
                        {
                            "alert_type": "tool_loop",
                            "severity": "high",
                            "signal": f"Repeated tool loop for {tool_name}",
                            "event_id": event.id,
                        }
                    )
            else:
                previous_tool_name = None
                consecutive_tool_loop = 0

        return event_rankings, behavior_alerts
