"""E2E S4 — retry loop: repeated failed strategy + behavior alert + low trust."""

from __future__ import annotations

import pytest

from .agents import retry_loop_agent
from .conftest import run_scenario

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_repeated_failed_strategy_signal_fires(api, e2e_sdk):
    result = await run_scenario(retry_loop_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/audit")
    assert resp.status_code == 200
    audit = resp.json()["audit"]

    repeated = [s for s in audit["signals"] if s["type"] == "repeated_failed_strategy"]
    assert repeated, "expected repeated_failed_strategy signal"
    assert repeated[0]["severity"] == "high"
    assert "crm_sync" in repeated[0]["message"]
    assert repeated[0]["event_id"]


async def test_loop_alert_lands_as_localized_failure(api, e2e_sdk):
    result = await run_scenario(retry_loop_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/audit")
    audit = resp.json()["audit"]

    modes = {failure["mode"] for failure in audit["failures"]}
    assert modes & {"looping_behavior", "behavior_anomaly", "tool_execution_failure"}
    narrative = audit["failure_narrative"]
    assert narrative["available"] is True
    assert narrative["symptom"]["mechanism_category"] in {
        "repeated_failed_strategy",
        "behavior_anomaly",
        "tool_invocation_failed",
        "decision_without_evidence",
    }


async def test_loop_run_never_reaches_high_trust(api, e2e_sdk):
    result = await run_scenario(retry_loop_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/audit")
    audit = resp.json()["audit"]

    assert audit["trust"]["band"] == "low"
    assert audit["summary"]["verdict"] == "fail"
    # The run hammered a read-like sync tool — stakes stay non-mutating.
    assert audit["summary"]["stakes"]["mutating"] is False


async def test_behavior_alert_visible_in_trace(api, e2e_sdk):
    result = await run_scenario(retry_loop_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/trace")
    events = resp.json()["events"]
    alerts = [e for e in events if e["event_type"].upper() == "BEHAVIOR_ALERT"]
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "tool_loop"
