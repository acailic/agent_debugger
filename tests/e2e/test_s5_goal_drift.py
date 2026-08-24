"""E2E S5 — goal drift: trailing decisions stop referencing the objective."""

from __future__ import annotations

import pytest

from .agents import goal_drift_agent
from .conftest import run_scenario

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_goal_drift_flagged_with_first_drifted_decision(api, e2e_sdk):
    result = await run_scenario(goal_drift_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/audit")
    assert resp.status_code == 200
    audit = resp.json()["audit"]

    drift = audit["goal_drift"]
    assert drift["objective"] == "migrate the billing database to the new cluster"
    assert drift["objective_referenced"] is True
    assert drift["drifted"] is True
    assert drift["first_drift_event_id"] == result.event_ids["off_task_1"]
    assert drift["decisions_after_last_reference"] == 2


async def test_goal_drift_emits_signal_and_review_point(api, e2e_sdk):
    result = await run_scenario(goal_drift_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/audit")
    audit = resp.json()["audit"]

    drift_signals = [s for s in audit["signals"] if s["type"] == "goal_drift"]
    assert drift_signals
    assert drift_signals[0]["event_id"] == result.event_ids["off_task_1"]


async def test_adherence_series_is_ordered_and_anchored(api, e2e_sdk):
    result = await run_scenario(goal_drift_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/audit")
    audit = resp.json()["audit"]

    series = audit["goal_drift"]["adherence_series"]
    assert [point["adherent"] for point in series] == [True, False, False]
    assert series[0]["event_id"] == result.event_ids["on_task"]
    assert series[1]["event_id"] == result.event_ids["off_task_1"]
    assert series[-1]["steps_since_reference"] == 2


async def test_failure_narrative_names_drift_as_contributing_factor(api, e2e_sdk):
    result = await run_scenario(goal_drift_agent())
    resp = await api.get(f"/api/sessions/{result.session_id}/audit")
    audit = resp.json()["audit"]

    factors = audit["failure_narrative"]["mechanism"]["contributing_factors"]
    factor_types = {factor["type"] for factor in factors}
    assert "goal_drift" in factor_types
