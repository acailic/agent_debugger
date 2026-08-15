"""Causal graph and workflow analysis services."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from agent_debugger_sdk.core.events import EventType, TraceEvent
from api.services.sessions import load_session_artifacts
from storage import TraceRepository

logger = logging.getLogger(__name__)

async def analyze_causal_graph(
    repo: TraceRepository,
    session_id: str,
) -> dict[str, Any]:
    """Perform causal root cause analysis on a session.

    Args:
        repo: Trace repository
        session_id: Session to analyze

    Returns:
        Dictionary with causal graph, critical paths, and root causes
    """
    from agent_debugger_sdk.core import CausalGraph

    events, _ = await load_session_artifacts(repo, session_id)

    if not events:
        return {
            "session_id": session_id,
            "causal_graph": {
                "nodes": [],
                "edges": [],
                "root_cause_candidates": [],
                "statistics": {
                    "total_nodes": 0,
                    "total_edges": 0,
                    "failure_count": 0,
                    "max_depth": 0,
                },
            },
            "critical_paths": {},
            "root_causes": [],
        }

    # Build causal graph
    graph = CausalGraph()
    graph.build_from_events(events)

    # Analyze critical paths for failures
    failure_nodes = [node for node in graph.nodes.values() if node.is_failure]
    critical_paths = {}

    for failure_node in failure_nodes:
        path_analysis = graph.get_critical_path(failure_node.id)
        critical_paths[failure_node.id] = path_analysis

    # Find root causes
    root_causes = graph.find_root_causes()
    root_cause_data = [node.to_dict() for node in root_causes]

    return {
        "session_id": session_id,
        "causal_graph": graph.to_dict(),
        "critical_paths": critical_paths,
        "root_causes": root_cause_data,
    }


def extract_workflow_graph(events: list[TraceEvent], session_id: str) -> dict[str, Any]:
    """Extract a workflow graph from session events.

    Creates a directed graph where:
    - Nodes represent decisions/tool calls/LLM requests
    - Edges represent data flow and dependencies

    Returns a dict with 'nodes' and 'edges' keys.
    """
    from api.schemas import WorkflowEdgeSchema, WorkflowGraphSchema, WorkflowNodeSchema

    # Filter relevant events for workflow nodes
    workflow_events = []
    for event in events:
        if event.event_type in (
            EventType.DECISION,
            EventType.TOOL_CALL,
            EventType.LLM_REQUEST,
            EventType.ERROR,
            EventType.CHECKPOINT,
        ):
            workflow_events.append(event)

    # Build nodes
    nodes = []
    event_to_node_id: dict[str, str] = {}

    for idx, event in enumerate(workflow_events):
        node_id = f"node_{idx}"
        event_to_node_id[event.id] = node_id

        # Determine node status
        status = "pending"
        if event.event_type == EventType.ERROR or getattr(event, "error", None):
            status = "failure"
        elif event.event_type in (EventType.TOOL_CALL, EventType.LLM_REQUEST):
            # Check if there's a corresponding result
            status = "success"  # Assume success if no error
        elif event.event_type == EventType.DECISION:
            status = "success"

        # Determine node type and label
        if event.event_type == EventType.DECISION:
            node_type = "decision"
            label = event.name or "Decision"
        elif event.event_type == EventType.TOOL_CALL:
            node_type = "tool_call"
            label = getattr(event, "tool_name", None) or event.name or "Tool Call"
        elif event.event_type == EventType.LLM_REQUEST:
            node_type = "llm_request"
            label = f"LLM: {getattr(event, 'model', None) or 'request'}"
        elif event.event_type == EventType.ERROR:
            node_type = "error"
            label = getattr(event, "error_message", None) or event.name or "Error"
        elif event.event_type == EventType.CHECKPOINT:
            node_type = "checkpoint"
            label = f"Checkpoint {event.data.get('sequence', '?')}"
        else:
            node_type = "unknown"
            label = event.name or "Unknown"

        # Extract token count
        token_count = None
        usage = getattr(event, "usage", None)
        if usage:
            token_count = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

        node = WorkflowNodeSchema(
            id=node_id,
            event_id=event.id,
            node_type=node_type,
            label=label,
            status=status,
            duration_ms=getattr(event, "duration_ms", None),
            token_count=token_count,
            timestamp=event.timestamp,
            parent_id=event.parent_id,
            metadata={
                "event_type": str(event.event_type),
                "importance": event.importance,
                "tool_name": getattr(event, "tool_name", None),
                "model": getattr(event, "model", None),
            }
        )
        nodes.append(node)

    # Build edges based on event relationships
    edges = []
    edge_counter = 0

    for event in workflow_events:
        if event.id not in event_to_node_id:
            continue

        source_id = event_to_node_id[event.id]

        # Add edge from parent
        if event.parent_id and event.parent_id in event_to_node_id:
            target_id = event_to_node_id[event.parent_id]
            edge = WorkflowEdgeSchema(
                id=f"edge_{edge_counter}",
                source_id=source_id,
                target_id=target_id,
                edge_type="control_flow",
                label="parent"
            )
            edges.append(edge)
            edge_counter += 1

        # Add edges for upstream dependencies
        for upstream_id in event.upstream_event_ids:
            if upstream_id in event_to_node_id:
                target_id = event_to_node_id[upstream_id]
                edge = WorkflowEdgeSchema(
                    id=f"edge_{edge_counter}",
                    source_id=source_id,
                    target_id=target_id,
                    edge_type="data_flow",
                    label="dependency"
                )
                edges.append(edge)
                edge_counter += 1

    # Create workflow graph
    graph = WorkflowGraphSchema(
        session_id=session_id,
        nodes=nodes,
        edges=edges,
        metadata={
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "extraction_timestamp": datetime.now().isoformat(),
        }
    )

    return {
        "graph": graph,
    }

