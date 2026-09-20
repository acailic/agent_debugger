"""Deterministic scenario agents for the e2e suite.

Each function is a scripted, realistic agent run captured through the PUBLIC
SDK surface (``trace_session`` + ``record_*`` + ``create_checkpoint``), the
way a user would instrument a real agent. No LLM, no randomness: the "model"
and "tools" are inline deterministic behaviors, so every assertion downstream
(audit statuses, trust bands, narratives) is stable.

Every scenario returns a :class:`ScenarioResult` with the session id and the
event ids later assertions need. Run them via :func:`run_scenario` from the
e2e conftest so they execute in a clean SDK context (real HTTP transport).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from agent_debugger_sdk import trace_session


@dataclass
class ScenarioResult:
    """What a scenario hands back to the test for follow-up queries."""

    session_id: str
    agent_name: str
    event_ids: dict[str, str] = field(default_factory=dict)
    checkpoint_ids: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


def _sid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------------------
# S1 — grounded support agent (happy path, everything verified)
# ---------------------------------------------------------------------------


async def grounded_support_agent() -> ScenarioResult:
    """A support agent that looks up the policy before answering.

    Story: user asks about refunds for damaged items, the agent searches the
    knowledge base, finds the policy, and answers citing it. The one decision
    is grounded in a successful tool result — the audit should pass it.
    """
    session_id = _sid("e2e-grounded")
    async with trace_session("support_agent", session_id=session_id, tags=["e2e", "happy-path"]) as ctx:
        turn_id = await ctx.record_agent_turn(
            agent_id="support_agent",
            speaker="user",
            turn_index=0,
            content="What is our refund policy for damaged items?",
        )
        search_id = await ctx.record_tool_result(
            "knowledge_search",
            result={"policy": "damaged items are refundable within 30 days", "source": "policy-db"},
            duration_ms=42,
            upstream_event_ids=[turn_id],
        )
        decision_id = await ctx.record_decision(
            reasoning="knowledge search returned the damaged-items refund policy",
            confidence=0.9,
            chosen_action="answer_with_policy_quote",
            evidence_event_ids=[search_id],
            evidence=[{"source": "tool_result", "content": "refundable within 30 days"}],
            upstream_event_ids=[turn_id],
        )
        await ctx.record_agent_turn(
            agent_id="support_agent",
            speaker="assistant",
            turn_index=1,
            content="Damaged items are refundable within 30 days (policy-db).",
            upstream_event_ids=[decision_id],
        )
    return ScenarioResult(
        session_id=session_id,
        agent_name="support_agent",
        event_ids={"turn": turn_id, "search": search_id, "decision": decision_id},
    )


# ---------------------------------------------------------------------------
# S2 — overconfident agent whose plan falls apart (contradiction + narrative)
# ---------------------------------------------------------------------------


async def overconfident_failure_agent() -> ScenarioResult:
    """A deploy agent asserts success criteria it never verified, then fails.

    Story: the agent confidently decides to deploy citing a stale CI check,
    the deploy tool fails, and it then asserts the incident is resolved with
    no evidence at all. Audit expectations: the first decision is
    contradicted by its failing subtree, the second is unsupported, trust is
    low (do-not-act), and the failure narrative localizes the deploy failure.
    """
    session_id = _sid("e2e-contradicted")
    async with trace_session("deploy_agent", session_id=session_id, tags=["e2e", "failure"]) as ctx:
        turn_id = await ctx.record_agent_turn(
            agent_id="deploy_agent",
            speaker="user",
            turn_index=0,
            content="Ship version 2.3 to production and confirm the health check.",
        )
        decision_id = await ctx.record_decision(
            reasoning="CI check passed yesterday, safe to deploy now",
            confidence=0.95,
            chosen_action="deploy_version_2_3",
            evidence_event_ids=[],
            alternatives=[{"action": "wait_for_fresh_ci_run", "chosen": False}],
            upstream_event_ids=[turn_id],
        )
        await ctx.record_tool_call(
            "deploy",
            arguments={"version": "2.3", "environment": "production"},
            upstream_event_ids=[decision_id],
        )
        failure_id = await ctx.record_tool_result(
            "deploy",
            result=None,
            error="health check failed: 3 replicas crashed after rollout",
            duration_ms=8300,
            upstream_event_ids=[decision_id],
        )
        unsupported_decision_id = await ctx.record_decision(
            reasoning="",
            confidence=0.8,
            chosen_action="declare_incident_resolved",
            upstream_event_ids=[failure_id],
        )
        await ctx.record_error(
            "RolloutError",
            "production rollout aborted: replicas crash-looping",
        )
    return ScenarioResult(
        session_id=session_id,
        agent_name="deploy_agent",
        event_ids={
            "turn": turn_id,
            "decision": decision_id,
            "failure": failure_id,
            "unsupported_decision": unsupported_decision_id,
        },
    )


# ---------------------------------------------------------------------------
# S3 — stale evidence (newer fact existed, was not cited)
# ---------------------------------------------------------------------------


async def stale_evidence_agent() -> ScenarioResult:
    """A pricing agent reads an old price sheet after a fresh one landed.

    Story: the agent fetches the price sheet, a price update lands seconds
    later, and the agent then decides with the OLD sheet as its only cited
    evidence even though the newer fact existed at decision time. The claim
    should be classified ``stale``.
    """
    session_id = _sid("e2e-stale")
    async with trace_session("pricing_agent", session_id=session_id, tags=["e2e", "stale"]) as ctx:
        turn_id = await ctx.record_agent_turn(
            agent_id="pricing_agent",
            speaker="user",
            turn_index=0,
            content="Set the product price for tomorrow's campaign.",
        )
        old_sheet_id = await ctx.record_tool_result(
            "fetch_price_sheet",
            result={"product": "widget", "price": 19.99},
            duration_ms=30,
            upstream_event_ids=[turn_id],
        )
        fresh_update_id = await ctx.record_tool_result(
            "price_update_feed",
            result={"product": "widget", "price": 24.99, "effective": "immediate"},
            duration_ms=18,
            upstream_event_ids=[turn_id],
        )
        decision_id = await ctx.record_decision(
            reasoning="price sheet says 19.99",
            confidence=0.85,
            chosen_action="set_price_19_99",
            evidence_event_ids=[old_sheet_id],
            upstream_event_ids=[turn_id],
        )
    return ScenarioResult(
        session_id=session_id,
        agent_name="pricing_agent",
        event_ids={
            "turn": turn_id,
            "old_sheet": old_sheet_id,
            "fresh_update": fresh_update_id,
            "decision": decision_id,
        },
    )


# ---------------------------------------------------------------------------
# S4 — retry loop (same tool fails repeatedly, behavior alert)
# ---------------------------------------------------------------------------


async def retry_loop_agent() -> ScenarioResult:
    """A sync agent hammers a flaky API instead of changing strategy.

    Story: the same tool fails three times in a row, the monitor raises a
    tool-loop behavior alert, and the agent gives up with an error. Audit
    expectations: ``repeated_failed_strategy`` signal, loop alert visible,
    low trust.
    """
    session_id = _sid("e2e-loop")
    async with trace_session("sync_agent", session_id=session_id, tags=["e2e", "loop"]) as ctx:
        turn_id = await ctx.record_agent_turn(
            agent_id="sync_agent",
            speaker="user",
            turn_index=0,
            content="Sync the customer records to the CRM.",
        )
        decision_id = await ctx.record_decision(
            reasoning="retry the CRM sync until it works",
            confidence=0.7,
            chosen_action="call_crm_sync",
            upstream_event_ids=[turn_id],
        )
        failure_ids = []
        for attempt in range(3):
            failure_ids.append(
                await ctx.record_tool_result(
                    "crm_sync",
                    result=None,
                    error=f"503 service unavailable (attempt {attempt + 1})",
                    duration_ms=5000 + attempt * 500,
                    upstream_event_ids=[decision_id],
                )
            )
        await ctx.record_behavior_alert(
            alert_type="tool_loop",
            signal="crm_sync invoked 3 times consecutively without a strategy change",
            related_event_ids=failure_ids,
            upstream_event_ids=[decision_id],
        )
        await ctx.record_error(
            "SyncFailedError",
            "CRM sync did not succeed after 3 attempts",
        )
    return ScenarioResult(
        session_id=session_id,
        agent_name="sync_agent",
        event_ids={"turn": turn_id, "decision": decision_id, "last_failure": failure_ids[-1]},
    )


# ---------------------------------------------------------------------------
# S5 — goal drift (trailing decisions stop referencing the objective)
# ---------------------------------------------------------------------------


async def goal_drift_agent() -> ScenarioResult:
    """A research agent starts on-task, then wanders off the objective.

    Story: objective is to migrate the billing database. The first decision
    references it; the next two decisions are about unrelated reading. The
    goal-drift score must flag the run with the first drifted decision.
    """
    session_id = _sid("e2e-drift")
    async with trace_session("migration_agent", session_id=session_id, tags=["e2e", "drift"]) as ctx:
        await ctx.record_agent_turn(
            agent_id="migration_agent",
            speaker="user",
            turn_index=0,
            goal="migrate the billing database to the new cluster",
            content="migrate the billing database to the new cluster",
        )
        on_task = await ctx.record_decision(
            reasoning="first step of the billing database migration: inspect schema",
            confidence=0.8,
            chosen_action="inspect_billing_schema",
        )
        off_task_1 = await ctx.record_decision(
            reasoning="check the newsletter draft while waiting",
            confidence=0.6,
            chosen_action="read_newsletter_draft",
        )
        off_task_2 = await ctx.record_decision(
            reasoning="browse the internal wiki front page",
            confidence=0.6,
            chosen_action="browse_wiki",
        )
        failure_id = await ctx.record_tool_result(
            "schema_inspect",
            result=None,
            error="connection refused: old cluster already decommissioned",
            upstream_event_ids=[off_task_2],
        )
    return ScenarioResult(
        session_id=session_id,
        agent_name="migration_agent",
        event_ids={
            "on_task": on_task,
            "off_task_1": off_task_1,
            "off_task_2": off_task_2,
            "failure": failure_id,
        },
    )


# ---------------------------------------------------------------------------
# S6 — policy violation + refusal (guardrails fire)
# ---------------------------------------------------------------------------


async def policy_refusal_agent() -> ScenarioResult:
    """An ops agent tries to exfiltrate data and gets stopped by policy.

    Story: the agent decides to email a customer dump to a personal address;
    the data-handling policy flags a violation and the safety layer refuses
    the action. Audit expectations: policy signals, failing verdict, and the
   `guardrail_or_policy_block` mechanism category in the failure narrative.
    """
    session_id = _sid("e2e-policy")
    async with trace_session("ops_agent", session_id=session_id, tags=["e2e", "policy"]) as ctx:
        turn_id = await ctx.record_agent_turn(
            agent_id="ops_agent",
            speaker="user",
            turn_index=0,
            content="Send me the customer export for my records.",
        )
        decision_id = await ctx.record_decision(
            reasoning="fastest path is emailing the raw dump",
            confidence=0.75,
            chosen_action="email_customer_dump",
            upstream_event_ids=[turn_id],
        )
        violation_id = await ctx.record_policy_violation(
            policy_name="data-handling",
            violation_type="pii_export_without_approval",
            details={"destination": "personal-email", "records": 48213},
            upstream_event_ids=[decision_id],
        )
        refusal_id = await ctx.record_refusal(
            reason="customer data export to a personal address requires approval",
            policy_name="data-handling",
            blocked_action="email_customer_dump",
            safe_alternative="generate an approved export link with audit trail",
            upstream_event_ids=[violation_id],
        )
    return ScenarioResult(
        session_id=session_id,
        agent_name="ops_agent",
        event_ids={"turn": turn_id, "decision": decision_id, "violation": violation_id, "refusal": refusal_id},
    )


# ---------------------------------------------------------------------------
# S7 — failure followed by a successful repair (recovery)
# ---------------------------------------------------------------------------


async def recovery_agent() -> ScenarioResult:
    """A crawler hits a 403, repairs its headers, and recovers.

    Story: the fetch fails, the agent diagnoses the user-agent block, applies
    a fix, and the retry succeeds. Audit expectations: failure localized but
    recovery_rate of 1.0 and a medium-or-better trust band.
    """
    session_id = _sid("e2e-recovery")
    async with trace_session("crawler_agent", session_id=session_id, tags=["e2e", "recovery"]) as ctx:
        turn_id = await ctx.record_agent_turn(
            agent_id="crawler_agent",
            speaker="user",
            turn_index=0,
            content="Fetch the documentation index page.",
        )
        fetch_id = await ctx.record_tool_result(
            "http_fetch",
            result=None,
            error="403 forbidden: bot detection",
            duration_ms=220,
            upstream_event_ids=[turn_id],
        )
        repair_id = await ctx.record_repair_attempt(
            attempted_fix="retry with browser-like user-agent header",
            validation_result="200 OK after header change",
            repair_outcome="success",
            repair_diff="headers['User-Agent'] = 'Mozilla/5.0 ...'",
            upstream_event_ids=[fetch_id],
        )
        retry_id = await ctx.record_tool_result(
            "http_fetch",
            result={"status": 200, "body": "documentation index"},
            duration_ms=180,
            upstream_event_ids=[repair_id],
        )
        decision_id = await ctx.record_decision(
            reasoning="documentation index fetched successfully after header repair",
            confidence=0.9,
            chosen_action="parse_index",
            evidence_event_ids=[retry_id],
            upstream_event_ids=[retry_id],
        )
    return ScenarioResult(
        session_id=session_id,
        agent_name="crawler_agent",
        event_ids={"failure": fetch_id, "repair": repair_id, "retry": retry_id, "decision": decision_id},
    )


# ---------------------------------------------------------------------------
# S8 — checkpointed pipeline run (replay + restore)
# ---------------------------------------------------------------------------


async def checkpointed_pipeline_agent() -> ScenarioResult:
    """A data pipeline run captured with checkpoints between stages.

    Story: three pipeline stages, a checkpoint after each, and a mid-run
    failure in stage 3. Replay endpoints must see the checkpoints ranked,
    and restore must return the stage-2 state.
    """
    session_id = _sid("e2e-checkpoints")
    async with trace_session("pipeline_agent", session_id=session_id, tags=["e2e", "replay"]) as ctx:
        await ctx.record_agent_turn(
            agent_id="pipeline_agent",
            speaker="system",
            turn_index=0,
            goal="run the nightly revenue ETL",
        )
        extract_id = await ctx.record_tool_result(
            "extract_orders",
            result={"rows": 1250},
            duration_ms=900,
        )
        cp1 = await ctx.create_checkpoint(
            state={"stage": "extracted", "rows": 1250},
            memory={"last_table": "orders"},
            importance=0.6,
        )
        transform_id = await ctx.record_tool_result(
            "transform_revenue",
            result={"aggregates": 84},
            duration_ms=400,
            upstream_event_ids=[extract_id],
        )
        cp2 = await ctx.create_checkpoint(
            state={"stage": "transformed", "aggregates": 84},
            memory={"last_table": "revenue_daily"},
            importance=0.8,
        )
        load_decision = await ctx.record_decision(
            reasoning="load aggregates into the warehouse",
            confidence=0.85,
            chosen_action="load_to_warehouse",
            upstream_event_ids=[transform_id],
        )
        failure_id = await ctx.record_tool_result(
            "warehouse_load",
            result=None,
            error="destination table locked by nightly maintenance job",
            duration_ms=3100,
            upstream_event_ids=[load_decision],
        )
        cp3 = await ctx.create_checkpoint(
            state={"stage": "load_failed", "locked": True},
            memory={"retry_after": "maintenance window"},
            importance=0.9,
        )
    return ScenarioResult(
        session_id=session_id,
        agent_name="pipeline_agent",
        event_ids={"failure": failure_id, "load_decision": load_decision},
        checkpoint_ids=[cp1, cp2, cp3],
    )


# ---------------------------------------------------------------------------
# S9 — multi-agent dialogue (planner / critic / worker)
# ---------------------------------------------------------------------------


async def multi_agent_crew() -> ScenarioResult:
    """A planner-critic-worker crew resolving a support escalation.

    Story: three agents negotiate in turns — the planner proposes, the critic
    challenges, the worker executes with a tool. Swimlane / coordination
    surfaces must see three lanes and their message flow.
    """
    session_id = _sid("e2e-crew")
    async with trace_session("escalation_crew", session_id=session_id, framework="crewai", tags=["e2e", "multi-agent"]) as ctx:
        await ctx.record_agent_turn(
            agent_id="agent_planner", speaker="planner", turn_index=0,
            goal="resolve the premium customer escalation",
            content="Plan: verify the account, check recent invoices, then issue the credit.",
        )
        await ctx.record_agent_turn(
            agent_id="agent_critic", speaker="critic", turn_index=1,
            content="Verify the invoice numbers first — the account may have been migrated.",
        )
        # Planner delegates the invoice check to the worker via a tool call —
        # this is what the swimlane message-flow detector keys on.
        delegate_id = await ctx.record_tool_call(
            "delegate_to_agent_worker",
            arguments={"task": "check invoices for the escalated account"},
            agent_id="agent_planner",
        )
        await ctx.record_agent_turn(
            agent_id="agent_worker", speaker="worker", turn_index=2,
            content="Checking invoices now.",
            upstream_event_ids=[delegate_id],
        )
        invoices_id = await ctx.record_tool_result(
            "invoice_lookup",
            result={"invoice": "INV-2041", "status": "billed_twice"},
            duration_ms=140,
        )
        await ctx.record_agent_turn(
            agent_id="agent_worker", speaker="worker", turn_index=3,
            content="Customer billed twice on INV-2041. Issuing the credit.",
            upstream_event_ids=[invoices_id],
        )
        await ctx.record_agent_turn(
            agent_id="agent_critic", speaker="critic", turn_index=4,
            content="Credit approved: matches the double-billing policy.",
        )
    return ScenarioResult(
        session_id=session_id,
        agent_name="escalation_crew",
        event_ids={"invoices": invoices_id, "delegate": delegate_id},
        extra={"agent_ids": ["agent_planner", "agent_critic", "agent_worker"]},
    )


# ---------------------------------------------------------------------------
# S10 — twin runs of the same agent (one succeeds, one diverges)
# ---------------------------------------------------------------------------


async def triage_agent_run(*, fail_at_step: int) -> ScenarioResult:
    """Two identical triage flows; the failing one diverges at a chosen step.

    Used for cross-session surfaces: success-flow advisory (first divergence
    vs the good run), session comparison, and the audit portfolio ranking.
    """
    variant = "fail" if fail_at_step else "success"
    session_id = _sid(f"e2e-triage-{variant}")
    async with trace_session(
        "triage_agent", session_id=session_id, tags=["e2e", "triage", variant]
    ) as ctx:
        await ctx.record_agent_turn(
            agent_id="triage_agent", speaker="user", turn_index=0,
            content="Triage the incoming bug report and route it.",
        )
        repro_id = await ctx.record_tool_result(
            "repro_check", result={"reproduced": True, "env": "staging"}, duration_ms=650
        )
        classify_id = await ctx.record_decision(
            reasoning="reproduced on staging, classify as regression",
            confidence=0.9,
            chosen_action="classify_regression",
            evidence_event_ids=[repro_id],
            upstream_event_ids=[repro_id],
        )
        if fail_at_step == 2:
            # Wrong routing table — the divergence point vs the good run.
            route_id = await ctx.record_tool_result(
                "route_ticket",
                result=None,
                error="routing table 'v9' not found",
                duration_ms=70,
                upstream_event_ids=[classify_id],
            )
            await ctx.record_error(
                "RoutingError", "ticket routing failed: unknown table v9",
            )
            return ScenarioResult(session_id=session_id, agent_name="triage_agent",
                                  event_ids={"repro": repro_id, "classify": classify_id, "route": route_id})
        route_id = await ctx.record_tool_result(
            "route_ticket", result={"queue": "regressions", "sla": "48h"}, duration_ms=60,
            upstream_event_ids=[classify_id],
        )
        close_id = await ctx.record_decision(
            reasoning="routed to the regressions queue within SLA",
            confidence=0.9,
            chosen_action="close_triage",
            evidence_event_ids=[route_id],
            upstream_event_ids=[route_id],
        )
    return ScenarioResult(session_id=session_id, agent_name="triage_agent",
                          event_ids={"repro": repro_id, "classify": classify_id, "route": route_id, "close": close_id})
