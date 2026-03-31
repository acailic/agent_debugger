"""Live monitoring summary and real-time alert derivation."""

from __future__ import annotations

from typing import Any

from agent_debugger_sdk.core.events import Checkpoint, EventType, TraceEvent

from .alerts import (
    AlertDeriver,
    GuardrailPressureAlerter,
    PolicyShiftAlerter,
    StrategyChangeAlerter,
    ToolLoopAlerter,
)
from .causal_analysis import _event_value
from .detection import detect_oscillation
from .models import CheckpointDelta, OscillationAlert, RollingSummary, RollingWindow
from .rolling import RollingWindowCalculator

__all__ = [
    "LiveMonitor",
    "RollingWindow",
    "RollingSummary",
    "OscillationAlert",
    "CheckpointDelta",
    "detect_oscillation",
    "auto_checkpoint_on_alert",
]


class LiveMonitor:
    """Derive a real-time monitoring snapshot from the current session state."""

    def __init__(self) -> None:
        """Initialize LiveMonitor with alerters and rolling window calculator."""
        self._rolling_calculator = RollingWindowCalculator()
        self._alerters: list[AlertDeriver] = [
            ToolLoopAlerter(),
            GuardrailPressureAlerter(),
            PolicyShiftAlerter(),
            StrategyChangeAlerter(),
        ]

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
        return self._rolling_calculator.compute_rolling_window(events, window_seconds)

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
        return self._rolling_calculator.build_rolling_summary(window)

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

            deltas.append(
                CheckpointDelta(
                    checkpoint_id=checkpoint.id,
                    event_id=checkpoint.event_id,
                    sequence=checkpoint.sequence,
                    time_since_previous=time_since,
                    events_since_previous=events_since,
                    importance_delta=round(importance_delta, 4),
                    restore_value=round(restore_value, 4),
                    state_keys_changed=sorted(state_keys),
                )
            )

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
            (event for event in reversed(events) if event.event_type in {EventType.TOOL_CALL, EventType.TOOL_RESULT}),
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

        # Use alerters to derive alerts from recent events
        for alerter in self._alerters:
            derived_alerts = alerter.derive(recent_events)
            recent_alerts.extend(derived_alerts)

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


def auto_checkpoint_on_alert(
    alert_event: TraceEvent,
    session_id: str,
    events: list[TraceEvent],
) -> Checkpoint | None:
    """Create an automatic checkpoint when a behavior alert fires.

    This function captures the current session state at the point where
    a behavior alert is triggered, enabling time-travel debugging to the
    exact moment of problematic behavior.

    Args:
        alert_event: The behavior_alert event that triggered this checkpoint
        session_id: ID of the session to create a checkpoint for
        events: List of trace events up to this point in the session

    Returns:
        A Checkpoint object if the alert warrants a checkpoint, None otherwise.
        Only high-severity alerts or derived alerts create checkpoints.
    """
    from agent_debugger_sdk.core.events import Checkpoint as CheckpointClass

    # Only checkpoint on significant alerts
    severity = _event_value(alert_event, "severity", "medium")
    alert_type = _event_value(alert_event, "alert_type", "unknown")

    # Skip low-severity or unknown alert types
    if severity == "low" or alert_type == "unknown":
        return None

    # Find the most recent stateful events to capture context
    recent_turn = next(
        (event for event in reversed(events) if event.event_type == EventType.AGENT_TURN),
        None,
    )
    recent_decision = next(
        (event for event in reversed(events) if event.event_type == EventType.DECISION),
        None,
    )

    # Build a minimal state snapshot from recent events
    state: dict[str, Any] = {
        "checkpoint_reason": f"behavior_alert:{alert_type}",
        "alert_severity": severity,
        "alert_signal": _event_value(alert_event, "signal", ""),
        "alert_timestamp": alert_event.timestamp.isoformat() if alert_event.timestamp else None,
    }

    # Add context from recent turn if available
    if recent_turn:
        state["recent_turn_goal"] = _event_value(recent_turn, "goal", "")
        state["recent_turn_speaker"] = _event_value(recent_turn, "speaker", "")
        state["recent_turn_summary"] = _event_value(recent_turn, "state_summary", "")

    # Add context from recent decision if available
    if recent_decision:
        state["recent_decision_action"] = _event_value(recent_decision, "chosen_action", "")
        state["recent_decision_confidence"] = _event_value(recent_decision, "confidence", 0.0)

    # Build memory snapshot from event metadata
    memory: dict[str, Any] = {
        "triggered_by_event_id": alert_event.id,
        "triggered_by_event_type": alert_event.event_type.value,
        "total_events_at_checkpoint": len(events),
    }

    # Calculate importance based on severity
    importance = 0.8 if severity == "high" else 0.6

    # Create the checkpoint
    checkpoint = CheckpointClass(
        session_id=session_id,
        event_id=alert_event.id,
        sequence=len(events),  # Use current event count as sequence
        state=state,
        memory=memory,
        importance=importance,
    )

    return checkpoint
