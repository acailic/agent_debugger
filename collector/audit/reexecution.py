"""Deterministic minimal re-execution set (roadmap M2.1).

For a suspect decision in a session audit, :func:`build_reexecution_set`
computes the smallest sub-graph that would need to re-run to confirm or
invalidate that decision's claim (see the provenance survey note,
``docs/papers/from-agent-traces-to-trust-provenance-survey.md`` → roadmap
``docs/ROADMAP.md`` M2.1):

* **decision** — the suspect node itself.
* **evidence** — every event it cites (resolved tool results / user inputs /
  retrieved facts) whose outputs would have to be reproduced.
* **upstream_tool_call** — the tool calls that produce that evidence.
* **downstream** — the events that depend on the decision's output (its
  causal subtree), each marked read-only vs required-rerun.

Design rules (same as the audit engine and failure narrative):

* Deterministic + inspectable. No LLM calls, no I/O, no randomness.
* Planning layer only — it names what *would* have to re-run, it never
  executes anything. Edge semantics are shared with
  :meth:`SessionAuditEngine.build_evidence_graph` by reusing its helpers.
"""

from __future__ import annotations

from typing import Any

from agent_debugger_sdk.core.events import EventType, TraceEvent

from ..intelligence.helpers import event_label, event_value
from .audit_engine import _build_children_index, _iso, _source_class_for

# Operator-supplied event types: re-supplied verbatim, never re-executed.
READ_ONLY_EVENT_TYPES = frozenset({EventType.AGENT_TURN, EventType.AGENT_START})

# Walk bound for the downstream subtree traversal — a cycle guard only,
# not a size cap (the full causal subtree is the re-execution set).
_MAX_WALK_ITERATIONS = 2000


def build_reexecution_set(
    events: list[TraceEvent], report: dict[str, Any], event_id: str
) -> dict[str, Any] | None:
    """Return the minimal re-execution set for a decision's claim.

    ``report`` is the dict produced by
    :meth:`collector.audit.SessionAuditEngine.audit`. Returns ``None`` when
    *event_id* is not a captured decision (unknown id, or the id belongs to
    a non-decision event) — callers map that to a 404. Pure function of
    (events, report, event_id): no I/O, no clock, no randomness.
    """
    claim = next(
        (item for item in report.get("claims", []) or [] if item.get("event_id") == event_id),
        None,
    )
    if claim is None:
        return None

    id_lookup = {event.id: event for event in events}
    position = {event.id: index for index, event in enumerate(events)}
    decision_event = id_lookup.get(event_id)
    if decision_event is None:
        return None

    children_by_parent = _build_children_index(events)

    # Role assignment with precedence: decision > evidence >
    # upstream_tool_call > downstream (an id keeps the first role it gets).
    roles: dict[str, str] = {event_id: "decision"}
    upstream_of: dict[str, str] = {}

    evidence_ids: list[str] = []
    for ref in claim.get("evidence_refs", []) or []:
        ref = str(ref)
        if ref in roles or ref not in id_lookup:
            continue
        roles[ref] = "evidence"
        evidence_ids.append(ref)

    for evidence_id in evidence_ids:
        evidence_event = id_lookup[evidence_id]
        for parent_id in _parent_refs(evidence_event):
            if parent_id in roles or parent_id not in id_lookup:
                continue
            if id_lookup[parent_id].event_type != EventType.TOOL_CALL:
                continue
            roles[parent_id] = "upstream_tool_call"
            upstream_of[parent_id] = evidence_id

    for descendant_id in _descendants(event_id, children_by_parent):
        if descendant_id in roles:
            continue
        roles[descendant_id] = "downstream"

    # Nodes in trace order — the single deterministic output order.
    ordered_ids = sorted(roles, key=lambda eid: position.get(eid, len(position)))
    nodes = [
        _node(
            id_lookup[eid],
            role=roles[eid],
            upstream_of=upstream_of.get(eid),
        )
        for eid in ordered_ids
        if eid in id_lookup
    ]

    # Evidence edges first (claim's ref order), then causal edges
    # (node trace order × captured parent-ref order). Deduped by tuple key.
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str, str | None]] = set()

    def add_edge(
        source_id: str, target_id: str, edge_type: str, source_class: str | None
    ) -> None:
        key = (source_id, target_id, edge_type, source_class)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append(
            {
                "source_id": source_id,
                "target_id": target_id,
                "edge_type": edge_type,
                "source_class": source_class,
            }
        )

    for ref in evidence_ids:
        add_edge(event_id, ref, "evidence", _source_class_for(id_lookup[ref]))
    for eid in ordered_ids:
        if eid not in id_lookup:
            continue
        for parent_id in _parent_refs(id_lookup[eid]):
            if parent_id in roles and parent_id in id_lookup:
                add_edge(parent_id, eid, "causal", None)

    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "markdown": _markdown(event_id, nodes, edges),
    }


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _parent_refs(event: TraceEvent) -> list[str]:
    """Ordered parent refs: ``parent_id`` first, then upstream ids as captured."""
    refs: list[str] = []
    if event.parent_id:
        refs.append(str(event.parent_id))
    for upstream_id in event_value(event, "upstream_event_ids", []) or []:
        refs.append(str(upstream_id))
    # Dedupe, preserving order.
    deduped: list[str] = []
    for ref in refs:
        if ref not in deduped:
            deduped.append(ref)
    return deduped


def _descendants(root_id: str, children_by_parent: dict[str, list[str]]) -> list[str]:
    """All event ids transitively downstream of *root_id*, in trace order.

    Mirrors :meth:`SessionAuditEngine._descendants_set` (same children index,
    same bounded walk as a cycle guard), then orders the result by trace
    position so no output ever depends on set iteration order.
    """
    seen: set[str] = set()
    frontier = list(children_by_parent.get(root_id, []))
    for _ in range(_MAX_WALK_ITERATIONS):
        if not frontier:
            break
        next_frontier: list[str] = []
        for node_id in frontier:
            if node_id in seen:
                continue
            seen.add(node_id)
            next_frontier.extend(children_by_parent.get(node_id, []))
        frontier = next_frontier
    return sorted(seen)


def _mode_for(event: TraceEvent, role: str) -> str:
    """Deterministic read-only vs required-rerun mode for a set member."""
    if role in {"decision", "upstream_tool_call"}:
        return "required_rerun"
    if event.event_type in READ_ONLY_EVENT_TYPES:
        return "read_only"
    return "required_rerun"


def _node(event: TraceEvent, *, role: str, upstream_of: str | None) -> dict[str, Any]:
    mode = _mode_for(event, role)
    return {
        "event_id": event.id,
        "event_type": str(event.event_type),
        "label": event_label(event),
        "role": role,
        "mode": mode,
        "why_included": _why_included(event, role, mode, upstream_of),
        "timestamp": _iso(event),
    }


def _why_included(event: TraceEvent, role: str, mode: str, upstream_of: str | None) -> str:
    """One-line reason the event is in the set (deterministic templates)."""
    if role == "decision":
        return "the suspect decision under audit — re-run to confirm or invalidate its claim"
    if role == "upstream_tool_call":
        return (
            f"tool call that produces the cited evidence {upstream_of} — must be re-invoked"
        )
    if role == "evidence":
        if event.event_type == EventType.TOOL_RESULT:
            return "cited tool result — its output must be reproduced to re-verify the claim"
        if event.event_type in READ_ONLY_EVENT_TYPES:
            return "cited user input — re-supplied verbatim, not re-executed"
        return "cited evidence — must be re-obtained to re-verify the claim"
    if mode == "read_only":
        return "operator input inside the decision's subtree — replayed verbatim"
    return "consumes the decision's output — re-runs when the decision is re-made"


def _markdown(
    event_id: str, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> str:
    """Compact deterministic markdown summary; sections always emitted."""
    required = [node for node in nodes if node["mode"] == "required_rerun"]
    read_only = [node for node in nodes if node["mode"] == "read_only"]
    lines = [
        f"# Minimal re-execution set — {event_id}",
        "",
        f"{len(nodes)} event(s): {len(required)} required-rerun, {len(read_only)} read-only.",
        "",
        "## Required re-runs",
    ]
    lines.extend(
        f"- `{node['event_id']}` ({node['role']}, {node['event_type']}): {node['why_included']}"
        for node in required
    )
    lines.append("")
    lines.append("## Read-only")
    if read_only:
        lines.extend(
            f"- `{node['event_id']}` ({node['role']}, {node['event_type']}): {node['why_included']}"
            for node in read_only
        )
    else:
        lines.append("None.")
    lines.append("")
    lines.append("## Edges")
    if edges:
        lines.extend(
            f"- `{edge['source_id']}` --{edge['edge_type']}--> `{edge['target_id']}`"
            for edge in edges
        )
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


__all__ = ["build_reexecution_set"]
