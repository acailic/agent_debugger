from __future__ import annotations

import asyncio

import pytest


# Set a no-op event persister so TraceContext never creates HTTP transport.
# This must happen before importing benchmarks (which creates TraceContext
# instances that would otherwise try to connect to localhost:8000).
async def _noop_persist(event):  # noqa: ARG001
    """No-op persister to prevent HTTP transport creation."""
    pass


from agent_debugger_sdk.core.context import configure_event_pipeline  # noqa: E402

configure_event_pipeline(None, persist_event=_noop_persist)


@pytest.fixture(autouse=True)
def _reconfigure_noop_pipeline():
    """Re-configure the no-op pipeline before each test.

    xdist workers share processes: another test may call
    configure_event_pipeline(persist_event=None), resetting the
    ContextVar.  This fixture restores the no-op before every test.
    """
    configure_event_pipeline(None, persist_event=_noop_persist)
    yield

from benchmarks import (  # noqa: E402
    run_evidence_grounding_session,
    run_failure_cluster_session,
    run_looping_behavior_session,
    run_multi_agent_dialogue_session,
    run_prompt_injection_session,
    run_prompt_policy_shift_session,
    run_replay_determinism_session,
    run_safety_escalation_session,
)
from collector.intelligence.facade import TraceIntelligence  # noqa: E402
from collector.replay import build_replay  # noqa: E402


def test_prompt_injection_refusal_benchmark():
    seeded = asyncio.run(run_prompt_injection_session("prompt-injection-benchmark"))
    event_types = [event.event_type.value for event in seeded.events]
    assert "prompt_policy" in event_types
    assert "safety_check" in event_types
    assert "policy_violation" in event_types
    assert "refusal" in event_types

    analysis = TraceIntelligence().analyze_session(seeded.events, seeded.checkpoints)
    refusal_id = next(event.id for event in seeded.events if event.event_type.value == "refusal")
    assert refusal_id in analysis["high_replay_value_ids"]


def test_evidence_grounded_decision_benchmark():
    seeded = asyncio.run(run_evidence_grounding_session("evidence-benchmark"))
    tool_result_id = next(event.id for event in seeded.events if event.event_type.value == "tool_result")
    decision = next(event for event in seeded.events if event.event_type.value == "decision")
    assert decision.evidence_event_ids == [tool_result_id]
    assert decision.upstream_event_ids == [tool_result_id]


def test_multi_agent_dialogue_benchmark():
    seeded = asyncio.run(run_multi_agent_dialogue_session("multi-agent-benchmark"))
    event_types = [event.event_type.value for event in seeded.events]
    assert event_types.count("agent_turn") == 2
    assert "prompt_policy" in event_types


def test_looping_behavior_alert_benchmark():
    seeded = asyncio.run(run_looping_behavior_session("looping-behavior-benchmark"))
    analysis = TraceIntelligence().analyze_session(seeded.events, checkpoints=[])
    assert analysis["behavior_alerts"]
    assert analysis["behavior_alerts"][0]["alert_type"] == "tool_loop"


def test_replay_determinism_benchmark():
    seeded = asyncio.run(run_replay_determinism_session("replay-benchmark"))
    checkpoint_id = seeded.checkpoints[0].id
    refusal_id = next(event.id for event in seeded.events if event.event_type.value == "refusal")
    failure_replay = build_replay(seeded.events, seeded.checkpoints, mode="failure", focus_event_id=None)
    focus_replay = build_replay(seeded.events, seeded.checkpoints, mode="focus", focus_event_id=refusal_id)

    assert checkpoint_id == failure_replay["nearest_checkpoint"]["id"]
    assert checkpoint_id == focus_replay["nearest_checkpoint"]["id"]
    assert failure_replay["events"][-1]["event_type"] == "refusal"
    assert focus_replay["events"][-1]["event_type"] == "refusal"


def test_prompt_policy_shift_benchmark():
    seeded = asyncio.run(run_prompt_policy_shift_session("prompt-policy-shift-benchmark"))
    prompt_policies = [event for event in seeded.events if event.event_type.value == "prompt_policy"]
    llm_request = next(event for event in seeded.events if event.event_type.value == "llm_request")
    llm_response = next(event for event in seeded.events if event.event_type.value == "llm_response")

    assert len(prompt_policies) == 2
    assert llm_request.upstream_event_ids == [prompt_policies[0].id]
    assert llm_response.parent_id == llm_request.id


def test_failure_cluster_benchmark():
    seeded = asyncio.run(run_failure_cluster_session("failure-cluster-benchmark"))
    analysis = TraceIntelligence().analyze_session(seeded.events, seeded.checkpoints)

    assert analysis["failure_clusters"]
    assert analysis["failure_clusters"][0]["count"] >= 2
    assert analysis["representative_failure_ids"][0] in analysis["failure_clusters"][0]["event_ids"]


def test_safety_escalation_breakpoint_benchmark():
    seeded = asyncio.run(run_safety_escalation_session("safety-escalation-benchmark"))
    replay = build_replay(
        seeded.events,
        seeded.checkpoints,
        mode="failure",
        focus_event_id=None,
        breakpoint_safety_outcomes={"warn", "block"},
    )

    assert replay["nearest_checkpoint"] is not None
    assert any(event["event_type"] == "safety_check" for event in replay["breakpoints"])
