"""Multi-agent swimlane debugger with message flow tracing.

Provides primitives for visualizing and analyzing multi-agent sessions
as horizontal swimlanes with inter-agent communication flows, coordination
analysis, and emergent behavior detection.
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
    "MessageFlowType",
    "CoordinationIssue",
    "CoordinationSeverity",
    "EmergentBehaviorType",
    "SwimlaneLane",
    "MessageFlow",
    "CoordinationIssue",
    "EmergentBehavior",
    "MultiAgentSession",
    "CoordinationAnalyzer",
    "EmergentBehaviorDetector",
    "analyze_multi_agent_session",
    "detect_coordination_issues",
    "detect_emergent_behaviors",
    "get_swimlane_data",
    "get_message_flows",
]


class MessageFlowType(StrEnum):
    """Types of message flows between agents."""

    REQUEST = "request"  # One agent requesting action from another
    RESPONSE = "response"  # Response to a request
    NOTIFICATION = "notification"  # One-way information sharing
    SYNCHRONIZATION = "synchronization"  # Coordination message
    BROADCAST = "broadcast"  # Message to all agents
    DELEGATION = "delegation"  # Task delegation


class CoordinationIssue(StrEnum):
    """Types of coordination issues in multi-agent systems."""

    DEADLOCK = "deadlock"  # Agents waiting on each other
    RACE_CONDITION = "race_condition"  # Timing-based conflicts
    COMMUNICATION_GAP = "communication_gap"  # Missing expected messages
    CIRCULAR_DEPENDENCY = "circular_dependency"  # Circular waiting pattern
    RESOURCE_CONFLICT = "resource_conflict"  # Competing for shared resources
    INCONSISTENT_STATE = "inconsistent_state"  # State divergence between agents
    TIMEOUT = "timeout"  # Agent not responding


class CoordinationSeverity(StrEnum):
    """Severity levels for coordination issues."""

    CRITICAL = "critical"  # System blocked or failed
    HIGH = "high"  # Significant coordination problem
    MEDIUM = "medium"  # Moderate coordination issue
    LOW = "low"  # Minor coordination problem


class EmergentBehaviorType(StrEnum):
    """Types of emergent behaviors in multi-agent systems."""

    COLLABORATIVE_PROBLEM_SOLVING = "collaborative_problem_solving"
    EMERGENT_HIERARCHY = "emergent_hierarchy"  # Leadership patterns
    SWARM_INTELLIGENCE = "swarm_intelligence"  # Collective behavior
    ADAPTIVE_SPECIALIZATION = "adaptive_specialization"  # Role adaptation
    CONSENSUS_BUILDING = "consensus_building"  # Agreement formation
    EMERGENT_WORKFLOW = "emergent_workflow"  # Process emergence
    SELF_ORGANIZATION = "self_organization"  # Autonomous structuring


@dataclass(kw_only=True)
class SwimlaneLane:
    """Represents a single agent's actions in temporal order.

    Attributes:
        agent_id: Unique identifier for the agent
        agent_name: Human-readable agent name
        events: Ordered list of events for this agent
        start_time: When this agent started activity
        end_time: When this agent ended activity
        color: Color for visualization
        metadata: Additional agent information
    """

    agent_id: str
    agent_name: str
    events: list[TraceEvent] = field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None
    color: str = "#3b82f6"  # Default blue
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_event(self, event: TraceEvent) -> None:
        """Add an event to this lane."""
        self.events.append(event)
        # Update time bounds
        if event.timestamp:
            if self.start_time is None or event.timestamp < self.start_time:
                self.start_time = event.timestamp
            if self.end_time is None or event.timestamp > self.end_time:
                self.end_time = event.timestamp

    def get_event_count(self) -> int:
        """Get total number of events in this lane."""
        return len(self.events)

    def get_duration_seconds(self) -> float:
        """Get duration of this lane's activity in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "events": [e.id for e in self.events],  # Only event IDs for serialization
            "event_count": len(self.events),
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.get_duration_seconds(),
            "color": self.color,
            "metadata": dict(self.metadata),
        }


@dataclass(kw_only=True)
class MessageFlow:
    """Represents communication between agents.

    Attributes:
        flow_id: Unique identifier for this flow
        from_agent_id: Source agent
        to_agent_id: Destination agent
        flow_type: Type of message flow
        event_id: Event that triggered this flow
        timestamp: When this flow occurred
        description: Human-readable description
        metadata: Additional flow information
    """

    flow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_agent_id: str = ""
    to_agent_id: str = ""
    flow_type: MessageFlowType = MessageFlowType.NOTIFICATION
    event_id: str = ""
    timestamp: datetime | None = None
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "flow_id": self.flow_id,
            "from_agent_id": self.from_agent_id,
            "to_agent_id": self.to_agent_id,
            "flow_type": str(self.flow_type),
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "description": self.description,
            "metadata": dict(self.metadata),
        }


@dataclass(kw_only=True)
class CoordinationIssue:
    """Represents a coordination issue detected in multi-agent interaction.

    Attributes:
        issue_id: Unique identifier for this issue
        issue_type: Type of coordination issue
        severity: Severity level
        involved_agents: List of agent IDs involved
        event_ids: Related events
        description: Human-readable description
        timestamp: When issue was detected
        suggestion: Suggested resolution
        metadata: Additional issue information
    """

    issue_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    issue_type: CoordinationIssue = CoordinationIssue.COMMUNICATION_GAP
    severity: CoordinationSeverity = CoordinationSeverity.MEDIUM
    involved_agents: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    description: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    suggestion: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "issue_id": self.issue_id,
            "issue_type": str(self.issue_type),
            "severity": str(self.severity),
            "involved_agents": list(self.involved_agents),
            "event_ids": list(self.event_ids),
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
            "suggestion": self.suggestion,
            "metadata": dict(self.metadata),
        }


@dataclass(kw_only=True)
class EmergentBehavior:
    """Represents emergent behavior from agent interactions.

    Attributes:
        behavior_id: Unique identifier for this behavior
        behavior_type: Type of emergent behavior
        confidence: How confident we are this is emergent (0.0-1.0)
        involved_agents: List of agent IDs involved
        event_ids: Related events
        description: Human-readable description
        timestamp: When behavior was detected
        pattern_description: Description of the interaction pattern
        metadata: Additional behavior information
    """

    behavior_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    behavior_type: EmergentBehaviorType = EmergentBehaviorType.COLLABORATIVE_PROBLEM_SOLVING
    confidence: float = 0.5
    involved_agents: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    description: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    pattern_description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "behavior_id": self.behavior_id,
            "behavior_type": str(self.behavior_type),
            "confidence": self.confidence,
            "involved_agents": list(self.involved_agents),
            "event_ids": list(self.event_ids),
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
            "pattern_description": self.pattern_description,
            "metadata": dict(self.metadata),
        }


@dataclass(kw_only=True)
class MultiAgentSession:
    """Represents a multi-agent session with swimlane visualization.

    Attributes:
        session_id: Unique session identifier
        lanes: Agent swimlanes
        message_flows: Inter-agent communications
        start_time: Session start
        end_time: Session end
        coordination_issues: Detected coordination problems
        emergent_behaviors: Detected emergent behaviors
        metadata: Additional session information
    """

    session_id: str = ""
    lanes: dict[str, SwimlaneLane] = field(default_factory=dict)
    message_flows: list[MessageFlow] = field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None
    coordination_issues: list[CoordinationIssue] = field(default_factory=list)
    emergent_behaviors: list[EmergentBehavior] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_event(self, event: TraceEvent) -> None:
        """Add an event to the appropriate lane."""
        agent_id = _extract_agent_id(event)
        if not agent_id:
            return

        if agent_id not in self.lanes:
            agent_name = _extract_agent_name(event) or agent_id
            self.lanes[agent_id] = SwimlaneLane(
                agent_id=agent_id,
                agent_name=agent_name,
            )

        self.lanes[agent_id].add_event(event)

        # Update session time bounds
        if event.timestamp:
            if self.start_time is None or event.timestamp < self.start_time:
                self.start_time = event.timestamp
            if self.end_time is None or event.timestamp > self.end_time:
                self.end_time = event.timestamp

    def get_agent_count(self) -> int:
        """Get number of agents in this session."""
        return len(self.lanes)

    def get_total_event_count(self) -> int:
        """Get total number of events across all lanes."""
        return sum(lane.get_event_count() for lane in self.lanes.values())

    def get_duration_seconds(self) -> float:
        """Get session duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "session_id": self.session_id,
            "lanes": {agent_id: lane.to_dict() for agent_id, lane in self.lanes.items()},
            "message_flows": [flow.to_dict() for flow in self.message_flows],
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.get_duration_seconds(),
            "agent_count": self.get_agent_count(),
            "total_event_count": self.get_total_event_count(),
            "coordination_issues": [issue.to_dict() for issue in self.coordination_issues],
            "emergent_behaviors": [behavior.to_dict() for behavior in self.emergent_behaviors],
            "metadata": dict(self.metadata),
        }


class CoordinationAnalyzer:
    """Analyzer for detecting coordination issues in multi-agent sessions."""

    def __init__(self, session: MultiAgentSession) -> None:
        """Initialize the analyzer.

        Args:
            session: Multi-agent session to analyze
        """
        self.session = session
        self.issues: list[CoordinationIssue] = []

    def analyze(self) -> list[CoordinationIssue]:
        """Run full coordination analysis.

        Returns:
            List of detected coordination issues
        """
        self.issues = []
        self._detect_deadlocks()
        self._detect_communication_gaps()
        self._detect_circular_dependencies()
        self._detect_resource_conflicts()
        self._detect_timeouts()
        self._detect_state_inconsistencies()

        self.session.coordination_issues = self.issues
        return self.issues

    def _detect_deadlocks(self) -> None:
        """Detect deadlock patterns where agents wait on each other."""
        # Look for circular waiting patterns
        agent_wait_graph: dict[str, set[str]] = {}

        for lane in self.session.lanes.values():
            waiting_for = set()
            for event in lane.events:
                # Check if agent is waiting for response from another agent
                if event.event_type == EventType.TOOL_CALL:
                    target_agent = _extract_target_agent(event)
                    if target_agent and target_agent in self.session.lanes:
                        waiting_for.add(target_agent)

            if waiting_for:
                agent_wait_graph[lane.agent_id] = waiting_for

        # Detect cycles
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def has_cycle(agent_id: str) -> bool:
            visited.add(agent_id)
            rec_stack.add(agent_id)

            neighbors = agent_wait_graph.get(agent_id, set())
            for neighbor in neighbors:
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(agent_id)
            return False

        for agent_id in self.session.lanes:
            if agent_id not in visited:
                if has_cycle(agent_id):
                    # Found deadlock
                    involved = list(agent_wait_graph.keys())
                    issue = CoordinationIssue(
                        issue_type=CoordinationIssue.DEADLOCK,
                        severity=CoordinationSeverity.CRITICAL,
                        involved_agents=involved,
                        description=f"Deadlock detected among agents: {', '.join(involved)}",
                        suggestion="Break circular dependencies by introducing timeout or mediator",
                    )
                    self.issues.append(issue)

    def _detect_communication_gaps(self) -> None:
        """Detect missing expected communications between agents."""
        # Look for request events without corresponding responses
        pending_requests: dict[str, list[TraceEvent]] = {}

        for lane in self.session.lanes.values():
            for event in lane.events:
                if event.event_type == EventType.TOOL_CALL:
                    target_agent = _extract_target_agent(event)
                    if target_agent and target_agent in self.session.lanes:
                        # Check if there's a response
                        if not _has_response(event, self.session.lanes[target_agent].events):
                            pending_requests.setdefault(target_agent, []).append(event)

        for agent_id, requests in pending_requests.items():
            if len(requests) > 2:  # Threshold for gap detection
                issue = CoordinationIssue(
                    issue_type=CoordinationIssue.COMMUNICATION_GAP,
                    severity=CoordinationSeverity.HIGH,
                    involved_agents=[agent_id],
                    event_ids=[r.id for r in requests],
                    description=f"Agent {agent_id} has {len(requests)} unanswered requests",
                    suggestion="Check if target agent is properly handling requests",
                )
                self.issues.append(issue)

    def _detect_circular_dependencies(self) -> None:
        """Detect circular dependency patterns in agent interactions."""
        # Similar to deadlock but for task dependencies
        agent_deps: dict[str, set[str]] = {}

        for lane in self.session.lanes.values():
            dependencies = set()
            for event in lane.events:
                # Look for delegation patterns
                if event.event_type == EventType.DECISION:
                    delegated_to = _extract_delegated_agent(event)
                    if delegated_to and delegated_to in self.session.lanes:
                        dependencies.add(delegated_to)

            if dependencies:
                agent_deps[lane.agent_id] = dependencies

        # Detect cycles
        for agent_id in agent_deps:
            visited_in_path = set()
            current = agent_id

            while current in agent_deps and current not in visited_in_path:
                visited_in_path.add(current)
                next_deps = agent_deps[current]
                if agent_id in next_deps:
                    # Found circular dependency
                    involved = list(visited_in_path)
                    issue = CoordinationIssue(
                        issue_type=CoordinationIssue.CIRCULAR_DEPENDENCY,
                        severity=CoordinationSeverity.MEDIUM,
                        involved_agents=involved,
                        description=f"Circular dependency detected: {' -> '.join(involved)} -> {agent_id}",
                        suggestion="Introduce clear task ownership or break dependency cycle",
                    )
                    self.issues.append(issue)
                    break
                current = next(iter(next_deps)) if next_deps else ""

    def _detect_resource_conflicts(self) -> None:
        """Detect conflicts over shared resources."""
        # Look for agents competing for same resources
        resource_usage: dict[str, list[str]] = {}

        for lane in self.session.lanes.values():
            for event in lane.events:
                resource = _extract_resource_accessed(event)
                if resource:
                    resource_usage.setdefault(resource, []).append(lane.agent_id)

        for resource, agents in resource_usage.items():
            if len(agents) > 1:
                # Multiple agents accessing same resource
                issue = CoordinationIssue(
                    issue_type=CoordinationIssue.RESOURCE_CONFLICT,
                    severity=CoordinationSeverity.MEDIUM,
                    involved_agents=agents,
                    description=f"Multiple agents accessing resource: {resource}",
                    suggestion="Implement resource locking or coordination protocol",
                )
                self.issues.append(issue)

    def _detect_timeouts(self) -> None:
        """Detect timeout situations where agents don't respond."""
        TIMEOUT_THRESHOLD_SECONDS = 30.0

        for lane in self.session.lanes.values():
            for i, event in enumerate(lane.events):
                if event.event_type == EventType.TOOL_CALL:
                    target_agent = _extract_target_agent(event)
                    if target_agent and target_agent in self.session.lanes:
                        # Check if response came within threshold
                        response_time = _find_response_time(event, self.session.lanes[target_agent].events)
                        if response_time and response_time > TIMEOUT_THRESHOLD_SECONDS:
                            issue = CoordinationIssue(
                                issue_type=CoordinationIssue.TIMEOUT,
                                severity=CoordinationSeverity.HIGH,
                                involved_agents=[lane.agent_id, target_agent],
                                event_ids=[event.id],
                                description=f"Response from {target_agent} took {response_time:.1f}s (> {TIMEOUT_THRESHOLD_SECONDS}s threshold)",
                                suggestion="Investigate why agent is slow to respond or consider timeout",
                            )
                            self.issues.append(issue)

    def _detect_state_inconsistencies(self) -> None:
        """Detect inconsistencies in agent states."""
        # Look for checkpoint events with conflicting states
        agent_states: dict[str, dict[str, Any]] = {}

        for lane in self.session.lanes.values():
            for event in lane.events:
                if event.event_type == EventType.CHECKPOINT:
                    state = getattr(event, "state", None) or event.data.get("state", {})
                    if isinstance(state, dict):
                        # Compare with other agents' states
                        for other_agent, other_state in agent_states.items():
                            if other_agent != lane.agent_id:
                                conflicts = _compare_states(state, other_state)
                                if conflicts:
                                    issue = CoordinationIssue(
                                        issue_type=CoordinationIssue.INCONSISTENT_STATE,
                                        severity=CoordinationSeverity.MEDIUM,
                                        involved_agents=[lane.agent_id, other_agent],
                                        event_ids=[event.id],
                                        description=f"State inconsistency: {', '.join(conflicts)}",
                                        suggestion="Ensure state synchronization protocol is working",
                                    )
                                    self.issues.append(issue)

                        agent_states[lane.agent_id] = state


class EmergentBehaviorDetector:
    """Detector for emergent behaviors in multi-agent systems."""

    def __init__(self, session: MultiAgentSession) -> None:
        """Initialize the detector.

        Args:
            session: Multi-agent session to analyze
        """
        self.session = session
        self.behaviors: list[EmergentBehavior] = []

    def detect(self) -> list[EmergentBehavior]:
        """Run full emergent behavior detection.

        Returns:
            List of detected emergent behaviors
        """
        self.behaviors = []
        self._detect_collaborative_problem_solving()
        self._detect_emergent_hierarchy()
        self._detect_swarm_intelligence()
        self._detect_adaptive_specialization()
        self._detect_consensus_building()
        self._detect_emergent_workflow()
        self._detect_self_organization()

        self.session.emergent_behaviors = self.behaviors
        return self.behaviors

    def _detect_collaborative_problem_solving(self) -> None:
        """Detect collaborative problem solving patterns."""
        # Look for agents building on each other's work
        collaboration_sequences: list[list[str]] = []

        for lane in self.session.lanes.values():
            sequence = []
            for event in lane.events:
                if event.event_type == EventType.DECISION:
                    # Check if decision builds on other agent's work
                    referenced_agents = _extract_referenced_agents(event)
                    if referenced_agents:
                        sequence.extend(referenced_agents)

            if len(sequence) >= 3:
                collaboration_sequences.append(sequence)

        if collaboration_sequences:
            behavior = EmergentBehavior(
                behavior_type=EmergentBehaviorType.COLLABORATIVE_PROBLEM_SOLVING,
                confidence=0.7,
                involved_agents=list(self.session.lanes.keys()),
                description="Agents are building on each other's work to solve problems",
                pattern_description="Sequential decision-making with cross-references",
            )
            self.behaviors.append(behavior)

    def _detect_emergent_hierarchy(self) -> None:
        """Detect emergence of leadership/hierarchy patterns."""
        # Look for one agent directing others
        direction_counts: dict[str, int] = {}

        for lane in self.session.lanes.values():
            for event in lane.events:
                if event.event_type == EventType.DECISION:
                    directed_to = _extract_directed_agents(event)
                    for agent in directed_to:
                        direction_counts[lane.agent_id] = direction_counts.get(lane.agent_id, 0) + 1

        if direction_counts:
            # Find agent with most directions
            leader = max(direction_counts.items(), key=lambda x: x[1])
            if leader[1] > len(self.session.lanes) * 2:
                behavior = EmergentBehavior(
                    behavior_type=EmergentBehaviorType.EMERGENT_HIERARCHY,
                    confidence=0.6,
                    involved_agents=[leader[0]],
                    description=f"Agent {leader[0]} has emerged as leader",
                    pattern_description=f"{leader[1]} directional decisions from {leader[0]}",
                )
                self.behaviors.append(behavior)

    def _detect_swarm_intelligence(self) -> None:
        """Detect swarm intelligence patterns."""
        # Look for parallel exploration with information sharing
        parallel_activity = _detect_parallel_activity(self.session)

        if parallel_activity and len(parallel_activity) >= 3:
            behavior = EmergentBehavior(
                behavior_type=EmergentBehaviorType.SWARM_INTELLIGENCE,
                confidence=0.5,
                involved_agents=list(self.session.lanes.keys()),
                description="Multiple agents working in parallel with information sharing",
                pattern_description=f"{len(parallel_activity)} parallel activity streams detected",
            )
            self.behaviors.append(behavior)

    def _detect_adaptive_specialization(self) -> None:
        """Detect adaptive role specialization."""
        # Look for agents taking on specialized roles over time
        agent_specializations: dict[str, list[str]] = {}

        for lane in self.session.lanes.values():
            specializations = []
            for event in lane.events:
                role = _extract_agent_role(event)
                if role and role not in specializations:
                    specializations.append(role)

            if len(set(specializations)) > 1:
                agent_specializations[lane.agent_id] = specializations

        if agent_specializations:
            behavior = EmergentBehavior(
                behavior_type=EmergentBehaviorType.ADAPTIVE_SPECIALIZATION,
                confidence=0.6,
                involved_agents=list(agent_specializations.keys()),
                description="Agents are adapting and specializing in different roles",
                pattern_description=f"Role adaptation detected in {len(agent_specializations)} agents",
            )
            self.behaviors.append(behavior)

    def _detect_consensus_building(self) -> None:
        """Detect consensus building patterns."""
        # Look for iterative agreement formation
        consensus_rounds = 0

        for lane in self.session.lanes.values():
            for event in lane.events:
                if event.event_type == EventType.DECISION:
                    if _is_consensus_event(event):
                        consensus_rounds += 1

        if consensus_rounds >= 2:
            behavior = EmergentBehavior(
                behavior_type=EmergentBehaviorType.CONSENSUS_BUILDING,
                confidence=0.7,
                involved_agents=list(self.session.lanes.keys()),
                description="Agents are building consensus through iterative agreement",
                pattern_description=f"{consensus_rounds} consensus rounds detected",
            )
            self.behaviors.append(behavior)

    def _detect_emergent_workflow(self) -> None:
        """Detect emergence of structured workflows."""
        # Look for repeated patterns becoming workflow
        workflow_patterns = _detect_workflow_patterns(self.session)

        if workflow_patterns:
            behavior = EmergentBehavior(
                behavior_type=EmergentBehaviorType.EMERGENT_WORKFLOW,
                confidence=0.5,
                involved_agents=list(self.session.lanes.keys()),
                description="Structured workflow has emerged from agent interactions",
                pattern_description=f"{len(workflow_patterns)} distinct workflow patterns detected",
            )
            self.behaviors.append(behavior)

    def _detect_self_organization(self) -> None:
        """Detect self-organization patterns."""
        # Look for autonomous structuring without central coordination
        autonomous_decisions = 0

        for lane in self.session.lanes.values():
            for event in lane.events:
                if event.event_type == EventType.DECISION:
                    if _is_autonomous_decision(event):
                        autonomous_decisions += 1

        if autonomous_decisions >= len(self.session.lanes) * 2:
            behavior = EmergentBehavior(
                behavior_type=EmergentBehaviorType.SELF_ORGANIZATION,
                confidence=0.6,
                involved_agents=list(self.session.lanes.keys()),
                description="Agents are self-organizing without central coordination",
                pattern_description=f"{autonomous_decisions} autonomous decisions detected",
            )
            self.behaviors.append(behavior)


# =============================================================================
# High-level analysis functions
# =============================================================================


def analyze_multi_agent_session(events: list[TraceEvent]) -> MultiAgentSession:
    """Analyze a multi-agent session and create swimlane visualization.

    Args:
        events: List of events from the session

    Returns:
        MultiAgentSession with lanes and analysis
    """
    if not events:
        return MultiAgentSession(session_id="")

    session_id = events[0].session_id if events else ""
    multi_session = MultiAgentSession(session_id=session_id)

    # Sort events by timestamp
    sorted_events = sorted(events, key=lambda e: e.timestamp or datetime.min(timezone.utc))

    # Add events to appropriate lanes
    for event in sorted_events:
        multi_session.add_event(event)

    # Detect message flows
    multi_session.message_flows = _detect_message_flows(multi_session)

    return multi_session


def detect_coordination_issues(session: MultiAgentSession) -> list[CoordinationIssue]:
    """Detect coordination issues in a multi-agent session.

    Args:
        session: Multi-agent session to analyze

    Returns:
        List of detected coordination issues
    """
    analyzer = CoordinationAnalyzer(session)
    return analyzer.analyze()


def detect_emergent_behaviors(session: MultiAgentSession) -> list[EmergentBehavior]:
    """Detect emergent behaviors in a multi-agent session.

    Args:
        session: Multi-agent session to analyze

    Returns:
        List of detected emergent behaviors
    """
    detector = EmergentBehaviorDetector(session)
    return detector.detect()


def get_swimlane_data(session_id: str, events: list[TraceEvent]) -> dict[str, Any]:
    """Get swimlane visualization data for a session.

    Args:
        session_id: Session identifier
        events: List of events from the session

    Returns:
        Dictionary with swimlane data
    """
    session = analyze_multi_agent_session(events)
    session.session_id = session_id
    return session.to_dict()


def get_message_flows(session_id: str, events: list[TraceEvent]) -> list[dict[str, Any]]:
    """Get message flows between agents for a session.

    Args:
        session_id: Session identifier
        events: List of events from the session

    Returns:
        List of message flow dictionaries
    """
    session = analyze_multi_agent_session(events)
    return [flow.to_dict() for flow in session.message_flows]


# =============================================================================
# Internal helper functions
# =============================================================================


def _extract_agent_id(event: TraceEvent) -> str | None:
    """Extract agent ID from event."""
    # Try multiple sources for agent ID
    agent_id = (
        getattr(event, "agent_id", None)
        or event.data.get("agent_id")
        or getattr(event, "speaker", None)
        or event.data.get("speaker")
        or event.metadata.get("agent_id")
    )
    return agent_id


def _extract_agent_name(event: TraceEvent) -> str | None:
    """Extract agent name from event."""
    return (
        getattr(event, "agent_name", None)
        or event.data.get("agent_name")
        or getattr(event, "speaker", None)
    )


def _extract_target_agent(event: TraceEvent) -> str | None:
    """Extract target agent from tool call event."""
    tool_name = getattr(event, "tool_name", None) or event.data.get("tool_name")
    if tool_name:
        # Check if tool name contains agent reference
        for agent_id in ["agent", "bot", "worker", "specialist"]:
            if agent_id in tool_name.lower():
                return tool_name
    return event.data.get("target_agent")


def _extract_delegated_agent(event: TraceEvent) -> str | None:
    """Extract delegated agent from decision event."""
    return event.data.get("delegated_to") or event.data.get("assigned_agent")


def _extract_resource_accessed(event: TraceEvent) -> str | None:
    """Extract resource being accessed from event."""
    if event.event_type == EventType.TOOL_CALL:
        tool_name = getattr(event, "tool_name", None) or event.data.get("tool_name")
        return tool_name
    return event.data.get("resource")


def _extract_referenced_agents(event: TraceEvent) -> list[str]:
    """Extract agents referenced in decision event."""
    references = event.data.get("referenced_agents", [])
    if isinstance(references, list):
        return references
    if isinstance(references, str):
        return [references]
    return []


def _extract_directed_agents(event: TraceEvent) -> list[str]:
    """Extract agents being directed in decision event."""
    directed = event.data.get("directed_agents", [])
    if isinstance(directed, list):
        return directed
    if isinstance(directed, str):
        return [directed]
    return []


def _extract_agent_role(event: TraceEvent) -> str | None:
    """Extract agent role from event."""
    return event.data.get("role") or getattr(event, "role", None)


def _has_response(request_event: TraceEvent, target_events: list[TraceEvent]) -> bool:
    """Check if request has corresponding response."""
    request_time = request_event.timestamp
    if not request_time:
        return False

    for event in target_events:
        if event.timestamp and event.timestamp > request_time:
            # Check if this is a response to our request
            if event.event_type == EventType.TOOL_RESULT:
                if getattr(event, "tool_name", None) == getattr(request_event, "tool_name", None):
                    return True
            elif event.event_type == EventType.DECISION:
                # Check if decision references the request
                if request_event.id in event.data.get("evidence_event_ids", []):
                    return True

    return False


def _find_response_time(request_event: TraceEvent, target_events: list[TraceEvent]) -> float | None:
    """Find time to get response for request."""
    request_time = request_event.timestamp
    if not request_time:
        return None

    for event in target_events:
        if event.timestamp and event.timestamp > request_time:
            if event.event_type == EventType.TOOL_RESULT:
                if getattr(event, "tool_name", None) == getattr(request_event, "tool_name", None):
                    return (event.timestamp - request_time).total_seconds()

    return None


def _compare_states(state1: dict[str, Any], state2: dict[str, Any]) -> list[str]:
    """Compare two states and return conflicting keys."""
    conflicts = []
    all_keys = set(list(state1.keys()) + list(state2.keys()))

    for key in all_keys:
        val1 = state1.get(key)
        val2 = state2.get(key)
        if val1 != val2:
            conflicts.append(key)

    return conflicts


def _detect_message_flows(session: MultiAgentSession) -> list[MessageFlow]:
    """Detect message flows between agents."""
    flows: list[MessageFlow] = []

    for lane in session.lanes.values():
        for event in lane.events:
            if event.event_type == EventType.TOOL_CALL:
                target_agent = _extract_target_agent(event)
                if target_agent and target_agent in session.lanes:
                    # Determine flow type based on context
                    flow_type = _determine_flow_type(event)
                    flow = MessageFlow(
                        from_agent_id=lane.agent_id,
                        to_agent_id=target_agent,
                        flow_type=flow_type,
                        event_id=event.id,
                        timestamp=event.timestamp,
                        description=f"{lane.agent_name} -> {session.lanes[target_agent].agent_name}: {flow_type.value}",
                    )
                    flows.append(flow)

    return flows


def _determine_flow_type(event: TraceEvent) -> MessageFlowType:
    """Determine the type of message flow."""
    tool_name = getattr(event, "tool_name", "") or event.data.get("tool_name", "")
    tool_lower = tool_name.lower()

    if "delegate" in tool_lower or "assign" in tool_lower:
        return MessageFlowType.DELEGATION
    elif "broadcast" in tool_lower or "notify" in tool_lower:
        return MessageFlowType.BROADCAST
    elif "sync" in tool_lower or "coordinate" in tool_lower:
        return MessageFlowType.SYNCHRONIZATION
    elif "request" in tool_lower or "ask" in tool_lower:
        return MessageFlowType.REQUEST
    else:
        return MessageFlowType.NOTIFICATION


def _is_consensus_event(event: TraceEvent) -> bool:
    """Check if decision represents consensus building."""
    return "consensus" in str(getattr(event, "reasoning", "")).lower() or "agree" in str(getattr(event, "reasoning", "")).lower()


def _is_autonomous_decision(event: TraceEvent) -> bool:
    """Check if decision was made autonomously."""
    reasoning = str(getattr(event, "reasoning", "")).lower()
    return "autonomous" in reasoning or "self-directed" in reasoning or "independent" in reasoning


def _detect_parallel_activity(session: MultiAgentSession) -> list[list[str]]:
    """Detect parallel activity patterns."""
    # Group events by time windows
    time_windows: dict[str, list[str]] = {}
    WINDOW_SECONDS = 5.0

    for lane in session.lanes.values():
        for event in lane.events:
            if event.timestamp:
                window_key = event.timestamp.strftime("%Y%m%d%H%M%S")
                window_start = event.timestamp.timestamp()
                window_end = window_start + WINDOW_SECONDS

                # Find nearby events from other agents
                active_agents = set()
                for other_lane in session.lanes.values():
                    for other_event in other_lane.events:
                        if other_event.timestamp:
                            event_time = other_event.timestamp.timestamp()
                            if window_start <= event_time <= window_end:
                                active_agents.add(other_lane.agent_id)

                if len(active_agents) >= 2:
                    time_windows[window_key] = list(active_agents)

    # Return unique parallel activity patterns
    unique_patterns = []
    seen_patterns = set()

    for agents in time_windows.values():
        pattern_key = ",".join(sorted(agents))
        if pattern_key not in seen_patterns:
            seen_patterns.add(pattern_key)
            unique_patterns.append(agents)

    return unique_patterns


def _detect_workflow_patterns(session: MultiAgentSession) -> list[str]:
    """Detect repeated workflow patterns."""
    patterns = []

    # Look for repeated event sequences
    for lane in session.lanes.values():
        event_types = [str(e.event_type) for e in lane.events]
        # Simple pattern detection: look for repeated sequences of 3+
        for i in range(len(event_types) - 2):
            sequence = tuple(event_types[i:i+3])
            if sequence in event_types[i+3:]:
                patterns.append(f"{lane.agent_id}: {' -> '.join(sequence)}")

    return patterns[:5]  # Limit to 5 patterns


