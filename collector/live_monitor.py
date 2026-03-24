"""Live monitoring summary and real-time alert derivation."""

from __future__ import annotations

from typing import Any

from agent_debugger_sdk.core.events import Checkpoint, EventType, TraceEvent

from .causal_analysis import _event_value


class LiveMonitor:
    """Derive a real-time monitoring snapshot from the current session state."""

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
                "recent_alerts": [],
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

        rolling_summary = (
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
            "rolling_summary": rolling_summary,
            "recent_alerts": recent_alerts[-6:],
        }
