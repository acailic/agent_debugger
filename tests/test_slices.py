"""Tests for collector/audit/slices.py — Weiser program slices.

Covers the backward / forward slice and damage-radius computations over a
session's evidence graph (docs/papers/weiser-program-slicing.md): chain
correctness with evidence citations, via-edge attribution, direction
symmetry, the 64-entry cap + truncation flag, damage radius == forward
slice from the first bad decision, empty slices at the chain's ends,
determinism, and missing nodes yielding empty results (never errors).

All ids are prefixed ``wsl-`` so they never collide with other tests'
ids under the shared-database / xdist uniqueness rule.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.audit import SessionAuditEngine
from collector.audit.slices import (
    SLICE_CAP,
    backward_slice,
    damage_radius,
    forward_slice,
)

# ---------------------------------------------------------------------------
# Test helpers (mirror test_audit_engine.py conventions)
# ---------------------------------------------------------------------------


def _event(
    event_id: str,
    event_type: EventType,
    session_id: str = "wsl-session",
    parent_id: str | None = None,
    timestamp: datetime | None = None,
    **data,
) -> TraceEvent:
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        parent_id=parent_id,
        name=f"test_{event_type}",
        event_type=event_type,
        timestamp=timestamp or datetime(2026, 1, 1, tzinfo=timezone.utc),
        data=data,
        upstream_event_ids=[],
    )


def _decision(
    event_id: str,
    *,
    confidence: float = 0.5,
    evidence_event_ids: list[str] | None = None,
    chosen_action: str = "act",
    parent_id: str | None = None,
    timestamp: datetime | None = None,
) -> TraceEvent:
    return _event(
        event_id,
        EventType.DECISION,
        parent_id=parent_id,
        timestamp=timestamp,
        confidence=confidence,
        evidence_event_ids=evidence_event_ids or [],
        chosen_action=chosen_action,
    )


def _chain_session() -> list[TraceEvent]:
    """decision -> tool -> decision -> failure chain with evidence citations.

    Graph (dependence orientation — fact feeds the claim that cites it,
    parent feeds the child):

        wsl-u1 --causal--> wsl-t1, wsl-d1, wsl-d2   (session root's children)
        wsl-t1 --evidence--> wsl-d1                 (d1 cites the search result)
        wsl-d1 --causal--> wsl-t2                   (deploy fails)
        wsl-t2 --evidence--> wsl-d2                 (d2 cites the failure)
        wsl-d2 --causal--> wsl-t3                   (rollback succeeds)
    """
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        _event("wsl-u1", EventType.AGENT_START, goal="deploy the service", timestamp=base),
        _event(
            "wsl-t1",
            EventType.TOOL_RESULT,
            parent_id="wsl-u1",
            tool_name="search",
            result={"hits": 2},
            timestamp=base + timedelta(minutes=1),
        ),
        _decision(
            "wsl-d1",
            confidence=0.9,
            evidence_event_ids=["wsl-t1"],
            chosen_action="deploy now",
            parent_id="wsl-u1",
            timestamp=base + timedelta(minutes=2),
        ),
        _event(
            "wsl-t2",
            EventType.TOOL_RESULT,
            parent_id="wsl-d1",
            tool_name="deploy",
            error="500",
            timestamp=base + timedelta(minutes=3),
        ),
        _decision(
            "wsl-d2",
            confidence=0.7,
            evidence_event_ids=["wsl-t2"],
            chosen_action="roll back",
            parent_id="wsl-u1",
            timestamp=base + timedelta(minutes=4),
        ),
        _event(
            "wsl-t3",
            EventType.TOOL_RESULT,
            parent_id="wsl-d2",
            tool_name="rollback",
            result={"ok": True},
            timestamp=base + timedelta(minutes=5),
        ),
    ]


def _chain_graph():
    events = _chain_session()
    graph = SessionAuditEngine().build_evidence_graph(events)
    return events, graph


def _ids(result: dict) -> list[str]:
    return [entry["event_id"] for entry in result["slice"]]


def _via(result: dict) -> dict[str, str]:
    return {entry["event_id"]: entry["via"] for entry in result["slice"]}


# ---------------------------------------------------------------------------
# Backward slice — "what fed this"
# ---------------------------------------------------------------------------


def test_backward_slice_from_decision_returns_evidence_and_causal_parents():
    events, graph = _chain_graph()

    result = backward_slice(events, graph, "wsl-d1")

    assert result["node_id"] == "wsl-d1"
    assert result["direction"] == "backward"
    assert _ids(result) == ["wsl-u1", "wsl-t1"]
    assert result["size"] == 2
    assert result["truncated"] is False


def test_backward_slice_entries_carry_type_label_and_via():
    events, graph = _chain_graph()

    result = backward_slice(events, graph, "wsl-d1")
    entries = {entry["event_id"]: entry for entry in result["slice"]}

    assert set(entries) == {"wsl-u1", "wsl-t1"}
    assert set(entries["wsl-u1"]) == {"event_id", "event_type", "label", "via"}
    assert entries["wsl-u1"]["event_type"] == "agent_start"
    assert entries["wsl-u1"]["label"] == "deploy the service"
    assert entries["wsl-u1"]["via"] == "causal"
    assert entries["wsl-t1"]["event_type"] == "tool_result"
    assert entries["wsl-t1"]["label"] == "search"
    assert entries["wsl-t1"]["via"] == "evidence"


def test_backward_slice_transitively_walks_the_whole_chain():
    # From the last decision everything upstream is an ancestor: the root,
    # the search result, the deploy decision, and the failed deploy it
    # cites (reached through the evidence citation).
    events, graph = _chain_graph()

    result = backward_slice(events, graph, "wsl-d2")

    assert _ids(result) == ["wsl-u1", "wsl-t1", "wsl-d1", "wsl-t2"]
    assert _via(result) == {
        "wsl-u1": "causal",
        "wsl-t1": "evidence",
        "wsl-d1": "causal",
        "wsl-t2": "evidence",
    }


# ---------------------------------------------------------------------------
# Forward slice — "what it fed" (the damage radius)
# ---------------------------------------------------------------------------


def test_forward_slice_from_decision_returns_downstream_damage():
    events, graph = _chain_graph()

    result = forward_slice(events, graph, "wsl-d1")

    assert result["node_id"] == "wsl-d1"
    assert result["direction"] == "forward"
    # The failed deploy, the rollback decision it fed (via the citation of
    # the failure), and the cleanup it triggered.
    assert _ids(result) == ["wsl-t2", "wsl-d2", "wsl-t3"]
    assert _via(result) == {"wsl-t2": "causal", "wsl-d2": "evidence", "wsl-t3": "causal"}
    assert result["size"] == 3
    assert result["truncated"] is False


def test_forward_slice_never_lists_the_nodes_own_citations_as_damage():
    # d1 cites t1; the citation is dependence fact -> claim, so t1 is
    # upstream of d1 and must not appear in d1's forward slice.
    events, graph = _chain_graph()

    result = forward_slice(events, graph, "wsl-d1")

    assert "wsl-t1" not in _ids(result)
    assert "wsl-t1" in _ids(backward_slice(events, graph, "wsl-d1"))


# ---------------------------------------------------------------------------
# Deterministic ordering + via attribution
# ---------------------------------------------------------------------------


def test_slice_entries_are_sorted_by_trace_position_then_id():
    # Facts listed z2-before-z1: positional order must beat alphabetical.
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = [
        _event(
            "wsl-z2",
            EventType.TOOL_RESULT,
            tool_name="late",
            result={},
            timestamp=base,
        ),
        _event(
            "wsl-z1",
            EventType.TOOL_RESULT,
            tool_name="early",
            result={},
            timestamp=base + timedelta(minutes=1),
        ),
        _decision(
            "wsl-zd",
            confidence=0.9,
            evidence_event_ids=["wsl-z2", "wsl-z1"],
            timestamp=base + timedelta(minutes=2),
        ),
    ]
    graph = SessionAuditEngine().build_evidence_graph(events)

    result = backward_slice(events, graph, "wsl-zd")

    assert _ids(result) == ["wsl-z2", "wsl-z1"]
    assert _via(result) == {"wsl-z2": "evidence", "wsl-z1": "evidence"}


def test_via_attribution_is_deterministic_when_both_edge_types_connect_a_pair():
    # d1 triggers t1 (causal, via parent) AND cites t1 as its evidence —
    # both edge types connect the same pair in the same direction. The
    # stable neighbor order (position, id, edge type) makes "causal" the
    # winning attribution in both slice directions, every run.
    events = [
        _decision(
            "wsl-dual-d1",
            confidence=0.9,
            evidence_event_ids=["wsl-dual-t1"],
            chosen_action="probe then cite",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        _event(
            "wsl-dual-t1",
            EventType.TOOL_RESULT,
            parent_id="wsl-dual-d1",
            tool_name="probe",
            result={},
            timestamp=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
        ),
    ]
    graph = SessionAuditEngine().build_evidence_graph(events)

    dual_edges = [
        e for e in graph["edges"] if e["source_id"] == "wsl-dual-d1" and e["target_id"] == "wsl-dual-t1"
    ]
    assert {e["edge_type"] for e in dual_edges} == {"evidence", "causal"}

    backward = backward_slice(events, graph, "wsl-dual-t1")
    forward = forward_slice(events, graph, "wsl-dual-d1")

    assert _via(backward)["wsl-dual-d1"] == "causal"
    assert _via(forward)["wsl-dual-t1"] == "causal"


def test_slices_are_deterministic():
    events = _chain_session()
    engine = SessionAuditEngine()
    graph_a = engine.build_evidence_graph(copy.deepcopy(events))
    graph_b = engine.build_evidence_graph(copy.deepcopy(events))

    for node_id in ("wsl-d1", "wsl-d2", "wsl-t2"):
        assert backward_slice(events, graph_a, node_id) == backward_slice(
            events, graph_b, node_id
        )
        assert forward_slice(events, graph_a, node_id) == forward_slice(
            events, graph_b, node_id
        )
        # Repeated calls over the same inputs are stable too.
        assert backward_slice(events, graph_a, node_id) == backward_slice(
            events, graph_a, node_id
        )


# ---------------------------------------------------------------------------
# Direction symmetry
# ---------------------------------------------------------------------------


def test_forward_and_backward_slices_are_direction_symmetric():
    # b is in forward(a) exactly when a is in backward(b), for every pair.
    events, graph = _chain_graph()
    node_ids = [event.id for event in events]

    for source in node_ids:
        forward_ids = set(_ids(forward_slice(events, graph, source)))
        for target in node_ids:
            backward_ids = set(_ids(backward_slice(events, graph, target)))
            assert (target in forward_ids) == (source in backward_ids), (
                f"asymmetric pair ({source} -> {target})"
            )


# ---------------------------------------------------------------------------
# Cap + truncation
# ---------------------------------------------------------------------------


def _wide_session(child_count: int) -> list[TraceEvent]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = [
        _decision("wsl-w0", confidence=0.9, chosen_action="fan out", timestamp=base)
    ]
    for index in range(1, child_count + 1):
        events.append(
            _event(
                f"wsl-w{index:02d}",
                EventType.TOOL_RESULT,
                parent_id="wsl-w0",
                tool_name=f"step{index}",
                result={"index": index},
                timestamp=base + timedelta(minutes=index),
            )
        )
    return events


def test_forward_slice_caps_at_slice_cap_and_flags_truncation():
    events = _wide_session(child_count=SLICE_CAP + 6)
    graph = SessionAuditEngine().build_evidence_graph(events)

    result = forward_slice(events, graph, "wsl-w0")

    assert result["truncated"] is True
    assert result["size"] == SLICE_CAP == len(result["slice"])
    # The cap keeps the earliest entries by trace position, in order.
    assert _ids(result) == [f"wsl-w{index:02d}" for index in range(1, SLICE_CAP + 1)]
    assert all(entry["via"] == "causal" for entry in result["slice"])


def test_backward_slice_of_wide_session_stays_small_and_untruncated():
    events = _wide_session(child_count=SLICE_CAP + 6)
    graph = SessionAuditEngine().build_evidence_graph(events)

    result = backward_slice(events, graph, "wsl-w70")

    assert result["truncated"] is False
    assert _ids(result) == ["wsl-w0"]
    assert result["size"] == 1


def test_chain_slices_are_not_truncated():
    events, graph = _chain_graph()

    for node_id in ("wsl-u1", "wsl-d1", "wsl-d2"):
        assert backward_slice(events, graph, node_id)["truncated"] is False
        assert forward_slice(events, graph, node_id)["truncated"] is False


# ---------------------------------------------------------------------------
# Damage radius — forward slice from the first bad decision
# ---------------------------------------------------------------------------


def test_damage_radius_equals_forward_slice_from_first_bad_decision():
    events = _chain_session()
    engine = SessionAuditEngine()
    graph = engine.build_evidence_graph(events)
    report = engine.audit(events)
    first_bad = report["questions"]["where_it_failed"]["first_bad_decision"]

    # The confident deploy decision is contradicted by its failing subtree.
    assert first_bad == "wsl-d1"

    radius = damage_radius(events, graph, first_bad)
    expected = forward_slice(events, graph, first_bad)

    assert set(radius) == {"node_id", "direction", "slice", "size", "truncated", "first_bad_decision"}
    assert radius["first_bad_decision"] == "wsl-d1"
    assert radius["direction"] == "forward"
    assert radius["slice"] == expected["slice"]
    assert radius["size"] == expected["size"]
    assert radius["truncated"] == expected["truncated"]
    # The damage includes the failure itself and what consumed it.
    assert "wsl-t2" in _ids(radius)
    assert "wsl-d2" in _ids(radius)


def test_damage_radius_with_missing_or_unset_first_bad_decision_is_empty():
    events, graph = _chain_graph()

    for bad in ("wsl-ghost", None):
        radius = damage_radius(events, graph, bad)
        assert radius["slice"] == []
        assert radius["size"] == 0
        assert radius["truncated"] is False
        assert radius["first_bad_decision"] == bad


# ---------------------------------------------------------------------------
# Chain ends, missing nodes, degenerate inputs
# ---------------------------------------------------------------------------


def test_empty_slice_for_root_backward_and_leaf_forward():
    events, graph = _chain_graph()

    # Nothing fed the goal; nothing consumed the last rollback result.
    root = backward_slice(events, graph, "wsl-u1")
    leaf = forward_slice(events, graph, "wsl-t3")

    assert root["slice"] == [] and root["size"] == 0 and root["truncated"] is False
    assert leaf["slice"] == [] and leaf["size"] == 0 and leaf["truncated"] is False


def test_missing_node_yields_empty_result_not_an_error():
    events, graph = _chain_graph()

    for direction_fn, direction in ((backward_slice, "backward"), (forward_slice, "forward")):
        result = direction_fn(events, graph, "wsl-does-not-exist")
        assert result == {
            "node_id": "wsl-does-not-exist",
            "direction": direction,
            "slice": [],
            "size": 0,
            "truncated": False,
        }


def test_empty_session_yields_empty_graph_and_empty_slices():
    graph = SessionAuditEngine().build_evidence_graph([])

    result = backward_slice([], graph, "wsl-any")
    assert result["slice"] == []
    assert result["size"] == 0
    assert damage_radius([], graph, None)["slice"] == []


def test_slice_terminates_on_cyclic_graph():
    # A hand-built dependence cycle (causal edges both ways plus an
    # evidence citation): traversal must terminate via the seen set.
    events = [
        _decision("wsl-cy1", confidence=0.9, chosen_action="probe"),
        _event(
            "wsl-cy2",
            EventType.TOOL_RESULT,
            parent_id="wsl-cy1",
            tool_name="probe",
            result={},
        ),
    ]
    graph = {
        "session_id": "wsl-session",
        "nodes": [
            {
                "event_id": "wsl-cy1",
                "event_type": "decision",
                "role": "claim",
                "label": "probe",
            },
            {
                "event_id": "wsl-cy2",
                "event_type": "tool_result",
                "role": "tool_fact",
                "label": "probe",
            },
        ],
        "edges": [
            {
                "source_id": "wsl-cy1",
                "target_id": "wsl-cy2",
                "edge_type": "evidence",
                "source_class": "tool_backed",
            },
            {
                "source_id": "wsl-cy1",
                "target_id": "wsl-cy2",
                "edge_type": "causal",
                "source_class": None,
            },
            {
                "source_id": "wsl-cy2",
                "target_id": "wsl-cy1",
                "edge_type": "causal",
                "source_class": None,
            },
        ],
        "stats": {},
    }

    assert _ids(forward_slice(events, graph, "wsl-cy1")) == ["wsl-cy2"]
    backward = backward_slice(events, graph, "wsl-cy1")
    assert _ids(backward) == ["wsl-cy2"]
    assert backward["slice"][0]["via"] == "causal"
