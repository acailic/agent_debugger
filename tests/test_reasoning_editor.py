"""Tests for reasoning editor primitives."""

import uuid
from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core import (
    DecisionEvent,
    EditOperation,
    EditableEvent,
    EventType,
    ReasoningEdit,
    ReasoningEditor,
    ScenarioBranch,
    TraceEvent,
)


@pytest.fixture
def sample_events():
    """Create sample events for testing."""
    session_id = str(uuid.uuid4())

    # Create a decision event with reasoning
    decision = DecisionEvent(
        session_id=session_id,
        name="analyze_request",
        reasoning="1. Parse user input\n2. Identify intent\n3. Choose appropriate tool",
        confidence=0.8,
        chosen_action="call_tool:search",
    )

    # Create an LLM request event
    llm_request = TraceEvent(
        session_id=session_id,
        parent_id=decision.id,
        event_type=EventType.LLM_REQUEST,
        name="llm_request",
        data={"model": "gpt-4", "messages": [{"role": "user", "content": "test"}]},
    )

    # Create another decision
    decision2 = DecisionEvent(
        session_id=session_id,
        parent_id=llm_request.id,
        name="process_response",
        reasoning="Evaluate response quality\ndetermine next action",
        confidence=0.9,
        chosen_action="return_result",
    )

    return [decision, llm_request, decision2]


@pytest.fixture
def reasoning_editor(sample_events):
    """Create a reasoning editor with sample events."""
    return ReasoningEditor(events=sample_events)


class TestReasoningEdit:
    """Test ReasoningEdit dataclass."""

    def test_create_edit(self):
        """Test creating a reasoning edit."""
        edit = ReasoningEdit(
            operation=EditOperation.MODIFY,
            event_id="event_123",
            field_name="reasoning",
            old_value="old reasoning",
            new_value="new reasoning",
        )

        assert edit.operation == EditOperation.MODIFY
        assert edit.event_id == "event_123"
        assert edit.field_name == "reasoning"
        assert edit.old_value == "old reasoning"
        assert edit.new_value == "new reasoning"
        assert isinstance(edit.edit_id, str)
        assert isinstance(edit.created_at, datetime)


class TestEditableEvent:
    """Test EditableEvent wrapper."""

    def test_create_editable_event(self, sample_events):
        """Test creating an editable event wrapper."""
        event = sample_events[0]
        editable = EditableEvent(event=event)

        assert editable.event == event
        assert editable.is_modified is False
        assert len(editable.applied_edits) == 0

    def test_apply_modify_edit(self, sample_events):
        """Test applying a modify edit."""
        event = sample_events[0]
        editable = EditableEvent(event=event)

        edit = ReasoningEdit(
            operation=EditOperation.MODIFY,
            event_id=event.id,
            field_name="reasoning",
            old_value=event.reasoning,
            new_value="Updated reasoning",
        )

        editable.apply_edit(edit)

        assert editable.is_modified is True
        assert len(editable.applied_edits) == 1
        assert editable.event.reasoning == "Updated reasoning"

    def test_apply_delete_edit(self, sample_events):
        """Test applying a delete edit."""
        event = sample_events[0]
        editable = EditableEvent(event=event)

        edit = ReasoningEdit(
            operation=EditOperation.DELETE,
            event_id=event.id,
            field_name="reasoning",
            old_value=event.reasoning,
        )

        editable.apply_edit(edit)

        assert editable.is_modified is True
        assert editable.event.reasoning == ""

    def test_apply_insert_edit_beginning(self, sample_events):
        """Test inserting reasoning at beginning."""
        event = sample_events[0]
        original_reasoning = event.reasoning
        editable = EditableEvent(event=event)

        edit = ReasoningEdit(
            operation=EditOperation.INSERT,
            event_id=event.id,
            field_name="reasoning",
            new_value="New first step",
            position=-2,  # Beginning
        )

        editable.apply_edit(edit)

        expected = "New first step\n" + original_reasoning
        assert editable.event.reasoning == expected

    def test_apply_insert_edit_end(self, sample_events):
        """Test inserting reasoning at end."""
        event = sample_events[0]
        original_reasoning = event.reasoning
        editable = EditableEvent(event=event)

        edit = ReasoningEdit(
            operation=EditOperation.INSERT,
            event_id=event.id,
            field_name="reasoning",
            new_value="Final step",
            position=-1,  # End
        )

        editable.apply_edit(edit)

        expected = original_reasoning + "\nFinal step"
        assert editable.event.reasoning == expected

    def test_get_modified_event(self, sample_events):
        """Test getting modified event copy."""
        event = sample_events[0]
        editable = EditableEvent(event=event)

        edit = ReasoningEdit(
            operation=EditOperation.MODIFY,
            event_id=event.id,
            field_name="reasoning",
            old_value=event.reasoning,
            new_value="Modified",
        )

        editable.apply_edit(edit)
        modified = editable.get_modified_event()

        assert modified.reasoning == "Modified"
        assert modified.id == event.id


class TestScenarioBranch:
    """Test ScenarioBranch dataclass."""

    def test_create_branch(self):
        """Test creating a scenario branch."""
        branch = ScenarioBranch(
            name="Alternative approach",
            description="Testing different reasoning",
            parent_event_id="event_123",
            original_session_id="session_456",
        )

        assert branch.name == "Alternative approach"
        assert branch.parent_event_id == "event_123"
        assert len(branch.edits) == 0
        assert isinstance(branch.branch_id, str)


class TestReasoningEditor:
    """Test ReasoningEditor main class."""

    def test_initialization(self, sample_events):
        """Test editor initialization."""
        editor = ReasoningEditor(events=sample_events)

        assert len(editor.events) == 3
        assert len(editor.editable_events) == 3
        assert len(editor.scenarios) == 0

    def test_get_event_by_id(self, reasoning_editor):
        """Test retrieving event by ID."""
        event = reasoning_editor.get_event_by_id(reasoning_editor.events[0].id)
        assert event is not None
        assert event.name == "analyze_request"

    def test_get_event_by_id_not_found(self, reasoning_editor):
        """Test retrieving non-existent event."""
        event = reasoning_editor.get_event_by_id("nonexistent")
        assert event is None

    def test_edit_reasoning_modify(self, reasoning_editor):
        """Test editing reasoning with MODIFY operation."""
        event_id = reasoning_editor.events[0].id
        edit = reasoning_editor.edit_reasoning(
            event_id=event_id,
            operation=EditOperation.MODIFY,
            field_name="reasoning",
            new_value="Completely new reasoning",
        )

        assert edit.operation == EditOperation.MODIFY
        assert edit.new_value == "Completely new reasoning"

        # Check event was modified
        modified_event = reasoning_editor.editable_events[event_id].event
        assert modified_event.reasoning == "Completely new reasoning"

    def test_edit_reasoning_delete(self, reasoning_editor):
        """Test editing reasoning with DELETE operation."""
        event_id = reasoning_editor.events[0].id
        edit = reasoning_editor.edit_reasoning(
            event_id=event_id,
            operation=EditOperation.DELETE,
            field_name="reasoning",
        )

        assert edit.operation == EditOperation.DELETE

        # Check event was cleared
        modified_event = reasoning_editor.editable_events[event_id].event
        assert modified_event.reasoning == ""

    def test_create_branch(self, reasoning_editor):
        """Test creating a scenario branch."""
        branch = reasoning_editor.create_branch(
            name="Test branch",
            parent_event_id=reasoning_editor.events[0].id,
            description="Test scenario",
        )

        assert branch.name == "Test branch"
        assert branch.parent_event_id == reasoning_editor.events[0].id
        assert len(reasoning_editor.scenarios) == 1
        assert branch.branch_id in reasoning_editor.scenarios

    def test_get_events_for_replay(self, reasoning_editor):
        """Test getting events for replay from a point."""
        from_event_id = reasoning_editor.events[1].id  # Start from second event
        replay_events = reasoning_editor.get_events_for_replay(from_event_id)

        assert len(replay_events) == 2  # Should return 2nd and 3rd events
        assert replay_events[0].id == from_event_id

    def test_get_events_for_replay_with_branch_edits(self, reasoning_editor):
        """Test getting events for replay with branch edits applied."""
        # Create a branch with edits
        event_id = reasoning_editor.events[0].id
        edit = ReasoningEdit(
            operation=EditOperation.MODIFY,
            event_id=event_id,
            field_name="reasoning",
            new_value="Branch-specific reasoning",
        )

        branch = reasoning_editor.create_branch(
            name="Test branch",
            parent_event_id=event_id,
            description="Test",
            edits=[edit],
        )

        # Get events for replay with branch edits
        replay_events = reasoning_editor.get_events_for_replay(
            from_event_id=event_id,
            include_branch_edits=True,
            branch_id=branch.branch_id,
        )

        # First event should have modified reasoning
        assert replay_events[0].reasoning == "Branch-specific reasoning"

    def test_get_hierarchical_reasoning(self, reasoning_editor):
        """Test extracting hierarchical reasoning structure."""
        event_id = reasoning_editor.events[0].id
        hierarchy = reasoning_editor.get_hierarchical_reasoning(event_id)

        assert "topics" in hierarchy
        assert "raw" in hierarchy
        assert len(hierarchy["topics"]) > 0
        assert hierarchy["raw"] == reasoning_editor.events[0].reasoning

    def test_export_import_scenario(self, reasoning_editor):
        """Test exporting and importing a scenario."""
        # Create a branch
        branch = reasoning_editor.create_branch(
            name="Export test",
            parent_event_id=reasoning_editor.events[0].id,
            description="Test export/import",
        )

        # Export
        exported = reasoning_editor.export_scenario(branch.branch_id)
        assert exported["name"] == "Export test"
        assert exported["branch_id"] == branch.branch_id

        # Create new editor and import
        new_editor = ReasoningEditor(events=reasoning_editor.events)
        imported_branch = new_editor.import_scenario(exported)

        assert imported_branch.name == "Export test"
        assert imported_branch.branch_id == branch.branch_id
        assert len(new_editor.scenarios) == 1

    def test_compare_scenarios(self, reasoning_editor):
        """Test comparing multiple scenario branches."""
        # Create two branches
        branch1 = reasoning_editor.create_branch(
            name="Branch 1",
            parent_event_id=reasoning_editor.events[0].id,
            description="First branch",
        )

        branch2 = reasoning_editor.create_branch(
            name="Branch 2",
            parent_event_id=reasoning_editor.events[1].id,
            description="Second branch",
        )

        # Compare
        comparison = reasoning_editor.compare_scenarios([branch1.branch_id, branch2.branch_id])

        assert len(comparison["branches"]) == 2
        assert len(comparison["differences"]) > 0
        assert comparison["branches"][0]["name"] == "Branch 1"
        assert comparison["branches"][1]["name"] == "Branch 2"

    def test_edit_nonexistent_event_raises_error(self, reasoning_editor):
        """Test that editing non-existent event raises error."""
        with pytest.raises(ValueError, match="Event .* not found"):
            reasoning_editor.edit_reasoning(
                event_id="nonexistent",
                operation=EditOperation.MODIFY,
                field_name="reasoning",
                new_value="test",
            )

    def test_get_events_for_replay_nonexistent_event_raises_error(self, reasoning_editor):
        """Test that getting events for replay with nonexistent event raises error."""
        with pytest.raises(ValueError, match="Event .* not found"):
            reasoning_editor.get_events_for_replay("nonexistent")

    def test_export_nonexistent_scenario_raises_error(self, reasoning_editor):
        """Test that exporting non-existent scenario raises error."""
        with pytest.raises(ValueError, match="Branch .* not found"):
            reasoning_editor.export_scenario("nonexistent")


class TestIntegration:
    """Integration tests for reasoning editor workflow."""

    def test_full_editing_workflow(self, sample_events):
        """Test complete workflow: edit, branch, compare."""
        editor = ReasoningEditor(events=sample_events)

        # Step 1: Edit reasoning in first event
        event_id = sample_events[0].id
        editor.edit_reasoning(
            event_id=event_id,
            operation=EditOperation.MODIFY,
            field_name="reasoning",
            new_value="1. Improved parsing\n2. Better intent recognition\n3. Optimal tool selection",
        )

        # Step 2: Create branch from edited point
        branch = editor.create_branch(
            name="Improved workflow",
            parent_event_id=event_id,
            description="Better reasoning chain",
            edits=editor.editable_events[event_id].applied_edits,
        )

        # Step 3: Get replay events
        replay_events = editor.get_events_for_replay(
            from_event_id=event_id,
            include_branch_edits=True,
            branch_id=branch.branch_id,
        )

        # Verify workflow
        assert len(replay_events) == 3
        assert "Improved parsing" in replay_events[0].reasoning
        assert len(branch.edits) == 1

        # Step 4: Create alternative branch for comparison
        branch2 = editor.create_branch(
            name="Alternative approach",
            parent_event_id=event_id,
            description="Different reasoning",
        )

        # Step 5: Compare branches
        comparison = editor.compare_scenarios([branch.branch_id, branch2.branch_id])
        assert len(comparison["branches"]) == 2

    def test_hierarchical_reasoning_structure(self, sample_events):
        """Test that hierarchical reasoning extracts topics correctly."""
        editor = ReasoningEditor(events=sample_events)

        # Event with numbered reasoning
        event_id = sample_events[0].id
        hierarchy = editor.get_hierarchical_reasoning(event_id)

        # Should extract topics from numbered list
        assert len(hierarchy["topics"]) >= 1
        assert any("Parse user input" in topic.get("title", "") for topic in hierarchy["topics"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])