"""Interactive breakpoint and step-through debugging for agent sessions.

Based on traditional debugger paradigms adapted for AI agent execution, this
module provides primitives for setting breakpoints, stepping through execution,
inspecting agent state, and branching from any breakpoint.

Key capabilities:
- Breakpoint model: markers on event types, tool names, confidence thresholds, safety outcomes
- StepControls: step_into (next decision), step_over (skip tool internals), step_out (return to parent)
- StateInspector: show agent context at each breakpoint
- BranchAndReplay: create alternative paths from any breakpoint
"""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# Python 3.10 compatibility: StrEnum was added in Python 3.11
if sys.version_info >= (3, 11):
    from enum import StrEnum  # type: ignore[assignment]
else:

    class StrEnum(str, Enum):  # type: ignore[misc]
        """Compatibility shim for StrEnum in Python 3.10."""

        def __str__(self) -> str:
            return str(self.value)


from agent_debugger_sdk.core.events import EventType, TraceEvent

__all__ = [
    "BreakpointType",
    "StepAction",
    "Breakpoint",
    "StepperState",
    "StepResult",
    "BranchPoint",
    "AgentStepper",
]


class BreakpointType(StrEnum):
    """Types of breakpoints for agent execution."""

    EVENT_TYPE = "event_type"  # Break on specific event type
    TOOL_NAME = "tool_name"  # Break when specific tool is called
    CONFIDENCE_THRESHOLD = "confidence_threshold"  # Break on confidence below threshold
    SAFETY_OUTCOME = "safety_outcome"  # Break on specific safety outcome
    CUSTOM_CONDITION = "custom_condition"  # Break on custom Python expression
    EVENT_ID = "event_id"  # Break at specific event ID


class StepAction(StrEnum):
    """Step actions for navigation through execution."""

    STEP_INTO = "step_into"  # Step into next decision/tool call
    STEP_OVER = "step_over"  # Skip over tool internals
    STEP_OUT = "step_out"  # Return to parent context
    CONTINUE = "continue"  # Continue to next breakpoint
    RUN_TO = "run_to"  # Run to specific event ID


@dataclass(kw_only=True)
class Breakpoint:
    """A breakpoint in agent execution.

    Attributes:
        breakpoint_id: Unique identifier for this breakpoint
        breakpoint_type: Type of breakpoint condition
        condition_value: Value for the breakpoint condition
        description: Human-readable description
        enabled: Whether breakpoint is active
        hit_count: Number of times breakpoint was hit
        created_at: When breakpoint was created
    """

    breakpoint_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    breakpoint_type: BreakpointType = BreakpointType.EVENT_TYPE
    condition_value: Any = None
    description: str = ""
    enabled: bool = True
    hit_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def should_trigger(self, event: TraceEvent) -> bool:
        """Check if breakpoint should trigger for an event.

        Args:
            event: Event to check against breakpoint condition

        Returns:
            True if breakpoint should trigger
        """
        if not self.enabled:
            return False

        if self.breakpoint_type == BreakpointType.EVENT_TYPE:
            return str(event.event_type) == str(self.condition_value)

        elif self.breakpoint_type == BreakpointType.TOOL_NAME:
            tool_name = getattr(event, "tool_name", None) or event.data.get("tool_name")
            return tool_name == self.condition_value

        elif self.breakpoint_type == BreakpointType.CONFIDENCE_THRESHOLD:
            confidence = getattr(event, "confidence", None) or event.data.get("confidence")
            if confidence is not None:
                return float(confidence) < float(self.condition_value)
            return False

        elif self.breakpoint_type == BreakpointType.SAFETY_OUTCOME:
            outcome = getattr(event, "safety_outcome", None) or event.data.get("safety_outcome")
            return str(outcome) == str(self.condition_value)

        elif self.breakpoint_type == BreakpointType.EVENT_ID:
            return event.id == self.condition_value

        elif self.breakpoint_type == BreakpointType.CUSTOM_CONDITION:
            # Evaluate custom condition safely
            try:
                return bool(eval(str(self.condition_value), {}, {"event": event}))
            except Exception:
                return False

        return False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "breakpoint_id": self.breakpoint_id,
            "breakpoint_type": str(self.breakpoint_type),
            "condition_value": self.condition_value,
            "description": self.description,
            "enabled": self.enabled,
            "hit_count": self.hit_count,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(kw_only=True)
class StepperState:
    """Current state of the debugger stepper.

    Attributes:
        current_event_index: Index of current event in execution
        current_event_id: ID of current event
        breakpoints: Active breakpoints
        step_history: History of step actions taken
        paused: Whether execution is paused
        completed: Whether execution has completed
    """

    current_event_index: int = 0
    current_event_id: str = ""
    breakpoints: list[Breakpoint] = field(default_factory=list)
    step_history: list[dict[str, Any]] = field(default_factory=list)
    paused: bool = True
    completed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "current_event_index": self.current_event_index,
            "current_event_id": self.current_event_id,
            "breakpoints": [bp.to_dict() for bp in self.breakpoints],
            "step_history": list(self.step_history),
            "paused": self.paused,
            "completed": self.completed,
        }


@dataclass(kw_only=True)
class StepResult:
    """Result of a step action.

    Attributes:
        success: Whether step was successful
        current_event: Current event after step
        next_event: Next event to execute
        breakpoint_hit: Which breakpoint was hit (if any)
        state: Updated stepper state
        message: Human-readable message
    """

    success: bool = True
    current_event: TraceEvent | None = None
    next_event: TraceEvent | None = None
    breakpoint_hit: Breakpoint | None = None
    state: StepperState | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "success": self.success,
            "current_event": self.current_event.to_dict() if self.current_event else None,
            "next_event": self.next_event.to_dict() if self.next_event else None,
            "breakpoint_hit": self.breakpoint_hit.to_dict() if self.breakpoint_hit else None,
            "state": self.state.to_dict() if self.state else None,
            "message": self.message,
        }


@dataclass(kw_only=True)
class BranchPoint:
    """A branch point in execution for alternative path exploration.

    Attributes:
        branch_id: Unique identifier for this branch
        parent_event_id: Event where branch starts
        name: Human-readable name for the branch
        description: What this branch explores
        created_at: When branch was created
        replay_events: Events to replay in this branch
        branch_result: Result of branching execution
    """

    branch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_event_id: str = ""
    name: str = ""
    description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    replay_events: list[TraceEvent] = field(default_factory=list)
    branch_result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "branch_id": self.branch_id,
            "parent_event_id": self.parent_event_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "replay_events_count": len(self.replay_events),
            "branch_result": self.branch_result,
        }


class AgentStepper:
    """Interactive stepper for agent execution debugging.

    Provides breakpoint management, step-through execution, state inspection,
    and branching capabilities for debugging agent sessions.

    Example usage::

        stepper = AgentStepper(session_events)

        # Set a breakpoint
        stepper.set_breakpoint(
            breakpoint_type=BreakpointType.EVENT_TYPE,
            condition_value="decision",
            description="Break on all decisions"
        )

        # Step through execution
        result = stepper.step(StepAction.STEP_INTO)
        while result.success:
            # Inspect state
            state = stepper.get_state_at_current_position()

            # Continue stepping
            result = stepper.step(StepAction.STEP_INTO)

        # Create branch from current position
        branch = stepper.create_branch(
            name="Alternative path",
            parent_event_id=stepper.state.current_event_id,
            description="Explore different decision"
        )
    """

    def __init__(self, events: list[TraceEvent] | None = None) -> None:
        """Initialize the agent stepper.

        Args:
            events: List of events from a session to debug
        """
        self.events: list[TraceEvent] = events or []
        self.state = StepperState()
        self.branches: dict[str, BranchPoint] = {}
        self._build_event_index()

    def _build_event_index(self) -> None:
        """Build index mapping event IDs to their positions."""
        self.event_index: dict[str, int] = {}
        for i, event in enumerate(self.events):
            self.event_index[event.id] = i

    def set_breakpoint(
        self,
        breakpoint_type: BreakpointType,
        condition_value: Any = None,
        description: str = "",
    ) -> Breakpoint:
        """Set a breakpoint for execution.

        Args:
            breakpoint_type: Type of breakpoint condition
            condition_value: Value for the breakpoint condition
            description: Human-readable description

        Returns:
            The created Breakpoint
        """
        breakpoint = Breakpoint(
            breakpoint_type=breakpoint_type,
            condition_value=condition_value,
            description=description or f"Break on {breakpoint_type}: {condition_value}",
        )

        self.state.breakpoints.append(breakpoint)
        return breakpoint

    def clear_breakpoint(self, breakpoint_id: str) -> bool:
        """Clear a breakpoint by ID.

        Args:
            breakpoint_id: ID of breakpoint to clear

        Returns:
            True if breakpoint was found and cleared
        """
        for i, bp in enumerate(self.state.breakpoints):
            if bp.breakpoint_id == breakpoint_id:
                self.state.breakpoints.pop(i)
                return True
        return False

    def clear_all_breakpoints(self) -> None:
        """Clear all breakpoints."""
        self.state.breakpoints.clear()

    def step(self, action: StepAction, target_event_id: str | None = None) -> StepResult:
        """Execute a step action.

        Args:
            action: Step action to perform
            target_event_id: Target event ID for STEP_OVER or RUN_TO

        Returns:
            StepResult with current event and state
        """
        if self.state.completed:
            return StepResult(
                success=False,
                state=self.state,
                message="Execution already completed",
            )

        current_event = None
        next_event = None
        breakpoint_hit = None

        if action == StepAction.STEP_INTO:
            # Step to next event
            if self.state.current_event_index < len(self.events):
                current_event = self.events[self.state.current_event_index]
                next_event = self.events[self.state.current_event_index + 1] if self.state.current_event_index + 1 < len(self.events) else None
                self.state.current_event_index += 1
                if next_event:
                    self.state.current_event_id = next_event.id
            else:
                self.state.completed = True

        elif action == StepAction.STEP_OVER:
            # Skip over tool internals
            if self.state.current_event_index < len(self.events):
                current_event = self.events[self.state.current_event_index]
                # Find next non-tool-result event
                i = self.state.current_event_index + 1
                while i < len(self.events):
                    next_event = self.events[i]
                    if next_event.event_type != EventType.TOOL_RESULT:
                        self.state.current_event_index = i
                        self.state.current_event_id = next_event.id
                        break
                    i += 1
                else:
                    self.state.completed = True
            else:
                self.state.completed = True

        elif action == StepAction.STEP_OUT:
            # Return to parent context
            if self.state.current_event_index < len(self.events):
                current_event = self.events[self.state.current_event_index]
                parent_id = current_event.parent_id
                if parent_id:
                    # Find parent event index
                    parent_index = self.event_index.get(parent_id)
                    if parent_index is not None:
                        self.state.current_event_index = parent_index
                        self.state.current_event_id = parent_id
                        # Next event after parent
                        next_event = self.events[parent_index + 1] if parent_index + 1 < len(self.events) else None
                else:
                    # Already at root, step normally
                    next_event = self.events[self.state.current_event_index + 1] if self.state.current_event_index + 1 < len(self.events) else None
                    self.state.current_event_index += 1
                    if next_event:
                        self.state.current_event_id = next_event.id
            else:
                self.state.completed = True

        elif action == StepAction.CONTINUE:
            # Continue to next breakpoint
            found_breakpoint = False
            for i in range(self.state.current_event_index, len(self.events)):
                event = self.events[i]
                for bp in self.state.breakpoints:
                    if bp.should_trigger(event):
                        bp.hit_count += 1
                        self.state.current_event_index = i
                        self.state.current_event_id = event.id
                        current_event = event
                        next_event = self.events[i + 1] if i + 1 < len(self.events) else None
                        breakpoint_hit = bp
                        found_breakpoint = True
                        break
                if found_breakpoint:
                    break
            else:
                # No breakpoint found, complete execution
                self.state.completed = True

        elif action == StepAction.RUN_TO:
            # Run to specific event
            if target_event_id:
                target_index = self.event_index.get(target_event_id)
                if target_index is not None:
                    current_event = self.events[self.state.current_event_index]
                    next_event = self.events[target_index]
                    self.state.current_event_index = target_index
                    self.state.current_event_id = target_event_id
                else:
                    return StepResult(
                        success=False,
                        state=self.state,
                        message=f"Event {target_event_id} not found",
                    )

        # Record step in history
        self.state.step_history.append({
            "action": str(action),
            "event_index": self.state.current_event_index,
            "event_id": self.state.current_event_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return StepResult(
            success=True,
            current_event=current_event,
            next_event=next_event,
            breakpoint_hit=breakpoint_hit,
            state=self.state,
            message=f"Stepped to event {self.state.current_event_id}",
        )

    def get_state_at_current_position(self) -> dict[str, Any]:
        """Get agent state at current stepper position.

        Returns:
            Dictionary with agent context, events, and state
        """
        if self.state.current_event_index >= len(self.events):
            return {
                "completed": True,
                "current_position": self.state.current_event_index,
                "total_events": len(self.events),
            }

        current_event = self.events[self.state.current_event_index]

        # Get events up to current position
        events_up_to_current = self.events[: self.state.current_event_index + 1]

        # Extract agent state from current event
        agent_state = {
            "event_id": current_event.id,
            "event_type": str(current_event.event_type),
            "timestamp": current_event.timestamp.isoformat() if current_event.timestamp else None,
            "name": current_event.name,
            "data": dict(current_event.data) if current_event.data else {},
            "parent_id": current_event.parent_id,
        }

        # Add confidence if available
        if hasattr(current_event, "confidence"):
            agent_state["confidence"] = current_event.confidence

        # Add reasoning if available
        if hasattr(current_event, "reasoning"):
            agent_state["reasoning"] = current_event.reasoning

        # Add tool name if available
        if hasattr(current_event, "tool_name"):
            agent_state["tool_name"] = current_event.tool_name

        return {
            "completed": False,
            "current_position": self.state.current_event_index,
            "total_events": len(self.events),
            "current_event": agent_state,
            "events_count": len(events_up_to_current),
            "breakpoints_active": len([bp for bp in self.state.breakpoints if bp.enabled]),
            "paused": self.state.paused,
        }

    def create_branch(
        self,
        name: str,
        parent_event_id: str,
        description: str = "",
    ) -> BranchPoint:
        """Create a branch point for alternative path exploration.

        Args:
            name: Human-readable name for the branch
            parent_event_id: Event where this branch starts
            description: What this branch explores

        Returns:
            The created BranchPoint
        """
        # Find event index
        parent_index = self.event_index.get(parent_event_id, 0)

        # Get events from branch point onwards
        replay_events = self.events[parent_index:]

        branch = BranchPoint(
            name=name,
            parent_event_id=parent_event_id,
            description=description,
            replay_events=replay_events,
        )

        self.branches[branch.branch_id] = branch
        return branch

    def get_branch(self, branch_id: str) -> BranchPoint | None:
        """Get a branch by ID.

        Args:
            branch_id: ID of branch to retrieve

        Returns:
            BranchPoint if found, None otherwise
        """
        return self.branches.get(branch_id)

    def list_branches(self) -> list[BranchPoint]:
        """List all branches.

        Returns:
            List of all branches
        """
        return list(self.branches.values())

    def delete_branch(self, branch_id: str) -> bool:
        """Delete a branch by ID.

        Args:
            branch_id: ID of branch to delete

        Returns:
            True if branch was found and deleted
        """
        if branch_id in self.branches:
            del self.branches[branch_id]
            return True
        return False

    def reset(self) -> None:
        """Reset stepper to initial state."""
        self.state = StepperState()
        self.branches.clear()

    def get_execution_context(self) -> dict[str, Any]:
        """Get full execution context with state and branches.

        Returns:
            Complete execution context
        """
        return {
            "state": self.state.to_dict(),
            "events_count": len(self.events),
            "branches": [branch.to_dict() for branch in self.branches.values()],
            "breakpoints": [bp.to_dict() for bp in self.state.breakpoints],
        }

    def export_state(self) -> dict[str, Any]:
        """Export stepper state for persistence.

        Returns:
            JSON-serializable state representation
        """
        return {
            "state": self.state.to_dict(),
            "branches": [branch.to_dict() for branch in self.branches.values()],
            "events_count": len(self.events),
        }

    def import_state(self, state_data: dict[str, Any]) -> None:
        """Import stepper state from exported data.

        Args:
            state_data: Exported state data
        """
        self.state = StepperState(**state_data.get("state", {}))
        self.branches.clear()
        for branch_data in state_data.get("branches", []):
            branch = BranchPoint(
                branch_id=branch_data["branch_id"],
                parent_event_id=branch_data["parent_event_id"],
                name=branch_data["name"],
                description=branch_data["description"],
                created_at=datetime.fromisoformat(branch_data["created_at"]),
                branch_result=branch_data.get("branch_result"),
            )
            self.branches[branch.branch_id] = branch