"""E2E S2 — overconfident deploy agent: contradiction, narrative, do-not-act."""

from __future__ import annotations

import httpx
import pytest

from .agents import overconfident_failure_agent
from .conftest import run_scenario

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def _audit(api: httpx.AsyncClient, session_id: str) -> dict:
    resp = await api.get(f"/api/sessions/{session_id}/audit")
    assert resp.status_code == 200
    return resp.json()["audit"]


async def test_confident_decision_is_contradicted_by_failing_subtree(api, e2e_sdk):
    result = await run_scenario(overconfident_failure_agent())
    audit = await _audit(api, result.session_id)

    contradicted = next(
        c for c in audit["claims"] if c["event_id"] == result.event_ids["decision"]
    )
    assert contradicted["verification_status"] == "contradicted"
    assert contradicted["contradicted"] is True

    unsupported = next(
        c for c in audit["claims"]
        if c["event_id"] == result.event_ids["unsupported_decision"]
    )
    assert unsupported["verification_status"] == "unsupported"


async def test_failure_narrative_localizes_the_deploy_failure(api, e2e_sdk):
    result = await run_scenario(overconfident_failure_agent())
    audit = await _audit(api, result.session_id)

    narrative = audit["failure_narrative"]
    assert narrative["available"] is True
    assert narrative["symptom"]["failure_event_id"] == result.event_ids["failure"]
    assert narrative["mechanism"]["localized"] is True
    assert narrative["next_inspection"]["event_id"]
    chain_ids = {item["event_id"] for item in narrative["mechanism"]["cause_chain"]}
    assert result.event_ids["failure"] in chain_ids
    assert narrative["confidence"] > 0.4
    assert narrative["narrative"].startswith("Symptom:")


async def test_verdict_fails_with_do_not_act_band(api, e2e_sdk):
    result = await run_scenario(overconfident_failure_agent())
    audit = await _audit(api, result.session_id)

    assert audit["trust"]["band"] == "low"
    assert audit["summary"]["verdict"] == "fail"
    assert audit["summary"]["trust_band_label"] == "do-not-act"
    # Deploy is a write-like tool call — the stakes line must say state changed.
    assert audit["summary"]["stakes"]["mutating"] is True
    assert audit["summary"]["stakes"]["write_like_calls"] >= 1


async def test_first_bad_decision_and_review_points_surface(api, e2e_sdk):
    result = await run_scenario(overconfident_failure_agent())
    audit = await _audit(api, result.session_id)

    assert (
        audit["questions"]["where_it_failed"]["first_bad_decision"]
        == result.event_ids["decision"]
    )
    priorities = [point["priority"] for point in audit["review_points"]]
    assert "high" in priorities
    review_event_ids = {point["event_id"] for point in audit["review_points"]}
    assert result.event_ids["decision"] in review_event_ids


async def test_decision_justification_drill_down(api, e2e_sdk):
    result = await run_scenario(overconfident_failure_agent())
    resp = await api.get(
        f"/api/sessions/{result.session_id}/decisions/{result.event_ids['decision']}/justification"
    )
    assert resp.status_code == 200
    justification = resp.json()["justification"]
    assert justification["where_it_failed"]["contradicted"] is True
    assert justification["outcome"]["downstream_failures"] >= 1
    assert justification["evidence"]["verification_status"] == "contradicted"
