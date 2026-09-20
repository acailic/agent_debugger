"""Deterministic failure narrative — the XAI explanation bundle.

Given a session audit report (from :class:`SessionAuditEngine`) and the
session's events, :func:`build_failure_narrative` produces the structured
explanation bundle the XAI-for-coding-agent-failures note calls for:

* **symptom** — what was observed (primary failure + normalized mechanism
  category from a small failure-mode taxonomy).
* **mechanism** — why it happened: the cause chain from the localized
  root-cause suspect down to the failure, the first bad decision, and the
  deterministic signals that contributed (drift, loops, contradictions...).
* **evidence** — anchored links back to the underlying events, so the
  narrative is auditable rather than a wall of generated text.
* **next inspection point** — the single best place for the operator to look
  next, with a deterministic suggested action.

Design rules (same as the audit engine):

* Deterministic + inspectable. No LLM calls, no randomness.
* Compression layer only — every claim in the narrative resolves to an event
  id in the trace, and uncertainty is stated explicitly via ``weakness``
  when localization is weak (per the note's caution).
"""

from __future__ import annotations

from typing import Any

from agent_debugger_sdk.core.events import EventType, TraceEvent

from ..intelligence.helpers import event_label, event_value

# Normalized mechanism taxonomy (paper takeaway #2: failure modes should be
# comparable across sessions, not free-form per-run strings).
MECHANISM_CATEGORIES: dict[str, str] = {
    "tool_execution_failure": "tool_invocation_failed",
    "ungrounded_decision": "decision_without_evidence",
    "looping_behavior": "repeated_failed_strategy",
    "behavior_anomaly": "behavior_anomaly",
    "guardrail_block": "guardrail_or_policy_block",
    "policy_mismatch": "guardrail_or_policy_block",
    "upstream_runtime_error": "runtime_error",
    "diagnostic_review": "uncategorized",
}

# Deterministic signal types that count as contributing factors, mapped to a
# short human label. Everything else stays in the report's signal list.
CONTRIBUTING_SIGNAL_LABELS: dict[str, str] = {
    "repeated_failed_strategy": "repeated failed strategy",
    "contradiction": "claim contradicted by outcome",
    "stale_evidence": "decision made on superseded evidence",
    "unsupported_claim": "claim asserted without evidence",
    "policy_violation": "policy violation",
    "plan_drift": "plan drift",
    "goal_drift": "goal drift",
}

# Confidence ceiling for a narrative whose primary failure has no localized
# upstream cause — honest "symptom-only" explanation, never overstated.
UNLOCALIZED_CONFIDENCE_CAP = 0.4

MAX_EVIDENCE_EVENTS = 6
MAX_CONTRIBUTING_FACTORS = 4
MAX_CAUSE_CHAIN = 8


def build_failure_narrative(
    events: list[TraceEvent], report: dict[str, Any]
) -> dict[str, Any]:
    """Return the structured failure-narrative bundle for an audit report.

    ``report`` is the dict produced by
    :meth:`collector.audit.SessionAuditEngine.audit`. The narrative focuses on
    the primary failure (highest-confidence localized failure, matching the
    report's own ordering). Pure function of (events, report) — no I/O.
    """
    failures = report.get("failures", []) or []
    if not failures:
        return {
            "available": False,
            "headline": "",
            "symptom": {},
            "mechanism": {},
            "evidence": [],
            "next_inspection": {},
            "confidence": 0.0,
            "weakness": None,
            "narrative": "",
        }

    id_lookup = {event.id: event for event in events}
    position = {event.id: index for index, event in enumerate(events)}
    primary = failures[0]

    failure_event_id = str(primary.get("event_id") or "")
    cause_event_id = primary.get("likely_cause_event_id")
    mode = str(primary.get("mode") or "diagnostic_review")
    category = MECHANISM_CATEGORIES.get(mode, "uncategorized")

    cause_chain = _cause_chain(primary, position, id_lookup)
    contributing = _contributing_factors(report)
    first_bad_decision = (
        report.get("questions", {}).get("where_it_failed", {}) or {}
    ).get("first_bad_decision")

    symptom = {
        "text": str(primary.get("symptom") or ""),
        "failure_event_id": failure_event_id,
        "mode": mode,
        "mechanism_category": category,
    }
    mechanism = {
        "text": str(primary.get("likely_cause") or ""),
        "cause_event_id": cause_event_id,
        "localized": cause_event_id is not None,
        "cause_chain": cause_chain,
        "first_bad_decision": first_bad_decision,
        "contributing_factors": contributing,
    }
    evidence = _evidence_entries(primary, cause_event_id, position, id_lookup)

    localized = cause_event_id is not None
    confidence = float(primary.get("confidence") or 0.0)
    weakness: str | None = None
    if not localized:
        confidence = min(confidence, UNLOCALIZED_CONFIDENCE_CAP)
        weakness = (
            "No upstream cause was localized for this failure — the narrative "
            "is symptom-only; treat the mechanism line as unconfirmed."
        )
    elif cause_event_id not in id_lookup:
        weakness = "The localized cause event is missing from the trace."

    next_inspection = _next_inspection(
        cause_event_id=cause_event_id,
        first_bad_decision=first_bad_decision,
        failure_event_id=failure_event_id,
        id_lookup=id_lookup,
    )

    narrative_text = _narrative_text(
        symptom=symptom,
        mechanism=mechanism,
        contributing=contributing,
        next_inspection=next_inspection,
    )
    headline = (
        f"{category.replace('_', ' ')}: {symptom['text']}"
        if symptom["text"]
        else category
    )

    return {
        "available": True,
        "headline": headline,
        "symptom": symptom,
        "mechanism": mechanism,
        "evidence": evidence,
        "next_inspection": next_inspection,
        "confidence": round(confidence, 4),
        "weakness": weakness,
        "narrative": narrative_text,
    }


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _cause_chain(
    primary: dict[str, Any],
    position: dict[str, int],
    id_lookup: dict[str, TraceEvent],
) -> list[dict[str, Any]]:
    """Ordered root-cause → failure chain from the failure's supporting ids.

    Deterministic ordering: trace position (the supporting ids from
    FailureDiagnostics start with the failure itself, so a plain position sort
    already reads cause-first for upstream suspects).
    """
    chain_ids = {
        str(primary.get("event_id")),
        str(primary.get("likely_cause_event_id")),
        *(str(eid) for eid in primary.get("supporting_event_ids", []) or []),
    }
    chain_ids.discard("None")
    ordered = sorted(
        (eid for eid in chain_ids if eid in id_lookup),
        key=lambda eid: position.get(eid, len(position)),
    )
    chain: list[dict[str, Any]] = []
    for eid in ordered[:MAX_CAUSE_CHAIN]:
        event = id_lookup[eid]
        chain.append(
            {
                "event_id": eid,
                "event_type": str(event.event_type),
                "label": event_label(event),
                "role": "failure" if eid == primary.get("event_id") else "cause",
            }
        )
    return chain


def _contributing_factors(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic signals that plausibly contributed to the failure.

    Ordered by severity then first appearance in the signal list, capped so
    the narrative stays a summary rather than a signal dump.
    """
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    signals = [
        signal
        for signal in report.get("signals", []) or []
        if signal.get("type") in CONTRIBUTING_SIGNAL_LABELS
    ]
    signals.sort(
        key=lambda signal: (
            severity_rank.get(str(signal.get("severity")), 3),
            str(signal.get("type")),
        )
    )
    factors: list[dict[str, Any]] = []
    seen_types: set[str] = set()
    for signal in signals:
        signal_type = str(signal.get("type"))
        if signal_type in seen_types:
            continue
        seen_types.add(signal_type)
        factors.append(
            {
                "type": signal_type,
                "label": CONTRIBUTING_SIGNAL_LABELS[signal_type],
                "text": str(signal.get("message") or ""),
                "event_id": signal.get("event_id"),
            }
        )
        if len(factors) >= MAX_CONTRIBUTING_FACTORS:
            break

    drift = report.get("goal_drift", {}) or {}
    if drift.get("drifted") and "goal_drift" not in seen_types:
        factors.append(
            {
                "type": "goal_drift",
                "label": CONTRIBUTING_SIGNAL_LABELS["goal_drift"],
                "text": (
                    "Objective stopped being referenced "
                    f"{drift.get('decisions_after_last_reference')} decisions "
                    "before the run ended."
                ),
                "event_id": drift.get("first_drift_event_id"),
            }
        )
    return factors


def _evidence_entries(
    primary: dict[str, Any],
    cause_event_id: Any,
    position: dict[str, int],
    id_lookup: dict[str, TraceEvent],
) -> list[dict[str, Any]]:
    """Trace-anchored evidence entries (why each event supports the narrative)."""
    failure_event_id = str(primary.get("event_id") or "")
    entries: list[dict[str, Any]] = []

    def add(event_id: str, why: str) -> None:
        event = id_lookup.get(event_id)
        if event is None:
            return
        entries.append(
            {
                "event_id": event_id,
                "event_type": str(event.event_type),
                "label": event_label(event),
                "why": why,
            }
        )

    if cause_event_id:
        add(str(cause_event_id), "localized root-cause suspect")
    if failure_event_id:
        add(failure_event_id, "the observed failure")
    for eid in primary.get("supporting_event_ids", []) or []:
        add(str(eid), "supports the cause attribution")

    # Deduplicate by event id, preserving the deterministic order above.
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        if entry["event_id"] in seen:
            continue
        seen.add(entry["event_id"])
        deduped.append(entry)
    # Trace order reads naturally (cause before failure) and stays stable.
    deduped.sort(key=lambda entry: position.get(entry["event_id"], len(position)))
    return deduped[:MAX_EVIDENCE_EVENTS]


def _next_inspection(
    *,
    cause_event_id: Any,
    first_bad_decision: Any,
    failure_event_id: str,
    id_lookup: dict[str, TraceEvent],
) -> dict[str, Any]:
    """Pick the single best next inspection point and a suggested action.

    Priority: the localized cause (fix the origin, not the symptom), then the
    first bad decision, then the failure event itself. The suggested action is
    a deterministic template keyed off the inspection point's event type.
    """
    if cause_event_id and str(cause_event_id) in id_lookup:
        event = id_lookup[str(cause_event_id)]
        if event.event_type == EventType.DECISION:
            why = "The suspected origin is a decision — check whether its evidence justified the action."
            action = "Open the decision justification and compare its cited evidence against what the action needed."
        elif event.event_type == EventType.TOOL_RESULT and event_value(event, "error"):
            why = "The suspected origin is itself a failed tool result — this failure cascaded."
            action = "Inspect the first failing tool call in the chain and whether later steps depended on its output."
        else:
            why = "The strongest upstream suspect for the primary failure."
            action = "Inspect this event's inputs and outputs; downstream steps consumed them."
        return {
            "event_id": str(cause_event_id),
            "why": why,
            "suggested_action": action,
        }

    if first_bad_decision and str(first_bad_decision) in id_lookup:
        return {
            "event_id": str(first_bad_decision),
            "why": "The earliest decision that was unsupported, contradicted, or blamed as the cause.",
            "suggested_action": (
                "Open the decision justification; verify its evidence and "
                "whether the failure changes its verdict."
            ),
        }

    return {
        "event_id": failure_event_id or None,
        "why": "No upstream cause was localized — start from the observed failure."
        if failure_event_id
        else "",
        "suggested_action": (
            "Compare against a successful reference run (success-flow advisory) "
            "to locate the first divergence."
        ),
    }


def _narrative_text(
    *,
    symptom: dict[str, Any],
    mechanism: dict[str, Any],
    contributing: list[dict[str, Any]],
    next_inspection: dict[str, Any],
) -> str:
    """Compact prose paragraph tying the bundle together (pure template)."""
    parts: list[str] = []
    if symptom.get("text"):
        parts.append(f"Symptom: {symptom['text']}.")
    if mechanism.get("text"):
        parts.append(f"Mechanism: {mechanism['text']}.")
    elif not mechanism.get("localized"):
        parts.append(
            "Mechanism: no upstream cause was localized from the captured links."
        )
    if contributing:
        labels = ", ".join(factor["label"] for factor in contributing)
        parts.append(f"Contributing factors: {labels}.")
    if next_inspection.get("event_id"):
        parts.append(
            f"Next inspection point: event {next_inspection['event_id']} — "
            f"{next_inspection.get('suggested_action', '')}"
        )
    return " ".join(parts)


__all__ = [
    "CONTRIBUTING_SIGNAL_LABELS",
    "MECHANISM_CATEGORIES",
    "UNLOCALIZED_CONFIDENCE_CAP",
    "build_failure_narrative",
]
