"""Replay helpers shared by the API and tests."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from agent_debugger_sdk.core.events import Checkpoint, EventType, TraceEvent


def build_tree(events: list[TraceEvent]) -> dict[str, Any] | None:
    """Build a tree structure from a flat event list."""
    if not events:
        return None

    nodes: dict[str, dict[str, Any]] = {
        event.id: {
            "event": event.to_dict(),
            "children": [],
        }
        for event in events
    }
    roots: list[dict[str, Any]] = []

    for event in events:
        node = nodes[event.id]
        if event.parent_id and event.parent_id in nodes:
            nodes[event.parent_id]["children"].append(node)
        else:
            roots.append(node)

    return roots[0] if roots else None


def event_is_failure(event: TraceEvent) -> bool:
    """Return True when the event represents a failure or blocked action."""
    if event.event_type in {EventType.ERROR, EventType.REFUSAL, EventType.POLICY_VIOLATION}:
        return True
    if event.event_type == EventType.SAFETY_CHECK:
        return getattr(event, "outcome", event.data.get("outcome", "pass")) != "pass"
    if event.event_type == EventType.BEHAVIOR_ALERT:
        return True
    if event.event_type == EventType.TOOL_RESULT:
        return bool(getattr(event, "error", event.data.get("error")))
    return False


def matches_breakpoint(
    event: TraceEvent,
    *,
    event_types: set[str],
    tool_names: set[str],
    confidence_below: float | None,
    safety_outcomes: set[str],
) -> bool:
    """Return True when an event matches any configured breakpoint rule."""
    if event_types and str(event.event_type) in event_types:
        return True
    if tool_names and getattr(event, "tool_name", "") in tool_names:
        return True
    if confidence_below is not None and getattr(event, "confidence", 1.0) <= confidence_below:
        return True
    if safety_outcomes and getattr(event, "outcome", "") in safety_outcomes:
        return True
    return False


def _collect_focus_scope_ids(
    events: list[TraceEvent],
    *,
    focus_event_id: str,
    start_index: int,
) -> set[str]:
    """Collect the focused branch from the replay start to the focus subtree.

    The scope follows both structural ancestry (`parent_id`) and provenance
    ancestry (`upstream_event_ids`) so safety and evidence events remain
    visible even when they are not direct tree parents.
    """
    event_index = {event.id: index for index, event in enumerate(events)}
    if focus_event_id not in event_index:
        return {event.id for event in events[start_index:]}

    event_by_id = {event.id: event for event in events}
    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for event in events:
        if event.parent_id:
            children_by_parent[event.parent_id].append(event.id)

    scoped_ids: set[str] = set()
    visited_ancestors: set[str] = set()
    ancestor_stack = [focus_event_id]
    while ancestor_stack:
        current_id = ancestor_stack.pop()
        if current_id in visited_ancestors:
            continue
        visited_ancestors.add(current_id)
        current_index = event_index.get(current_id)
        if current_index is None or current_index < start_index:
            continue
        scoped_ids.add(current_id)

        event = event_by_id[current_id]
        if event.parent_id:
            ancestor_stack.append(event.parent_id)
        ancestor_stack.extend(getattr(event, "upstream_event_ids", []))

    visited: set[str] = set()
    stack = [focus_event_id]
    while stack:
        event_id = stack.pop()
        if event_id in visited:
            continue
        visited.add(event_id)
        current_index = event_index.get(event_id)
        if current_index is None or current_index < start_index:
            continue
        scoped_ids.add(event_id)
        stack.extend(children_by_parent.get(event_id, ()))

    if start_index < len(events):
        scoped_ids.add(events[start_index].id)

    return scoped_ids


def build_replay(
    events: list[TraceEvent],
    checkpoints: list[Checkpoint],
    *,
    mode: str,
    focus_event_id: str | None,
    breakpoint_event_types: set[str] | None = None,
    breakpoint_tool_names: set[str] | None = None,
    breakpoint_confidence_below: float | None = None,
    breakpoint_safety_outcomes: set[str] | None = None,
) -> dict[str, Any]:
    """Build replay output from events and checkpoints."""
    if not events:
        return {
            "mode": mode,
            "focus_event_id": focus_event_id,
            "start_index": 0,
            "events": [],
            "checkpoints": [checkpoint.to_dict() for checkpoint in checkpoints],
            "nearest_checkpoint": None,
            "breakpoints": [],
            "failure_event_ids": [],
        }

    failure_event_ids = [event.id for event in events if event_is_failure(event)]
    if mode == "failure" and failure_event_ids:
        focus_event_id = failure_event_ids[-1]

    event_index = {event.id: index for index, event in enumerate(events)}
    focus_index = event_index.get(focus_event_id, 0) if focus_event_id else 0

    nearest_checkpoint: Checkpoint | None = None
    checkpoint_index = 0
    for checkpoint in checkpoints:
        checkpoint_event_index = event_index.get(checkpoint.event_id, -1)
        if checkpoint_event_index <= focus_index:
            nearest_checkpoint = checkpoint
            checkpoint_index = max(checkpoint_event_index, 0)

    start_index = checkpoint_index if mode in {"focus", "failure"} else 0
    replay_window_events = events[start_index:]
    if mode in {"focus", "failure"} and focus_event_id:
        scoped_ids = _collect_focus_scope_ids(events, focus_event_id=focus_event_id, start_index=start_index)
        replay_events = [
            event
            for event in replay_window_events
            if event.id in scoped_ids
        ]
        replay_checkpoints = [checkpoint for checkpoint in checkpoints if checkpoint.event_id in scoped_ids]
        if nearest_checkpoint and all(checkpoint.id != nearest_checkpoint.id for checkpoint in replay_checkpoints):
            replay_checkpoints.insert(0, nearest_checkpoint)
    else:
        replay_events = replay_window_events
        replay_checkpoints = checkpoints
    breakpoint_event_types = breakpoint_event_types or set()
    breakpoint_tool_names = breakpoint_tool_names or set()
    breakpoint_safety_outcomes = breakpoint_safety_outcomes or set()

    breakpoints = [
        event.to_dict()
        for event in replay_window_events
        if matches_breakpoint(
            event,
            event_types=breakpoint_event_types,
            tool_names=breakpoint_tool_names,
            confidence_below=breakpoint_confidence_below,
            safety_outcomes=breakpoint_safety_outcomes,
        )
    ]

    return {
        "mode": mode,
        "focus_event_id": focus_event_id,
        "start_index": start_index,
        "events": [event.to_dict() for event in replay_events],
        "checkpoints": [checkpoint.to_dict() for checkpoint in replay_checkpoints],
        "nearest_checkpoint": nearest_checkpoint.to_dict() if nearest_checkpoint else None,
        "breakpoints": breakpoints,
        "failure_event_ids": failure_event_ids,
    }
