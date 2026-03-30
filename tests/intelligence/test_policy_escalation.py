"""Tests for policy escalation tracking functionality."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import (
    EventType,
    PromptPolicyEvent,
    SafetyCheckEvent,
)
from collector.intelligence import TraceIntelligence


class TestPolicyEscalationTracking:
    """Tests for policy escalation tracking functionality."""

    @pytest.fixture
    def intelligence(self) -> TraceIntelligence:
        """Create a TraceIntelligence instance for tests."""
        return TraceIntelligence()

    @pytest.fixture
    def events_with_policy_escalation(self, make_trace_event):
        """Create events with policy escalation pattern."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        return [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            PromptPolicyEvent(
                id="policy-1",
                session_id="session-1",
                template_id="low-risk-policy",
                policy_parameters={"strictness": "low"},
                speaker="system",
                state_summary="Low risk mode",
                goal="Normal operation",
                timestamp=timestamp,
            ),
            SafetyCheckEvent(
                id="safety-1",
                session_id="session-1",
                policy_name="low-risk-policy",
                outcome="pass",
                risk_level="low",
                rationale="No issues detected",
                timestamp=timestamp,
            ),
            PromptPolicyEvent(
                id="policy-2",
                session_id="session-1",
                template_id="high-risk-policy",
                policy_parameters={"strictness": "high"},
                speaker="system",
                state_summary="Escalated to high risk",
                goal="Handle elevated risk",
                timestamp=timestamp,
            ),
            SafetyCheckEvent(
                id="safety-2",
                session_id="session-1",
                policy_name="high-risk-policy",
                outcome="warn",
                risk_level="medium",
                rationale="Potential issue detected",
                timestamp=timestamp,
            ),
            PromptPolicyEvent(
                id="policy-3",
                session_id="session-1",
                template_id="critical-policy",
                policy_parameters={"strictness": "critical"},
                speaker="system",
                state_summary="Critical mode",
                goal="Block dangerous actions",
                timestamp=timestamp,
            ),
            SafetyCheckEvent(
                id="safety-3",
                session_id="session-1",
                policy_name="critical-policy",
                outcome="block",
                risk_level="high",
                rationale="Dangerous action blocked",
                blocked_action="execute_command",
                timestamp=timestamp,
            ),
        ]

    def test_detect_policy_shifts_via_live_summary(self, events_with_policy_escalation, intelligence):
        """Verify that policy shifts are detected in live summary."""
        live_summary = intelligence.build_live_summary(events_with_policy_escalation, [])
        policy_shift_alerts = [
            alert for alert in live_summary["recent_alerts"] if alert["alert_type"] == "policy_shift"
        ]
        assert len(policy_shift_alerts) >= 1, "Should detect policy shifts"
        for alert in policy_shift_alerts:
            assert alert["severity"] == "medium"
            assert "signal" in alert
            assert "policies" in alert["signal"].lower() or "policy" in alert["signal"].lower()

    def test_escalation_increases_replay_value(self, events_with_policy_escalation, intelligence):
        """Verify that policy escalation increases session replay value."""
        analysis = intelligence.analyze_session(events_with_policy_escalation, [])
        assert analysis["session_replay_value"] > 0.4, "Policy escalation should increase replay value"
        assert analysis["retention_tier"] in {"full", "summarized"}

    def test_blocked_actions_have_high_severity(self, events_with_policy_escalation, intelligence):
        """Verify that blocked actions have high severity scores."""
        analysis = intelligence.analyze_session(events_with_policy_escalation, [])
        blocked_safety_ranking = next(r for r in analysis["event_rankings"] if r["event_id"] == "safety-3")
        assert blocked_safety_ranking["severity"] >= 0.75, "Blocked safety checks should have high severity"

    def test_escalation_chain_in_failure_explanations(self, events_with_policy_escalation, intelligence):
        """Verify that policy escalation appears in failure explanations."""
        analysis = intelligence.analyze_session(events_with_policy_escalation, [])
        failed_safety = [e for e in analysis["failure_explanations"] if e["failure_event_id"] == "safety-3"]
        assert len(failed_safety) == 1
        explanation = failed_safety[0]
        assert "failure_mode" in explanation
        assert "symptom" in explanation
        assert "likely_cause" in explanation

    def test_no_escalation_in_stable_session(self, intelligence, make_trace_event):
        """Verify that stable sessions don't trigger escalation alerts."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            PromptPolicyEvent(
                id="policy-1",
                session_id="session-1",
                template_id="stable-policy",
                policy_parameters={"strictness": "medium"},
                speaker="system",
                state_summary="Stable mode",
                goal="Normal operation",
                timestamp=timestamp,
            ),
            SafetyCheckEvent(
                id="safety-1",
                session_id="session-1",
                policy_name="stable-policy",
                outcome="pass",
                risk_level="low",
                rationale="No issues",
                timestamp=timestamp,
            ),
        ]
        live_summary = intelligence.build_live_summary(events, [])
        policy_shift_alerts = [
            alert for alert in live_summary["recent_alerts"] if alert["alert_type"] == "policy_shift"
        ]
        assert len(policy_shift_alerts) == 0, "Single policy should not trigger policy shift"
