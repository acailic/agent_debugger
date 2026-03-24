"""Checkpoint dataclass for state snapshot tracking."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(kw_only=True)
class Checkpoint:
    """Dataclass representing a state snapshot for time-travel debugging.

    Checkpoints capture the complete state of an agent at a specific
    point in execution, enabling state restoration and analysis.

    Attributes:
        id: Unique checkpoint identifier (UUID)
        session_id: ID of the session this checkpoint belongs to
        event_id: ID of the event this checkpoint is associated with
        sequence: Sequential number for ordering checkpoints
        state: The agent's state at this point
        memory: The agent's memory/context at this point
        timestamp: When this checkpoint was created
        importance: Relative importance score (0.0-1.0)
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    event_id: str = ""
    sequence: int = 0
    state: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    importance: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        """Serialize the checkpoint to a dictionary."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "event_id": self.event_id,
            "sequence": self.sequence,
            "state": self.state,
            "memory": self.memory,
            "timestamp": self.timestamp.isoformat(),
            "importance": self.importance,
        }
