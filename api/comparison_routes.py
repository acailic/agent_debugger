"""Cross-session comparison API routes.

Provides endpoints for comparing sessions with non-heuristic policy analysis
and escalation detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends

from api.dependencies import get_repository
from api.services import (
    load_session_artifacts,
    normalize_session,
    require_session,
)
from collector.escalation_detection import (
    EscalationSignal,
    compute_escalation_score,
    detect_escalation_signals,
)
from collector.policy_analysis import PolicyShift, analyze_policy_sequence
from storage import TraceRepository

router = APIRouter(tags=["comparison"])


@dataclass
class PolicyAnalysisResult:
    """Policy analysis result for a session."""

    shifts: list[PolicyShift]
    shift_count: int
    avg_shift_magnitude: float


@dataclass
class EscalationAnalysisResult:
    """Escalation analysis result for a session."""

    signals: list[EscalationSignal]
    score: float
    dominant_signal_type: str | None


@router.get("/api/compare/{primary_id}/{secondary_id}")
async def compare_sessions(
    primary_id: str,
    secondary_id: str,
    repo: TraceRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Compare two sessions with detailed multi-agent analysis.

    This endpoint provides non-heuristic policy analysis and escalation
    detection for comparing agent behavior across sessions.

    Args:
        primary_id: Primary session ID
        secondary_id: Secondary session ID to compare against

    Returns:
        Comparison data including policy shifts, escalation signals, and deltas
    """
    # Load both sessions
    primary_session = await require_session(repo, primary_id)
    secondary_session = await require_session(repo, secondary_id)

    # Load artifacts
    primary_events, primary_checkpoints = await load_session_artifacts(repo, primary_id)
    secondary_events, secondary_checkpoints = await load_session_artifacts(repo, secondary_id)

    # Analyze policy sequences
    primary_policy_analysis = _analyze_session_policies(primary_events)
    secondary_policy_analysis = _analyze_session_policies(secondary_events)

    # Analyze escalation signals
    primary_escalation = _analyze_session_escalation(primary_events)
    secondary_escalation = _analyze_session_escalation(secondary_events)

    # Compute deltas
    deltas = _compute_comparison_deltas(
        primary_events,
        primary_checkpoints,
        secondary_events,
        secondary_checkpoints,
        primary_policy_analysis,
        secondary_policy_analysis,
        primary_escalation,
        secondary_escalation,
    )

    return {
        "primary": {
            "session": normalize_session(primary_session).model_dump(),
            "policy_analysis": _policy_to_dict(primary_policy_analysis),
            "escalation_analysis": _escalation_to_dict(primary_escalation),
        },
        "secondary": {
            "session": normalize_session(secondary_session).model_dump(),
            "policy_analysis": _policy_to_dict(secondary_policy_analysis),
            "escalation_analysis": _escalation_to_dict(secondary_escalation),
        },
        "comparison_deltas": deltas,
    }


def _analyze_session_policies(events: list[Any]) -> PolicyAnalysisResult:
    """Analyze policy sequence for a session."""
    from agent_debugger_sdk.core.events import EventType

    policies = [e for e in events if getattr(e, "event_type", None) == EventType.PROMPT_POLICY]
    turns = [e for e in events if getattr(e, "event_type", None) == EventType.AGENT_TURN]

    shifts = analyze_policy_sequence(policies, turns)

    shift_count = len(shifts)
    avg_magnitude = sum(s.shift_magnitude for s in shifts) / shift_count if shift_count > 0 else 0.0

    return PolicyAnalysisResult(
        shifts=shifts,
        shift_count=shift_count,
        avg_shift_magnitude=avg_magnitude,
    )


def _analyze_session_escalation(events: list[Any]) -> EscalationAnalysisResult:
    """Analyze escalation signals for a session."""
    from agent_debugger_sdk.core.events import EventType

    turns = [e for e in events if getattr(e, "event_type", None) == EventType.AGENT_TURN]
    decisions = [e for e in events if getattr(e, "event_type", None) == EventType.DECISION]
    tool_calls = [e for e in events if getattr(e, "event_type", None) == EventType.TOOL_CALL]

    safety_events = [
        e
        for e in events
        if getattr(e, "event_type", None)
        in (
            EventType.SAFETY_CHECK,
            EventType.REFUSAL,
            EventType.POLICY_VIOLATION,
        )
    ]

    signals = detect_escalation_signals(turns, decisions, safety_events, tool_calls)
    score = compute_escalation_score(signals)

    # Find dominant signal type
    dominant_type = None
    if signals:
        type_scores: dict[str, float] = {}
        for signal in signals:
            type_scores[signal.signal_type] = type_scores.get(signal.signal_type, 0.0) + signal.magnitude
        dominant_type = max(type_scores, key=type_scores.get)

    return EscalationAnalysisResult(
        signals=signals,
        score=score,
        dominant_signal_type=dominant_type,
    )


def _compute_comparison_deltas(
    primary_events: list[Any],
    primary_checkpoints: list[Any],
    secondary_events: list[Any],
    secondary_checkpoints: list[Any],
    primary_policy: PolicyAnalysisResult,
    secondary_policy: PolicyAnalysisResult,
    primary_escalation: EscalationAnalysisResult,
    secondary_escalation: EscalationAnalysisResult,
) -> dict[str, Any]:
    """Compute delta metrics between two sessions."""
    from agent_debugger_sdk.core.events import EventType

    def count_by_type(events: list[Any], event_type: EventType) -> int:
        return sum(1 for e in events if getattr(e, "event_type", None) == event_type)

    # Basic counts
    primary_turns = count_by_type(primary_events, EventType.AGENT_TURN)
    secondary_turns = count_by_type(secondary_events, EventType.AGENT_TURN)

    primary_policies = count_by_type(primary_events, EventType.PROMPT_POLICY)
    secondary_policies = count_by_type(secondary_events, EventType.PROMPT_POLICY)

    primary_speakers = _count_unique_speakers(primary_events)
    secondary_speakers = _count_unique_speakers(secondary_events)

    primary_decisions = count_by_type(primary_events, EventType.DECISION)
    secondary_decisions = count_by_type(secondary_events, EventType.DECISION)

    primary_grounded = _count_grounded_decisions(primary_events)
    secondary_grounded = _count_grounded_decisions(secondary_events)

    return {
        "turn_count": {
            "primary": primary_turns,
            "secondary": secondary_turns,
            "delta": primary_turns - secondary_turns,
        },
        "policy_count": {
            "primary": primary_policies,
            "secondary": secondary_policies,
            "delta": primary_policies - secondary_policies,
        },
        "speaker_count": {
            "primary": primary_speakers,
            "secondary": secondary_speakers,
            "delta": primary_speakers - secondary_speakers,
        },
        "stance_shift_count": {
            "primary": primary_policy.shift_count,
            "secondary": secondary_policy.shift_count,
            "delta": primary_policy.shift_count - secondary_policy.shift_count,
        },
        "escalation_count": {
            "primary": len(primary_escalation.signals),
            "secondary": len(secondary_escalation.signals),
            "delta": len(primary_escalation.signals) - len(secondary_escalation.signals),
        },
        "escalation_score": {
            "primary": round(primary_escalation.score, 4),
            "secondary": round(secondary_escalation.score, 4),
            "delta": round(primary_escalation.score - secondary_escalation.score, 4),
        },
        "grounded_decision_count": {
            "primary": primary_grounded,
            "secondary": secondary_grounded,
            "delta": primary_grounded - secondary_grounded,
        },
        "grounding_rate": {
            "primary": round(primary_grounded / primary_decisions, 4) if primary_decisions > 0 else 0.0,
            "secondary": round(secondary_grounded / secondary_decisions, 4) if secondary_decisions > 0 else 0.0,
            "delta": round(
                (primary_grounded / primary_decisions if primary_decisions > 0 else 0.0)
                - (secondary_grounded / secondary_decisions if secondary_decisions > 0 else 0.0),
                4,
            ),
        },
        "avg_shift_magnitude": {
            "primary": round(primary_policy.avg_shift_magnitude, 4),
            "secondary": round(secondary_policy.avg_shift_magnitude, 4),
            "delta": round(primary_policy.avg_shift_magnitude - secondary_policy.avg_shift_magnitude, 4),
        },
    }


def _count_unique_speakers(events: list[Any]) -> int:
    """Count unique speakers in session."""
    from agent_debugger_sdk.core.events import EventType

    speakers: set[str] = set()
    for event in events:
        if getattr(event, "event_type", None) == EventType.AGENT_TURN:
            speaker = (
                getattr(event, "speaker", None)
                or getattr(event, "agent_id", None)
                or (getattr(event, "data", {}).get("speaker") if hasattr(event, "data") else None)
            )
            if speaker:
                speakers.add(speaker)
    return len(speakers)


def _count_grounded_decisions(events: list[Any]) -> int:
    """Count decisions with evidence grounding."""
    from agent_debugger_sdk.core.events import EventType

    count = 0
    for event in events:
        if getattr(event, "event_type", None) == EventType.DECISION:
            evidence = getattr(event, "evidence_event_ids", None) or (
                getattr(event, "data", {}).get("evidence_event_ids") if hasattr(event, "data") else None
            )
            if evidence and len(evidence) > 0:
                count += 1
    return count


def _policy_to_dict(analysis: PolicyAnalysisResult) -> dict[str, Any]:
    """Convert policy analysis to dict for JSON response."""
    return {
        "shift_count": analysis.shift_count,
        "avg_shift_magnitude": round(analysis.avg_shift_magnitude, 4),
        "shifts": [s.to_dict() for s in analysis.shifts[:10]],  # Limit to 10 for response
    }


def _escalation_to_dict(analysis: EscalationAnalysisResult) -> dict[str, Any]:
    """Convert escalation analysis to dict for JSON response."""
    return {
        "score": round(analysis.score, 4),
        "signal_count": len(analysis.signals),
        "dominant_signal_type": analysis.dominant_signal_type,
        "signals": [s.to_dict() for s in analysis.signals[:10]],  # Limit to 10 for response
    }
