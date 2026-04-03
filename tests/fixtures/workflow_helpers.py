"""Shared helpers for workflow-based tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agent_debugger_sdk.core.events.base import (
    EventType,
    RiskLevel,
    SafetyOutcome,
    TraceEvent,
)
from agent_debugger_sdk.core.events.decisions import DecisionEvent
from agent_debugger_sdk.core.events.errors import ErrorEvent
from agent_debugger_sdk.core.events.llm import LLMRequestEvent, LLMResponseEvent
from agent_debugger_sdk.core.events.safety import (
    PolicyViolationEvent,
    RefusalEvent,
    SafetyCheckEvent,
)
from agent_debugger_sdk.core.events.tools import ToolCallEvent, ToolResultEvent

# ── Cassette loading ──────────────────────────────────────────────────────────

CASSETTES_DIR = Path(__file__).resolve().parent.parent / "cassettes"


def load_cassette(path: str | Path) -> list[dict[str, Any]]:
    """Load a YAML cassette and return raw interaction dicts."""
    full_path = CASSETTES_DIR / path if not Path(path).is_absolute() else path
    with open(full_path) as f:
        data = yaml.safe_load(f)
    return data["interactions"]


def cassette_events(interactions: list[dict[str, Any]], session_id: str = "cassette-session") -> list[TraceEvent]:
    """Convert cassette interactions into typed TraceEvent instances."""
    events: list[TraceEvent] = []
    type_map = {
        "llm_request": LLMRequestEvent,
        "llm_response": LLMResponseEvent,
        "tool_call": ToolCallEvent,
        "tool_result": ToolResultEvent,
        "decision": DecisionEvent,
        "safety_check": SafetyCheckEvent,
        "refusal": RefusalEvent,
        "policy_violation": PolicyViolationEvent,
        "error": ErrorEvent,
    }
    for interaction in interactions:
        event_payload = dict(interaction)
        event_type_str = event_payload.pop("type")
        cls = type_map.get(event_type_str, TraceEvent)
        if cls is TraceEvent:
            event_payload["event_type"] = EventType(event_type_str)
        event = cls(session_id=session_id, **event_payload)
        events.append(event)
    return events


# ── Event querying ────────────────────────────────────────────────────────────


def find_event(events: list[TraceEvent], *, event_type: EventType, index: int = 0) -> TraceEvent | None:
    """Find the nth event of a given type."""
    matches = [e for e in events if e.event_type == event_type]
    return matches[index] if index < len(matches) else None


def filter_events(events: list[TraceEvent], *, event_type: EventType) -> list[TraceEvent]:
    """Return all events matching a given type."""
    return [e for e in events if e.event_type == event_type]


def get_event_by_id(events: list[TraceEvent], event_id: str) -> TraceEvent | None:
    """Look up an event by its ID."""
    for e in events:
        if e.id == event_id:
            return e
    return None


# ── Root cause helpers ────────────────────────────────────────────────────────


@dataclass
class EvidenceIssue:
    """Describes a single problem found in an evidence chain."""

    kind: str  # "missing", "temporal", "content_mismatch", "error_source"
    evidence_id: str
    detail: str


def validate_evidence_chain(
    decision: DecisionEvent,
    events: list[TraceEvent],
) -> list[EvidenceIssue]:
    """Validate a decision's evidence chain at three levels.

    Checks:
    1. **Existence** — every evidence_event_id resolves to a real event
    2. **Temporal** — evidence events precede the decision in the trace
    3. **Content** — numeric facts in the decision's evidence list appear
       in the source event's data (surface-level check)
    """
    issues: list[EvidenceIssue] = []
    id_to_index = {e.id: i for i, e in enumerate(events)}

    for evidence_id in decision.evidence_event_ids:
        ev = get_event_by_id(events, evidence_id)

        if ev is None:
            issues.append(
                EvidenceIssue(
                    kind="missing",
                    evidence_id=evidence_id,
                    detail=f"Evidence event {evidence_id} not found in session",
                )
            )
            continue

        if ev.event_type == EventType.ERROR:
            issues.append(
                EvidenceIssue(
                    kind="error_source",
                    evidence_id=evidence_id,
                    detail=f"Evidence references an error event: {ev.data.get('error_message', ev.name)}",
                )
            )
            continue

        ev_idx = id_to_index.get(evidence_id)
        if ev_idx is not None and hasattr(decision, "id"):
            dec_idx = id_to_index.get(decision.id)
            if dec_idx is not None and ev_idx >= dec_idx:
                issues.append(
                    EvidenceIssue(
                        kind="temporal",
                        evidence_id=evidence_id,
                        detail="Evidence event occurs at or after the decision",
                    )
                )

    # Content check: compare numeric values in decision.evidence vs source events
    _check_content_consistency(decision, events, issues)

    return issues


def _check_content_consistency(
    decision: DecisionEvent,
    events: list[TraceEvent],
    issues: list[EvidenceIssue],
) -> None:
    """Surface-level check: do numeric claims in evidence dicts match source events?"""
    import re

    # Extract numeric tokens from decision's evidence dicts (including from strings)
    evidence_numbers: list[float] = []
    for ev_dict in decision.evidence:
        if not isinstance(ev_dict, dict):
            continue
        for value in ev_dict.values():
            if isinstance(value, (int, float)):
                evidence_numbers.append(float(value))
            elif isinstance(value, str):
                # Extract numbers like "37.4" from "37.4 million metro population"
                for m in re.findall(r"\d+\.?\d*", value):
                    try:
                        evidence_numbers.append(float(m))
                    except ValueError:
                        pass

    if not evidence_numbers:
        return

    # Build a bag of numeric values from all evidence events (data + typed fields)
    source_numbers: list[float] = []
    for evidence_id in decision.evidence_event_ids:
        ev = get_event_by_id(events, evidence_id)
        if ev is None:
            continue
        _collect_numbers(ev.data, source_numbers)
        # Also check typed attributes (e.g. ToolResultEvent.result)
        for attr in ("result",):
            val = getattr(ev, attr, None)
            if val is not None:
                _collect_numbers(val, source_numbers)

    # Check each evidence number against source numbers
    for claimed_val in evidence_numbers:
        # Skip small integers (unlikely to be factual claims)
        if claimed_val == int(claimed_val) and claimed_val <= 10:
            continue
        # Check if a close match exists in the source data
        found = any(abs(claimed_val - src) < 0.01 * max(abs(claimed_val), 1) for src in source_numbers)
        if not found and source_numbers:  # only flag if there were source numbers to compare
            issues.append(
                EvidenceIssue(
                    kind="content_mismatch",
                    evidence_id="",
                    detail=f"Evidence claims {claimed_val} but source events contain {source_numbers}",
                )
            )


def _collect_numbers(obj: Any, out: list[float]) -> None:
    """Recursively collect numeric values from a nested dict/list."""
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_numbers(v, out)


# ── Safety helpers ────────────────────────────────────────────────────────────


def find_risky_passes(events: list[TraceEvent]) -> list[SafetyCheckEvent]:
    """Find safety checks that passed despite high risk."""
    return [
        e
        for e in events
        if isinstance(e, SafetyCheckEvent) and e.outcome == SafetyOutcome.PASS and e.risk_level == RiskLevel.HIGH
    ]


def find_downstream_danger(events: list[TraceEvent], safety_event: SafetyCheckEvent) -> TraceEvent | None:
    """Find a downstream event after a safety check that materialized the risk."""
    idx = next((i for i, e in enumerate(events) if e.id == safety_event.id), -1)
    if idx < 0:
        return None
    for event in events[idx + 1 :]:
        if event.event_type in (EventType.TOOL_CALL, EventType.DECISION):
            return event
    return None


# ── Reproducibility helpers ───────────────────────────────────────────────────


@dataclass
class Divergence:
    """Represents a point where two sessions diverge."""

    index: int
    event_a: TraceEvent | None
    event_b: TraceEvent | None
    explanation: str


def find_first_divergence(
    events_a: list[TraceEvent],
    events_b: list[TraceEvent],
) -> Divergence | None:
    """Find the first point where two event sequences diverge."""
    max_len = max(len(events_a), len(events_b))
    for i in range(max_len):
        a = events_a[i] if i < len(events_a) else None
        b = events_b[i] if i < len(events_b) else None
        if a is None and b is None:
            continue
        if a is None:
            return Divergence(index=i, event_a=None, event_b=b, explanation="Session A ended before Session B")
        if b is None:
            return Divergence(index=i, event_a=a, event_b=None, explanation="Session B ended before Session A")
        if a.event_type != b.event_type:
            return Divergence(
                index=i, event_a=a, event_b=b, explanation=f"Event type mismatch: {a.event_type} vs {b.event_type}"
            )
        if a.data != b.data:
            return Divergence(index=i, event_a=a, event_b=b, explanation=f"Event data differs at index {i}")
    return None
