"""Repair attempt events for tracking failed and successful repair attempts.

Based on the FailureMem paper (arXiv:2603.17826), failed repair attempts are valuable
artifacts worth preserving for analysis and learning.
"""

from dataclasses import dataclass
from enum import Enum

from .base import EventType, TraceEvent

__all__ = ["RepairAttemptEvent", "RepairOutcome"]


class RepairOutcome(str, Enum):
    """Possible outcomes of a repair attempt."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


@dataclass(kw_only=True)
class RepairAttemptEvent(TraceEvent):
    """Event representing a repair attempt during agent execution.

    Captures attempts to fix issues, including the proposed fix, validation results,
    and the final outcome. This enables analysis of repair strategies and their effectiveness.

    Attributes:
        event_type: Always EventType.REPAIR_ATTEMPT
        attempted_fix: Description of the fix that was attempted
        validation_result: Result of validating the fix, if available
        repair_outcome: Final outcome of the repair attempt
        repair_sequence_id: ID linking multiple repair attempts in sequence
        repair_diff: Actual diff/changes made during the repair, if available
    """

    event_type: EventType = EventType.REPAIR_ATTEMPT
    attempted_fix: str = ""
    validation_result: str | None = None
    repair_outcome: RepairOutcome = RepairOutcome.FAILURE
    repair_sequence_id: str | None = None
    repair_diff: str | None = None

    def __post_init__(self) -> None:
        """Validate repair_outcome is a valid RepairOutcome."""
        if isinstance(self.repair_outcome, str):
            self.repair_outcome = RepairOutcome(self.repair_outcome)

    def to_trace_event(self) -> TraceEvent:
        """Convert this RepairAttemptEvent to a base TraceEvent.

        Returns:
            A TraceEvent with all repair-specific fields merged into the data payload.
        """
        return TraceEvent(
            id=self.id,
            session_id=self.session_id,
            parent_id=self.parent_id,
            event_type=self.event_type,
            timestamp=self.timestamp,
            name=self.name,
            data=self.to_storage_data(),
            metadata=self.metadata,
            importance=self.importance,
            upstream_event_ids=self.upstream_event_ids,
        )
