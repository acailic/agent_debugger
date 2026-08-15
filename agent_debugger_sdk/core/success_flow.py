"""Success-flow deviation advisory.

Implements the no-ML experiment from the "Tracing Agentic Failure from the
Flow of Success" (OAT) note: localize where a failing run departs from how
a successful run of the same task typically flows, by aligning the two
runs' step-signature sequences and reporting the first divergence.

This is an *advisory* layer — statistical contrast, not evidence. It must
never feed the deterministic trust score or claim verification; it points
an auditor at a candidate first-bad-step to compare against the audit
engine's own localization.
"""

from __future__ import annotations

from typing import Any

from .events import EventType, TraceEvent

#: Event types whose identity is flow-relevant beyond their kind: tool
#: steps carry the tool name so "search then summarize" differs from
#: "write then summarize". Everything else is compared by kind only —
#: event names are too run-specific to align across sessions.
_TOOL_EVENTS = frozenset({EventType.TOOL_CALL, EventType.TOOL_RESULT})


def step_signature(event: TraceEvent) -> str:
    """Stable cross-run signature for one step of a session's flow."""
    if event.event_type in _TOOL_EVENTS:
        tool_name = str(
            getattr(event, "tool_name", None)
            or (event.data or {}).get("tool_name")
            or ""
        ).lower()
        return f"{event.event_type.value}:{tool_name}" if tool_name else event.event_type.value
    return event.event_type.value


def build_success_flow_advisory(
    target_events: list[TraceEvent],
    reference_events: list[TraceEvent],
    *,
    reference_session_id: str | None = None,
) -> dict[str, Any]:
    """Compare a target run's flow against a successful reference run.

    Returns the length of the common step-signature prefix, the first
    diverging step in the target run (the candidate first-bad-step), and
    how much of the reference flow the target covered. Pure, deterministic,
    and advisory-only by construction.
    """
    target_steps = [step_signature(event) for event in target_events]
    reference_steps = [step_signature(event) for event in reference_events]

    common_prefix = 0
    for target_step, reference_step in zip(target_steps, reference_steps):
        if target_step != reference_step:
            break
        common_prefix += 1

    first_divergence = None
    if common_prefix < len(target_steps) and reference_steps:
        event = target_events[common_prefix]
        first_divergence = {
            "event_id": event.id,
            "step_index": common_prefix,
            "target_signature": target_steps[common_prefix],
            "reference_signature": (
                reference_steps[common_prefix]
                if common_prefix < len(reference_steps)
                else None
            ),
        }

    reference_coverage = (
        common_prefix / len(reference_steps) if reference_steps else 0.0
    )

    return {
        "advisory": True,
        "method": "success-flow first-divergence (deterministic sequence alignment)",
        "reference_session_id": reference_session_id,
        "target_steps": len(target_steps),
        "reference_steps": len(reference_steps),
        "common_prefix_steps": common_prefix,
        "reference_coverage": round(reference_coverage, 3),
        "first_divergence": first_divergence,
        "candidate_first_bad_step": (
            first_divergence["event_id"] if first_divergence else None
        ),
        "note": (
            "Advisory contrast against one successful run — statistical "
            "hint, not deterministic verification. Never feeds the trust "
            "score."
        ),
    }
