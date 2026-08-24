"""E2E S9 — multi-agent crew: swimlanes, message flows, coordination surfaces."""

from __future__ import annotations

import pytest

from .agents import multi_agent_crew
from .conftest import run_scenario

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_swimlanes_show_one_lane_per_agent(api, e2e_sdk):
    result = await run_scenario(multi_agent_crew())
    resp = await api.get(f"/api/sessions/{result.session_id}/swimlane")
    assert resp.status_code == 200
    lanes = resp.json()["swimlane_data"]["lanes"]
    assert set(lanes) == {"agent_planner", "agent_critic", "agent_worker"}
    worker_events = lanes["agent_worker"]["events"]
    assert len(worker_events) >= 2


async def test_delegation_creates_inter_agent_message_flow(api, e2e_sdk):
    result = await run_scenario(multi_agent_crew())
    resp = await api.get(f"/api/sessions/{result.session_id}/messages")
    assert resp.status_code == 200
    body = resp.json()
    flows = body["message_flows"]
    assert flows, "planner->worker delegation must produce a message flow"
    flow = flows[0]
    assert flow["from_agent_id"] == "agent_planner"
    assert flow["to_agent_id"] == "agent_worker"
    assert body["flow_summary"]["total_flows"] >= 1


async def test_coordination_analysis_runs(api, e2e_sdk):
    result = await run_scenario(multi_agent_crew())
    resp = await api.post(f"/api/sessions/{result.session_id}/coordination-analysis")
    assert resp.status_code == 200
    assert resp.json()  # non-empty analysis payload


async def test_multi_agent_analysis_sees_all_participants(api, e2e_sdk):
    result = await run_scenario(multi_agent_crew())
    resp = await api.get(f"/api/sessions/{result.session_id}/multi-agent-analysis")
    assert resp.status_code == 200
    body = resp.json()
    assert "coordination_analysis" in body
    assert body["session_info"]["agent_name"] == "escalation_crew"
    assert len(body["swimlane_data"]["lanes"]) == 3
