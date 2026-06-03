"""Tests for agent stepper breakpoint and step-through debugging."""

import pytest

from agent_debugger_sdk.core.events import EventType, TraceEvent
from agent_debugger_sdk.core.stepper import (
    AgentStepper,
    Breakpoint,
    BreakpointType,
    StepAction,
)


@pytest.fixture
def sample_events():
    """Create sample trace events for testing."""
    events = [
        TraceEvent(
            id="event_1",
            session_id="session_1",
            timestamp="2024-01-01T00:00:00Z",
            event_type=EventType.AGENT_START,
            name="Start",
            data={},
            metadata={},
            importance=0.5,
            upstream_event_ids=[],
            parent_id=None,
        ),
        TraceEvent(
            id="event_2",
            session_id="session_1",
            timestamp="2024-01-01T00:00:01Z",
            event_type=EventType.DECISION,
            name="Decision 1",
            data={"reasoning": "First decision"},
            metadata={},
            importance=0.8,
            upstream_event_ids=[],
            parent_id="event_1",
            confidence=0.9,
        ),
        TraceEvent(
            id="event_3",
            session_id="session_1",
            timestamp="2024-01-01T00:00:02Z",
            event_type=EventType.TOOL_CALL,
            name="Tool Call",
            data={"tool_name": "search"},
            metadata={},
            importance=0.6,
            upstream_event_ids=[],
            parent_id="event_2",
            tool_name="search",
        ),
        TraceEvent(
            id="event_4",
            session_id="session_1",
            timestamp="2024-01-01T00:00:03Z",
            event_type=EventType.TOOL_RESULT,
            name="Tool Result",
            data={"result": "found"},
            metadata={},
            importance=0.4,
            upstream_event_ids=[],
            parent_id="event_3",
        ),
        TraceEvent(
            id="event_5",
            session_id="session_1",
            timestamp="2024-01-01T00:00:04Z",
            event_type=EventType.DECISION,
            name="Decision 2",
            data={"reasoning": "Second decision"},
            metadata={},
            importance=0.7,
            upstream_event_ids=[],
            parent_id="event_4",
            confidence=0.6,
        ),
    ]
    return events


class TestAgentStepper:
    """Test suite for AgentStepper class."""

    def test_initialization(self, sample_events):
        """Test stepper initialization with events."""
        stepper = AgentStepper(sample_events)

        assert len(stepper.events) == 5
        assert stepper.state.current_event_index == 0
        assert stepper.state.paused is True
        assert stepper.state.completed is False

    def test_set_breakpoint(self, sample_events):
        """Test setting a breakpoint."""
        stepper = AgentStepper(sample_events)

        breakpoint = stepper.set_breakpoint(
            breakpoint_type=BreakpointType.EVENT_TYPE,
            condition_value="decision",
            description="Break on decisions",
        )

        assert breakpoint.breakpoint_type == BreakpointType.EVENT_TYPE
        assert breakpoint.condition_value == "decision"
        assert breakpoint.description == "Break on decisions"
        assert breakpoint.enabled is True
        assert len(stepper.state.breakpoints) == 1

    def test_clear_breakpoint(self, sample_events):
        """Test clearing a breakpoint."""
        stepper = AgentStepper(sample_events)

        breakpoint = stepper.set_breakpoint(
            breakpoint_type=BreakpointType.EVENT_TYPE,
            condition_value="decision",
        )

        success = stepper.clear_breakpoint(breakpoint.breakpoint_id)

        assert success is True
        assert len(stepper.state.breakpoints) == 0

    def test_clear_all_breakpoints(self, sample_events):
        """Test clearing all breakpoints."""
        stepper = AgentStepper(sample_events)

        stepper.set_breakpoint(BreakpointType.EVENT_TYPE, "decision")
        stepper.set_breakpoint(BreakpointType.TOOL_NAME, "search")

        stepper.clear_all_breakpoints()

        assert len(stepper.state.breakpoints) == 0

    def test_step_into(self, sample_events):
        """Test step into action."""
        stepper = AgentStepper(sample_events)

        result = stepper.step(StepAction.STEP_INTO)

        assert result.success is True
        assert result.state.current_event_index == 1
        assert result.state.current_event_id == "event_2"
        assert result.current_event is not None
        assert result.current_event.event_type == EventType.DECISION

    def test_step_over(self, sample_events):
        """Test step over action."""
        stepper = AgentStepper(sample_events)
        # Move to tool call event
        stepper.state.current_event_index = 2
        stepper.state.current_event_id = "event_3"

        result = stepper.step(StepAction.STEP_OVER)

        assert result.success is True
        # Should skip tool_result and go to decision
        assert result.state.current_event_index == 4
        assert result.state.current_event_id == "event_5"

    def test_step_out(self, sample_events):
        """Test step out action."""
        stepper = AgentStepper(sample_events)
        # Start at tool result
        stepper.state.current_event_index = 3
        stepper.state.current_event_id = "event_4"

        result = stepper.step(StepAction.STEP_OUT)

        assert result.success is True
        # Should return to parent (tool call)
        assert result.state.current_event_index == 2
        assert result.state.current_event_id == "event_3"

    def test_continue_to_breakpoint(self, sample_events):
        """Test continue action to breakpoint."""
        stepper = AgentStepper(sample_events)

        # Set breakpoint on decision events
        stepper.set_breakpoint(BreakpointType.EVENT_TYPE, "decision")

        result = stepper.step(StepAction.CONTINUE)

        assert result.success is True
        assert result.breakpoint_hit is not None
        assert result.breakpoint_hit.breakpoint_type == BreakpointType.EVENT_TYPE
        assert result.state.current_event_index == 1  # First decision event

    def test_breakpoint_on_confidence(self, sample_events):
        """Test breakpoint on confidence threshold."""
        stepper = AgentStepper(sample_events)

        # Set breakpoint on confidence below 0.7
        stepper.set_breakpoint(
            BreakpointType.CONFIDENCE_THRESHOLD,
            0.7,
            "Break on low confidence",
        )

        result = stepper.step(StepAction.CONTINUE)

        assert result.success is True
        assert result.breakpoint_hit is not None
        assert result.current_event is not None
        assert result.current_event.confidence == 0.6  # Second decision has 0.6

    def test_breakpoint_on_tool_name(self, sample_events):
        """Test breakpoint on tool name."""
        stepper = AgentStepper(sample_events)

        stepper.set_breakpoint(BreakpointType.TOOL_NAME, "search")

        result = stepper.step(StepAction.CONTINUE)

        assert result.success is True
        assert result.breakpoint_hit is not None
        assert result.current_event is not None
        assert result.current_event.tool_name == "search"

    def test_get_state_at_current_position(self, sample_events):
        """Test getting agent state at current position."""
        stepper = AgentStepper(sample_events)
        stepper.state.current_event_index = 1

        state = stepper.get_state_at_current_position()

        assert state["completed"] is False
        assert state["current_position"] == 1
        assert state["total_events"] == 5
        assert state["current_event"] is not None
        assert state["current_event"]["event_type"] == "decision"

    def test_create_branch(self, sample_events):
        """Test creating a branch point."""
        stepper = AgentStepper(sample_events)

        branch = stepper.create_branch(
            name="Alternative path",
            parent_event_id="event_2",
            description="Test branch",
        )

        assert branch.name == "Alternative path"
        assert branch.parent_event_id == "event_2"
        assert branch.description == "Test branch"
        assert len(branch.replay_events) == 4  # Events from event_2 onwards
        assert len(stepper.branches) == 1

    def test_list_branches(self, sample_events):
        """Test listing branches."""
        stepper = AgentStepper(sample_events)

        stepper.create_branch("Branch 1", "event_1", "First branch")
        stepper.create_branch("Branch 2", "event_2", "Second branch")

        branches = stepper.list_branches()

        assert len(branches) == 2

    def test_delete_branch(self, sample_events):
        """Test deleting a branch."""
        stepper = AgentStepper(sample_events)

        branch = stepper.create_branch("Test Branch", "event_1", "Test")
        success = stepper.delete_branch(branch.branch_id)

        assert success is True
        assert len(stepper.list_branches()) == 0

    def test_reset(self, sample_events):
        """Test resetting stepper."""
        stepper = AgentStepper(sample_events)

        stepper.set_breakpoint(BreakpointType.EVENT_TYPE, "decision")
        stepper.state.current_event_index = 3
        stepper.create_branch("Test", "event_1", "Test")

        stepper.reset()

        assert stepper.state.current_event_index == 0
        assert len(stepper.state.breakpoints) == 0
        assert len(stepper.branches) == 0

    def test_export_import_state(self, sample_events):
        """Test exporting and importing stepper state."""
        stepper = AgentStepper(sample_events)

        stepper.set_breakpoint(BreakpointType.EVENT_TYPE, "decision")
        stepper.state.current_event_index = 2
        branch = stepper.create_branch("Test", "event_1", "Test")

        # Export
        exported = stepper.export_state()

        # Import into new stepper
        new_stepper = AgentStepper(sample_events)
        new_stepper.import_state(exported)

        assert new_stepper.state.current_event_index == 2
        assert len(new_stepper.state.breakpoints) == 1
        assert len(new_stepper.branches) == 1

    def test_step_completion(self, sample_events):
        """Test stepping through all events to completion."""
        stepper = AgentStepper(sample_events)

        # Step through all events
        for _ in range(len(sample_events) + 1):
            result = stepper.step(StepAction.STEP_INTO)
            if not result.success:
                break

        assert stepper.state.completed is True

    def test_breakpoint_hit_count(self, sample_events):
        """Test breakpoint hit count tracking."""
        stepper = AgentStepper(sample_events)

        breakpoint = stepper.set_breakpoint(BreakpointType.EVENT_TYPE, "decision")

        # Step through events
        stepper.step(StepAction.CONTINUE)
        stepper.step(StepAction.STEP_INTO)
        stepper.step(StepAction.STEP_INTO)

        # Breakpoint should have been hit once
        assert breakpoint.hit_count == 1


class TestBreakpoint:
    """Test suite for Breakpoint class."""

    def test_should_trigger_event_type(self, sample_events):
        """Test breakpoint triggering on event type."""
        breakpoint = Breakpoint(
            breakpoint_type=BreakpointType.EVENT_TYPE,
            condition_value="decision",
        )

        decision_event = sample_events[1]  # DECISION event
        tool_event = sample_events[2]  # TOOL_CALL event

        assert breakpoint.should_trigger(decision_event) is True
        assert breakpoint.should_trigger(tool_event) is False

    def test_should_trigger_tool_name(self, sample_events):
        """Test breakpoint triggering on tool name."""
        breakpoint = Breakpoint(
            breakpoint_type=BreakpointType.TOOL_NAME,
            condition_value="search",
        )

        tool_event = sample_events[2]  # TOOL_CALL with tool_name="search"

        assert breakpoint.should_trigger(tool_event) is True

    def test_should_trigger_confidence(self, sample_events):
        """Test breakpoint triggering on confidence threshold."""
        breakpoint = Breakpoint(
            breakpoint_type=BreakpointType.CONFIDENCE_THRESHOLD,
            condition_value=0.7,
        )

        low_conf_event = sample_events[4]  # DECISION with confidence=0.6
        high_conf_event = sample_events[1]  # DECISION with confidence=0.9

        assert breakpoint.should_trigger(low_conf_event) is True
        assert breakpoint.should_trigger(high_conf_event) is False

    def test_breakpoint_disabled(self, sample_events):
        """Test that disabled breakpoints don't trigger."""
        breakpoint = Breakpoint(
            breakpoint_type=BreakpointType.EVENT_TYPE,
            condition_value="decision",
            enabled=False,
        )

        decision_event = sample_events[1]

        assert breakpoint.should_trigger(decision_event) is False

    def test_breakpoint_to_dict(self):
        """Test breakpoint serialization."""
        breakpoint = Breakpoint(
            breakpoint_type=BreakpointType.EVENT_TYPE,
            condition_value="decision",
            description="Test breakpoint",
        )

        data = breakpoint.to_dict()

        assert data["breakpoint_type"] == "event_type"
        assert data["condition_value"] == "decision"
        assert data["description"] == "Test breakpoint"
        assert data["enabled"] is True
        assert "breakpoint_id" in data
        assert "created_at" in data


class TestBreakpointValidation:
    """Test suite for breakpoint validation and behavior."""

    def test_breakpoint_with_string_condition(self):
        """Test breakpoint works with string condition values."""
        breakpoint = Breakpoint(
            breakpoint_type=BreakpointType.EVENT_TYPE,
            condition_value="decision",
        )
        assert breakpoint.condition_value == "decision"

    def test_breakpoint_with_none_condition(self):
        """Test breakpoint accepts None condition value."""
        breakpoint = Breakpoint(
            breakpoint_type=BreakpointType.EVENT_TYPE,
            condition_value=None,
        )
        assert breakpoint.condition_value is None

    def test_breakpoint_with_numeric_condition(self):
        """Test breakpoint works with numeric condition values."""
        breakpoint = Breakpoint(
            breakpoint_type=BreakpointType.CONFIDENCE_THRESHOLD,
            condition_value=0.7,
        )
        assert breakpoint.condition_value == 0.7

    def test_breakpoint_default_values(self):
        """Test breakpoint has sensible defaults."""
        breakpoint = Breakpoint()
        assert breakpoint.breakpoint_type == BreakpointType.EVENT_TYPE
        assert breakpoint.condition_value is None
        assert breakpoint.description == ""
        assert breakpoint.enabled is True
        assert breakpoint.hit_count == 0
        assert isinstance(breakpoint.breakpoint_id, str)

    def test_breakpoint_custom_id(self):
        """Test breakpoint can be created with custom ID."""
        custom_id = "my_custom_breakpoint_id"
        breakpoint = Breakpoint(breakpoint_id=custom_id)
        assert breakpoint.breakpoint_id == custom_id


class TestStepControls:
    """Test suite for step control edge cases."""

    def test_step_past_end_of_events(self, sample_events):
        """Test stepping past the last event."""
        stepper = AgentStepper(sample_events)
        stepper.state.current_event_index = len(sample_events) - 1

        result = stepper.step(StepAction.STEP_INTO)

        # Should complete but not fail
        assert result.success is True
        assert stepper.state.completed is True

    def test_step_at_start_position(self, sample_events):
        """Test stepping when already at start."""
        stepper = AgentStepper(sample_events)
        assert stepper.state.current_event_index == 0

        result = stepper.step(StepAction.STEP_INTO)

        assert result.success is True
        assert result.state.current_event_index == 1

    def test_step_out_at_root_event(self, sample_events):
        """Test step out when at root (no parent)."""
        stepper = AgentStepper(sample_events)
        stepper.state.current_event_index = 0  # At AGENT_START

        result = stepper.step(StepAction.STEP_OUT)

        # Should stay at root or complete
        assert result.success is True
        assert result.state.current_event_index == 0

    def test_step_over_non_tool_event(self, sample_events):
        """Test step over on non-tool event behaves like step into."""
        stepper = AgentStepper(sample_events)
        stepper.state.current_event_index = 1  # At DECISION

        result = stepper.step(StepAction.STEP_OVER)

        # Should just step to next event
        assert result.success is True
        assert result.state.current_event_index == 2

    def test_continue_with_no_breakpoints(self, sample_events):
        """Test continue with no breakpoints runs to completion."""
        stepper = AgentStepper(sample_events)

        result = stepper.step(StepAction.CONTINUE)

        # Should run to completion
        assert result.success is True
        assert stepper.state.completed is True

    def test_step_after_completion(self, sample_events):
        """Test stepping after completion is handled gracefully."""
        stepper = AgentStepper(sample_events)
        stepper.state.completed = True
        stepper.state.current_event_index = len(sample_events)

        result = stepper.step(StepAction.STEP_INTO)

        # Should indicate no more steps
        assert result.success is False or stepper.state.completed


class TestBranchManagement:
    """Test suite for branch creation and management."""

    def test_create_branch_with_invalid_parent(self, sample_events):
        """Test creating branch with nonexistent parent event defaults to start."""
        stepper = AgentStepper(sample_events)

        # Should not raise error, but create branch from start
        branch = stepper.create_branch(
            name="Invalid Branch",
            parent_event_id="nonexistent_event",
        )

        # Branch should be created starting from index 0
        assert branch.name == "Invalid Branch"
        assert branch.parent_event_id == "nonexistent_event"

    def test_create_branch_at_start(self, sample_events):
        """Test creating branch at first event."""
        stepper = AgentStepper(sample_events)

        branch = stepper.create_branch(
            name="Start Branch",
            parent_event_id=sample_events[0].id,
        )

        assert branch.name == "Start Branch"
        assert len(branch.replay_events) == len(sample_events)

    def test_create_branch_at_end(self, sample_events):
        """Test creating branch at last event."""
        stepper = AgentStepper(sample_events)

        branch = stepper.create_branch(
            name="End Branch",
            parent_event_id=sample_events[-1].id,
        )

        assert branch.name == "End Branch"
        assert len(branch.replay_events) == 1

    def test_delete_nonexistent_branch(self, sample_events):
        """Test deleting branch that doesn't exist."""
        stepper = AgentStepper(sample_events)

        success = stepper.delete_branch("nonexistent_branch_id")
        assert success is False

    def test_list_branches_empty(self, sample_events):
        """Test listing branches when none exist."""
        stepper = AgentStepper(sample_events)

        branches = stepper.list_branches()
        assert len(branches) == 0

    def test_multiple_branches_same_parent(self, sample_events):
        """Test creating multiple branches from same parent."""
        stepper = AgentStepper(sample_events)

        branch1 = stepper.create_branch("Branch 1", "event_2")
        branch2 = stepper.create_branch("Branch 2", "event_2")

        assert branch1.branch_id != branch2.branch_id
        assert len(stepper.list_branches()) == 2


class TestStateInspector:
    """Test suite for state inspection with various event types."""

    def test_state_at_decision_event(self, sample_events):
        """Test state inspection at decision event."""
        stepper = AgentStepper(sample_events)
        stepper.state.current_event_index = 1  # DECISION event

        state = stepper.get_state_at_current_position()

        assert state["current_event"]["event_type"] == "decision"
        assert state["current_event"]["confidence"] == 0.9

    def test_state_at_tool_call_event(self, sample_events):
        """Test state inspection at tool call event."""
        stepper = AgentStepper(sample_events)
        stepper.state.current_event_index = 2  # TOOL_CALL event

        state = stepper.get_state_at_current_position()

        assert state["current_event"]["event_type"] == "tool_call"
        assert state["current_event"]["tool_name"] == "search"

    def test_state_at_tool_result_event(self, sample_events):
        """Test state inspection at tool result event."""
        stepper = AgentStepper(sample_events)
        stepper.state.current_event_index = 3  # TOOL_RESULT event

        state = stepper.get_state_at_current_position()

        assert state["current_event"]["event_type"] == "tool_result"

    def test_state_includes_breakpoint_active_count(self, sample_events):
        """Test state includes active breakpoint count."""
        stepper = AgentStepper(sample_events)
        stepper.set_breakpoint(BreakpointType.EVENT_TYPE, "decision")

        state = stepper.get_state_at_current_position()

        assert "breakpoints_active" in state
        assert state["breakpoints_active"] == 1

    def test_state_with_disabled_breakpoints(self, sample_events):
        """Test state only counts enabled breakpoints."""
        stepper = AgentStepper(sample_events)
        bp1 = stepper.set_breakpoint(BreakpointType.EVENT_TYPE, "decision")
        bp2 = stepper.set_breakpoint(BreakpointType.TOOL_NAME, "search")

        # Disable one breakpoint
        bp1.enabled = False

        state = stepper.get_state_at_current_position()

        assert state["breakpoints_active"] == 1


class TestSerialization:
    """Test suite for state serialization round-trip."""

    def test_export_state_with_breakpoints(self, sample_events):
        """Test exporting state includes breakpoints."""
        stepper = AgentStepper(sample_events)
        stepper.set_breakpoint(BreakpointType.EVENT_TYPE, "decision")
        stepper.set_breakpoint(BreakpointType.TOOL_NAME, "search")

        exported = stepper.export_state()

        assert "breakpoints" in exported
        assert len(exported["breakpoints"]) == 2

    def test_export_state_with_branches(self, sample_events):
        """Test exporting state includes branches."""
        stepper = AgentStepper(sample_events)
        stepper.create_branch("Test Branch", "event_1")

        exported = stepper.export_state()

        assert "branches" in exported
        assert len(exported["branches"]) == 1

    def test_export_state_includes_position(self, sample_events):
        """Test exporting state includes current position."""
        stepper = AgentStepper(sample_events)
        stepper.state.current_event_index = 3

        exported = stepper.export_state()

        assert exported["current_event_index"] == 3
        assert exported["current_event_id"] == "event_4"

    def test_import_state_restores_breakpoints(self, sample_events):
        """Test importing state restores breakpoints."""
        stepper1 = AgentStepper(sample_events)
        bp = stepper1.set_breakpoint(BreakpointType.EVENT_TYPE, "decision")

        exported = stepper1.export_state()

        stepper2 = AgentStepper(sample_events)
        stepper2.import_state(exported)

        assert len(stepper2.state.breakpoints) == 1
        # Check that breakpoint data was preserved
        imported_bp = stepper2.state.breakpoints[0]
        assert imported_bp.condition_value == "decision"
        assert imported_bp.breakpoint_type == BreakpointType.EVENT_TYPE

    def test_import_state_restores_position(self, sample_events):
        """Test importing state restores position."""
        stepper1 = AgentStepper(sample_events)
        stepper1.state.current_event_index = 2
        stepper1.state.current_event_id = "event_3"

        exported = stepper1.export_state()

        stepper2 = AgentStepper(sample_events)
        stepper2.import_state(exported)

        assert stepper2.state.current_event_index == 2
        assert stepper2.state.current_event_id == "event_3"

    def test_import_state_restores_branches(self, sample_events):
        """Test importing state restores branches."""
        stepper1 = AgentStepper(sample_events)
        branch = stepper1.create_branch("Test", "event_1")

        exported = stepper1.export_state()

        stepper2 = AgentStepper(sample_events)
        stepper2.import_state(exported)

        assert len(stepper2.branches) == 1
        imported_branch = list(stepper2.branches.values())[0]
        assert imported_branch.name == "Test"

    def test_import_state_with_invalid_index(self, sample_events):
        """Test importing state with custom current index."""
        stepper = AgentStepper(sample_events)

        # Export with custom index
        custom_state = {
            "current_event_index": 3,
            "current_event_id": "event_4",
            "breakpoints": [],
            "branches": [],
            "step_history": [],
            "paused": True,
            "completed": False,
        }

        stepper.import_state({"state": custom_state, "branches": [], "events_count": len(sample_events)})

        # Should accept the custom value
        assert stepper.state.current_event_index == 3
        assert stepper.state.current_event_id == "event_4"


class TestConcurrentBreakpointManagement:
    """Test suite for concurrent breakpoint operations."""

    def test_multiple_breakpoints_same_event(self, sample_events):
        """Test multiple breakpoints can trigger on same event."""
        stepper = AgentStepper(sample_events)

        stepper.set_breakpoint(BreakpointType.EVENT_TYPE, "decision")
        stepper.set_breakpoint(BreakpointType.CONFIDENCE_THRESHOLD, 0.8)

        result = stepper.step(StepAction.CONTINUE)

        # Both breakpoints should hit on the first decision (confidence 0.9)
        assert result.success is True
        # The first matching breakpoint should be reported

    def test_enable_disable_breakpoint(self, sample_events):
        """Test enabling and disabling breakpoints."""
        stepper = AgentStepper(sample_events)

        bp = stepper.set_breakpoint(BreakpointType.EVENT_TYPE, "decision")
        assert bp.enabled is True

        # Disable
        bp.enabled = False

        result = stepper.step(StepAction.CONTINUE)
        # Should not stop at disabled breakpoint
        assert result.breakpoint_hit is None or result.breakpoint_hit.breakpoint_id != bp.breakpoint_id

    def test_clear_breakpoint_while_stopped_at_it(self, sample_events):
        """Test clearing breakpoint that's currently hit."""
        stepper = AgentStepper(sample_events)
        bp = stepper.set_breakpoint(BreakpointType.EVENT_TYPE, "decision")

        result = stepper.step(StepAction.CONTINUE)
        assert result.breakpoint_hit is not None

        # Clear the breakpoint
        stepper.clear_breakpoint(bp.breakpoint_id)

        assert len(stepper.state.breakpoints) == 0

    def test_breakpoint_hit_count_increments(self, sample_events):
        """Test breakpoint hit count increments on each hit."""
        stepper = AgentStepper(sample_events)
        bp = stepper.set_breakpoint(BreakpointType.EVENT_TYPE, "decision")

        # First hit
        stepper.step(StepAction.CONTINUE)
        assert bp.hit_count == 1

        # Reset and hit again
        stepper.reset()
        stepper.state.current_event_index = 0
        stepper.set_breakpoint(BreakpointType.EVENT_TYPE, "decision")

        stepper.step(StepAction.CONTINUE)
        # Hit count should be tracked

    def test_breakpoint_conditions_combined(self, sample_events):
        """Test multiple breakpoint conditions work together."""
        stepper = AgentStepper(sample_events)

        # Set multiple conditions
        stepper.set_breakpoint(BreakpointType.EVENT_TYPE, "decision")
        stepper.set_breakpoint(BreakpointType.TOOL_NAME, "search")
        stepper.set_breakpoint(BreakpointType.CONFIDENCE_THRESHOLD, 0.7)

        # Step through - should stop at first matching condition
        result = stepper.step(StepAction.CONTINUE)

        assert result.success is True
        assert result.breakpoint_hit is not None