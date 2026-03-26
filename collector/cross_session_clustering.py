"""Cross-session failure clustering for pattern detection."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_debugger_sdk.core.events import Session, TraceEvent
    from storage import TraceRepository


@dataclass
class CrossSessionCluster:
    """Represents a cluster of failures across multiple sessions."""

    id: str
    fingerprint: str
    session_ids: list[str] = field(default_factory=list)
    event_count: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    representative_session_id: str | None = None
    representative_event_id: str | None = None
    avg_severity: float = 0.0
    sample_failure_mode: str | None = None
    sample_symptom: str | None = None


class CrossSessionClusterer:
    """Cluster failures across sessions using fingerprint similarity."""

    # Minimum severity threshold for an event to be considered a failure
    FAILURE_SEVERITY_THRESHOLD = 0.78

    def __init__(self, repository: TraceRepository | None = None):
        """Initialize the clusterer.

        Args:
            repository: Optional TraceRepository for persisting clusters.
        """
        self.repository = repository

    async def cluster_failures(
        self,
        sessions: list[Session],
        events_by_session: dict[str, list[TraceEvent]],
        time_window_days: int = 7,
    ) -> list[CrossSessionCluster]:
        """Cluster failures across sessions using fingerprint similarity.

        Args:
            sessions: List of sessions to analyze.
            events_by_session: Dict mapping session IDs to their events.
            time_window_days: Time window for clustering (not used in basic impl).

        Returns:
            List of CrossSessionCluster sorted by severity * session count.
        """
        if not sessions:
            return []

        # Extract all failure events grouped by fingerprint
        failure_events: dict[str, list[tuple[str, TraceEvent]]] = defaultdict(list)

        for session in sessions:
            events = events_by_session.get(session.id, [])
            for event in events:
                importance = getattr(event, "importance", None) or 0
                if importance >= self.FAILURE_SEVERITY_THRESHOLD:
                    fingerprint = self._compute_fingerprint(event)
                    failure_events[fingerprint].append((session.id, event))

        # Build clusters from grouped failures
        clusters: list[CrossSessionCluster] = []
        for fingerprint, session_events in failure_events.items():
            if not session_events:
                continue

            # Deduplicate session IDs
            session_ids = list(set(se[0] for se in session_events))
            events = [se[1] for se in session_events]

            # Compute average severity
            total_severity = sum(getattr(e, "importance", 0) or 0 for e in events)
            avg_severity = total_severity / len(events) if events else 0.0

            # Find timestamps
            timestamps = [e.timestamp for e in events if hasattr(e, "timestamp") and e.timestamp]
            first_seen = min(timestamps) if timestamps else None
            last_seen = max(timestamps) if timestamps else None

            # Select representative: highest importance in most recent session
            sorted_by_importance = sorted(
                session_events,
                key=lambda se: (-(getattr(se[1], "importance", 0) or 0), se[0]),
            )
            rep_session_id, rep_event = sorted_by_importance[0]

            # Extract failure mode and symptom from event data
            event_data = getattr(rep_event, "data", {}) or {}
            sample_failure_mode = self._extract_failure_mode(rep_event, event_data)
            sample_symptom = self._extract_symptom(rep_event, event_data)

            cluster = CrossSessionCluster(
                id=str(uuid.uuid4()),
                fingerprint=fingerprint,
                session_ids=session_ids,
                event_count=len(events),
                first_seen=first_seen,
                last_seen=last_seen,
                representative_session_id=rep_session_id,
                representative_event_id=rep_event.id,
                avg_severity=avg_severity,
                sample_failure_mode=sample_failure_mode,
                sample_symptom=sample_symptom,
            )
            clusters.append(cluster)

        # Sort by severity * session count (impact score)
        return sorted(clusters, key=lambda c: -(c.avg_severity * len(c.session_ids)))

    def _compute_fingerprint(self, event: TraceEvent) -> str:
        """Compute a fingerprint for clustering similar failures.

        The fingerprint is based on event type and key identifying fields.

        Args:
            event: The trace event to fingerprint.

        Returns:
            A string fingerprint for clustering.
        """
        event_type = str(getattr(event, "event_type", "unknown"))
        name = getattr(event, "name", "") or ""
        data = getattr(event, "data", {}) or {}

        # Extract secondary identifier based on event type
        secondary = ""
        if "tool_name" in data:
            secondary = str(data["tool_name"])
        elif "error_type" in data:
            secondary = str(data["error_type"])
        elif "policy_name" in data:
            secondary = str(data["policy_name"])
        elif "alert_type" in data:
            secondary = str(data["alert_type"])

        return f"{event_type}:{name}:{secondary}"

    def _extract_failure_mode(
        self,
        event: TraceEvent,
        data: dict[str, Any],
    ) -> str | None:
        """Extract a failure mode classification from an event.

        Args:
            event: The trace event.
            data: The event's data dictionary.

        Returns:
            A failure mode string or None.
        """
        event_type = str(getattr(event, "event_type", ""))

        if event_type == "error":
            return str(data.get("error_type", "unknown_error"))
        elif event_type == "refusal":
            return str(data.get("policy_name", "policy_refusal"))
        elif event_type == "policy_violation":
            return str(data.get("violation_type", "policy_violation"))
        elif event_type == "behavior_alert":
            return str(data.get("alert_type", "behavior_alert"))
        elif event_type == "safety_check":
            outcome = data.get("outcome", "unknown")
            return f"safety_{outcome}"

        return None

    def _extract_symptom(
        self,
        event: TraceEvent,
        data: dict[str, Any],
    ) -> str | None:
        """Extract a symptom description from an event.

        Args:
            event: The trace event.
            data: The event's data dictionary.

        Returns:
            A symptom string or None.
        """
        # Try common symptom fields
        for key in ["error_message", "message", "reason", "signal", "details"]:
            if key in data:
                value = str(data[key])
                # Truncate long messages
                if len(value) > 512:
                    return value[:509] + "..."
                return value

        return None
