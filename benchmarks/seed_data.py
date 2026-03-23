"""Reusable benchmark sessions for tests, demos, and seeded local data."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from agent_debugger_sdk.core.context import TraceContext
from agent_debugger_sdk.core.events import Checkpoint, TraceEvent


@dataclass
class SeedSession:
    """Materialized benchmark session data."""

    session_id: str
    events: list[TraceEvent]
    checkpoints: list[Checkpoint]


SeedRunner = Callable[[str | None], Awaitable[SeedSession]]

DEFAULT_SEED_SESSION_IDS = {
    "prompt_injection": "seed-prompt-injection",
    "evidence_grounding": "seed-evidence-grounding",
    "multi_agent_dialogue": "seed-multi-agent-dialogue",
    "prompt_policy_shift": "seed-prompt-policy-shift",
    "safety_escalation": "seed-safety-escalation",
    "looping_behavior": "seed-looping-behavior",
    "failure_cluster": "seed-failure-cluster",
    "replay_determinism": "seed-replay-determinism",
}


def _split_records(records: list[TraceEvent | Checkpoint]) -> tuple[list[TraceEvent], list[Checkpoint]]:
    events: list[TraceEvent] = []
    checkpoints: list[Checkpoint] = []
    for record in records:
        if isinstance(record, Checkpoint):
            checkpoints.append(record)
        else:
            events.append(record)
    return events, checkpoints


async def run_prompt_injection_session(session_id: str | None = None) -> SeedSession:
    session_id = session_id or DEFAULT_SEED_SESSION_IDS["prompt_injection"]
    async with TraceContext(session_id=session_id, agent_name="guardrail_agent", framework="benchmark") as ctx:
        policy_event_id = await ctx.record_prompt_policy(
            template_id="secure-router-v2",
            policy_parameters={"persona": "defensive", "risk_budget": "low"},
            speaker="router",
            state_summary="User asks for hidden system prompt and tool credentials.",
            goal="Route suspicious request safely",
        )
        await ctx.record_safety_check(
            policy_name="prompt_injection",
            outcome="block",
            risk_level="high",
            rationale="Request attempts to override hidden instructions and exfiltrate secrets.",
            blocked_action="reveal_system_prompt",
            upstream_event_ids=[policy_event_id],
        )
        await ctx.record_policy_violation(
            policy_name="prompt_injection",
            violation_type="instruction_override",
            severity="high",
            details={"source": "user_input", "signature": "ignore previous instructions"},
            upstream_event_ids=[policy_event_id],
        )
        await ctx.record_refusal(
            reason="Prompt injection attempt detected.",
            policy_name="prompt_injection",
            risk_level="high",
            blocked_action="reveal_system_prompt",
            safe_alternative="Offer high-level help without disclosing hidden instructions.",
            upstream_event_ids=[policy_event_id],
        )
        records = await ctx.get_events()

    events, checkpoints = _split_records(records)
    return SeedSession(session_id=session_id, events=events, checkpoints=checkpoints)


async def run_evidence_grounding_session(session_id: str | None = None) -> SeedSession:
    session_id = session_id or DEFAULT_SEED_SESSION_IDS["evidence_grounding"]
    async with TraceContext(session_id=session_id, agent_name="evidence_agent", framework="benchmark") as ctx:
        request_id = await ctx.record_llm_request(
            model="gpt-5.4-mini",
            messages=[{"role": "user", "content": "What is the capital of Serbia?"}],
            settings={"temperature": 0.1},
        )
        tool_call_id = await ctx.record_tool_call(
            "retrieval.search",
            {"query": "capital of Serbia"},
            upstream_event_ids=[request_id],
            parent_id=request_id,
        )
        tool_result_id = await ctx.record_tool_result(
            "retrieval.search",
            result={"facts": ["Belgrade is the capital of Serbia."], "confidence": 0.94},
            duration_ms=33.0,
            upstream_event_ids=[tool_call_id],
            parent_id=tool_call_id,
        )
        decision_id = await ctx.record_decision(
            reasoning="Use retrieved source instead of free-form recall.",
            confidence=0.31,
            evidence=[{"source": "retrieval.search", "content": "Belgrade is the capital of Serbia."}],
            evidence_event_ids=[tool_result_id],
            chosen_action="answer_with_grounded_fact",
            upstream_event_ids=[tool_result_id],
            alternatives=[{"action": "guess", "reason_rejected": "Unverifiable"}],
        )
        await ctx.record_llm_response(
            model="gpt-5.4-mini",
            content="Belgrade is the capital of Serbia.",
            usage={"input_tokens": 122, "output_tokens": 18},
            cost_usd=0.0021,
            duration_ms=241.0,
            upstream_event_ids=[decision_id],
            parent_id=request_id,
        )
        records = await ctx.get_events()

    events, checkpoints = _split_records(records)
    return SeedSession(session_id=session_id, events=events, checkpoints=checkpoints)


async def run_multi_agent_dialogue_session(session_id: str | None = None) -> SeedSession:
    session_id = session_id or DEFAULT_SEED_SESSION_IDS["multi_agent_dialogue"]
    async with TraceContext(session_id=session_id, agent_name="debate_agent", framework="benchmark") as ctx:
        first_turn = await ctx.record_agent_turn(
            agent_id="planner",
            speaker="planner",
            turn_index=1,
            goal="Propose a retrieval-first plan",
            content="Let us gather external evidence before answering.",
        )
        await ctx.record_prompt_policy(
            template_id="debate-turn",
            policy_parameters={"stance": "evidence_first"},
            speaker="critic",
            state_summary="Planner suggested retrieval-first answer path.",
            goal="Challenge unsupported assumptions",
            upstream_event_ids=[first_turn],
        )
        second_turn = await ctx.record_agent_turn(
            agent_id="critic",
            speaker="critic",
            turn_index=2,
            goal="Stress test the plan",
            content="What if the retrieval result is stale or contradictory?",
            upstream_event_ids=[first_turn],
        )
        await ctx.record_decision(
            reasoning="Debate reveals the need to verify freshness before responding.",
            confidence=0.44,
            evidence=[{"source": "critic", "content": "Need freshness check"}],
            chosen_action="perform_freshness_check",
            upstream_event_ids=[second_turn],
        )
        records = await ctx.get_events()

    events, checkpoints = _split_records(records)
    return SeedSession(session_id=session_id, events=events, checkpoints=checkpoints)


async def run_prompt_policy_shift_session(session_id: str | None = None) -> SeedSession:
    session_id = session_id or DEFAULT_SEED_SESSION_IDS["prompt_policy_shift"]
    async with TraceContext(session_id=session_id, agent_name="policy_router", framework="benchmark") as ctx:
        router_policy_id = await ctx.record_prompt_policy(
            template_id="router-v3",
            policy_parameters={"mode": "fast_path", "delegation": "light"},
            speaker="router",
            state_summary="Low-risk factual query arrives.",
            goal="Answer quickly with evidence",
        )
        request_id = await ctx.record_llm_request(
            model="gpt-5.4-mini",
            messages=[{"role": "user", "content": "Summarize the finding and cite evidence."}],
            settings={"temperature": 0.2},
            upstream_event_ids=[router_policy_id],
        )
        responder_policy_id = await ctx.record_prompt_policy(
            template_id="responder-v2",
            policy_parameters={"citation_style": "explicit", "verbosity": "tight"},
            speaker="responder",
            state_summary="Router approved evidence-first answer path.",
            goal="Produce concise cited answer",
            upstream_event_ids=[request_id],
        )
        await ctx.record_llm_response(
            model="gpt-5.4-mini",
            content="Belgrade is the capital of Serbia, based on the retrieved evidence.",
            usage={"input_tokens": 140, "output_tokens": 24},
            cost_usd=0.0028,
            duration_ms=286.0,
            upstream_event_ids=[responder_policy_id],
            parent_id=request_id,
        )
        records = await ctx.get_events()

    events, checkpoints = _split_records(records)
    return SeedSession(session_id=session_id, events=events, checkpoints=checkpoints)


async def run_safety_escalation_session(session_id: str | None = None) -> SeedSession:
    session_id = session_id or DEFAULT_SEED_SESSION_IDS["safety_escalation"]
    async with TraceContext(session_id=session_id, agent_name="guarded_tool_agent", framework="benchmark") as ctx:
        policy_id = await ctx.record_prompt_policy(
            template_id="tool-guard-v4",
            policy_parameters={"allow_external_writes": False, "risk_budget": "medium"},
            speaker="controller",
            state_summary="User asks for external system modification.",
            goal="Assess and constrain tool use",
        )
        request_id = await ctx.record_llm_request(
            model="gpt-5.4",
            messages=[{"role": "user", "content": "Update the production payroll records immediately."}],
            settings={"temperature": 0.0},
            upstream_event_ids=[policy_id],
        )
        tool_call_id = await ctx.record_tool_call(
            "hr.write_payroll",
            {"scope": "production", "operation": "update"},
            upstream_event_ids=[request_id],
            parent_id=request_id,
        )
        await ctx.record_safety_check(
            policy_name="destructive_tool_use",
            outcome="warn",
            risk_level="medium",
            rationale="Requested action targets production records without approval context.",
            blocked_action=None,
            upstream_event_ids=[tool_call_id],
        )
        tool_result_id = await ctx.record_tool_result(
            "hr.write_payroll",
            result=None,
            error="Approval token missing",
            duration_ms=71.0,
            upstream_event_ids=[tool_call_id],
            parent_id=tool_call_id,
        )
        await ctx.create_checkpoint(
            state={"phase": "guard-escalation", "approval_token": None},
            memory={"last_tool_result_id": tool_result_id},
            importance=0.91,
        )
        await ctx.record_safety_check(
            policy_name="destructive_tool_use",
            outcome="block",
            risk_level="high",
            rationale="Tool failed without approval token and cannot be retried safely.",
            blocked_action="hr.write_payroll",
            upstream_event_ids=[tool_result_id],
        )
        await ctx.record_policy_violation(
            policy_name="destructive_tool_use",
            violation_type="missing_approval_token",
            severity="high",
            details={"tool_name": "hr.write_payroll"},
            upstream_event_ids=[tool_result_id],
        )
        await ctx.record_refusal(
            reason="Cannot modify production payroll without an approval token.",
            policy_name="destructive_tool_use",
            risk_level="high",
            blocked_action="hr.write_payroll",
            safe_alternative="Ask for a valid approval token or use the sandbox environment.",
            upstream_event_ids=[tool_result_id],
        )
        records = await ctx.get_events()

    events, checkpoints = _split_records(records)
    return SeedSession(session_id=session_id, events=events, checkpoints=checkpoints)


async def run_looping_behavior_session(session_id: str | None = None) -> SeedSession:
    session_id = session_id or DEFAULT_SEED_SESSION_IDS["looping_behavior"]
    async with TraceContext(session_id=session_id, agent_name="looping_agent", framework="benchmark") as ctx:
        first_call = await ctx.record_tool_call("search", {"query": "capital of Serbia"})
        second_call = await ctx.record_tool_call("search", {"query": "capital of Serbia again"}, parent_id=first_call)
        await ctx.record_tool_call("search", {"query": "capital of Serbia retry"}, parent_id=second_call)
        records = await ctx.get_events()

    events, checkpoints = _split_records(records)
    return SeedSession(session_id=session_id, events=events, checkpoints=checkpoints)


async def run_failure_cluster_session(session_id: str | None = None) -> SeedSession:
    session_id = session_id or DEFAULT_SEED_SESSION_IDS["failure_cluster"]
    async with TraceContext(session_id=session_id, agent_name="cluster_agent", framework="benchmark") as ctx:
        for attempt in range(1, 4):
            tool_call_id = await ctx.record_tool_call(
                "catalog.lookup",
                {"sku": "missing-item", "attempt": attempt},
            )
            tool_result_id = await ctx.record_tool_result(
                "catalog.lookup",
                result=None,
                error="Item not found",
                duration_ms=20.0 + attempt,
                upstream_event_ids=[tool_call_id],
                parent_id=tool_call_id,
            )
            await ctx.record_policy_violation(
                policy_name="inventory_integrity",
                violation_type="missing_catalog_item",
                severity="high",
                details={"sku": "missing-item", "attempt": attempt},
                upstream_event_ids=[tool_result_id],
            )
        records = await ctx.get_events()

    events, checkpoints = _split_records(records)
    return SeedSession(session_id=session_id, events=events, checkpoints=checkpoints)


async def run_replay_determinism_session(session_id: str | None = None) -> SeedSession:
    session_id = session_id or DEFAULT_SEED_SESSION_IDS["replay_determinism"]
    async with TraceContext(session_id=session_id, agent_name="replay_agent", framework="benchmark") as ctx:
        tool_call_id = await ctx.record_tool_call("fetch", {"step": 1})
        tool_result_id = await ctx.record_tool_result(
            "fetch",
            {"step": 1},
            duration_ms=10.0,
            upstream_event_ids=[tool_call_id],
            parent_id=tool_call_id,
        )
        await ctx.create_checkpoint(
            state={"step": 1},
            memory={"last_event": tool_result_id},
            importance=0.9,
        )
        decision_id = await ctx.record_decision(
            reasoning="Tool output conflicts with policy.",
            confidence=0.22,
            evidence=[{"source": "fetch", "content": "Conflicting result"}],
            evidence_event_ids=[tool_result_id],
            chosen_action="block",
            upstream_event_ids=[tool_result_id],
        )
        await ctx.record_refusal(
            reason="Unsafe to proceed after conflicting evidence.",
            policy_name="conflict_guard",
            blocked_action="continue_execution",
            upstream_event_ids=[decision_id],
        )
        records = await ctx.get_events()

    events, checkpoints = _split_records(records)
    return SeedSession(session_id=session_id, events=events, checkpoints=checkpoints)


def iter_seed_scenarios() -> list[tuple[str, SeedRunner]]:
    """Return demo and benchmark scenarios in a stable order."""
    return [
        ("prompt_injection", run_prompt_injection_session),
        ("evidence_grounding", run_evidence_grounding_session),
        ("multi_agent_dialogue", run_multi_agent_dialogue_session),
        ("prompt_policy_shift", run_prompt_policy_shift_session),
        ("safety_escalation", run_safety_escalation_session),
        ("looping_behavior", run_looping_behavior_session),
        ("failure_cluster", run_failure_cluster_session),
        ("replay_determinism", run_replay_determinism_session),
    ]
