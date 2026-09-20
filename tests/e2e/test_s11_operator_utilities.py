"""E2E S11 — operator utilities: search, export, cost, stepper, baseline.

Covers the day-to-day surfaces around the audit: finding events across
sessions, exporting a session, checking spend, setting a debugger breakpoint,
and reading an agent baseline built from real captured runs.
"""

from __future__ import annotations

import pytest

from .agents import checkpointed_pipeline_agent, grounded_support_agent, triage_agent_run
from .conftest import run_scenario

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_trace_search_finds_events_across_sessions(api, e2e_sdk):
    await run_scenario(grounded_support_agent())
    result = await run_scenario(checkpointed_pipeline_agent())

    resp = await api.get("/api/traces/search", params={"query": "warehouse"})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results, "warehouse_load failure must be findable"
    assert any(r["session_id"] == result.session_id for r in results)


async def test_search_scopes_to_event_type(api, e2e_sdk):
    await run_scenario(grounded_support_agent())
    resp = await api.get(
        "/api/traces/search",
        params={"query": "policy", "event_type": "tool_result"},
    )
    assert resp.status_code == 200
    for hit in resp.json()["results"]:
        assert hit["event_type"].lower() == "tool_result"


async def test_export_returns_the_full_session_json(api, e2e_sdk):
    result = await run_scenario(grounded_support_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/export")
    assert resp.status_code == 200
    export = resp.json()
    assert export["session"]["id"] == result.session_id
    exported_ids = {event["id"] for event in export["events"]}
    assert result.event_ids["decision"] in exported_ids
    assert result.event_ids["search"] in exported_ids


async def test_cost_endpoints_answer(api, e2e_sdk):
    result = await run_scenario(grounded_support_agent())
    summary = await api.get("/api/cost/summary")
    assert summary.status_code == 200
    per_session = await api.get(f"/api/cost/sessions/{result.session_id}")
    assert per_session.status_code == 200
    body = per_session.json()
    assert body["session_id"] == result.session_id


async def test_stepper_breakpoint_and_step(api, e2e_sdk):
    result = await run_scenario(checkpointed_pipeline_agent())

    create = await api.post(
        f"/api/sessions/{result.session_id}/breakpoints",
        params={
            "breakpoint_type": "event_type",
            "condition_value": "TOOL_RESULT",
            "description": "break on tool results",
        },
    )
    assert create.status_code == 200, create.text

    step = await api.post(
        f"/api/sessions/{result.session_id}/step",
        params={"action": "continue"},
    )
    assert step.status_code == 200, step.text
    body = step.json()
    assert "step_result" in body
    assert body["step_result"]["message"]


async def test_agent_baseline_builds_from_real_runs(api, e2e_sdk):
    await run_scenario(triage_agent_run(fail_at_step=0))
    await run_scenario(triage_agent_run(fail_at_step=2))

    resp = await api.get("/api/agents/triage_agent/baseline")
    assert resp.status_code == 200
    baseline = resp.json()
    assert baseline["agent_name"] == "triage_agent"
    assert baseline["session_count"] >= 2
    assert baseline["error_rate"] > 0
