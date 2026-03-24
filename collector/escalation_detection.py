"""Non-heuristic escalation detection using multi-signal analysis.

This module provides escalation detection based on multiple signals rather
than simple keyword matching. It combines confidence degradation, tool stake
increases, decision chain depth, safety pressure, and handoff patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from agent_debugger_sdk.core.events import TraceEvent


SIGNAL_TYPE = Literal[
    "explicit_keyword",
    "confidence_degradation",
    "tool_stake_increase",
    "decision_chain_depth",
    "safety_pressure",
    "handoff_pattern",
]

WEIGHTS: dict[SIGNAL_TYPE, float] = {
    "explicit_keyword": 0.15,
    "confidence_degradation": 0.25,
    "tool_stake_increase": 0.20,
    "decision_chain_depth": 0.15,
    "safety_pressure": 0.15,
    "handoff_pattern": 0.10,
}


@dataclass
class EscalationSignal:
    """Represents a detected escalation signal."""

    event_id: str
    turn_index: int
    signal_type: SIGNAL_TYPE
    magnitude: float
    evidence_event_ids: list[str] = field(default_factory=list)
    narrative: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "turn_index": self.turn_index,
            "signal_type": self.signal_type,
            "magnitude": round(self.magnitude, 4),
            "evidence_event_ids": self.evidence_event_ids,
            "narrative": self.narrative,
        }


def detect_escalation_signals(
    turns: list[TraceEvent],
    decisions: list[TraceEvent],
    safety_events: list[TraceEvent],
    tool_calls: list[TraceEvent] | None = None,
) -> list[EscalationSignal]:
    """Detect escalation signals using multi-signal approach.

    Args:
        turns: List of AGENT_TURN events
        decisions: List of DECISION events
        safety_events: List of SAFETY_CHECK, REFUSAL, POLICY_VIOLATION events
        tool_calls: Optional list of TOOL_CALL events

    Returns:
        List of detected EscalationSignal objects
    """
    signals: list[EscalationSignal] = []

    # 1. Confidence degradation (highest weight)
    signals.extend(_detect_confidence_degradation(decisions))

    # 2. Safety pressure
    signals.extend(_detect_safety_pressure(safety_events))

    # 3. Handoff patterns
    signals.extend(_detect_handoff_patterns(turns))

    # 4. Tool stake increase
    if tool_calls:
        signals.extend(_detect_tool_stake_increase(tool_calls))

    # 5. Decision chain depth
    signals.extend(_detect_decision_chain_depth(decisions))

    # 6. Explicit keywords (lowest weight, used as supporting signal)
    signals.extend(_detect_explicit_keywords(turns))

    return signals


def compute_escalation_score(signals: list[EscalationSignal]) -> float:
    """Compute weighted escalation score from detected signals.

    The score is a weighted combination of signal magnitudes,
    where higher-weight signals contribute more to the final score.

    Args:
        signals: List of detected escalation signals

    Returns:
        Escalation score from 0.0 to 1.0
    """
    if not signals:
        return 0.0

    weighted_sum = sum(
        s.magnitude * WEIGHTS.get(s.signal_type, 0.1)
        for s in signals
    )
    return min(1.0, weighted_sum)


def _detect_confidence_degradation(
    decisions: list[TraceEvent],
) -> list[EscalationSignal]:
    """Detect significant confidence drops in decision sequence."""
    signals: list[EscalationSignal] = []

    for i, decision in enumerate(decisions):
        if i == 0:
            continue

        confidence = _get_confidence(decision)
        prev_confidence = _get_confidence(decisions[i - 1])

        if confidence is None or prev_confidence is None:
            continue

        # Detect significant drop (>0.2)
        drop = prev_confidence - confidence
        if drop > 0.2:
            signals.append(EscalationSignal(
                event_id=decision.id,
                turn_index=i,
                signal_type="confidence_degradation",
                magnitude=min(1.0, drop),
                evidence_event_ids=[decisions[i - 1].id, decision.id],
                narrative=(
                    f"Decision confidence dropped from {prev_confidence:.2f} "
                    f"to {confidence:.2f} ({drop:.2f} decrease)"
                ),
            ))

    return signals


def _detect_safety_pressure(
    safety_events: list[TraceEvent],
) -> list[EscalationSignal]:
    """Detect high density of safety events indicating pressure."""
    if len(safety_events) < 2:
        return []

    # Group safety events by session position (every 5 events is a checkpoint)
    # Higher density indicates more safety pressure
    event_count = len(safety_events)

    # Check for escalating severity pattern
    has_escalating_severity = False
    severities = [_get_severity(e) for e in safety_events]
    if len(severities) >= 3:
        # Check if last 3 events have increasing severity
        if all(severities[i] <= severities[i + 1] for i in range(-3, -1)):
            has_escalating_severity = True

    magnitude = min(1.0, event_count / 5)
    if has_escalating_severity:
        magnitude = min(1.0, magnitude + 0.3)

    return [EscalationSignal(
        event_id=safety_events[-1].id,
        turn_index=event_count,
        signal_type="safety_pressure",
        magnitude=magnitude,
        evidence_event_ids=[e.id for e in safety_events[-5:]],
        narrative=(
            f"{event_count} safety events detected"
            f"{' with escalating severity' if has_escalating_severity else ''}"
        ),
    )]


def _detect_handoff_patterns(
    turns: list[TraceEvent],
) -> list[EscalationSignal]:
    """Detect speaker handoff patterns indicating escalation."""
    signals: list[EscalationSignal] = []

    for i, turn in enumerate(turns):
        if i == 0:
            continue

        prev_speaker = _get_speaker(turns[i - 1])
        curr_speaker = _get_speaker(turn)

        if prev_speaker == curr_speaker:
            continue

        # Check for goal transfer language
        goal = (_get_goal(turn) or "").lower()
        content = (_get_content(turn) or "").lower()
        combined = goal + " " + content

        transfer_keywords = ["escalate", "handoff", "transfer", "review", "supervisor", "hand over", "take over"]
        if any(kw in combined for kw in transfer_keywords):
            signals.append(EscalationSignal(
                event_id=turn.id,
                turn_index=i,
                signal_type="handoff_pattern",
                magnitude=0.7,
                evidence_event_ids=[turns[i - 1].id, turn.id],
                narrative=f"Speaker changed from '{prev_speaker}' to '{curr_speaker}' with transfer intent",
            ))

    return signals


def _detect_tool_stake_increase(
    tool_calls: list[TraceEvent],
) -> list[EscalationSignal]:
    """Detect increasing stakes in tool usage (destructive operations)."""
    signals: list[EscalationSignal] = []

    high_stake_tools = {
        "delete": 0.9,
        "remove": 0.8,
        "drop": 0.8,
        "truncate": 0.7,
        "update": 0.5,
        "modify": 0.5,
        "write": 0.4,
        "create": 0.3,
    }

    for i, tool in enumerate(tool_calls):
        tool_name = (_get_tool_name(tool) or "").lower()

        for keyword, stake_level in high_stake_tools.items():
            if keyword in tool_name:
                # Check if this is preceded by read-only operations
                if i > 0:
                    prev_tools = [_get_tool_name(t) or "" for t in tool_calls[:i]]
                    read_only = all(
                        not any(kw in pt.lower() for kw in high_stake_tools)
                        for pt in prev_tools[-3:]  # Check last 3 tools
                    )
                    if read_only:
                        signals.append(EscalationSignal(
                            event_id=tool.id,
                            turn_index=i,
                            signal_type="tool_stake_increase",
                            magnitude=stake_level,
                            evidence_event_ids=[tool.id],
                            narrative=f"Transitioned to high-stake operation '{tool_name}' after read-only phase",
                        ))
                break

    return signals


def _detect_decision_chain_depth(
    decisions: list[TraceEvent],
) -> list[EscalationSignal]:
    """Detect unusually long decision chains indicating complexity."""
    signals: list[EscalationSignal] = []

    if len(decisions) < 5:
        return signals

    # Long decision chains (>5) indicate complexity
    if len(decisions) > 5:
        magnitude = min(1.0, (len(decisions) - 5) / 10 + 0.3)
        signals.append(EscalationSignal(
            event_id=decisions[-1].id,
            turn_index=len(decisions),
            signal_type="decision_chain_depth",
            magnitude=magnitude,
            evidence_event_ids=[d.id for d in decisions[-5:]],
            narrative=f"Long decision chain of {len(decisions)} decisions detected",
        ))

    return signals


def _detect_explicit_keywords(
    turns: list[TraceEvent],
) -> list[EscalationSignal]:
    """Detect explicit escalation keywords (supporting signal only)."""
    keywords = ["escalate", "supervisor", "review", "critical", "urgent", "emergency"]
    signals: list[EscalationSignal] = []

    for i, turn in enumerate(turns):
        content = (_get_content(turn) or "").lower()
        goal = (_get_goal(turn) or "").lower()
        combined = content + " " + goal

        matched_keywords = [kw for kw in keywords if kw in combined]
        if matched_keywords:
            # Lower magnitude for keyword-only detection
            magnitude = 0.3 + 0.1 * len(matched_keywords)
            signals.append(EscalationSignal(
                event_id=turn.id,
                turn_index=i,
                signal_type="explicit_keyword",
                magnitude=min(0.6, magnitude),
                evidence_event_ids=[turn.id],
                narrative=f"Escalation keywords detected: {', '.join(matched_keywords)}",
            ))

    return signals


# Helper functions for extracting event attributes

def _get_confidence(event: TraceEvent) -> float | None:
    """Extract confidence from event."""
    if hasattr(event, "confidence") and event.confidence is not None:
        return event.confidence
    if hasattr(event, "data") and event.data:
        return event.data.get("confidence")
    return None


def _get_severity(event: TraceEvent) -> float:
    """Extract severity from event (0-1 scale)."""
    if hasattr(event, "severity"):
        sev = event.severity
        if isinstance(sev, (int, float)):
            return float(sev)
    if hasattr(event, "data") and event.data:
        sev = event.data.get("severity", 0)
        if isinstance(sev, (int, float)):
            return float(sev)
    return 0.0


def _get_speaker(event: TraceEvent) -> str:
    """Extract speaker from turn event."""
    if hasattr(event, "speaker") and event.speaker:
        return event.speaker
    if hasattr(event, "agent_id") and event.agent_id:
        return event.agent_id
    if hasattr(event, "data") and event.data:
        return event.data.get("speaker", event.data.get("agent_id", "unknown"))
    return "unknown"


def _get_goal(event: TraceEvent) -> str | None:
    """Extract goal from turn event."""
    if hasattr(event, "goal") and event.goal:
        return event.goal
    if hasattr(event, "data") and event.data:
        return event.data.get("goal")
    return None


def _get_content(event: TraceEvent) -> str | None:
    """Extract content from turn event."""
    if hasattr(event, "content") and event.content:
        return event.content
    if hasattr(event, "data") and event.data:
        return event.data.get("content")
    return None


def _get_tool_name(event: TraceEvent) -> str | None:
    """Extract tool name from tool call event."""
    if hasattr(event, "tool_name") and event.tool_name:
        return event.tool_name
    if hasattr(event, "name") and event.name:
        return event.name
    if hasattr(event, "data") and event.data:
        return event.data.get("tool_name", event.data.get("name"))
    return None
