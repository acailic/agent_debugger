"""Tests for retry churn detection functionality."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import (
    EventType,
    ToolCallEvent,
    ToolResultEvent,
)
from collector.intelligence.facade import TraceIntelligence


class TestRetryChurnDetection:
    """Tests for retry churn detection functionality."""

    @pytest.fixture
    def intelligence(self) -> TraceIntelligence:
        """Create a TraceIntelligence instance for tests."""
        return TraceIntelligence()

    @pytest.fixture
    def events_with_retry_churn(self, make_trace_event):
        """Create events with retry churn pattern - consecutive tool calls to same tool."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        return [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            ToolCallEvent(
                id="tool-call-1",
                session_id="session-1",
                tool_name="search",
                arguments={"query": "test query"},
                timestamp=timestamp,
            ),
            ToolCallEvent(
                id="tool-call-2",
                session_id="session-1",
                tool_name="search",
                arguments={"query": "test query"},
                timestamp=timestamp,
            ),
            ToolCallEvent(
                id="tool-call-3",
                session_id="session-1",
                tool_name="search",
                arguments={"query": "test query"},
                timestamp=timestamp,
            ),
        ]

    def test_detect_tool_loop_as_churn_indicator(self, events_with_retry_churn, intelligence):
        """Verify that repeated tool calls trigger tool_loop alerts."""
        analysis = intelligence.analyze_session(events_with_retry_churn, [])
        tool_loop_alerts = [alert for alert in analysis["behavior_alerts"] if alert["alert_type"] == "tool_loop"]
        assert len(tool_loop_alerts) >= 1, "Should detect tool loop from retry churn"
        for alert in tool_loop_alerts:
            assert "severity" in alert
            assert alert["severity"] == "high"
            assert "signal" in alert
            assert "event_id" in alert

    def test_churn_affects_novelty_and_recurrence(self, events_with_retry_churn, intelligence):
        """Verify that retry churn affects novelty and recurrence scores."""
        analysis = intelligence.analyze_session(events_with_retry_churn, [])
        tool_call_rankings = [r for r in analysis["event_rankings"] if r["event_type"] == "tool_call"]
        assert len(tool_call_rankings) >= 3
        for ranking in tool_call_rankings:
            assert ranking["novelty"] < 0.5
        for ranking in tool_call_rankings:
            assert ranking["recurrence"] >= 0.5, "Higher recurrence means more like retry"
        assert analysis["retention_tier"] in {"full", "summarized"}, (
            "Sessions with churn should have higher retention tier"
        )

    def test_different_tool_calls_no_churn(self, intelligence, make_trace_event):
        """Verify that different tool calls don't trigger churn detection."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            ToolCallEvent(
                id="tool-call-1",
                session_id="session-1",
                tool_name="search",
                arguments={"query": "query 1"},
                timestamp=timestamp,
            ),
            ToolResultEvent(
                id="tool-result-1",
                session_id="session-1",
                tool_name="search",
                result="ok",
                timestamp=timestamp,
            ),
            ToolCallEvent(
                id="tool-call-2",
                session_id="session-1",
                tool_name="read",
                arguments={"file": "test.txt"},
                timestamp=timestamp,
            ),
            ToolResultEvent(
                id="tool-result-2",
                session_id="session-1",
                tool_name="read",
                result="ok",
                timestamp=timestamp,
            ),
        ]
        analysis = intelligence.analyze_session(events, [])
        tool_loop_alerts = [alert for alert in analysis["behavior_alerts"] if alert["alert_type"] == "tool_loop"]
        assert len(tool_loop_alerts) == 0, "Different tools should not trigger tool loop"
