"""Lightweight fake implementations for unit tests.

These are real implementations with in-memory behavior, not mocks.
They satisfy the same interface contracts as production classes so tests
stay stable even if internals change.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from agent_debugger_sdk.core.events import Checkpoint, TraceEvent
from collector.buffer_base import BufferBase


class FakeEventBuffer(BufferBase):
    """In-memory buffer that records all calls for assertion.

    Subscribers receive events via asyncio queues, matching the
    real EventBuffer contract.
    """

    def __init__(self) -> None:
        self.published: list[tuple[str, TraceEvent]] = []
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    async def publish(self, session_id: str, event: TraceEvent) -> None:
        self.published.append((session_id, event))
        for q in self._subscribers.get(session_id, []):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def subscribe(self, session_id: str) -> asyncio.Queue:
        q: asyncio.Queue[TraceEvent] = asyncio.Queue(maxsize=100)
        self._subscribers[session_id].append(q)
        return q

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(session_id, [])
        if queue in subs:
            subs.remove(queue)

    async def get_events(self, session_id: str) -> list[TraceEvent]:
        return [e for sid, e in self.published if sid == session_id]

    async def get_session_ids(self) -> list[str]:
        return list({sid for sid, _ in self.published})

    async def flush(self, session_id: str) -> list[TraceEvent]:
        events = [e for sid, e in self.published if sid == session_id]
        self.published = [(sid, e) for sid, e in self.published if sid != session_id]
        return events


class FakeTraceIntelligence:
    """Returns deterministic analysis for testing.

    All method calls are recorded so tests can assert invocation.
    """

    def __init__(self, replay_value: float = 0.5) -> None:
        self._replay_value = replay_value
        self.analyze_session_calls: list[tuple[list[TraceEvent], list[Checkpoint]]] = []
        self.build_live_summary_calls: list[tuple[list[TraceEvent], list[Checkpoint]]] = []

    def analyze_session(
        self,
        events: list[TraceEvent],
        checkpoints: list[Checkpoint],
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.analyze_session_calls.append((events, checkpoints))
        return {
            "event_rankings": [],
            "failure_clusters": [],
            "representative_failure_ids": [],
            "high_replay_value_ids": [],
            "behavior_alerts": [],
            "checkpoint_rankings": [],
            "session_replay_value": self._replay_value,
            "retention_tier": "full",
            "session_summary": {
                "failure_count": 0,
                "behavior_alert_count": 0,
                "high_severity_count": 0,
                "checkpoint_count": len(checkpoints),
            },
            "failure_explanations": [],
            "live_summary": {
                "event_count": len(events),
                "checkpoint_count": len(checkpoints),
                "latest": {
                    "decision_event_id": None,
                    "tool_event_id": None,
                    "safety_event_id": None,
                    "turn_event_id": None,
                    "policy_event_id": None,
                    "checkpoint_id": None,
                },
                "rolling_summary": "",
                "recent_alerts": [],
            },
            "highlights": [],
        }

    def build_live_summary(
        self,
        events: list[TraceEvent],
        checkpoints: list[Checkpoint],
    ) -> dict[str, Any]:
        self.build_live_summary_calls.append((events, checkpoints))
        return {
            "event_count": len(events),
            "checkpoint_count": len(checkpoints),
            "latest": {
                "decision_event_id": None,
                "tool_event_id": None,
                "safety_event_id": None,
                "turn_event_id": None,
                "policy_event_id": None,
                "checkpoint_id": None,
            },
            "rolling_summary": "",
            "recent_alerts": [],
        }


class FakeRedactionPipeline:
    """Redaction pipeline that records calls and returns events unchanged."""

    def __init__(self) -> None:
        self.apply_calls: list[TraceEvent] = []

    def apply(self, event: TraceEvent) -> TraceEvent:
        self.apply_calls.append(event)
        return event
