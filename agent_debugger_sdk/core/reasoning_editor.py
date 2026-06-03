"""Reasoning editor primitives for interactive CoT editing and live replay.

Based on the IUI 2026 paper "Interactive Reasoning: Visualizing and Controlling
Chain-of-Thought Reasoning in LMs" by Pang et al., this module provides primitives
for editing agent reasoning chains and replaying execution with modified reasoning.

Key capabilities:
- Edit reasoning steps in DecisionEvent and LLM events
- Create execution branches from modified reasoning
- Live replay with alternative reasoning paths
- Scenario management for comparing edited executions
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from agent_debugger_sdk.core.events import (
    TraceEvent,
)


class EditOperation(str, Enum):
    """Types of reasoning edit operations."""

    MODIFY = "modify"  # Change existing reasoning content
    INSERT = "insert"  # Add new reasoning step
    DELETE = "delete"  # Remove reasoning step
    REPLACE = "replace"  # Replace entire reasoning chain


@dataclass(kw_only=True)
class ReasoningEdit:
    """Represents a single edit to reasoning content.

    Attributes:
        edit_id: Unique identifier for this edit
        operation: Type of edit operation
        event_id: ID of the event being edited
        field_name: Which field to edit (e.g., "reasoning", "content")
        position: For INSERT, position in reasoning chain (0-based)
        old_value: Original value being replaced/deleted
        new_value: New value to insert/replace
        created_at: When this edit was created
    """

    edit_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    operation: EditOperation = EditOperation.MODIFY
    event_id: str = ""
    field_name: str = ""
    position: int = -1  # -1 for end, -2 for beginning, >=0 for specific position
    old_value: Any = None
    new_value: Any = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(kw_only=True)
class ScenarioBranch:
    """A branch point in execution with modified reasoning.

    Represents an alternative execution path created by editing reasoning
    at a specific event and replaying from that point.

    Attributes:
        branch_id: Unique identifier for this branch
        name: Human-readable name for the scenario
        description: What was changed and why
        parent_event_id: Event where branch starts
        edits: List of edits applied in this branch
        original_session_id: Original session this branches from
        created_at: When this branch was created
        replay_result: Result of replaying with edits (if available)
    """

    branch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    parent_event_id: str = ""
    edits: list[ReasoningEdit] = field(default_factory=list)
    original_session_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    replay_result: dict[str, Any] | None = None  # Stores replay outcome


@dataclass(kw_only=True)
class EditableEvent:
    """Wrapper for events with edit capabilities.

    Provides utilities for applying and tracking edits to reasoning content.

    Attributes:
        event: Original event being edited
        applied_edits: List of edits applied to this event
        is_modified: Whether this event has been modified
    """

    event: TraceEvent
    applied_edits: list[ReasoningEdit] = field(default_factory=list)
    is_modified: bool = False

    def apply_edit(self, edit: ReasoningEdit) -> EditableEvent:
        """Apply a reasoning edit to the event.

        Args:
            edit: The edit to apply

        Returns:
            Self for chaining
        """
        if edit.operation == EditOperation.DELETE:
            self._apply_delete(edit)
        elif edit.operation == EditOperation.INSERT:
            self._apply_insert(edit)
        elif edit.operation == EditOperation.MODIFY:
            self._apply_modify(edit)
        elif edit.operation == EditOperation.REPLACE:
            self._apply_replace(edit)

        self.applied_edits.append(edit)
        self.is_modified = True
        return self

    def _apply_modify(self, edit: ReasoningEdit) -> None:
        """Modify an existing field value."""
        if hasattr(self.event, edit.field_name):
            setattr(self.event, edit.field_name, edit.new_value)
        elif edit.field_name in self.event.data:
            self.event.data[edit.field_name] = edit.new_value

    def _apply_replace(self, edit: ReasoningEdit) -> None:
        """Replace entire reasoning chain."""
        if hasattr(self.event, edit.field_name):
            setattr(self.event, edit.field_name, edit.new_value)
        elif edit.field_name in self.event.data:
            self.event.data[edit.field_name] = edit.new_value

    def _apply_insert(self, edit: ReasoningEdit) -> None:
        """Insert new reasoning step at position."""
        current_value = getattr(self.event, edit.field_name, None) or self.event.data.get(edit.field_name, "")

        if isinstance(current_value, str):
            # Insert into string reasoning
            if edit.position == -2:  # Beginning
                new_value = str(edit.new_value) + "\n" + current_value
            elif edit.position == -1 or edit.position >= len(current_value):  # End
                new_value = current_value + "\n" + str(edit.new_value)
            else:  # Specific position
                new_value = (
                    current_value[:edit.position]
                    + "\n"
                    + str(edit.new_value)
                    + current_value[edit.position:]
                )

            if hasattr(self.event, edit.field_name):
                setattr(self.event, edit.field_name, new_value)
            else:
                self.event.data[edit.field_name] = new_value

    def _apply_delete(self, edit: ReasoningEdit) -> None:
        """Delete reasoning content."""
        if hasattr(self.event, edit.field_name):
            setattr(self.event, edit.field_name, "")
        elif edit.field_name in self.event.data:
            self.event.data[edit.field_name] = ""

    def get_modified_event(self) -> TraceEvent:
        """Get the modified event copy.

        Returns:
            A deep copy of the event with edits applied
        """
        return copy.deepcopy(self.event)


class ReasoningEditor:
    """Main editor for reasoning chains and scenario management.

    Provides high-level API for editing reasoning, creating branches,
    and managing scenarios for interactive CoT manipulation.

    Example usage::

        editor = ReasoningEditor(session_events)

        # Edit a decision's reasoning
        decision_event = editor.get_event_by_id("decision_123")
        editor.edit_reasoning(
            event_id="decision_123",
            operation=EditOperation.MODIFY,
            field_name="reasoning",
            new_value="Updated reasoning with better logic"
        )

        # Create a scenario branch
        branch = editor.create_branch(
            name="Alternative approach",
            parent_event_id="decision_123",
            description="Trying different reasoning path"
        )

        # Get events for replay from branch point
        replay_events = editor.get_events_for_replay(branch.parent_event_id)
    """

    def __init__(self, events: list[TraceEvent] | None = None) -> None:
        """Initialize the reasoning editor.

        Args:
            events: List of events from a session to edit
        """
        self.events: list[TraceEvent] = events or []
        self.editable_events: dict[str, EditableEvent] = {}
        self.scenarios: dict[str, ScenarioBranch] = {}
        self._build_editable_cache()

    def _build_editable_cache(self) -> None:
        """Build cache of editable events by ID."""
        for event in self.events:
            self.editable_events[event.id] = EditableEvent(event=event)

    def get_event_by_id(self, event_id: str) -> TraceEvent | None:
        """Get an event by its ID.

        Args:
            event_id: The event ID to look up

        Returns:
            The event if found, None otherwise
        """
        editable = self.editable_events.get(event_id)
        return editable.event if editable else None

    def edit_reasoning(
        self,
        event_id: str,
        operation: EditOperation,
        field_name: str = "reasoning",
        new_value: Any = None,
        position: int = -1,
    ) -> ReasoningEdit:
        """Edit reasoning content in an event.

        Args:
            event_id: ID of event to edit
            operation: Type of edit operation
            field_name: Field to edit (default: "reasoning")
            new_value: New value to set
            position: Position for INSERT operations

        Returns:
            The created ReasoningEdit
        """
        editable = self.editable_events.get(event_id)
        if not editable:
            raise ValueError(f"Event {event_id} not found")

        # Get old value for tracking
        old_value = getattr(editable.event, field_name, None) or editable.event.data.get(field_name, "")

        edit = ReasoningEdit(
            operation=operation,
            event_id=event_id,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            position=position,
        )

        editable.apply_edit(edit)
        return edit

    def create_branch(
        self,
        name: str,
        parent_event_id: str,
        description: str = "",
        edits: list[ReasoningEdit] | None = None,
    ) -> ScenarioBranch:
        """Create a new scenario branch.

        Args:
            name: Human-readable name for the branch
            parent_event_id: Event where this branch diverges
            description: What changes this branch introduces
            edits: List of edits to apply in this branch

        Returns:
            The created ScenarioBranch
        """
        branch = ScenarioBranch(
            name=name,
            description=description,
            parent_event_id=parent_event_id,
            edits=edits or [],
            original_session_id=self.events[0].session_id if self.events else "",
        )

        self.scenarios[branch.branch_id] = branch
        return branch

    def get_events_for_replay(
        self,
        from_event_id: str,
        include_branch_edits: bool = True,
        branch_id: str | None = None,
    ) -> list[TraceEvent]:
        """Get events for replay starting from a specific event.

        Args:
            from_event_id: Event ID to start replay from
            include_branch_edits: Whether to include branch edits
            branch_id: Specific branch to get edits from

        Returns:
            List of events in replay order
        """
        from_index = -1
        for i, event in enumerate(self.events):
            if event.id == from_event_id:
                from_index = i
                break

        if from_index == -1:
            raise ValueError(f"Event {from_event_id} not found in events")

        events_to_replay = []

        # Apply branch edits if specified
        if include_branch_edits and branch_id:
            branch = self.scenarios.get(branch_id)
            if branch:
                # Create modified copies with edits applied
                for event in self.events[from_index:]:
                    editable = self.editable_events.get(event.id)
                    if editable:
                        modified = copy.deepcopy(editable)
                        # Apply branch-specific edits
                        for edit in branch.edits:
                            if edit.event_id == event.id:
                                modified.apply_edit(edit)
                        events_to_replay.append(modified.get_modified_event())
                    else:
                        events_to_replay.append(event)
            else:
                events_to_replay = self.events[from_index:]
        else:
            events_to_replay = self.events[from_index:]

        return events_to_replay

    def get_hierarchical_reasoning(self, event_id: str) -> dict[str, Any]:
        """Extract hierarchical reasoning structure from an event.

        Based on IUI 2026 paper's topic hierarchy visualization,
        this structures reasoning as a tree of topics/subtopics.

        Args:
            event_id: Event ID to extract reasoning from

        Returns:
            Hierarchical structure with topics, subtopics, and content
        """
        event = self.get_event_by_id(event_id)
        if not event:
            return {}

        reasoning = getattr(event, "reasoning", "") or event.data.get("reasoning", "")

        # Parse reasoning into hierarchical structure
        # Simple implementation: split by common reasoning markers
        topics = []
        current_topic = None

        for line in reasoning.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Detect topic markers (numbers, bullets, etc.)
            if line.startswith(("1.", "2.", "3.", "•", "-", "*")):
                if current_topic:
                    topics.append(current_topic)
                current_topic = {"title": line, "content": [], "subtopics": []}
            elif current_topic is not None:
                current_topic["content"].append(line)
            else:
                # First line without marker becomes root topic
                current_topic = {"title": line, "content": [], "subtopics": []}

        if current_topic:
            topics.append(current_topic)

        return {"topics": topics, "raw": reasoning}

    def compare_scenarios(
        self,
        branch_ids: list[str],
    ) -> dict[str, Any]:
        """Compare multiple scenario branches.

        Args:
            branch_ids: List of branch IDs to compare

        Returns:
            Comparison with metrics, differences, and recommendations
        """
        comparison = {
            "branches": [],
            "differences": [],
            "metrics": {},
        }

        for branch_id in branch_ids:
            branch = self.scenarios.get(branch_id)
            if branch:
                comparison["branches"].append(
                    {
                        "id": branch.branch_id,
                        "name": branch.name,
                        "description": branch.description,
                        "edit_count": len(branch.edits),
                        "created_at": branch.created_at.isoformat(),
                    }
                )

        # Calculate differences between branches
        for i, branch_id_a in enumerate(branch_ids):
            for branch_id_b in branch_ids[i + 1 :]:
                branch_a = self.scenarios.get(branch_id_a)
                branch_b = self.scenarios.get(branch_id_b)

                if branch_a and branch_b:
                    diff = self._compare_branches(branch_a, branch_b)
                    comparison["differences"].append(diff)

        return comparison

    def _compare_branches(
        self,
        branch_a: ScenarioBranch,
        branch_b: ScenarioBranch,
    ) -> dict[str, Any]:
        """Compare two branches for differences.

        Args:
            branch_a: First branch to compare
            branch_b: Second branch to compare

        Returns:
            Differences between the branches
        """
        return {
            "branch_a": branch_a.branch_id,
            "branch_b": branch_b.branch_id,
            "edit_difference": len(branch_a.edits) - len(branch_b.edits),
            "shared_parent": branch_a.parent_event_id == branch_b.parent_event_id,
        }

    def export_scenario(self, branch_id: str) -> dict[str, Any]:
        """Export a scenario as JSON-serializable dict.

        Args:
            branch_id: Branch ID to export

        Returns:
            JSON-serializable representation of the scenario
        """
        branch = self.scenarios.get(branch_id)
        if not branch:
            raise ValueError(f"Branch {branch_id} not found")

        return {
            "branch_id": branch.branch_id,
            "name": branch.name,
            "description": branch.description,
            "parent_event_id": branch.parent_event_id,
            "edits": [
                {
                    "edit_id": edit.edit_id,
                    "operation": edit.operation.value,
                    "event_id": edit.event_id,
                    "field_name": edit.field_name,
                    "old_value": edit.old_value,
                    "new_value": edit.new_value,
                    "position": edit.position,
                    "created_at": edit.created_at.isoformat(),
                }
                for edit in branch.edits
            ],
            "original_session_id": branch.original_session_id,
            "created_at": branch.created_at.isoformat(),
            "replay_result": branch.replay_result,
        }

    def import_scenario(self, scenario_data: dict[str, Any]) -> ScenarioBranch:
        """Import a scenario from exported data.

        Args:
            scenario_data: exported scenario data

        Returns:
            The imported ScenarioBranch
        """
        edits = []
        for edit_data in scenario_data.get("edits", []):
            edit = ReasoningEdit(
                edit_id=edit_data["edit_id"],
                operation=EditOperation(edit_data["operation"]),
                event_id=edit_data["event_id"],
                field_name=edit_data["field_name"],
                old_value=edit_data["old_value"],
                new_value=edit_data["new_value"],
                position=edit_data["position"],
                created_at=datetime.fromisoformat(edit_data["created_at"]),
            )
            edits.append(edit)

        branch = ScenarioBranch(
            branch_id=scenario_data["branch_id"],
            name=scenario_data["name"],
            description=scenario_data["description"],
            parent_event_id=scenario_data["parent_event_id"],
            edits=edits,
            original_session_id=scenario_data["original_session_id"],
            created_at=datetime.fromisoformat(str(scenario_data["created_at"])),
            replay_result=scenario_data.get("replay_result"),
        )

        self.scenarios[branch.branch_id] = branch
        return branch


__all__ = [
    "EditOperation",
    "ReasoningEdit",
    "ScenarioBranch",
    "EditableEvent",
    "ReasoningEditor",
]