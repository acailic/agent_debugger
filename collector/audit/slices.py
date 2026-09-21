"""Program slices over a captured session's evidence graph.

Weiser (1984) defined the slice as the subset of program statements that
can influence a value at a program point, and motivated it by debugging:
localizing a fault means reasoning over a reduced, precise projection of
the run (docs/papers/weiser-program-slicing.md). The causal chain is a
dependence graph in exactly that sense — every claim cites the evidence
it was checked against, and every action depends on the decision and
evidence that triggered it — so the two operator questions become the two
slice directions:

* **Backward** — "why did the agent believe X": what fed this node.
* **Forward** — "what it fed": the damage radius, made precise as the
  forward slice from the first bad decision (:func:`damage_radius`).

Exactness wording (the product's differentiator): these functions slice
one recorded execution, so they answer what DID influence a node in this
run — never what could have in general. Weiser's static slices
over-approximate; a recorded trace does not.

Completeness caveat: a slice is only as complete as the capture. Where
session completeness diagnostics flag missing events, the slice is
silently partial too.

Design rules (same as the audit engine):

* Deterministic + inspectable. No LLM calls, no randomness, no network.
* Operates on the evidence-graph dict returned by
  :meth:`collector.audit.SessionAuditEngine.build_evidence_graph`;
  edges are never re-derived here.
* Edge orientation: a recorded ``evidence`` edge points claim -> cited
  fact (a citation pointer), but the dependence runs fact -> claim (the
  fact influenced the claim); ``causal`` edges (parent -> child) already
  record the influence direction. Slices traverse the dependence
  orientation, so a backward slice from a claim includes the evidence it
  cited, and a forward slice from a decision never lists the decision's
  own citations as "damage".
"""

from __future__ import annotations

from typing import Any

from agent_debugger_sdk.core.events import TraceEvent

#: Maximum number of entries a slice returns before truncation. A recorded
#: chain an operator would actually inspect is far smaller; the cap only
#: bounds a pathological (or adversarially wide) graph, and ``truncated``
#: says when it fired.
SLICE_CAP = 64

#: Direction labels for the returned payload.
BACKWARD = "backward"
FORWARD = "forward"

#: The two edge types the evidence graph records (see
#: :meth:`SessionAuditEngine.build_evidence_graph`).
_EVIDENCE = "evidence"
_CAUSAL = "causal"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def backward_slice(
    events: list[TraceEvent], graph: dict[str, Any], node_id: str
) -> dict[str, Any]:
    """Return the backward slice of *node_id* — everything that fed it.

    "Why did the agent believe X": the transitive ancestors of *node_id*
    over ``evidence`` + ``causal`` dependence edges. Because the slice runs
    over one recorded execution, it answers what DID influence the node in
    this run (a dynamic slice), never what could have in general. A slice
    is only as complete as the capture — missing events make it silently
    partial.

    Args:
        events: The session's events, in trace order (they define each
            node's trace position; the graph supplies edges and labels).
        graph: The evidence-graph dict from
            :meth:`SessionAuditEngine.build_evidence_graph`.
        node_id: The node to slice from. A node absent from the graph
            yields an empty slice, not an error.

    Returns:
        ``{"node_id", "direction": "backward", "slice", "size",
        "truncated"}`` where each slice entry is
        ``{"event_id", "event_type", "label", "via": "evidence"|"causal"}``.
        Entries are sorted by trace position (then event id); ``via`` is
        the edge type through which the node was first reached on the
        deterministic BFS. Capped at :data:`SLICE_CAP` entries.
    """
    return _traverse(events, graph, node_id, BACKWARD)


def forward_slice(
    events: list[TraceEvent], graph: dict[str, Any], node_id: str
) -> dict[str, Any]:
    """Return the forward slice of *node_id* — everything it fed.

    "What it fed": the transitive descendants of *node_id* over
    ``evidence`` + ``causal`` dependence edges — what DID consume this
    node's output in this run, never what could have in general. A slice
    is only as complete as the capture — missing events make it silently
    partial.

    Args:
        events: The session's events, in trace order.
        graph: The evidence-graph dict from
            :meth:`SessionAuditEngine.build_evidence_graph`.
        node_id: The node to slice from. A node absent from the graph
            yields an empty slice, not an error.

    Returns:
        Same shape as :func:`backward_slice` with
        ``"direction": "forward"``.
    """
    return _traverse(events, graph, node_id, FORWARD)


def damage_radius(
    events: list[TraceEvent], graph: dict[str, Any], first_bad_decision: str | None
) -> dict[str, Any]:
    """Return the forward slice from the first bad decision — the damage radius.

    Weiser's downstream-damage localization made precise: the set of nodes
    the first bad decision DID influence in this run, never the nodes it
    could have influenced in general (a dynamic slice of one recorded
    execution). Downstream damage then has an exact size, and a slice is
    only as complete as the capture — missing events make it silently
    partial.

    Args:
        events: The session's events, in trace order.
        graph: The evidence-graph dict from
            :meth:`SessionAuditEngine.build_evidence_graph`.
        first_bad_decision: The first bad decision's event id, as
            localized by the session audit
            (``report["questions"]["where_it_failed"]["first_bad_decision"]``).
            ``None`` or an id absent from the graph yields an empty radius
            (no damage localized), not an error.

    Returns:
        The forward-slice payload plus ``{"first_bad_decision": id}``.
    """
    radius = _traverse(events, graph, first_bad_decision, FORWARD)
    radius["first_bad_decision"] = first_bad_decision
    return radius


# ---------------------------------------------------------------------------
# Traversal internals
# ---------------------------------------------------------------------------


def _traverse(
    events: list[TraceEvent],
    graph: dict[str, Any],
    node_id: str | None,
    direction: str,
) -> dict[str, Any]:
    """Shared BFS machinery for both slice directions (deterministic)."""
    start = str(node_id) if node_id is not None else ""
    result: dict[str, Any] = {
        "node_id": start,
        "direction": direction,
        "slice": [],
        "size": 0,
        "truncated": False,
    }
    if not start:
        return result

    nodes = _graph_node_lookup(graph)
    feeders, fed = _dependence_adjacency(graph)
    if start not in nodes and start not in feeders and start not in fed:
        return result

    position = {event.id: index for index, event in enumerate(events)}
    via = _bfs(start, feeders if direction == BACKWARD else fed, position)

    entries = [
        {
            "event_id": event_id,
            "event_type": str(nodes[event_id].get("event_type") or ""),
            "label": str(nodes[event_id].get("label") or event_id),
            "via": edge_type,
        }
        for event_id, edge_type in via.items()
    ]
    entries.sort(key=lambda entry: (position.get(entry["event_id"], len(events)), entry["event_id"]))

    result["truncated"] = len(entries) > SLICE_CAP
    result["slice"] = entries[:SLICE_CAP]
    result["size"] = len(result["slice"])
    return result


def _bfs(
    start: str,
    adjacency: dict[str, list[tuple[str, str]]],
    position: dict[str, int],
) -> dict[str, str]:
    """BFS over *adjacency*; returns ``{node_id: edge_type of first discovery}``.

    Neighbors are visited in a stable order — trace position, then event
    id, then edge type — so discovery order (and the winning ``via`` when
    a node is reachable through several edge types) is fully determined by
    the capture. The start node never appears in its own slice, and the
    ``seen`` set makes a cyclic graph terminate.
    """
    fallback = len(position)
    via: dict[str, str] = {}
    seen: set[str] = {start}
    queue: list[str] = [start]
    while queue:
        current = queue.pop(0)
        neighbors = sorted(
            adjacency.get(current, []),
            key=lambda item: (position.get(item[0], fallback), item[0], item[1]),
        )
        for neighbor, edge_type in neighbors:
            if neighbor in seen:
                continue
            seen.add(neighbor)
            via[neighbor] = edge_type
            queue.append(neighbor)
    return via


def _graph_node_lookup(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map event id -> node record for the graph's node list."""
    lookup: dict[str, dict[str, Any]] = {}
    for node in graph.get("nodes") or []:
        if isinstance(node, dict) and node.get("event_id"):
            lookup[str(node["event_id"])] = node
    return lookup


def _dependence_adjacency(
    graph: dict[str, Any],
) -> tuple[dict[str, list[tuple[str, str]]], dict[str, list[tuple[str, str]]]]:
    """Return ``(feeders, fed)`` adjacency in dependence orientation.

    ``feeders[n]`` lists the nodes that fed *n* and the edge type they fed
    it through; ``fed[n]`` lists the nodes *n* fed. Dependence runs
    fact -> claim for ``evidence`` edges (the recorded edge is the
    citation pointer claim -> fact, so it is flipped here) and
    parent -> child for ``causal`` edges (already the influence direction).
    """
    feeders: dict[str, list[tuple[str, str]]] = {}
    fed: dict[str, list[tuple[str, str]]] = {}
    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source_id") or "")
        target = str(edge.get("target_id") or "")
        edge_type = str(edge.get("edge_type") or "")
        if not source or not target or edge_type not in {_EVIDENCE, _CAUSAL}:
            continue
        if edge_type == _EVIDENCE:
            fed.setdefault(target, []).append((source, edge_type))
            feeders.setdefault(source, []).append((target, edge_type))
        else:
            fed.setdefault(source, []).append((target, edge_type))
            feeders.setdefault(target, []).append((source, edge_type))
    return feeders, fed
