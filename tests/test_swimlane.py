"""Tests for multi-agent swimlane debugger."""

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import (
    DecisionEvent,
    EventType,
    ToolCallEvent,
    ToolResultEvent,
    TraceEvent,
)
from agent_debugger_sdk.core.swimlane import (
    CoordinationAnalyzer,
    CoordinationIssue,
    EmergentBehaviorDetector,
    EmergentBehaviorType,
    MessageFlow,
    MessageFlowType,
    MultiAgentSession,
    SwimlaneLane,
    analyze_multi_agent_session,
    detect_coordination_issues,
    detect_emergent_behaviors,
    get_message_flows,
    get_swimlane_data,
)


@pytest.fixture
def sample_multi_agent_events():
    """Create sample events for multi-agent session."""
    session_id = "test_session_1"
    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    events = []

    # Agent 1 events
    events.append(
        ToolCallEvent(
            id="tool_1",
            session_id=session_id,
            timestamp=base_time,
            event_type=EventType.TOOL_CALL,
            parent_id=None,
            name="Agent 1 calls Agent 2",
            data={"agent_id": "agent_1"},
            metadata={},
            importance=0.5,
            upstream_event_ids=[],
            tool_name="delegate_to_agent_2",
            arguments={"task": "analyze_data"},
        )
    )

    events.append(
        DecisionEvent(
            id="decision_1",
            session_id=session_id,
            timestamp=base_time.replace(second=1),
            event_type=EventType.DECISION,
            parent_id=None,
            name="Agent 1 decision",
            data={"agent_id": "agent_1"},
            metadata={},
            importance=0.7,
            upstream_event_ids=[],
            reasoning="Deciding to delegate task to Agent 2",
            confidence=0.8,
        )
    )

    # Agent 2 events
    events.append(
        ToolResultEvent(
            id="tool_result_1",
            session_id=session_id,
            timestamp=base_time.replace(second=2),
            event_type=EventType.TOOL_RESULT,
            parent_id="tool_1",
            name="Agent 2 responds",
            data={"agent_id": "agent_2"},
            metadata={},
            importance=0.5,
            upstream_event_ids=["tool_1"],
            tool_name="delegate_to_agent_2",
            result={"status": "completed"},
        )
    )

    events.append(
        DecisionEvent(
            id="decision_2",
            session_id=session_id,
            timestamp=base_time.replace(second=3),
            event_type=EventType.DECISION,
            parent_id=None,
            name="Agent 2 decision",
            data={"agent_id": "agent_2"},
            metadata={},
            importance=0.6,
            upstream_event_ids=[],
            reasoning="Collaborating with Agent 1 on the task",
            confidence=0.9,
        )
    )

    # Agent 3 events
    events.append(
        ToolCallEvent(
            id="tool_2",
            session_id=session_id,
            timestamp=base_time.replace(second=4),
            event_type=EventType.TOOL_CALL,
            parent_id=None,
            name="Agent 3 broadcasts",
            data={"agent_id": "agent_3"},
            metadata={},
            importance=0.5,
            upstream_event_ids=[],
            tool_name="broadcast_update",
            arguments={"message": "task_complete"},
        )
    )

    return events


def test_swimlane_lane_creation():
    """Test creating a swimlane lane."""
    lane = SwimlaneLane(agent_id="agent_1", agent_name="Agent 1")

    assert lane.agent_id == "agent_1"
    assert lane.agent_name == "Agent 1"
    assert lane.get_event_count() == 0
    assert lane.get_duration_seconds() == 0.0


def test_swimlane_lane_add_event():
    """Test adding events to a lane."""
    lane = SwimlaneLane(agent_id="agent_1", agent_name="Agent 1")

    event = TraceEvent(
        id="event_1",
        session_id="session_1",
        timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        event_type=EventType.DECISION,
        parent_id=None,
        name="Test Event",
        data={},
        metadata={},
        importance=0.5,
        upstream_event_ids=[],
    )

    lane.add_event(event)

    assert lane.get_event_count() == 1
    assert len(lane.events) == 1
    assert lane.start_time is not None
    assert lane.end_time is not None


def test_message_flow_creation():
    """Test creating a message flow."""
    flow = MessageFlow(
        from_agent_id="agent_1",
        to_agent_id="agent_2",
        flow_type=MessageFlowType.REQUEST,
        description="Agent 1 requests action from Agent 2",
    )

    assert flow.from_agent_id == "agent_1"
    assert flow.to_agent_id == "agent_2"
    assert flow.flow_type == MessageFlowType.REQUEST
    assert len(flow.flow_id) > 0  # UUID should be generated


def test_multi_agent_session_creation():
    """Test creating a multi-agent session."""
    session = MultiAgentSession(session_id="session_1")

    assert session.session_id == "session_1"
    assert session.get_agent_count() == 0
    assert session.get_total_event_count() == 0


def test_analyze_multi_agent_session(sample_multi_agent_events):
    """Test analyzing a multi-agent session."""
    session = analyze_multi_agent_session(sample_multi_agent_events)

    assert session.session_id == "test_session_1"
    assert session.get_agent_count() >= 2  # Should have multiple agents
    assert session.get_total_event_count() == len(sample_multi_agent_events)
    assert session.get_duration_seconds() > 0


def test_get_swimlane_data(sample_multi_agent_events):
    """Test getting swimlane visualization data."""
    data = get_swimlane_data("test_session_1", sample_multi_agent_events)

    assert data["session_id"] == "test_session_1"
    assert "lanes" in data
    assert len(data["lanes"]) >= 2
    assert data["total_event_count"] == len(sample_multi_agent_events)


def test_get_message_flows(sample_multi_agent_events):
    """Test getting message flows between agents."""
    flows = get_message_flows("test_session_1", sample_multi_agent_events)

    assert isinstance(flows, list)
    # Should have at least one message flow (from tool calls)
    assert len(flows) >= 1


def test_coordination_analyzer_no_issues():
    """Test coordination analyzer with no issues."""
    session = MultiAgentSession(session_id="test_session")

    # Add simple lane without issues
    lane = SwimlaneLane(agent_id="agent_1", agent_name="Agent 1")
    session.lanes["agent_1"] = lane

    analyzer = CoordinationAnalyzer(session)
    issues = analyzer.analyze()

    assert len(issues) == 0


def test_coordination_analyzer_detects_deadlock():
    """Test coordination analyzer detects deadlocks."""
    session = MultiAgentSession(session_id="test_session")

    # Create lanes that wait on each other
    lane1 = SwimlaneLane(agent_id="agent_1", agent_name="Agent 1")
    lane2 = SwimlaneLane(agent_id="agent_2", agent_name="Agent 2")

    # Add events that create circular dependency
    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    tool_1 = ToolCallEvent(
        id="tool_1",
        session_id="test_session",
        timestamp=base_time,
        event_type=EventType.TOOL_CALL,
        parent_id=None,
        name="Agent 1 calls Agent 2",
        data={"target_agent": "agent_2"},
        metadata={},
        importance=0.5,
        upstream_event_ids=[],
        tool_name="request_agent_2",
        arguments={},
    )

    tool_2 = ToolCallEvent(
        id="tool_2",
        session_id="test_session",
        timestamp=base_time.replace(second=1),
        event_type=EventType.TOOL_CALL,
        parent_id=None,
        name="Agent 2 calls Agent 1",
        data={"target_agent": "agent_1"},
        metadata={},
        importance=0.5,
        upstream_event_ids=[],
        tool_name="request_agent_1",
        arguments={},
    )

    lane1.add_event(tool_1)
    lane2.add_event(tool_2)

    session.lanes["agent_1"] = lane1
    session.lanes["agent_2"] = lane2

    analyzer = CoordinationAnalyzer(session)
    issues = analyzer.analyze()

    # Should detect deadlock
    deadlock_issues = [i for i in issues if i.issue_type == CoordinationIssue.DEADLOCK]
    assert len(deadlock_issues) >= 1


def test_emergent_behavior_detector_no_behaviors():
    """Test emergent behavior detector with no behaviors."""
    session = MultiAgentSession(session_id="test_session")

    lane = SwimlaneLane(agent_id="agent_1", agent_name="Agent 1")
    session.lanes["agent_1"] = lane

    detector = EmergentBehaviorDetector(session)
    behaviors = detector.detect()

    assert len(behaviors) == 0


def test_emergent_behavior_detector_collaboration():
    """Test emergent behavior detector finds collaborative problem solving."""
    session = MultiAgentSession(session_id="test_session")

    # Create multiple agents with collaborative patterns
    for i in range(3):
        lane = SwimlaneLane(agent_id=f"agent_{i}", agent_name=f"Agent {i}")

        # Add decision events that reference other agents
        for j in range(3):
            event = DecisionEvent(
                id=f"decision_{i}_{j}",
                session_id="test_session",
                timestamp=datetime(2024, 1, 1, 12, 0, j, tzinfo=timezone.utc),
                event_type=EventType.DECISION,
                parent_id=None,
                name=f"Agent {i} decision {j}",
                data={
                    "agent_id": f"agent_{i}",
                    "referenced_agents": [f"agent_{(i+1)%3}"],
                },
                metadata={},
                importance=0.7,
                upstream_event_ids=[],
                reasoning=f"Building on work from Agent {(i+1)%3}",
                confidence=0.8,
            )
            lane.add_event(event)

        session.lanes[f"agent_{i}"] = lane

    detector = EmergentBehaviorDetector(session)
    behaviors = detector.detect()

    # Should detect collaborative problem solving
    collab_behaviors = [
        b for b in behaviors
        if b.behavior_type == EmergentBehaviorType.COLLABORATIVE_PROBLEM_SOLVING
    ]
    assert len(collab_behaviors) >= 1


def test_detect_coordination_issues(sample_multi_agent_events):
    """Test detecting coordination issues in a session."""
    session = analyze_multi_agent_session(sample_multi_agent_events)
    issues = detect_coordination_issues(session)

    # Should return a list (may be empty if no issues)
    assert isinstance(issues, list)


def test_detect_emergent_behaviors(sample_multi_agent_events):
    """Test detecting emergent behaviors in a session."""
    session = analyze_multi_agent_session(sample_multi_agent_events)
    behaviors = detect_emergent_behaviors(session)

    # Should return a list (may be empty if no behaviors)
    assert isinstance(behaviors, list)


def test_swimlane_lane_to_dict():
    """Test serializing swimlane lane to dict."""
    lane = SwimlaneLane(agent_id="agent_1", agent_name="Agent 1")

    event = TraceEvent(
        id="event_1",
        session_id="session_1",
        timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        event_type=EventType.DECISION,
        parent_id=None,
        name="Test Event",
        data={},
        metadata={},
        importance=0.5,
        upstream_event_ids=[],
    )

    lane.add_event(event)

    lane_dict = lane.to_dict()

    assert lane_dict["agent_id"] == "agent_1"
    assert lane_dict["agent_name"] == "Agent 1"
    assert lane_dict["event_count"] == 1
    assert "events" in lane_dict
    assert "duration_seconds" in lane_dict


def test_message_flow_to_dict():
    """Test serializing message flow to dict."""
    flow = MessageFlow(
        from_agent_id="agent_1",
        to_agent_id="agent_2",
        flow_type=MessageFlowType.DELEGATION,
        description="Agent 1 delegates to Agent 2",
        timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )

    flow_dict = flow.to_dict()

    assert flow_dict["from_agent_id"] == "agent_1"
    assert flow_dict["to_agent_id"] == "agent_2"
    assert flow_dict["flow_type"] == "delegation"
    assert flow_dict["description"] == "Agent 1 delegates to Agent 2"


def test_multi_agent_session_to_dict(sample_multi_agent_events):
    """Test serializing multi-agent session to dict."""
    session = analyze_multi_agent_session(sample_multi_agent_events)
    session_dict = session.to_dict()

    assert session_dict["session_id"] == "test_session_1"
    assert "lanes" in session_dict
    assert "message_flows" in session_dict
    assert "agent_count" in session_dict
    assert "total_event_count" in session_dict