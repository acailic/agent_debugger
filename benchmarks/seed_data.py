"""Reusable benchmark sessions for tests, demos, and seeded local data."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from agent_debugger_sdk.core.context import TraceContext
from agent_debugger_sdk.core.events import Checkpoint, TraceEvent


@dataclass
class SeedSession:
    """Materialized benchmark session data."""

    session_id: str
    events: list[TraceEvent]
    checkpoints: list[Checkpoint]
    session_overrides: dict[str, object] = field(default_factory=dict)


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
    "replay_breakpoints": "seed-replay-breakpoints",
    "retention_recent_failure": "seed-retention-recent-failure",
    "retention_stale_failure": "seed-retention-stale-failure",
    "repair_memory": "seed-repair-memory",
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


def _retime_records(records: list[TraceEvent | Checkpoint], *, age_days: int) -> dict[str, object]:
    """Shift a seed session's timestamps so it lands at a target age in days."""
    target_end = datetime.now(timezone.utc) - timedelta(days=age_days)
    timestamps = [record.timestamp for record in records if getattr(record, "timestamp", None) is not None]
    if not timestamps:
        return {"started_at": target_end, "ended_at": target_end}

    current_end = max(timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc) for timestamp in timestamps)
    delta = target_end - current_end

    for record in records:
        timestamp = getattr(record, "timestamp", None)
        if timestamp is None:
            continue
        aware_timestamp = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
        record.timestamp = aware_timestamp + delta

    shifted_timestamps = [record.timestamp for record in records if getattr(record, "timestamp", None) is not None]
    return {
        "started_at": min(shifted_timestamps),
        "ended_at": max(shifted_timestamps),
    }


async def run_prompt_injection_session(session_id: str | None = None) -> SeedSession:
    session_id = session_id or DEFAULT_SEED_SESSION_IDS["prompt_injection"]
    async with TraceContext(session_id=session_id, agent_name="guardrail_agent", framework="benchmark") as ctx:
        policy_event_id = await ctx.record_prompt_policy(
            name="Policy injection: secure routing configuration",
            template_id="secure-router-v2",
            policy_parameters={"persona": "defensive", "risk_budget": "low"},
            speaker="router",
            state_summary="User asks for hidden system prompt and tool credentials.",
            goal="Route suspicious request safely",
        )
        await ctx.record_safety_check(
            name="Safety check: prompt injection block",
            policy_name="prompt_injection",
            outcome="block",
            risk_level="high",
            rationale="Request attempts to override hidden instructions and exfiltrate secrets.",
            blocked_action="reveal_system_prompt",
            upstream_event_ids=[policy_event_id],
        )
        await ctx.record_policy_violation(
            name="Policy violation: prompt injection detected",
            policy_name="prompt_injection",
            violation_type="instruction_override",
            severity="high",
            details={
                "source": "user_input",
                "signature": "ignore previous instructions",
                "attack_type": "prompt injection",
            },
            upstream_event_ids=[policy_event_id],
        )
        await ctx.record_refusal(
            name="Refusal: prompt injection blocked",
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
        decision_id = await ctx.record_decision(
            reasoning="Debate reveals the need to verify freshness before responding.",
            confidence=0.44,
            evidence=[{"source": "critic", "content": "Need freshness check"}],
            chosen_action="perform_freshness_check",
            upstream_event_ids=[second_turn],
        )
        await ctx.record_behavior_alert(
            alert_type="role_confusion",
            severity="low",
            signal="Speaker roles may have overlapped in this exchange",
            upstream_event_ids=[decision_id],
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
            name="Safety policy: tool guard configuration",
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
            name="Tool call: hr.write_payroll",
            tool_name="hr.write_payroll",
            arguments={"scope": "production", "operation": "update"},
            upstream_event_ids=[request_id],
            parent_id=request_id,
        )
        await ctx.record_safety_check(
            name="Safety check: destructive tool use warning",
            policy_name="destructive_tool_use",
            outcome="warn",
            risk_level="medium",
            rationale="Requested action targets production records without approval context.",
            blocked_action=None,
            upstream_event_ids=[tool_call_id],
        )
        tool_result_id = await ctx.record_tool_result(
            name="Tool result: hr.write_payroll blocked",
            tool_name="hr.write_payroll",
            result=None,
            error=None,  # Don't count as session error - we'll use explicit error event
            duration_ms=71.0,
            upstream_event_ids=[tool_call_id],
            parent_id=tool_call_id,
        )
        await ctx.record_error(
            name="Error: safety approval token missing",
            error_type="ApprovalTokenMissing",
            error_message="Approval token missing for hr.write_payroll tool call",
        )
        await ctx.create_checkpoint(
            state={"phase": "guard-escalation", "approval_token": None},
            memory={"last_tool_result_id": tool_result_id},
            importance=0.91,
        )
        await ctx.record_safety_check(
            name="Safety check: block destructive tool use",
            policy_name="destructive_tool_use",
            outcome="block",
            risk_level="high",
            rationale="Tool failed without approval token and cannot be retried safely.",
            blocked_action="hr.write_payroll",
            upstream_event_ids=[tool_result_id],
        )
        await ctx.record_policy_violation(
            name="Policy violation: safety escalation required",
            policy_name="destructive_tool_use",
            violation_type="missing_approval_token",
            severity="high",
            details={"tool_name": "hr.write_payroll", "safety_check": "required"},
            upstream_event_ids=[tool_result_id],
        )
        await ctx.record_refusal(
            name="Refusal: safety escalation blocked tool call",
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
        third_call = await ctx.record_tool_call("search", {"query": "capital of Serbia retry"}, parent_id=second_call)
        await ctx.record_behavior_alert(
            alert_type="oscillation",
            severity="high",
            signal="Agent repeated the same action 3+ times without progress",
            upstream_event_ids=[third_call],
        )
        records = await ctx.get_events()

    events, checkpoints = _split_records(records)
    return SeedSession(session_id=session_id, events=events, checkpoints=checkpoints)


async def run_failure_cluster_session(session_id: str | None = None) -> SeedSession:
    session_id = session_id or DEFAULT_SEED_SESSION_IDS["failure_cluster"]
    async with TraceContext(session_id=session_id, agent_name="cluster_agent", framework="benchmark") as ctx:
        last_violation_id = None
        for attempt in range(1, 4):
            tool_call_id = await ctx.record_tool_call(
                name=f"Tool call: catalog lookup failure attempt {attempt}",
                tool_name="catalog.lookup",
                arguments={"sku": "missing-item", "attempt": attempt},
            )
            tool_result_id = await ctx.record_tool_result(
                name=f"Tool result: catalog lookup failure {attempt}",
                tool_name="catalog.lookup",
                result=None,
                error=None,  # Don't count as session error - we'll use explicit error events
                duration_ms=20.0 + attempt,
                upstream_event_ids=[tool_call_id],
                parent_id=tool_call_id,
            )
            await ctx.record_error(
                name=f"Error: catalog lookup failure attempt {attempt}",
                error_type="ItemNotFoundError",
                error_message=f"Catalog lookup failed for SKU 'missing-item' (attempt {attempt})",
            )
            violation_id = await ctx.record_policy_violation(
                name=f"Policy violation: catalog lookup failure {attempt}",
                policy_name="inventory_integrity",
                violation_type="missing_catalog_item",
                severity="high",
                details={"sku": "missing-item", "attempt": attempt, "error": "failure"},
                upstream_event_ids=[tool_result_id],
            )
            last_violation_id = violation_id
        await ctx.record_behavior_alert(
            name="Behavior alert: failure cluster detected",
            alert_type="loop",
            severity="medium",
            signal="Repeated policy violations suggest stuck retry pattern",
            upstream_event_ids=[last_violation_id] if last_violation_id else [],
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


async def run_replay_breakpoints_session(session_id: str | None = None) -> SeedSession:
    session_id = session_id or DEFAULT_SEED_SESSION_IDS["replay_breakpoints"]
    async with TraceContext(session_id=session_id, agent_name="replay_guard_agent", framework="benchmark") as ctx:
        policy_id = await ctx.record_prompt_policy(
            name="Prompt policy: refund approval workflow",
            template_id="refund-guard-v2",
            policy_parameters={"require_manual_approval": True, "confidence_floor": 0.4},
            speaker="controller",
            state_summary="User requests a production refund for a disputed invoice.",
            goal="Validate whether replay should pause on uncertainty or safety escalation.",
        )
        request_id = await ctx.record_llm_request(
            model="gpt-5.4",
            messages=[{"role": "user", "content": "Issue the refund now; finance is waiting."}],
            settings={"temperature": 0.0},
            upstream_event_ids=[policy_id],
        )
        tool_call_id = await ctx.record_tool_call(
            name="Tool call: payments.lookup_refund_eligibility",
            tool_name="payments.lookup_refund_eligibility",
            arguments={"invoice_id": "inv-778", "environment": "production"},
            upstream_event_ids=[request_id],
            parent_id=request_id,
        )
        tool_result_id = await ctx.record_tool_result(
            name="Tool result: payments.lookup_refund_eligibility inconclusive",
            tool_name="payments.lookup_refund_eligibility",
            result={"eligibility": "unknown", "approval_token": None, "ledger_state": "stale"},
            error=None,
            duration_ms=148.0,
            upstream_event_ids=[tool_call_id],
            parent_id=tool_call_id,
        )
        await ctx.create_checkpoint(
            state={"phase": "refund-review", "approval_token": None},
            memory={"last_tool_result_id": tool_result_id},
            importance=0.88,
        )
        decision_id = await ctx.record_decision(
            name="Decision: low-confidence refund path",
            reasoning="Eligibility lookup is stale, but the request appears urgent enough to keep evaluating a refund path.",
            confidence=0.24,
            evidence=[
                {"source": "payments.lookup_refund_eligibility", "content": "Eligibility unknown; approval token missing."},
            ],
            evidence_event_ids=[tool_result_id],
            chosen_action="prepare_refund_execution",
            upstream_event_ids=[tool_result_id],
            alternatives=[
                {"action": "halt_immediately", "reason_rejected": "Need one more safety gate before refusing."},
            ],
        )
        warning_id = await ctx.record_safety_check(
            name="Safety check: refund execution warning",
            policy_name="refund_guard",
            outcome="warn",
            risk_level="medium",
            rationale="Refund path is being prepared without a verified approval token or fresh ledger state.",
            blocked_action=None,
            upstream_event_ids=[decision_id],
        )
        execution_call_id = await ctx.record_tool_call(
            name="Tool call: payments.issue_refund",
            tool_name="payments.issue_refund",
            arguments={"invoice_id": "inv-778", "approval_token": None},
            upstream_event_ids=[warning_id, request_id],
            parent_id=warning_id,
        )
        block_id = await ctx.record_safety_check(
            name="Safety check: block refund execution",
            policy_name="refund_guard",
            outcome="block",
            risk_level="high",
            rationale="Refund execution cannot proceed without verified eligibility and a manual approval token.",
            blocked_action="payments.issue_refund",
            upstream_event_ids=[execution_call_id],
        )
        await ctx.record_refusal(
            name="Refusal: refund execution blocked",
            reason="Cannot issue a production refund until eligibility is refreshed and approval is present.",
            policy_name="refund_guard",
            risk_level="high",
            blocked_action="payments.issue_refund",
            safe_alternative="Refresh ledger state, obtain approval, and resume from the refund-review checkpoint.",
            upstream_event_ids=[block_id],
        )
        records = await ctx.get_events()

    events, checkpoints = _split_records(records)
    return SeedSession(session_id=session_id, events=events, checkpoints=checkpoints)


async def _run_retention_failure_session(session_id: str, *, age_days: int) -> SeedSession:
    async with TraceContext(session_id=session_id, agent_name="retention_agent", framework="benchmark") as ctx:
        policy_id = await ctx.record_prompt_policy(
            name="Prompt policy: credit adjustment guard",
            template_id="credit-adjustment-v1",
            policy_parameters={"auto_apply_limit": 0, "manual_review_required": True},
            speaker="controller",
            state_summary="Customer requests an immediate production credit adjustment.",
            goal="Preserve a compact but meaningful failure trace for retention scoring.",
        )
        request_id = await ctx.record_llm_request(
            model="gpt-5.4-mini",
            messages=[{"role": "user", "content": "Apply the disputed credit right now."}],
            settings={"temperature": 0.1},
            upstream_event_ids=[policy_id],
        )
        tool_call_id = await ctx.record_tool_call(
            name="Tool call: billing.lookup_credit_status",
            tool_name="billing.lookup_credit_status",
            arguments={"account_id": "acct-778", "environment": "production"},
            upstream_event_ids=[request_id],
            parent_id=request_id,
        )
        tool_result_id = await ctx.record_tool_result(
            name="Tool result: billing.lookup_credit_status incomplete",
            tool_name="billing.lookup_credit_status",
            result=None,
            error="Account balance snapshot has not propagated yet.",
            duration_ms=96.0,
            upstream_event_ids=[tool_call_id],
            parent_id=tool_call_id,
        )
        decision_id = await ctx.record_decision(
            name="Decision: tentative credit adjustment path",
            reasoning="The request looks plausible, but the adjustment should wait until the balance snapshot stabilizes.",
            confidence=0.8,
            evidence=[{"source": "billing.lookup_credit_status", "content": "Balance snapshot missing; eligibility cannot be confirmed."}],
            evidence_event_ids=[tool_result_id],
            chosen_action="queue_manual_credit_review",
            upstream_event_ids=[tool_result_id],
            alternatives=[
                {"action": "apply_credit_immediately", "reason_rejected": "Balance state is still incomplete."},
            ],
        )
        records = await ctx.get_events()

    session_overrides = _retime_records(records, age_days=age_days)
    events, checkpoints = _split_records(records)
    return SeedSession(
        session_id=session_id,
        events=events,
        checkpoints=checkpoints,
        session_overrides=session_overrides,
    )


async def run_retention_recent_failure_session(session_id: str | None = None) -> SeedSession:
    session_id = session_id or DEFAULT_SEED_SESSION_IDS["retention_recent_failure"]
    return await _run_retention_failure_session(session_id, age_days=2)


async def run_retention_stale_failure_session(session_id: str | None = None) -> SeedSession:
    session_id = session_id or DEFAULT_SEED_SESSION_IDS["retention_stale_failure"]
    return await _run_retention_failure_session(session_id, age_days=45)


async def run_repair_memory_session(session_id: str | None = None) -> SeedSession:
    session_id = session_id or DEFAULT_SEED_SESSION_IDS["repair_memory"]
    async with TraceContext(session_id=session_id, agent_name="repair_agent", framework="benchmark") as ctx:
        request_id = await ctx.record_llm_request(
            model="gpt-5.4",
            messages=[{"role": "user", "content": "Fix the flaky outbound invoice sync timeout."}],
            settings={"temperature": 0.0},
        )
        tool_call_id = await ctx.record_tool_call(
            "billing.sync_invoice",
            {"invoice_id": "inv-404", "mode": "production"},
            upstream_event_ids=[request_id],
            parent_id=request_id,
        )
        tool_result_id = await ctx.record_tool_result(
            "billing.sync_invoice",
            result=None,
            error=None,
            duration_ms=1820.0,
            upstream_event_ids=[tool_call_id],
            parent_id=tool_call_id,
        )
        error_id = await ctx.record_error(
            name="Error: invoice sync timeout",
            error_type="TimeoutError",
            error_message="Invoice sync timed out after waiting for upstream approval service.",
        )
        repair_sequence_id = f"{session_id}:repair-sequence"
        first_attempt_id = await ctx.record_repair_attempt(
            attempted_fix="Retry the request once with the existing timeout.",
            validation_result="Timeout reproduced under the same load pattern.",
            repair_outcome="failure",
            repair_sequence_id=repair_sequence_id,
            repair_diff="+ retry_count: 1",
            upstream_event_ids=[error_id, tool_result_id],
            name="Repair attempt: retry once",
        )
        second_attempt_id = await ctx.record_repair_attempt(
            attempted_fix="Increase timeout from 15s to 30s.",
            validation_result="Reduced failures locally, but production still timed out intermittently.",
            repair_outcome="failure",
            repair_sequence_id=repair_sequence_id,
            repair_diff="- timeout_seconds: 15\n+ timeout_seconds: 30",
            upstream_event_ids=[first_attempt_id],
            name="Repair attempt: extend timeout",
        )
        successful_attempt_id = await ctx.record_repair_attempt(
            attempted_fix="Add approval-service preflight check and exponential backoff before sync.",
            validation_result="Sync completed successfully in staging and production replay.",
            repair_outcome="success",
            repair_sequence_id=repair_sequence_id,
            repair_diff="+ approval_preflight: true\n+ retry_backoff: exponential",
            upstream_event_ids=[second_attempt_id],
            name="Repair attempt: preflight and backoff",
        )
        await ctx.create_checkpoint(
            state={"phase": "repair-validated", "repair_sequence_id": repair_sequence_id},
            memory={"latest_repair_attempt_id": successful_attempt_id},
            importance=0.93,
        )
        await ctx.record_decision(
            reasoning="Prior retries and timeout-only changes failed; preflight plus backoff resolved the upstream dependency issue.",
            confidence=0.79,
            evidence=[
                {"source": "repair_validation", "content": "Preflight + backoff removed timeout failures in replay."},
            ],
            evidence_event_ids=[successful_attempt_id],
            chosen_action="persist_successful_repair_pattern",
            upstream_event_ids=[successful_attempt_id],
            alternatives=[
                {"action": "keep_timeout_only_change", "reason_rejected": "Still flaky in production"},
            ],
            name="Decision: keep successful repair",
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
        ("replay_breakpoints", run_replay_breakpoints_session),
        ("retention_recent_failure", run_retention_recent_failure_session),
        ("retention_stale_failure", run_retention_stale_failure_session),
        ("repair_memory", run_repair_memory_session),
    ]
