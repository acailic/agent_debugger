"""Deterministic session audit engine.

Given a captured session's events and checkpoints, :class:`SessionAuditEngine`
produces a :data:`SessionAuditReport` that reframes the run as an audit record:

* **What happened** — action/tool/model/decision/retry sequence counts.
* **Why** — decisions with their rationale, confidence, and alternatives.
* **Evidence** — input sources used and evidence coverage.
* **Outcome** — successes, failures, and state changes.
* **Where it failed** — first bad decision, failure root-cause suspects,
  drift / loop / contradiction signals.

It also classifies every decision as a *claim* with a deterministic
``verification_status`` and emits an explainable trust score composed of
inspectable sub-metrics.

Design rules (see AGENTS.md / project philosophy):

* Deterministic + inspectable. No LLM calls, no randomness.
* Reuses :class:`~collector.causal_analysis.CausalAnalyzer` and
  :class:`~collector.failure_diagnostics.FailureDiagnostics` rather than
  re-deriving failure localization.
* Reads both typed event attributes and the ``data`` dict via
  :func:`~collector.intelligence.helpers.event_value`, so it works on
  events reconstructed from storage as well as freshly built ones.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from agent_debugger_sdk.core.events import Checkpoint, EventType, TraceEvent

from ..causal_analysis import CausalAnalyzer
from ..failure_diagnostics import FailureDiagnostics
from ..intelligence.helpers import event_value

# ---------------------------------------------------------------------------
# Verification taxonomy
# ---------------------------------------------------------------------------

#: A claim whose supporting evidence resolves to a concrete successful
#: tool result, user input, or retrieved document.
VERIFIED = "verified"
#: A claim that carries evidence, but none of it resolves to a concrete
#: tool/user/retrieved fact in the trace.
PARTIALLY_VERIFIED = "partially_verified"
#: A claim whose downstream subtree contains a failure — the confident
#: assertion was contradicted by what actually happened.
CONTRADICTED = "contradicted"
#: A confident claim (confidence >= 0.5) made with no evidence at all.
UNSUPPORTED = "unsupported"
#: A low-confidence claim with no evidence — an unverified assumption.
UNVERIFIED = "unverified"
#: A claim relying on evidence that exists but is older than the configured
#: staleness window (placeholder for future timestamp-based staleness).
STALE = "stale"

#: Evidence ``source`` values that count as tool-backed facts.
TOOL_BACKED_SOURCES = frozenset(
    {"tool_result", "tool", "function", "api", "tool_call"}
)
#: Evidence ``source`` values that count as user-provided facts.
USER_SOURCES = frozenset({"user_input", "user", "human", "operator"})
#: Evidence ``source`` values that count as retrieved documents.
RETRIEVED_SOURCES = frozenset(
    {"retrieved", "retrieval", "document", "search", "memory", "rag"}
)

# Claim/decision confidence threshold above which a missing-evidence claim is
# treated as "unsupported" rather than merely "unverified".
UNSUPPORTED_CONFIDENCE_THRESHOLD = 0.5
# Confidence above which an evidence-free decision is a notable risk signal.
HIGH_CONFIDENCE_THRESHOLD = 0.7


@dataclass
class SessionAuditReport:
    """Structured audit report for a single session (plain dict payload)."""

    session_id: str
    objective: str | None
    final_outcome: str
    questions: dict[str, Any]
    claims: list[dict[str, Any]]
    signals: list[dict[str, Any]]
    failures: list[dict[str, Any]]
    critical_decisions: list[dict[str, Any]]
    trust: dict[str, Any]
    review_points: list[dict[str, Any]] = field(default_factory=list)


class SessionAuditEngine:
    """Build a :class:`SessionAuditReport` from captured events.

    The engine is stateless: construct once, call :meth:`audit` per session.
    """

    def __init__(
        self,
        *,
        causal: CausalAnalyzer | None = None,
        diagnostics: FailureDiagnostics | None = None,
    ) -> None:
        self._causal = causal or CausalAnalyzer()
        self._diagnostics = diagnostics or FailureDiagnostics(self._causal)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def audit(
        self,
        events: list[TraceEvent],
        checkpoints: list[Checkpoint] | None = None,
        *,
        session: dict[str, Any] | None = None,
        failure_explanations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Return a JSON-serializable audit report dict.

        Args:
            events: Ordered session events.
            checkpoints: Optional checkpoints (used for outcome context).
            session: Optional session dict (``status``, ``agent_name`` ...).
            failure_explanations: Optional precomputed failure explanations
                from :class:`~collector.intelligence.facade.TraceIntelligence`.
                If omitted, the engine derives its own using
                :class:`FailureDiagnostics`.
        """
        checkpoints = checkpoints or []
        session = session or {}

        id_lookup = {event.id: event for event in events}
        children_by_parent = _build_children_index(events)

        tool_backed_ids, user_input_ids, retrieved_ids = self._index_facts(events)
        failure_events = [event for event in events if self._diagnostics.is_failure_event(event)]
        failure_event_ids = {event.id for event in failure_events}

        explanations = (
            failure_explanations
            if failure_explanations is not None
            else self._diagnostics.build_failure_explanations(
                events,
                self._empty_ranking_by_event_id(events),
                self._causal_headline,
            )
        )

        claims = self._build_claims(
            events,
            id_lookup=id_lookup,
            children_by_parent=children_by_parent,
            failure_event_ids=failure_event_ids,
            tool_backed_ids=tool_backed_ids,
            user_input_ids=user_input_ids,
            retrieved_ids=retrieved_ids,
        )
        signals = self._build_signals(events, claims)
        failures = self._build_failures(events, explanations)
        critical_decisions = self._build_critical_decisions(claims)

        trust = self._build_trust(
            events=events,
            claims=claims,
            failures=failures,
            signals=signals,
        )

        objective = self._infer_objective(events, session)
        final_outcome = self._infer_final_outcome(events, session)
        questions = self._build_questions(
            events=events,
            claims=claims,
            failures=failures,
            signals=signals,
            tool_backed_ids=tool_backed_ids,
            user_input_ids=user_input_ids,
            retrieved_ids=retrieved_ids,
            checkpoints=checkpoints,
        )

        report = SessionAuditReport(
            session_id=session.get("id") or (events[0].session_id if events else ""),
            objective=objective,
            final_outcome=final_outcome,
            questions=questions,
            claims=claims,
            signals=signals,
            failures=failures,
            critical_decisions=critical_decisions,
            trust=trust,
            review_points=self._build_review_points(claims, failures, signals),
        )
        return _report_to_dict(report)

    # ------------------------------------------------------------------
    # Fact indexing — what counts as grounded evidence in this trace
    # ------------------------------------------------------------------

    def _index_facts(
        self, events: list[TraceEvent]
    ) -> tuple[set[str], set[str], set[str]]:
        tool_backed: set[str] = set()
        user_input: set[str] = set()
        retrieved: set[str] = set()
        for event in events:
            if event.event_type == EventType.TOOL_RESULT and not event_value(event, "error"):
                tool_backed.add(event.id)
            if event.event_type in {EventType.AGENT_TURN, EventType.AGENT_START}:
                if event_value(event, "content") or event_value(event, "goal"):
                    user_input.add(event.id)
            # Evidence items that name a concrete source are themselves facts.
            for item in event_value(event, "evidence", []) or []:
                source = str(item.get("source", "")).lower() if isinstance(item, dict) else ""
                if source in TOOL_BACKED_SOURCES:
                    tool_backed.add(event.id)
                elif source in RETRIEVED_SOURCES:
                    retrieved.add(event.id)
                elif source in USER_SOURCES:
                    user_input.add(event.id)
        return tool_backed, user_input, retrieved

    # ------------------------------------------------------------------
    # Claim construction + verification
    # ------------------------------------------------------------------

    def _build_claims(
        self,
        events: list[TraceEvent],
        *,
        id_lookup: dict[str, TraceEvent],
        children_by_parent: dict[str, list[str]],
        failure_event_ids: set[str],
        tool_backed_ids: set[str],
        user_input_ids: set[str],
        retrieved_ids: set[str],
    ) -> list[dict[str, Any]]:
        claims: list[dict[str, Any]] = []
        for event in events:
            if event.event_type != EventType.DECISION:
                continue
            confidence = _as_float(event_value(event, "confidence", 0.5), default=0.5)
            evidence_items = event_value(event, "evidence", []) or []
            evidence_event_ids = event_value(event, "evidence_event_ids", []) or []
            rationale = (
                event_value(event, "rationale", None)
                or event_value(event, "reasoning", None)
                or ""
            )

            evidence_sources = _classify_evidence(evidence_items)
            resolved_evidence_ids = [eid for eid in evidence_event_ids if eid in id_lookup]

            verification_status, verification_basis = self._verify_claim(
                event=event,
                confidence=confidence,
                evidence_items=evidence_items,
                evidence_event_ids=evidence_event_ids,
                resolved_evidence_ids=resolved_evidence_ids,
                tool_backed_ids=tool_backed_ids,
                user_input_ids=user_input_ids,
                retrieved_ids=retrieved_ids,
                children_by_parent=children_by_parent,
                failure_event_ids=failure_event_ids,
            )

            contradicted = verification_status == CONTRADICTED
            claims.append(
                {
                    "event_id": event.id,
                    "event_type": str(event.event_type),
                    "headline": self._causal_headline(event),
                    "claim": event_value(event, "chosen_action", "") or rationale or event.name,
                    "rationale": rationale,
                    "confidence": round(confidence, 4),
                    "alternatives_considered": len(event_value(event, "alternatives", []) or []),
                    "evidence_refs": list(evidence_event_ids),
                    "evidence_sources": evidence_sources,
                    "verification_status": verification_status,
                    "verification_basis": verification_basis,
                    "contradicted": contradicted,
                    "timestamp": _iso(event),
                }
            )
        return claims

    def _verify_claim(
        self,
        *,
        event: TraceEvent,
        confidence: float,
        evidence_items: list[Any],
        evidence_event_ids: list[str],
        resolved_evidence_ids: list[str],
        tool_backed_ids: set[str],
        user_input_ids: set[str],
        retrieved_ids: set[str],
        children_by_parent: dict[str, list[str]],
        failure_event_ids: set[str],
    ) -> tuple[str, str]:
        has_evidence = bool(evidence_items) or bool(evidence_event_ids)

        # Contradiction: a confident decision whose downstream subtree failed.
        if confidence >= UNSUPPORTED_CONFIDENCE_THRESHOLD and _descendants_include_failure(
            event.id, children_by_parent, failure_event_ids
        ):
            return CONTRADICTED, "decision subtree contains a failure event"

        resolved_tool_backed = [eid for eid in resolved_evidence_ids if eid in tool_backed_ids]
        resolved_user = [eid for eid in resolved_evidence_ids if eid in user_input_ids]
        resolved_retrieved = [eid for eid in resolved_evidence_ids if eid in retrieved_ids]
        named_tool_backed = any(
            (isinstance(item, dict) and str(item.get("source", "")).lower() in TOOL_BACKED_SOURCES)
            for item in evidence_items
        )
        named_user = any(
            (isinstance(item, dict) and str(item.get("source", "")).lower() in USER_SOURCES)
            for item in evidence_items
        )
        named_retrieved = any(
            (isinstance(item, dict) and str(item.get("source", "")).lower() in RETRIEVED_SOURCES)
            for item in evidence_items
        )

        if resolved_tool_backed or named_tool_backed:
            return VERIFIED, "backed by a successful tool result"
        if resolved_user or named_user:
            return VERIFIED, "backed by user-provided input"
        if resolved_retrieved or named_retrieved:
            return PARTIALLY_VERIFIED, "backed by retrieved evidence (not tool-verified)"
        if has_evidence:
            return PARTIALLY_VERIFIED, "carries evidence that does not resolve to a concrete fact"
        if confidence >= UNSUPPORTED_CONFIDENCE_THRESHOLD:
            return UNSUPPORTED, "confident claim made with no evidence"
        return UNVERIFIED, "low-confidence claim with no evidence"

    # ------------------------------------------------------------------
    # Risk signals
    # ------------------------------------------------------------------

    def _build_signals(
        self,
        events: list[TraceEvent],
        claims: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []

        for claim in claims:
            event_id = claim["event_id"]
            confidence = claim["confidence"]
            evidence_refs = claim["evidence_refs"]
            evidence_sources = claim["evidence_sources"]

            # missing_evidence / unsupported_claim / confidence_evidence_mismatch
            if claim["verification_status"] == UNSUPPORTED:
                signals.append(
                    _signal(
                        event_id,
                        "unsupported_claim",
                        "high",
                        f'Decision "{claim["headline"]}" asserted at confidence '
                        f"{confidence:.2f} without any evidence.",
                    )
                )
                signals.append(
                    _signal(
                        event_id,
                        "confidence_evidence_mismatch",
                        "high",
                        f"Confidence {confidence:.2f} is unjustified: no evidence attached.",
                    )
                )
            elif not evidence_refs and not evidence_sources and confidence >= HIGH_CONFIDENCE_THRESHOLD:
                signals.append(
                    _signal(
                        event_id,
                        "missing_evidence",
                        "medium",
                        f'High-confidence decision "{claim["headline"]}" lacks evidence references.',
                    )
                )

            if claim["verification_status"] == CONTRADICTED:
                signals.append(
                    _signal(
                        event_id,
                        "contradiction",
                        "high",
                        f'Confident decision "{claim["headline"]}" was followed by a failure '
                        "in its causal subtree.",
                    )
                )

            if claim["verification_status"] == PARTIALLY_VERIFIED:
                signals.append(
                    _signal(
                        event_id,
                        "weak_evidence",
                        "low",
                        f'Decision "{claim["headline"]}" relies on evidence that is not '
                        "tool-verified.",
                    )
                )

        # repeated_failed_strategy: same tool failing more than once.
        tool_failures: Counter[str] = Counter()
        tool_failure_event: dict[str, str] = {}
        for event in events:
            if (
                event.event_type == EventType.TOOL_RESULT
                and event_value(event, "error")
            ):
                tool_name = event_value(event, "tool_name", "<unknown>") or "<unknown>"
                tool_failures[tool_name] += 1
                tool_failure_event.setdefault(tool_name, event.id)
        for tool_name, count in tool_failures.items():
            if count >= 2:
                signals.append(
                    _signal(
                        tool_failure_event[tool_name],
                        "repeated_failed_strategy",
                        "high" if count >= 3 else "medium",
                        f'Tool "{tool_name}" failed {count} times — repeated failed strategy.',
                    )
                )

        # plan_drift: explicit DRIFT events, tool-loop alerts, or status error.
        for event in events:
            if event.event_type == EventType.DRIFT:
                signals.append(
                    _signal(
                        event.id,
                        "plan_drift",
                        "high",
                        f"Drift detected: {event_value(event, 'signal', event.name or 'agent diverged from plan')}.",
                    )
                )
            if event.event_type == EventType.BEHAVIOR_ALERT and event_value(
                event, "alert_type", ""
            ) == "tool_loop":
                signals.append(
                    _signal(
                        event.id,
                        "plan_drift",
                        "high",
                        f"Tool-loop behavior: {event_value(event, 'signal', 'repeated tool invocations')}.",
                    )
                )

        # policy violations lower trust and are surfaced explicitly.
        for event in events:
            if event.event_type == EventType.POLICY_VIOLATION:
                signals.append(
                    _signal(
                        event.id,
                        "policy_violation",
                        "high",
                        f"Policy violation: {event_value(event, 'violation_type', event.name or 'rule breach')}.",
                    )
                )

        signals.sort(key=lambda item: (_SEVERITY_RANK[item["severity"]], item["type"]))
        return signals

    # ------------------------------------------------------------------
    # Failures (reuse FailureDiagnostics explanations)
    # ------------------------------------------------------------------

    def _build_failures(
        self, events: list[TraceEvent], explanations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        index_lookup = {event.id: index for index, event in enumerate(events)}
        failures: list[dict[str, Any]] = []
        for explanation in explanations:
            failures.append(
                {
                    "event_id": explanation.get("failure_event_id"),
                    "event_type": explanation.get("failure_event_type"),
                    "headline": explanation.get("failure_headline"),
                    "mode": explanation.get("failure_mode"),
                    "symptom": explanation.get("symptom"),
                    "likely_cause": explanation.get("likely_cause"),
                    "likely_cause_event_id": explanation.get("likely_cause_event_id"),
                    "confidence": explanation.get("confidence", 0.0),
                    "supporting_event_ids": explanation.get("supporting_event_ids", []),
                    "position": index_lookup.get(str(explanation.get("failure_event_id")), -1),
                }
            )
        failures.sort(key=lambda item: (-float(item.get("confidence") or 0.0), item.get("position", 0)))
        return failures

    def _build_critical_decisions(self, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """High-impact decisions worth surfacing for human review."""
        critical = [
            claim
            for claim in claims
            if claim["verification_status"] in {UNSUPPORTED, CONTRADICTED}
            or claim["confidence"] >= HIGH_CONFIDENCE_THRESHOLD
        ]
        critical.sort(key=lambda claim: (-claim["confidence"], claim["event_id"]))
        return critical[:10]

    # ------------------------------------------------------------------
    # Trust / reliability score (explainable)
    # ------------------------------------------------------------------

    def _build_trust(
        self,
        *,
        events: list[TraceEvent],
        claims: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        decisions = [event for event in events if event.event_type == EventType.DECISION]
        decision_count = len(decisions) or 1
        decisions_with_evidence = sum(1 for claim in claims if claim["evidence_refs"])

        evidence_coverage = decisions_with_evidence / decision_count
        verification_rate = _safe_rate(
            claims,
            lambda claim: claim["verification_status"] == VERIFIED,
        )
        contradiction_count = sum(1 for claim in claims if claim["verification_status"] == CONTRADICTED)
        contradiction_rate = contradiction_count / decision_count

        failure_severity = _max_failure_severity(failures, events, self._causal)

        repair_attempts = [event for event in events if event.event_type == EventType.REPAIR_ATTEMPT]
        recoveries = sum(
            1
            for event in repair_attempts
            if str(event_value(event, "repair_outcome", "")).lower() == "success"
        )
        failure_count = max(1, len(failures))
        recovery_rate = recoveries / failure_count

        policy_violations = sum(1 for event in events if event.event_type == EventType.POLICY_VIOLATION)
        policy_compliance = max(0.0, 1.0 - policy_violations / decision_count)

        repeated_strategy = sum(
            1 for signal in signals if signal["type"] == "repeated_failed_strategy"
        )

        # Transparent weighted blend. Each term is inspectable above.
        score = (
            0.30
            + 0.25 * evidence_coverage
            + 0.20 * verification_rate
            + 0.10 * policy_compliance
            + 0.10 * recovery_rate
            - 0.15 * failure_severity
            - 0.05 * contradiction_rate
            - 0.05 * min(repeated_strategy, 3) / 3.0
        )
        score = max(0.0, min(1.0, score))

        components = {
            "evidence_coverage": round(evidence_coverage, 4),
            "verification_rate": round(verification_rate, 4),
            "contradiction_count": contradiction_count,
            "contradiction_rate": round(contradiction_rate, 4),
            "failure_severity": round(failure_severity, 4),
            "recovery_rate": round(recovery_rate, 4),
            "policy_compliance": round(policy_compliance, 4),
            "decision_count": len(decisions),
            "failure_count": len(failures),
        }
        band = "low" if score < 0.45 else "medium" if score < 0.7 else "high"
        explanation = (
            f"trust={score:.2f} ({band}) from evidence_coverage={evidence_coverage:.2f}, "
            f"verification_rate={verification_rate:.2f}, policy_compliance={policy_compliance:.2f}, "
            f"recovery_rate={recovery_rate:.2f}, failure_severity={failure_severity:.2f}, "
            f"contradictions={contradiction_count}."
        )
        return {
            "score": round(score, 4),
            "band": band,
            "components": components,
            "explanation": explanation,
        }

    # ------------------------------------------------------------------
    # The five questions
    # ------------------------------------------------------------------

    def _build_questions(
        self,
        *,
        events: list[TraceEvent],
        claims: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        signals: list[dict[str, Any]],
        tool_backed_ids: set[str],
        user_input_ids: set[str],
        retrieved_ids: set[str],
        checkpoints: list[Checkpoint],
    ) -> dict[str, Any]:
        tool_calls = sum(1 for event in events if event.event_type == EventType.TOOL_CALL)
        tool_results = sum(1 for event in events if event.event_type == EventType.TOOL_RESULT)
        llm_calls = sum(1 for event in events if event.event_type == EventType.LLM_REQUEST)
        retries = sum(1 for event in events if event.event_type == EventType.REPAIR_ATTEMPT)
        decisions = [event for event in events if event.event_type == EventType.DECISION]
        edits = sum(
            1
            for event in events
            if event.event_type == EventType.REPAIR_ATTEMPT and event_value(event, "repair_diff")
        )

        what_happened = {
            "summary": (
                f"{len(events)} events: {tool_calls} tool calls, {llm_calls} model calls, "
                f"{len(decisions)} decisions, {retries} retries, {len(failures)} failures."
            ),
            "event_count": len(events),
            "tool_calls": tool_calls,
            "tool_results": tool_results,
            "llm_calls": llm_calls,
            "decisions": len(decisions),
            "retries": retries,
            "edits": edits,
        }

        why = {
            "decisions_with_rationale": [
                {
                    "event_id": claim["event_id"],
                    "headline": claim["headline"],
                    "rationale": claim["rationale"],
                    "confidence": claim["confidence"],
                    "alternatives_considered": claim["alternatives_considered"],
                }
                for claim in claims
                if claim["rationale"]
            ],
        }

        evidence = {
            "tool_backed_facts": len(tool_backed_ids),
            "user_input_facts": len(user_input_ids),
            "retrieved_facts": len(retrieved_ids),
            "evidence_sources": sorted(
                {source for claim in claims for source in claim["evidence_sources"]}
            ),
            "coverage_of_decisions": (
                sum(1 for claim in claims if claim["evidence_refs"]) / max(1, len(claims))
            ),
        }

        successful_tools = sum(
            1
            for event in events
            if event.event_type == EventType.TOOL_RESULT and not event_value(event, "error")
        )
        failed_tools = sum(
            1
            for event in events
            if event.event_type == EventType.TOOL_RESULT and event_value(event, "error")
        )
        outcome = {
            "success_count": successful_tools,
            "failure_count": len(failures),
            "failed_tool_results": failed_tools,
            "state_snapshots": len(checkpoints),
            "failures": [
                {
                    "event_id": failure["event_id"],
                    "mode": failure["mode"],
                    "symptom": failure["symptom"],
                    "likely_cause_event_id": failure["likely_cause_event_id"],
                }
                for failure in failures
            ],
        }

        where_failed = {
            "first_failure": failures[-1]["event_id"] if failures else None,
            "first_bad_decision": _first_bad_decision(claims, failures),
            "failures": len(failures),
            "top_signals": [
                {"type": signal["type"], "severity": signal["severity"], "message": signal["message"]}
                for signal in signals
                if signal["severity"] in {"high", "medium"}
            ][:8],
        }

        return {
            "what_happened": what_happened,
            "why": why,
            "evidence": evidence,
            "outcome": outcome,
            "where_it_failed": where_failed,
        }

    # ------------------------------------------------------------------
    # Objective / outcome inference
    # ------------------------------------------------------------------

    def _infer_objective(self, events: list[TraceEvent], session: dict[str, Any]) -> str | None:
        config_goal = session.get("goal") if isinstance(session.get("goal"), str) else None
        if config_goal:
            return config_goal
        for event in events:
            goal = event_value(event, "goal", None)
            if goal:
                return str(goal)
        # Fall back to the first user-flavored content.
        for event in events:
            if event.event_type in {EventType.AGENT_TURN, EventType.AGENT_START}:
                content = event_value(event, "content", None)
                if content:
                    return self._causal._clip(content, 160)
        return None

    def _infer_final_outcome(self, events: list[TraceEvent], session: dict[str, Any]) -> str:
        status = session.get("status")
        failures = [event for event in events if self._diagnostics.is_failure_event(event)]
        if status == "error" or (failures and not events):
            return "session ended in error"
        if failures:
            return f"completed with {len(failures)} failure signal(s)"
        if status:
            return f"completed ({status})"
        return "completed"

    # ------------------------------------------------------------------
    # Review points (human audit assist)
    # ------------------------------------------------------------------

    def _build_review_points(
        self,
        claims: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        signals: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        review: list[dict[str, Any]] = []
        for claim in claims:
            if claim["verification_status"] in {UNSUPPORTED, CONTRADICTED}:
                review.append(
                    {
                        "event_id": claim["event_id"],
                        "priority": "high",
                        "reason": (
                            f"Decision \"{claim['headline']}\" is {claim['verification_status']} "
                            f"(confidence {claim['confidence']:.2f})."
                        ),
                    }
                )
        for failure in failures[:3]:
            review.append(
                {
                    "event_id": failure["event_id"],
                    "priority": "high",
                    "reason": f"Failure ({failure['mode']}): {failure['symptom']}",
                }
            )
        for signal in signals:
            if signal["severity"] == "high":
                review.append(
                    {
                        "event_id": signal["event_id"],
                        "priority": "medium",
                        "reason": f"{signal['type']}: {signal['message']}",
                    }
                )
        # Deduplicate by (event_id, reason) while preserving order.
        seen: set[tuple[str, str]] = set()
        unique: list[dict[str, Any]] = []
        for item in review:
            key = (item["event_id"], item["reason"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        priority_rank = {"high": 0, "medium": 1, "low": 2}
        unique.sort(key=lambda item: (priority_rank[item["priority"]], item["event_id"]))
        return unique[:15]

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _causal_headline(self, event: TraceEvent) -> str:
        # Reuse the failure-diagnostics clip via the causal analyzer.
        name = event.name or str(event.event_type).replace("_", " ")
        return self._causal._clip(name, 96)

    def _empty_ranking_by_event_id(self, events: list[TraceEvent]) -> dict[str, dict[str, Any]]:
        return {
            event.id: {
                "event_id": event.id,
                "severity": self._causal.severity(event),
                "composite": self._causal.severity(event),
                "importance": float(event.importance or 0.0),
            }
            for event in events
        }


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _signal(event_id: str, signal_type: str, severity: str, message: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "type": signal_type,
        "severity": severity,
        "message": message,
    }


def _as_float(value: Any, *, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _iso(event: TraceEvent) -> str:
    timestamp = event.timestamp
    return timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp)


def _classify_evidence(evidence_items: list[Any]) -> list[str]:
    sources: list[str] = []
    for item in evidence_items or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "")).lower()
        if not source:
            continue
        if source in TOOL_BACKED_SOURCES:
            sources.append("tool_backed")
        elif source in USER_SOURCES:
            sources.append("user_provided")
        elif source in RETRIEVED_SOURCES:
            sources.append("retrieved")
        else:
            sources.append("inferred")
    return sources


def _build_children_index(events: list[TraceEvent]) -> dict[str, list[str]]:
    """Map each event id to the ids of events that declare it as a parent/upstream/evidence source.

    Used for downstream (causal-subtree) walks without re-scanning all events.
    """
    children: dict[str, list[str]] = {}
    for event in events:
        parent_refs = set(event_value(event, "upstream_event_ids", []) or [])
        parent_refs.update(event_value(event, "evidence_event_ids", []) or [])
        if event.parent_id:
            parent_refs.add(event.parent_id)
        for parent_id in parent_refs:
            children.setdefault(parent_id, []).append(event.id)
    return children


def _descendants_include_failure(
    root_id: str,
    children_by_parent: dict[str, list[str]],
    failure_event_ids: set[str],
) -> bool:
    """BFS downstream from *root_id*; True if any descendant is a failure event."""
    frontier = list(children_by_parent.get(root_id, []))
    seen: set[str] = {root_id}
    # Bound the walk so a cyclic graph cannot loop forever.
    for _ in range(200):
        if not frontier:
            return False
        next_frontier: list[str] = []
        for node_id in frontier:
            if node_id in seen:
                continue
            seen.add(node_id)
            if node_id in failure_event_ids:
                return True
            next_frontier.extend(children_by_parent.get(node_id, []))
        frontier = next_frontier
    return False


def _safe_rate(claims: list[dict[str, Any]], predicate) -> float:
    if not claims:
        return 0.0
    return sum(1 for claim in claims if predicate(claim)) / len(claims)


def _max_failure_severity(
    failures: list[dict[str, Any]],
    events: list[TraceEvent],
    causal: CausalAnalyzer,
) -> float:
    if not failures:
        return 0.0
    failure_ids = {failure["event_id"] for failure in failures if failure.get("event_id")}
    severities = [causal.severity(event) for event in events if event.id in failure_ids]
    return max(severities) if severities else 0.0


def _first_bad_decision(
    claims: list[dict[str, Any]], failures: list[dict[str, Any]]
) -> str | None:
    """Earliest decision that is unsupported/contradicted or blamed as a cause."""
    blamed = {failure.get("likely_cause_event_id") for failure in failures}
    blamed.discard(None)
    bad = [
        claim
        for claim in claims
        if claim["verification_status"] in {UNSUPPORTED, CONTRADICTED} or claim["event_id"] in blamed
    ]
    if not bad:
        return None
    return bad[0]["event_id"]


def _report_to_dict(report: SessionAuditReport) -> dict[str, Any]:
    return {
        "session_id": report.session_id,
        "objective": report.objective,
        "final_outcome": report.final_outcome,
        "questions": report.questions,
        "claims": report.claims,
        "signals": report.signals,
        "failures": report.failures,
        "critical_decisions": report.critical_decisions,
        "trust": report.trust,
        "review_points": report.review_points,
    }
