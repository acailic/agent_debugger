"""E2E S1 — happy path: a grounded support agent must audit clean.

Exercises the full loop: SDK trace_session over real HTTP into a real server
process with real persistence, then the operator queries the audit report.
"""

from __future__ import annotations

import httpx
import pytest

from .agents import grounded_support_agent
from .conftest import run_scenario

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_grounded_session_reaches_server(api: httpx.AsyncClient, e2e_sdk):
    result = await run_scenario(grounded_support_agent())

    detail = await api.get(f"/api/sessions/{result.session_id}")
    assert detail.status_code == 200
    session = detail.json()["session"]
    assert session["agent_name"] == "support_agent"
    assert session["id"] == result.session_id


async def test_grounded_decision_is_verified_and_session_passes(api: httpx.AsyncClient, e2e_sdk):
    result = await run_scenario(grounded_support_agent())

    resp = await api.get(f"/api/sessions/{result.session_id}/audit")
    assert resp.status_code == 200
    audit = resp.json()["audit"]

    claim = next(c for c in audit["claims"] if c["event_id"] == result.event_ids["decision"])
    assert claim["verification_status"] == "verified"
    assert claim["evidence_refs"] == [result.event_ids["search"]]

    assert audit["summary"]["verdict"] in {"pass", "review"}
    assert audit["trust"]["band"] in {"medium", "high"}
    assert audit["failures"] == []
    assert audit["failure_narrative"]["available"] is False


async def test_grounded_event_tree_and_trace_roundtrip(api: httpx.AsyncClient, e2e_sdk):
    result = await run_scenario(grounded_support_agent())

    tree = await api.get(f"/api/sessions/{result.session_id}/tree")
    assert tree.status_code == 200
    assert tree.json()["session_id"] == result.session_id

    bundle = await api.get(f"/api/sessions/{result.session_id}/trace")
    assert bundle.status_code == 200
    events = bundle.json()["events"]
    assert len(events) >= 4  # turn + tool result + decision + answer turn
    assert {result.event_ids["decision"]} <= {event["id"] for event in events}
