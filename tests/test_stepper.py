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