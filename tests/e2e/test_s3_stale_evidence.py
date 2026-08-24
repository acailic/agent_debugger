"""E2E S3 — stale evidence: newer fact existed, decision cited the old one."""

from __future__ import annotations

import pytest

from .agents import stale_evidence_agent
from .conftest import run_scenario

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_decision_on_superseded_evidence_is_stale(api, e2e_sdk):
    result = await run_scenario(stale_evidence_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/audit")
    assert resp.status_code == 200
    audit = resp.json()["audit"]

    claim = next(c for c in audit["claims"] if c["event_id"] == result.event_ids["decision"])
    assert claim["verification_status"] == "stale"
    assert "superseded" in claim["verification_basis"]


async def test_staleness_produces_risk_signal_and_review_point(api, e2e_sdk):
    result = await run_scenario(stale_evidence_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/audit")
    audit = resp.json()["audit"]

    signal_types = {s["type"] for s in audit["signals"]}
    assert "stale_evidence" in signal_types
    stale_signals = [s for s in audit["signals"] if s["type"] == "stale_evidence"]
    assert stale_signals[0]["event_id"] == result.event_ids["decision"]

    review_ids = {point["event_id"] for point in audit["review_points"]}
    assert result.event_ids["decision"] in review_ids


async def test_fresh_fact_is_visible_in_evidence_graph(api, e2e_sdk):
    result = await run_scenario(stale_evidence_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/evidence-graph")
    assert resp.status_code == 200
    graph = resp.json()["graph"]

    node_ids = {node["event_id"] for node in graph["nodes"]}
    # The fresh price update is a fact node that exists but was never cited.
    assert result.event_ids["fresh_update"] in node_ids
    cited_targets = {
        edge["target_id"] for edge in graph["edges"] if edge["edge_type"] == "evidence"
    }
    assert result.event_ids["old_sheet"] in cited_targets
    assert result.event_ids["fresh_update"] not in cited_targets
