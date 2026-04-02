"""Tests for alert derivation system."""

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.alerts.base import AlertDeriver
from collector.alerts.guardrail import GuardrailPressureAlerter
from collector.alerts.policy_shift import PolicyShiftAlerter
from collector.alerts.strategy_change import StrategyChangeAlerter
from collector.alerts.tool_loop import ToolLoopAlerter

# =============================================================================
# Test Helpers
# =============================================================================


def make_event(
    session_id: str = "s1",
    name: str = "test",
    event_type: EventType = EventType.TOOL_CALL,
    data: dict | None = None,
    metadata: dict | None = None,
    importance: float = 0.5,
    parent_id: str | None = None,
    upstream_event_ids: list | None = None,
) -> TraceEvent:
    """Factory to create TraceEvent instances for tests."""
    return TraceEvent(
        session_id=session_id,
        parent_id=parent_id,
        event_type=event_type,
        name=name,
        data=data or {},
        metadata=metadata or {},
        importance=importance,
        upstream_event_ids=upstream_event_ids or [],
    )


def assert_alert_structure(alert: dict, expected_type: str, expected_severity: str) -> None:
    """Helper to assert alert has required structure."""
    assert alert["alert_type"] == expected_type
    assert alert["severity"] == expected_severity
    assert "signal" in alert
    assert "event_id" in alert
    assert alert["source"] == "derived"


# =============================================================================
# ToolLoopAlerter Tests
# =============================================================================


class TestToolLoopAlerter:
    """Tests for ToolLoopAlerter."""

    def test_is_alert_deriver(self) -> None:
        """ToolLoopAlerter should implement AlertDeriver protocol."""
        alerter = ToolLoopAlerter()
        assert isinstance(alerter, AlertDeriver)
        assert hasattr(alerter, "derive")

    def test_no_loop_with_less_than_three_tool_calls(self) -> None:
        """Should not alert when there are fewer than 3 tool calls."""
        alerter = ToolLoopAlerter()
        events = [
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "search"}),
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "search"}),
        ]
        alerts = alerter.derive(events)
        assert alerts == []

    def test_detects_loop_with_three_same_tool_calls(self) -> None:
        """Should alert when there are 3 consecutive calls to the same tool."""
        alerter = ToolLoopAlerter()
        events = [
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "search"}),
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "search"}),
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "search"}),
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        assert_alert_structure(alerts[0], "tool_loop", "high")
        assert "search" in alerts[0]["signal"]
        assert alerts[0]["event_id"] == events[-1].id

    def test_no_loop_with_three_different_tools(self) -> None:
        """Should not alert when 3 consecutive calls are to different tools."""
        alerter = ToolLoopAlerter()
        events = [
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "search"}),
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "read"}),
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "write"}),
        ]
        alerts = alerter.derive(events)
        assert alerts == []

    def test_no_loop_with_two_same_then_one_different(self) -> None:
        """Should not alert when pattern is 2 same + 1 different."""
        alerter = ToolLoopAlerter()
        events = [
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "search"}),
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "search"}),
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "read"}),
        ]
        alerts = alerter.derive(events)
        assert alerts == []

    def test_no_loop_with_one_different_then_two_same(self) -> None:
        """Should not alert when pattern is 1 different + 2 same (not consecutive)."""
        alerter = ToolLoopAlerter()
        events = [
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "search"}),
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "read"}),
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "read"}),
        ]
        alerts = alerter.derive(events)
        assert alerts == []

    def test_detects_loop_with_more_than_three_same_calls(self) -> None:
        """Should alert when there are 4+ consecutive calls to the same tool."""
        alerter = ToolLoopAlerter()
        events = [
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "search"}),
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "search"}),
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "search"}),
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "search"}),
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        assert_alert_structure(alerts[0], "tool_loop", "high")

    def test_ignores_non_tool_call_events(self) -> None:
        """Should only consider TOOL_CALL events, ignoring others."""
        alerter = ToolLoopAlerter()
        events = [
            make_event(event_type=EventType.LLM_REQUEST),
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "search"}),
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "search"}),
            make_event(event_type=EventType.TOOL_CALL, data={"tool_name": "search"}),
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1

    def test_empty_event_list(self) -> None:
        """Should handle empty event list gracefully."""
        alerter = ToolLoopAlerter()
        alerts = alerter.derive([])
        assert alerts == []

    def test_no_tool_name_in_data(self) -> None:
        """Should not alert when tool_name is missing or empty."""
        alerter = ToolLoopAlerter()
        events = [
            make_event(event_type=EventType.TOOL_CALL, data={}),
            make_event(event_type=EventType.TOOL_CALL, data={}),
            make_event(event_type=EventType.TOOL_CALL, data={}),
        ]
        alerts = alerter.derive(events)
        assert alerts == []


# =============================================================================
# GuardrailPressureAlerter Tests
# =============================================================================


class TestGuardrailPressureAlerter:
    """Tests for GuardrailPressureAlerter."""

    def test_is_alert_deriver(self) -> None:
        """GuardrailPressureAlerter should implement AlertDeriver protocol."""
        alerter = GuardrailPressureAlerter()
        assert isinstance(alerter, AlertDeriver)
        assert hasattr(alerter, "derive")

    def test_no_alert_with_zero_guardrails(self) -> None:
        """Should not alert when there are no guardrail events."""
        alerter = GuardrailPressureAlerter()
        events = [
            make_event(event_type=EventType.TOOL_CALL),
            make_event(event_type=EventType.LLM_REQUEST),
        ]
        alerts = alerter.derive(events)
        assert alerts == []

    def test_no_alert_with_single_guardrail(self) -> None:
        """Should not alert when there is only 1 guardrail event."""
        alerter = GuardrailPressureAlerter()
        events = [
            make_event(event_type=EventType.REFUSAL, data={"reason": "blocked"}),
        ]
        alerts = alerter.derive(events)
        assert alerts == []

    def test_medium_severity_with_two_guardrails(self) -> None:
        """Should alert with medium severity when there are 2 guardrails."""
        alerter = GuardrailPressureAlerter()
        events = [
            make_event(event_type=EventType.REFUSAL, data={"reason": "blocked1"}),
            make_event(event_type=EventType.POLICY_VIOLATION, data={"policy": "violation1"}),
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        assert_alert_structure(alerts[0], "guardrail_pressure", "medium")
        assert "2 recent blocked or warned actions" in alerts[0]["signal"]

    def test_high_severity_with_three_guardrails(self) -> None:
        """Should alert with high severity when there are 3+ guardrails."""
        alerter = GuardrailPressureAlerter()
        events = [
            make_event(event_type=EventType.REFUSAL, data={"reason": "blocked1"}),
            make_event(event_type=EventType.POLICY_VIOLATION, data={"policy": "violation1"}),
            make_event(event_type=EventType.REFUSAL, data={"reason": "blocked2"}),
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        assert_alert_structure(alerts[0], "guardrail_pressure", "high")
        assert "3 recent blocked or warned actions" in alerts[0]["signal"]

    def test_high_severity_with_many_guardrails(self) -> None:
        """Should alert with high severity when there are 5+ guardrails."""
        alerter = GuardrailPressureAlerter()
        events = [make_event(event_type=EventType.REFUSAL, data={"reason": f"blocked{i}"}) for i in range(5)]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "high"
        assert "5 recent blocked or warned actions" in alerts[0]["signal"]

    def test_safety_check_with_outcome_pass_does_not_count(self) -> None:
        """SAFETY_CHECK events with outcome='pass' should NOT count as guardrails."""
        alerter = GuardrailPressureAlerter()
        events = [
            make_event(event_type=EventType.SAFETY_CHECK, data={"outcome": "pass", "check": "safe"}),
            make_event(event_type=EventType.REFUSAL, data={"reason": "blocked"}),
        ]
        alerts = alerter.derive(events)
        # Only 1 actual guardrail (REFUSAL), so no alert
        assert alerts == []

    def test_safety_check_with_non_pass_outcome_counts(self) -> None:
        """SAFETY_CHECK events with outcome != 'pass' should count as guardrails."""
        alerter = GuardrailPressureAlerter()
        events = [
            make_event(event_type=EventType.SAFETY_CHECK, data={"outcome": "fail", "check": "unsafe"}),
            make_event(event_type=EventType.REFUSAL, data={"reason": "blocked"}),
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        assert_alert_structure(alerts[0], "guardrail_pressure", "medium")

    def test_safety_check_with_missing_outcome_defaults_to_pass(self) -> None:
        """SAFETY_CHECK events with missing outcome should default to 'pass' and not count."""
        alerter = GuardrailPressureAlerter()
        events = [
            make_event(event_type=EventType.SAFETY_CHECK, data={"check": "test"}),
            make_event(event_type=EventType.REFUSAL, data={"reason": "blocked"}),
        ]
        alerts = alerter.derive(events)
        # Missing outcome defaults to 'pass', so only 1 actual guardrail
        assert alerts == []

    def test_all_guardrail_types_contribute(self) -> None:
        """REFUSAL, POLICY_VIOLATION, and failed SAFETY_CHECK all count."""
        alerter = GuardrailPressureAlerter()
        events = [
            make_event(event_type=EventType.REFUSAL, data={"reason": "blocked"}),
            make_event(event_type=EventType.POLICY_VIOLATION, data={"policy": "violated"}),
            make_event(event_type=EventType.SAFETY_CHECK, data={"outcome": "fail", "check": "unsafe"}),
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "high"
        assert "3 recent blocked or warned actions" in alerts[0]["signal"]

    def test_ignores_non_guardrail_events(self) -> None:
        """Should only consider guardrail events, ignoring others."""
        alerter = GuardrailPressureAlerter()
        events = [
            make_event(event_type=EventType.TOOL_CALL),
            make_event(event_type=EventType.REFUSAL, data={"reason": "blocked"}),
            make_event(event_type=EventType.LLM_REQUEST),
            make_event(event_type=EventType.POLICY_VIOLATION, data={"policy": "violation"}),
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        assert_alert_structure(alerts[0], "guardrail_pressure", "medium")

    def test_alert_uses_last_guardrail_event_id(self) -> None:
        """Alert should reference the last guardrail event's ID."""
        alerter = GuardrailPressureAlerter()
        events = [
            make_event(event_type=EventType.REFUSAL, data={"reason": "blocked1"}),
            make_event(event_type=EventType.POLICY_VIOLATION, data={"policy": "violation"}),
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        assert alerts[0]["event_id"] == events[-1].id


# =============================================================================
# PolicyShiftAlerter Tests
# =============================================================================


class TestPolicyShiftAlerter:
    """Tests for PolicyShiftAlerter."""

    def test_is_alert_deriver(self) -> None:
        """PolicyShiftAlerter should implement AlertDeriver protocol."""
        alerter = PolicyShiftAlerter()
        assert isinstance(alerter, AlertDeriver)
        assert hasattr(alerter, "derive")

    def test_no_alert_with_zero_policies(self) -> None:
        """Should not alert when there are no policy events."""
        alerter = PolicyShiftAlerter()
        events = [
            make_event(event_type=EventType.TOOL_CALL),
            make_event(event_type=EventType.LLM_REQUEST),
        ]
        alerts = alerter.derive(events)
        assert alerts == []

    def test_no_alert_with_single_policy(self) -> None:
        """Should not alert when there is only 1 unique policy."""
        alerter = PolicyShiftAlerter()
        events = [
            make_event(event_type=EventType.PROMPT_POLICY, data={"template_id": "policy_a"}),
        ]
        alerts = alerter.derive(events)
        assert alerts == []

    def test_alert_with_two_unique_policies(self) -> None:
        """Should alert when there are 2+ unique template_ids."""
        alerter = PolicyShiftAlerter()
        events = [
            make_event(event_type=EventType.PROMPT_POLICY, data={"template_id": "policy_a"}),
            make_event(event_type=EventType.PROMPT_POLICY, data={"template_id": "policy_b"}),
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        assert_alert_structure(alerts[0], "policy_shift", "medium")
        assert "2 prompt policies active" in alerts[0]["signal"]

    def test_alert_with_three_unique_policies(self) -> None:
        """Should alert when there are 3+ unique template_ids."""
        alerter = PolicyShiftAlerter()
        events = [
            make_event(event_type=EventType.PROMPT_POLICY, data={"template_id": f"policy_{chr(65 + i)}"})
            for i in range(3)
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        assert_alert_structure(alerts[0], "policy_shift", "medium")
        assert "3 prompt policies active" in alerts[0]["signal"]

    def test_no_alert_with_duplicate_policy_ids(self) -> None:
        """Should not alert when same template_id appears multiple times."""
        alerter = PolicyShiftAlerter()
        events = [
            make_event(event_type=EventType.PROMPT_POLICY, data={"template_id": "policy_a"}),
            make_event(event_type=EventType.PROMPT_POLICY, data={"template_id": "policy_a"}),
            make_event(event_type=EventType.PROMPT_POLICY, data={"template_id": "policy_a"}),
        ]
        alerts = alerter.derive(events)
        assert alerts == []

    def test_uses_name_as_fallback_for_template_id(self) -> None:
        """Should use event name when template_id is missing."""
        alerter = PolicyShiftAlerter()
        events = [
            make_event(event_type=EventType.PROMPT_POLICY, name="policy_x", data={}),
            make_event(event_type=EventType.PROMPT_POLICY, name="policy_y", data={}),
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        assert_alert_structure(alerts[0], "policy_shift", "medium")

    def test_ignores_empty_template_id_and_name(self) -> None:
        """Should ignore policies with empty/None template_id."""
        alerter = PolicyShiftAlerter()
        events = [
            make_event(event_type=EventType.PROMPT_POLICY, data={"template_id": ""}, name=""),
            make_event(event_type=EventType.PROMPT_POLICY, data={"template_id": "policy_a"}),
        ]
        alerts = alerter.derive(events)
        # Only 1 valid policy, so no alert
        assert alerts == []

    def test_ignores_non_policy_events(self) -> None:
        """Should only consider PROMPT_POLICY events."""
        alerter = PolicyShiftAlerter()
        events = [
            make_event(event_type=EventType.TOOL_CALL),
            make_event(event_type=EventType.PROMPT_POLICY, data={"template_id": "policy_a"}),
            make_event(event_type=EventType.LLM_REQUEST),
            make_event(event_type=EventType.PROMPT_POLICY, data={"template_id": "policy_b"}),
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        assert_alert_structure(alerts[0], "policy_shift", "medium")

    def test_alert_uses_last_policy_event_id(self) -> None:
        """Alert should reference the last policy event's ID."""
        alerter = PolicyShiftAlerter()
        events = [
            make_event(event_type=EventType.PROMPT_POLICY, data={"template_id": "policy_a"}),
            make_event(event_type=EventType.PROMPT_POLICY, data={"template_id": "policy_b"}),
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        assert alerts[0]["event_id"] == events[-1].id


# =============================================================================
# StrategyChangeAlerter Tests
# =============================================================================


class TestStrategyChangeAlerter:
    """Tests for StrategyChangeAlerter."""

    def test_is_alert_deriver(self) -> None:
        """StrategyChangeAlerter should implement AlertDeriver protocol."""
        alerter = StrategyChangeAlerter()
        assert isinstance(alerter, AlertDeriver)
        assert hasattr(alerter, "derive")

    def test_no_alert_with_zero_decisions(self) -> None:
        """Should not alert when there are no decision events."""
        alerter = StrategyChangeAlerter()
        events = [
            make_event(event_type=EventType.TOOL_CALL),
            make_event(event_type=EventType.LLM_REQUEST),
        ]
        alerts = alerter.derive(events)
        assert alerts == []

    def test_no_alert_with_single_decision(self) -> None:
        """Should not alert when there is only 1 decision event."""
        alerter = StrategyChangeAlerter()
        events = [
            make_event(
                event_type=EventType.DECISION,
                data={"chosen_action": "action_a", "reasoning": "test"},
            ),
        ]
        alerts = alerter.derive(events)
        assert alerts == []

    def test_alert_when_chosen_action_changes(self) -> None:
        """Should alert when chosen_action shifts between consecutive decisions."""
        alerter = StrategyChangeAlerter()
        events = [
            make_event(
                event_type=EventType.DECISION,
                data={"chosen_action": "action_a", "reasoning": "test"},
            ),
            make_event(
                event_type=EventType.DECISION,
                data={"chosen_action": "action_b", "reasoning": "test"},
            ),
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        assert_alert_structure(alerts[0], "strategy_change", "medium")
        assert 'action_a" to "action_b' in alerts[0]["signal"]

    def test_no_alert_when_same_action_repeated(self) -> None:
        """Should not alert when chosen_action is the same across decisions."""
        alerter = StrategyChangeAlerter()
        events = [
            make_event(
                event_type=EventType.DECISION,
                data={"chosen_action": "action_a", "reasoning": "test"},
            ),
            make_event(
                event_type=EventType.DECISION,
                data={"chosen_action": "action_a", "reasoning": "test"},
            ),
        ]
        alerts = alerter.derive(events)
        assert alerts == []

    def test_uses_name_as_fallback_for_chosen_action(self) -> None:
        """Should use event name when chosen_action is missing."""
        alerter = StrategyChangeAlerter()
        events = [
            make_event(event_type=EventType.DECISION, name="action_x", data={}),
            make_event(event_type=EventType.DECISION, name="action_y", data={}),
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        assert_alert_structure(alerts[0], "strategy_change", "medium")
        assert 'action_x" to "action_y' in alerts[0]["signal"]

    def test_ignores_non_decision_events(self) -> None:
        """Should only consider DECISION events."""
        alerter = StrategyChangeAlerter()
        events = [
            make_event(event_type=EventType.TOOL_CALL),
            make_event(
                event_type=EventType.DECISION,
                data={"chosen_action": "action_a", "reasoning": "test"},
            ),
            make_event(event_type=EventType.LLM_REQUEST),
            make_event(
                event_type=EventType.DECISION,
                data={"chosen_action": "action_b", "reasoning": "test"},
            ),
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        assert_alert_structure(alerts[0], "strategy_change", "medium")

    def test_only_considers_last_two_decisions(self) -> None:
        """Should only compare the last 2 decisions, ignoring earlier ones."""
        alerter = StrategyChangeAlerter()
        events = [
            make_event(
                event_type=EventType.DECISION,
                data={"chosen_action": "action_a", "reasoning": "test"},
            ),
            make_event(
                event_type=EventType.DECISION,
                data={"chosen_action": "action_b", "reasoning": "test"},
            ),
            make_event(
                event_type=EventType.DECISION,
                data={"chosen_action": "action_c", "reasoning": "test"},
            ),
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        # Should compare action_b -> action_c, not action_a -> action_b
        assert 'action_b" to "action_c' in alerts[0]["signal"]

    def test_alert_uses_latest_decision_event_id(self) -> None:
        """Alert should reference the latest decision event's ID."""
        alerter = StrategyChangeAlerter()
        events = [
            make_event(
                event_type=EventType.DECISION,
                data={"chosen_action": "action_a", "reasoning": "test"},
            ),
            make_event(
                event_type=EventType.DECISION,
                data={"chosen_action": "action_b", "reasoning": "test"},
            ),
        ]
        alerts = alerter.derive(events)
        assert len(alerts) == 1
        assert alerts[0]["event_id"] == events[-1].id

    def test_with_three_decisions_no_change_at_end(self) -> None:
        """Should not alert when last two decisions have same action."""
        alerter = StrategyChangeAlerter()
        events = [
            make_event(
                event_type=EventType.DECISION,
                data={"chosen_action": "action_a", "reasoning": "test"},
            ),
            make_event(
                event_type=EventType.DECISION,
                data={"chosen_action": "action_b", "reasoning": "test"},
            ),
            make_event(
                event_type=EventType.DECISION,
                data={"chosen_action": "action_b", "reasoning": "test"},
            ),
        ]
        alerts = alerter.derive(events)
        # Last two are both action_b, so no alert
        assert alerts == []
