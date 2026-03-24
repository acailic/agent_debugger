"""Live monitoring summary and real-time alert derivation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from agent_debugger_sdk.core.events import Checkpoint, EventType, TraceEvent

from .causal_analysis import _event_value


@dataclass
class RollingWindow:
    """Rolling window metrics for real-time monitoring."""

    window_start: datetime
    window_end: datetime
    event_count: int = 0
    tool_calls: int = 0
    llm_calls: int = 0
    decisions: int = 0
    errors: int = 0
    refusals: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    unique_tools: set[str] = field(default_factory=set)
    unique_agents: set[str] = field(default_factory=set)
    avg_confidence: float = 0.0
    state_progression: list[str] = field(default_factory=list)


@dataclass
class RollingSummary:
    """Human-readable rolling summary with structured metrics."""

    text: str
    metrics: dict[str, Any]
    window_type: str  # "time" or "event_count"
    window_size: int  # seconds or event count
    computed_at: datetime


@dataclass
class OscillationAlert:
    """Alert for detected oscillation patterns in agent behavior."""

    pattern: str  # e.g., "A->B->A->B"
    event_type: str
    repeat_count: int
    severity: float
    event_ids: list[str] = field(default_factory=list)


@dataclass
class CheckpointDelta:
    """Delta information between checkpoints."""

    checkpoint_id: str
    event_id: str
    sequence: int
    time_since_previous: float  # seconds
    events_since_previous: int
    importance_delta: float
    restore_value: float
    state_keys_changed: list[str] = field(default_factory=list)


def detect_oscillation(
    events: list[TraceEvent],
    window: int = 10,
) -> OscillationAlert | None:
    """Detect A->B->A->B patterns in tool calls or decisions.

    Algorithm:
    1. Extract sequence of (event_type, key_field) tuples
    2. For each subsequence length 2-4:
       - Check if sequence repeats at least twice
       - Compute oscillation score: repeat_count / window_size
    3. Return highest-scoring oscillation with severity
    """
    if len(events) < 4:
        return None

    recent = events[-window:] if len(events) > window else events

    # Extract sequence of (event_type, key) tuples for relevant event types
    sequence: list[tuple[str, str]] = []
    event_map: list[TraceEvent] = []

    for e in recent:
        # Only consider tool calls, decisions, and state changes for oscillation
        if e.event_type not in {EventType.TOOL_CALL, EventType.DECISION, EventType.AGENT_TURN}:
            continue

        key = e.name or str(e.event_type)
        if e.event_type == EventType.TOOL_CALL:
            tool_name = _event_value(e, "tool_name", "")
            if tool_name:
                key = tool_name
        elif e.event_type == EventType.DECISION:
            chosen_action = _event_value(e, "chosen_action", "")
            if chosen_action:
                key = chosen_action

        sequence.append((str(e.event_type), key))
        event_map.append(e)

    if len(sequence) < 4:
        return None

    # Check for oscillation patterns of different lengths
    best_alert: OscillationAlert | None = None

    for pattern_len in [2, 3, 4]:
        if len(sequence) < pattern_len * 2:
            continue

        pattern = sequence[:pattern_len]
        repeats = 1
        matched_indices: list[int] = list(range(pattern_len))

        for i in range(pattern_len, len(sequence) - pattern_len + 1, pattern_len):
            if sequence[i:i + pattern_len] == pattern:
                repeats += 1
                matched_indices.extend(range(i, i + pattern_len))

        if repeats >= 2:
            pattern_str = "->".join(p[1] for p in pattern)
            severity = min(1.0, repeats / 3.0 + (0.1 if repeats >= 3 else 0.0))
            matched_events = [event_map[i] for i in matched_indices if i < len(event_map)]

            if best_alert is None or severity > best_alert.severity:
                best_alert = OscillationAlert(
                    pattern=pattern_str,
                    event_type=pattern[0][0],
                    repeat_count=repeats,
                    severity=severity,
                    event_ids=[e.id for e in matched_events],
                )

    return best_alert


class LiveMonitor:
    """Derive a real-time monitoring snapshot from the current session state."""

    def compute_rolling_window(
        self,
        events: list[TraceEvent],
        window_seconds: int = 60,
    ) -> RollingWindow:
        """Compute rolling window metrics for the specified time period.

        Args:
            events: List of trace events to analyze
            window_seconds: Rolling window size in seconds (default: 60)

        Returns:
            RollingWindow dataclass with aggregated metrics
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_seconds)

        window = RollingWindow(
            window_start=cutoff,
            window_end=now,
        )

        recent_events = [e for e in events if e.timestamp and e.timestamp >= cutoff]

        confidences: list[float] = []
        for event in recent_events:
            window.event_count += 1

            if event.event_type == EventType.TOOL_CALL:
                window.tool_calls += 1
                tool_name = _event_value(event, "tool_name", "")
                if tool_name:
                    window.unique_tools.add(tool_name)
            elif event.event_type == EventType.LLM_REQUEST or event.event_type == EventType.LLM_RESPONSE:
                window.llm_calls += 1
                usage = _event_value(event, "usage", {}) or {}
                if isinstance(usage, dict):
                    window.total_tokens += usage.get("total_tokens", 0)
                cost = _event_value(event, "cost_usd", 0.0)
                if isinstance(cost, (int, float)):
                    window.total_cost_usd += float(cost)
            elif event.event_type == EventType.DECISION:
                window.decisions += 1
                confidence = _event_value(event, "confidence", None)
                if confidence is not None and isinstance(confidence, (int, float)):
                    confidences.append(float(confidence))
            elif event.event_type == EventType.ERROR:
                window.errors += 1
            elif event.event_type == EventType.REFUSAL:
                window.refusals += 1
            elif event.event_type == EventType.AGENT_TURN:
                speaker = _event_value(event, "speaker", "")
                if speaker:
                    window.unique_agents.add(speaker)
                state_summary = _event_value(event, "state_summary", "")
                if state_summary and isinstance(state_summary, str):
                    window.state_progression.append(state_summary)

        if confidences:
            window.avg_confidence = sum(confidences) / len(confidences)

        return window

    def build_rolling_summary(
        self,
        window: RollingWindow,
    ) -> RollingSummary:
        """Build a human-readable rolling summary from window metrics.

        Args:
            window: RollingWindow containing aggregated metrics

        Returns:
            RollingSummary with text description and structured metrics
        """
        parts: list[str] = []

        if window.event_count == 0:
            text = "No recent activity in the rolling window"
        else:
            parts.append(f"{window.event_count} events")

            detail_parts: list[str] = []
            if window.tool_calls > 0:
                detail_parts.append(f"{window.tool_calls} tool calls")
            if window.decisions > 0:
                detail_parts.append(f"{window.decisions} decisions")
            if window.llm_calls > 0:
                detail_parts.append(f"{window.llm_calls} LLM calls")

            if detail_parts:
                parts.append("(" + ", ".join(detail_parts) + ")")

            if window.errors > 0:
                parts.append(f", {window.errors} errors")
            if window.refusals > 0:
                parts.append(f", {window.refusals} refusals")

            if window.unique_tools:
                tools_preview = sorted(window.unique_tools)[:3]
                tools_str = ", ".join(tools_preview)
                if len(window.unique_tools) > 3:
                    tools_str += f" (+{len(window.unique_tools) - 3} more)"
                parts.append(f" | Tools: {tools_str}")

            text = " ".join(parts)

        metrics: dict[str, Any] = {
            "event_count": window.event_count,
            "tool_calls": window.tool_calls,
            "llm_calls": window.llm_calls,
            "decisions": window.decisions,
            "errors": window.errors,
            "refusals": window.refusals,
            "total_tokens": window.total_tokens,
            "total_cost_usd": round(window.total_cost_usd, 4),
            "unique_tools_count": len(window.unique_tools),
            "unique_agents_count": len(window.unique_agents),
            "avg_confidence": round(window.avg_confidence, 3),
        }

        return RollingSummary(
            text=text,
            metrics=metrics,
            window_type="time",
            window_size=60,
            computed_at=datetime.now(timezone.utc),
        )

    def compute_checkpoint_deltas(
        self,
        checkpoints: list[Checkpoint],
        events: list[TraceEvent],
    ) -> list[CheckpointDelta]:
        """Compute deltas between consecutive checkpoints.

        Args:
            checkpoints: List of checkpoints in sequence order
            events: List of trace events

        Returns:
            List of CheckpointDelta objects with inter-checkpoint metrics
        """
        if not checkpoints:
            return []

        deltas: list[CheckpointDelta] = []

        for i, checkpoint in enumerate(checkpoints):
            previous = checkpoints[i - 1] if i > 0 else None

            # Time since previous
            time_since = 0.0
            if previous and checkpoint.timestamp and previous.timestamp:
                time_since = (checkpoint.timestamp - previous.timestamp).total_seconds()

            # Events since previous
            events_since = 0
            if previous:
                events_since = checkpoint.sequence - previous.sequence
            else:
                events_since = checkpoint.sequence

            # Importance delta
            importance_delta = 0.0
            if previous:
                importance_delta = (checkpoint.importance or 0.0) - (previous.importance or 0.0)

            # State keys changed
            state_keys: set[str] = set()
            if previous and checkpoint.state and previous.state:
                current_keys = set(checkpoint.state.keys()) if isinstance(checkpoint.state, dict) else set()
                prev_keys = set(previous.state.keys()) if isinstance(previous.state, dict) else set()
                state_keys = current_keys.symmetric_difference(prev_keys)
                for key in current_keys & prev_keys:
                    if checkpoint.state.get(key) != previous.state.get(key):
                        state_keys.add(key)

            # Restore value estimate based on importance and position
            position_weight = 1.0 - (i / max(len(checkpoints), 1)) * 0.3
            restore_value = (checkpoint.importance or 0.5) * position_weight

            deltas.append(CheckpointDelta(
                checkpoint_id=checkpoint.id,
                event_id=checkpoint.event_id,
                sequence=checkpoint.sequence,
                time_since_previous=time_since,
                events_since_previous=events_since,
                importance_delta=round(importance_delta, 4),
                restore_value=round(restore_value, 4),
                state_keys_changed=sorted(state_keys),
            ))

        return deltas

    def build_live_summary(
        self,
        events: list[TraceEvent],
        checkpoints: list[Checkpoint],
    ) -> dict[str, Any]:
        """Build a live monitoring summary from the current persisted session state."""
        if not events:
            return {
                "event_count": 0,
                "checkpoint_count": len(checkpoints),
                "latest": {
                    "decision_event_id": None,
                    "tool_event_id": None,
                    "safety_event_id": None,
                    "turn_event_id": None,
                    "policy_event_id": None,
                    "checkpoint_id": checkpoints[-1].id if checkpoints else None,
                },
                "rolling_summary": "Awaiting richer live summaries",
                "rolling_summary_metrics": {},
                "recent_alerts": [],
                "oscillation_alert": None,
                "latest_checkpoints": [],
            }

        latest_decision = next((event for event in reversed(events) if event.event_type == EventType.DECISION), None)
        latest_tool = next(
            (
                event
                for event in reversed(events)
                if event.event_type in {EventType.TOOL_CALL, EventType.TOOL_RESULT}
            ),
            None,
        )
        latest_safety = next(
            (
                event
                for event in reversed(events)
                if event.event_type in {EventType.SAFETY_CHECK, EventType.REFUSAL, EventType.POLICY_VIOLATION}
            ),
            None,
        )
        latest_turn = next((event for event in reversed(events) if event.event_type == EventType.AGENT_TURN), None)
        latest_policy = next((event for event in reversed(events) if event.event_type == EventType.PROMPT_POLICY), None)

        recent_events = events[-12:]
        recent_alerts: list[dict[str, Any]] = [
            {
                "alert_type": _event_value(event, "alert_type", "behavior_alert"),
                "severity": _event_value(event, "severity", "medium"),
                "signal": _event_value(event, "signal", event.name),
                "event_id": event.id,
                "source": "captured",
            }
            for event in recent_events
            if event.event_type == EventType.BEHAVIOR_ALERT
        ]

        recent_tool_calls = [event for event in recent_events if event.event_type == EventType.TOOL_CALL]
        last_three_tool_calls = recent_tool_calls[-3:]
        if len(last_three_tool_calls) == 3:
            tool_name = _event_value(last_three_tool_calls[-1], "tool_name", "")
            if tool_name and all(_event_value(event, "tool_name", "") == tool_name for event in last_three_tool_calls):
                recent_alerts.append(
                    {
                        "alert_type": "tool_loop",
                        "severity": "high",
                        "signal": f"Three consecutive calls to {tool_name}",
                        "event_id": last_three_tool_calls[-1].id,
                        "source": "derived",
                    }
                )

        recent_guardrails = [
            event
            for event in recent_events
            if (
                event.event_type == EventType.REFUSAL
                or event.event_type == EventType.POLICY_VIOLATION
                or (
                    event.event_type == EventType.SAFETY_CHECK
                    and _event_value(event, "outcome", "pass") != "pass"
                )
            )
        ]
        if len(recent_guardrails) >= 2:
            recent_alerts.append(
                {
                    "alert_type": "guardrail_pressure",
                    "severity": "high" if len(recent_guardrails) >= 3 else "medium",
                    "signal": f"{len(recent_guardrails)} recent blocked or warned actions",
                    "event_id": recent_guardrails[-1].id,
                    "source": "derived",
                }
            )

        recent_policies = [event for event in recent_events if event.event_type == EventType.PROMPT_POLICY]
        unique_policies = {
            _event_value(event, "template_id", event.name)
            for event in recent_policies
            if _event_value(event, "template_id", event.name)
        }
        if len(unique_policies) >= 2:
            recent_alerts.append(
                {
                    "alert_type": "policy_shift",
                    "severity": "medium",
                    "signal": f"{len(unique_policies)} prompt policies active in the recent window",
                    "event_id": recent_policies[-1].id,
                    "source": "derived",
                }
            )

        recent_decisions = [event for event in recent_events if event.event_type == EventType.DECISION]
        last_two_decisions = recent_decisions[-2:]
        if len(last_two_decisions) == 2:
            previous_action = _event_value(last_two_decisions[0], "chosen_action", last_two_decisions[0].name)
            latest_action = _event_value(last_two_decisions[1], "chosen_action", last_two_decisions[1].name)
            if previous_action != latest_action:
                recent_alerts.append(
                    {
                        "alert_type": "strategy_change",
                        "severity": "medium",
                        "signal": f'Decision shifted from "{previous_action}" to "{latest_action}"',
                        "event_id": last_two_decisions[-1].id,
                        "source": "derived",
                    }
                )

        # Compute rolling window and summary
        window = self.compute_rolling_window(events)
        rolling = self.build_rolling_summary(window)

        # Detect oscillation patterns
        oscillation_alert = detect_oscillation(events)
        oscillation_dict: dict[str, Any] | None = None
        if oscillation_alert:
            oscillation_dict = {
                "pattern": oscillation_alert.pattern,
                "event_type": oscillation_alert.event_type,
                "repeat_count": oscillation_alert.repeat_count,
                "severity": oscillation_alert.severity,
                "event_ids": oscillation_alert.event_ids,
            }
            # Add oscillation as a derived alert if detected
            recent_alerts.append(
                {
                    "alert_type": "oscillation",
                    "severity": "high" if oscillation_alert.severity >= 0.7 else "medium",
                    "signal": (
                        f"Detected oscillation pattern: {oscillation_alert.pattern} "
                        f"(repeated {oscillation_alert.repeat_count}x)"
                    ),
                    "event_id": oscillation_alert.event_ids[-1] if oscillation_alert.event_ids else None,
                    "source": "derived",
                }
            )

        # Compute checkpoint deltas for last 5 checkpoints
        checkpoint_deltas = self.compute_checkpoint_deltas(checkpoints, events)
        latest_checkpoint_deltas = [
            {
                "checkpoint_id": d.checkpoint_id,
                "event_id": d.event_id,
                "sequence": d.sequence,
                "time_since_previous": d.time_since_previous,
                "events_since_previous": d.events_since_previous,
                "importance_delta": d.importance_delta,
                "restore_value": d.restore_value,
                "state_keys_changed": d.state_keys_changed,
            }
            for d in checkpoint_deltas[-5:]
        ]

        # Use rolling summary text as primary, fallback to state summaries
        rolling_summary_text = rolling.text
        if rolling_summary_text == "No recent activity in the rolling window":
            rolling_summary_text = (
                (_event_value(latest_turn, "state_summary", "") if latest_turn else "")
                or (_event_value(latest_policy, "state_summary", "") if latest_policy else "")
                or (_event_value(latest_decision, "reasoning", "") if latest_decision else "")
                or (recent_alerts[-1]["signal"] if recent_alerts else "Awaiting richer live summaries")
            )

        return {
            "event_count": len(events),
            "checkpoint_count": len(checkpoints),
            "latest": {
                "decision_event_id": latest_decision.id if latest_decision else None,
                "tool_event_id": latest_tool.id if latest_tool else None,
                "safety_event_id": latest_safety.id if latest_safety else None,
                "turn_event_id": latest_turn.id if latest_turn else None,
                "policy_event_id": latest_policy.id if latest_policy else None,
                "checkpoint_id": checkpoints[-1].id if checkpoints else None,
            },
            "rolling_summary": rolling_summary_text,
            "rolling_summary_metrics": rolling.metrics,
            "recent_alerts": recent_alerts[-8:],
            "oscillation_alert": oscillation_dict,
            "latest_checkpoints": latest_checkpoint_deltas,
        }
