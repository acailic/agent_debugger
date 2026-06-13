"""Causal tracer for root cause analysis of agent execution traces.

Based on AgentTrace methodology (arXiv:2603.14688, ICLR 2026 Workshop).
This module provides tools for building causal graphs from execution traces
and identifying root causes of failures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agent_debugger_sdk.core._compat import StrEnum
from agent_debugger_sdk.core.events import EventType, TraceEvent


class CausalRelationType(StrEnum):
    """Types of causal relationships between events."""

    DIRECT = "direct"  # Direct parent-child relationship
    TEMPORAL = "temporal"  # Time-based proximity
    DEPENDENCY = "dependency"  # Explicit upstream dependency
    FAILURE_PROPAGATION = "failure_propagation"  # Error propagates through chain
    STATE_DERIVATION = "state_derivation"  # State derived from previous state


@dataclass(kw_only=True)
class CausalNode:
    """A node in the causal graph representing a single event.

    Attributes:
        id: Unique identifier (same as event_id)
        event_type: The type of event this node represents
        timestamp: When the event occurred
        name: Event name/description
        parent_id: Parent event ID if any
        dependencies: List of event IDs this event depends on
        is_failure: Whether this event represents a failure
        failure_type: Type of failure if is_failure is True
        causal_depth: Depth in the causal chain (0 = root cause)
        metadata: Additional event metadata
    """

    id: str
    event_type: EventType
    timestamp: datetime
    name: str
    parent_id: str | None = None
    dependencies: list[str] = field(default_factory=list)
    is_failure: bool = False
    failure_type: str | None = None
    causal_depth: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "event_type": str(self.event_type),
            "timestamp": self.timestamp.isoformat(),
            "name": self.name,
            "parent_id": self.parent_id,
            "dependencies": list(self.dependencies),
            "is_failure": self.is_failure,
            "failure_type": self.failure_type,
            "causal_depth": self.causal_depth,
            "metadata": dict(self.metadata),
        }


@dataclass(kw_only=True)
class CausalEdge:
    """An edge in the causal graph representing a relationship between events.

    Attributes:
        from_node: Source event ID
        to_node: Target event ID
        relation_type: Type of causal relationship
        strength: Strength of causal relationship (0.0-1.0)
        evidence: Supporting evidence for this causal link
    """

    from_node: str
    to_node: str
    relation_type: CausalRelationType
    strength: float = 1.0
    evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "from_node": self.from_node,
            "to_node": self.to_node,
            "relation_type": str(self.relation_type),
            "strength": self.strength,
            "evidence": self.evidence,
        }


class CausalGraph:
    """Causal graph representation of agent execution trace.

    This class builds a directed graph from trace events and provides methods
    for analyzing causal relationships, tracing failures back to root causes,
    and identifying critical paths.
    """

    def __init__(self) -> None:
        """Initialize an empty causal graph."""
        self.nodes: dict[str, CausalNode] = {}
        self.edges: list[CausalEdge] = []
        self.root_cause_candidates: list[str] = []

    def build_from_events(self, events: list[TraceEvent]) -> None:
        """Build causal graph from a list of trace events.

        Args:
            events: List of trace events from a session
        """
        # Sort events by timestamp for processing order
        sorted_events = sorted(events, key=lambda e: e.timestamp)

        # Build nodes and identify failures
        for event in sorted_events:
            node = self._event_to_node(event)
            self.nodes[node.id] = node

        # Build edges based on relationships
        for event in sorted_events:
            self._build_edges_for_event(event, sorted_events)

        # Calculate causal depths and identify root causes
        self._calculate_causal_depths()
        self._identify_root_cause_candidates()

    def _event_to_node(self, event: TraceEvent) -> CausalNode:
        """Convert a TraceEvent to a CausalNode."""
        is_failure = self._is_failure_event(event)
        failure_type = None

        if is_failure:
            failure_type = self._classify_failure_type(event)

        return CausalNode(
            id=event.id,
            event_type=event.event_type,
            timestamp=event.timestamp,
            name=event.name or str(event.event_type),
            parent_id=event.parent_id,
            dependencies=list(event.upstream_event_ids or []),
            is_failure=is_failure,
            failure_type=failure_type,
            metadata=dict(event.metadata),
        )

    def _is_failure_event(self, event: TraceEvent) -> bool:
        """Determine if an event represents a failure."""
        # Explicit failure event types
        if event.event_type == EventType.ERROR:
            return True
        if event.event_type == EventType.REFUSAL:
            return True
        if event.event_type == EventType.POLICY_VIOLATION:
            return True
        if event.event_type == EventType.BEHAVIOR_ALERT:
            return True

        # Tool results with errors
        if event.event_type == EventType.TOOL_RESULT:
            # Check if there's an error in the event data
            error = event.data.get("error") or event.metadata.get("error")
            return error is not None

        # Safety checks that didn't pass
        if event.event_type == EventType.SAFETY_CHECK:
            outcome = event.data.get("outcome") or event.metadata.get("outcome")
            return outcome and outcome != "pass"

        return False

    def _classify_failure_type(self, event: TraceEvent) -> str:
        """Classify the type of failure for an event."""
        if event.event_type == EventType.ERROR:
            return "runtime_error"
        if event.event_type == EventType.REFUSAL:
            return "guardrail_block"
        if event.event_type == EventType.POLICY_VIOLATION:
            return "policy_violation"
        if event.event_type == EventType.BEHAVIOR_ALERT:
            alert_type = event.data.get("alert_type") or event.metadata.get("alert_type", "unknown")
            return f"behavior_alert_{alert_type}"
        if event.event_type == EventType.TOOL_RESULT:
            return "tool_execution_failure"
        if event.event_type == EventType.SAFETY_CHECK:
            return "safety_check_failure"
        return "unknown_failure"

    def _build_edges_for_event(self, event: TraceEvent, all_events: list[TraceEvent]) -> None:
        """Build causal edges for a given event."""
        if not event.id:
            return

        # Direct parent relationship
        if event.parent_id and event.parent_id in self.nodes:
            self.edges.append(CausalEdge(
                from_node=event.parent_id,
                to_node=event.id,
                relation_type=CausalRelationType.DIRECT,
                strength=1.0,
                evidence="Parent-child relationship in event tree"
            ))

        # Upstream event dependencies
        for upstream_id in (event.upstream_event_ids or []):
            if upstream_id in self.nodes:
                self.edges.append(CausalEdge(
                    from_node=upstream_id,
                    to_node=event.id,
                    relation_type=CausalRelationType.DEPENDENCY,
                    strength=0.9,
                    evidence="Explicit upstream dependency"
                ))

        # Temporal proximity for events without explicit relationships
        if not event.parent_id and not event.upstream_event_ids:
            self._add_temporal_edges(event, all_events)

    def _add_temporal_edges(self, event: TraceEvent, all_events: list[TraceEvent]) -> None:
        """Add temporal edges based on time proximity."""
        if not event.id:
            return

        # Find events that occurred within a short time window (5 seconds)
        time_window = 5.0
        event_time = event.timestamp

        for other in all_events:
            if other.id == event.id or other.id not in self.nodes:
                continue

            time_diff = abs((event_time - other.timestamp).total_seconds())

            if time_diff <= time_window and time_diff > 0:
                # Create edge from earlier to later event
                if other.timestamp < event.timestamp:
                    strength = 1.0 - (time_diff / time_window)  # Stronger for closer events
                    self.edges.append(CausalEdge(
                        from_node=other.id,
                        to_node=event.id,
                        relation_type=CausalRelationType.TEMPORAL,
                        strength=strength,
                        evidence=f"Events occurred {time_diff:.1f}s apart"
                    ))

    def _calculate_causal_depths(self) -> None:
        """Calculate causal depth for each node (distance from root causes)."""
        # Reset depths
        for node in self.nodes.values():
            node.causal_depth = 0

        # Find nodes with no incoming edges (potential root causes)
        nodes_with_incoming = {edge.to_node for edge in self.edges}
        potential_roots = [node_id for node_id in self.nodes.keys()
                         if node_id not in nodes_with_incoming]

        # BFS to calculate depths
        for root_id in potential_roots:
            self._bfs_calculate_depth(root_id, visited=set())

    def _bfs_calculate_depth(self, node_id: str, visited: set[str]) -> None:
        """BFS traversal to calculate causal depths."""
        if node_id in visited or node_id not in self.nodes:
            return

        visited.add(node_id)
        current_depth = self.nodes[node_id].causal_depth

        # Find all outgoing edges from this node
        for edge in self.edges:
            if edge.from_node == node_id and edge.to_node in self.nodes:
                neighbor = self.nodes[edge.to_node]
                # Update neighbor depth if we found a longer path
                if neighbor.causal_depth < current_depth + 1:
                    neighbor.causal_depth = current_depth + 1
                    self._bfs_calculate_depth(edge.to_node, visited)

    def _identify_root_cause_candidates(self) -> None:
        """Identify potential root cause nodes (no incoming edges)."""
        nodes_with_incoming = {edge.to_node for edge in self.edges}
        self.root_cause_candidates = [
            node_id for node_id in self.nodes.keys()
            if node_id not in nodes_with_incoming
        ]

    def trace_backward(self, failure_node_id: str) -> list[CausalNode]:
        """Trace backward from a failure to find causal chain.

        Args:
            failure_node_id: ID of the failure node to trace from

        Returns:
            List of nodes in the causal chain from root cause to failure
        """
        if failure_node_id not in self.nodes:
            return []

        chain = []
        current_id = failure_node_id

        # Follow incoming edges backwards
        visited = set()
        while current_id and current_id not in visited:
            visited.add(current_id)
            current_node = self.nodes[current_id]
            chain.append(current_node)

            # Find the parent/incoming node
            incoming_edges = [e for e in self.edges if e.to_node == current_id]

            if not incoming_edges:
                break

            # Choose the strongest incoming edge
            strongest_edge = max(incoming_edges, key=lambda e: e.strength)
            current_id = strongest_edge.from_node

        # Reverse to get root cause -> failure order
        chain.reverse()
        return chain

    def find_root_causes(self, failure_node_id: str | None = None) -> list[CausalNode]:
        """Find root cause nodes for failures.

        Args:
            failure_node_id: Specific failure to analyze (optional)

        Returns:
            List of root cause nodes
        """
        if failure_node_id:
            # Find root causes for specific failure
            chain = self.trace_backward(failure_node_id)
            return [chain[0]] if chain else []

        # Find all root causes that lead to failures
        failure_nodes = [node for node in self.nodes.values() if node.is_failure]

        root_causes = []
        for failure in failure_nodes:
            chain = self.trace_backward(failure.id)
            if chain and chain[0] not in root_causes:
                root_causes.append(chain[0])

        return root_causes

    def get_critical_path(self, failure_node_id: str) -> dict[str, Any]:
        """Get detailed analysis of the critical path to failure.

        Args:
            failure_node_id: ID of the failure node

        Returns:
            Dictionary with critical path analysis
        """
        chain = self.trace_backward(failure_node_id)

        if not chain:
            return {
                "failure_node_id": failure_node_id,
                "root_cause_found": False,
                "chain_length": 0,
                "critical_events": [],
                "weak_points": [],
            }

        # Analyze the chain
        critical_events = []
        weak_points = []

        for i, node in enumerate(chain):
            critical_events.append({
                "sequence": i,
                "event_id": node.id,
                "event_type": str(node.event_type),
                "name": node.name,
                "is_failure": node.is_failure,
                "failure_type": node.failure_type,
                "timestamp": node.timestamp.isoformat(),
            })

            # Identify weak points (decisions, state changes, etc.)
            if node.event_type == EventType.DECISION:
                confidence = node.metadata.get("confidence", 1.0)
                if confidence < 0.7:  # Low confidence decision
                    weak_points.append({
                        "event_id": node.id,
                        "weakness_type": "low_confidence_decision",
                        "description": f"Low confidence decision ({confidence:.2f})",
                        "position": i,
                    })

        return {
            "failure_node_id": failure_node_id,
            "root_cause_found": True,
            "root_cause_id": chain[0].id if chain else None,
            "chain_length": len(chain),
            "critical_events": critical_events,
            "weak_points": weak_points,
            "total_duration_seconds": (
                (chain[-1].timestamp - chain[0].timestamp).total_seconds()
                if len(chain) > 1 else 0.0
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entire graph to dictionary."""
        return {
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges],
            "root_cause_candidates": self.root_cause_candidates,
            "statistics": {
                "total_nodes": len(self.nodes),
                "total_edges": len(self.edges),
                "failure_count": sum(1 for node in self.nodes.values() if node.is_failure),
                "max_depth": max((node.causal_depth for node in self.nodes.values()), default=0),
            },
        }