"""Protocol interfaces for key dependencies.

These protocols enable structural subtyping so tests can use lightweight
fakes without inheritance. Production classes satisfy these protocols
implicitly, and test doubles can satisfy them by implementing the required
methods.
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol, runtime_checkable

from agent_debugger_sdk.core.events import Checkpoint, TraceEvent


@runtime_checkable
class IntelligenceProtocol(Protocol):
    """Protocol for session-level trace analysis and adaptive ranking.

    Any class that provides analyze_session and build_live_summary methods
    with compatible signatures satisfies this protocol.
    """

    def analyze_session(self, events: list[TraceEvent], checkpoints: list[Checkpoint]) -> dict[str, Any]:
        """Analyze session events for replay, clustering, and anomaly signals.

        Args:
            events: List of trace events from the session
            checkpoints: List of checkpoints captured during the session

        Returns:
            Dictionary containing event rankings, failure clusters, behavior
            alerts, checkpoint rankings, session replay value, retention tier,
            and session summary.
        """
        ...

    def build_live_summary(self, events: list[TraceEvent], checkpoints: list[Checkpoint]) -> dict[str, Any]:
        """Build a live monitoring summary from the current persisted session state.

        Args:
            events: List of trace events from the session
            checkpoints: List of checkpoints captured during the session

        Returns:
            Dictionary containing event count, checkpoint count, latest event
            IDs by type, rolling summary, and recent alerts.
        """
        ...


@runtime_checkable
class RedactionPipelineProtocol(Protocol):
    """Protocol for event redaction pipelines.

    Any class that provides an apply method for redacting trace events
    satisfies this protocol.
    """

    def apply(self, event: TraceEvent) -> TraceEvent:
        """Apply redaction rules to a trace event.

        Args:
            event: The event to redact

        Returns:
            The redacted event (may be the same instance or a copy)
        """
        ...


@runtime_checkable
class EventScorerProtocol(Protocol):
    """Protocol for event scoring.

    Any class that provides a score method for computing event importance
    satisfies this protocol.
    """

    def score(self, event: TraceEvent) -> float:
        """Compute a score for an event.

        Args:
            event: The event to score

        Returns:
            A float score, typically in [0, 1], representing the event's
            importance, severity, or replay value.
        """
        ...


@runtime_checkable
class BufferProtocol(Protocol):
    """Protocol for event pub/sub buffers.

    Any class that provides async publish/subscribe for real-time event
    streaming satisfies this protocol. This mirrors BufferBase but uses
    structural subtyping instead of inheritance.
    """

    async def publish(self, session_id: str, event: TraceEvent) -> None:
        """Publish event to all subscribers.

        Args:
            session_id: Session ID to publish to
            event: TraceEvent to publish
        """
        ...

    async def subscribe(self, session_id: str) -> asyncio.Queue:
        """Subscribe to events for a session.

        Args:
            session_id: Session ID to subscribe to

        Returns:
            asyncio.Queue that will receive events
        """
        ...

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        """Unsubscribe from events.

        Args:
            session_id: Session ID to unsubscribe from
            queue: Queue to remove from subscribers
        """
        ...

    async def get_events(self, session_id: str) -> list[TraceEvent]:
        """Get all stored events for a session.

        Args:
            session_id: Session ID to get events for

        Returns:
            List of TraceEvent objects
        """
        ...

    async def get_session_ids(self) -> list[str]:
        """Get all session IDs with buffered events.

        Returns:
            List of session IDs
        """
        ...

    async def flush(self, session_id: str) -> list[TraceEvent]:
        """Atomically pop and return all events for a session.

        Args:
            session_id: Session ID to flush

        Returns:
            List of TraceEvent objects (may be empty)
        """
        ...
