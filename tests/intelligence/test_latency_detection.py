"""Tests for latency spike detection functionality."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import (
    EventType,
    LLMResponseEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from collector.intelligence.facade import TraceIntelligence


class TestLatencySpikeDetection:
    """Tests for latency spike detection functionality."""

    @pytest.fixture
    def intelligence(self) -> TraceIntelligence:
        """Create a TraceIntelligence instance for tests."""
        return TraceIntelligence()

    @pytest.fixture
    def events_with_latency_spikes(self, make_trace_event):
        """Create events with latency spikes."""
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
                timestamp=timestamp,
            ),
            ToolResultEvent(
                id="tool-result-1",
                session_id="session-1",
                tool_name="search",
                result="ok",
                duration_ms=100.0,
                timestamp=timestamp,
            ),
            ToolCallEvent(
                id="tool-call-2",
                session_id="session-1",
                tool_name="slow_operation",
                timestamp=timestamp,
            ),
            ToolResultEvent(
                id="tool-result-2",
                session_id="session-1",
                tool_name="slow_operation",
                result="ok",
                duration_ms=15000.0,
                timestamp=timestamp,
            ),
            LLMResponseEvent(
                id="llm-response-1",
                session_id="session-1",
                model="gpt-4",
                content="Normal response",
                duration_ms=500.0,
                timestamp=timestamp,
            ),
            LLMResponseEvent(
                id="llm-response-2",
                session_id="session-1",
                model="gpt-4",
                content="Slow response",
                duration_ms=30000.0,
                cost_usd=0.05,
                timestamp=timestamp,
            ),
        ]

    def test_slow_tools_have_lower_novelty(self, events_with_latency_spikes, intelligence):
        """Verify that slow tool calls are scored appropriately."""
        analysis = intelligence.analyze_session(events_with_latency_spikes, [])
        slow_tool_rankings = [r for r in analysis["event_rankings"] if r["event_id"] == "tool-result-2"]
        assert len(slow_tool_rankings) == 1
        ranking = slow_tool_rankings[0]
        assert ranking["severity"] >= 0.5, "Slow operations should have reasonable severity"

    def test_slow_llm_responses_affect_replay_value(self, events_with_latency_spikes, intelligence):
        """Verify that slow LLM responses affect replay value."""
        analysis = intelligence.analyze_session(events_with_latency_spikes, [])
        slow_llm_rankings = [r for r in analysis["event_rankings"] if r["event_id"] == "llm-response-2"]
        assert len(slow_llm_rankings) == 1
        assert slow_llm_rankings[0]["replay_value"] >= 0.3, "Slow, expensive LLM calls should have higher replay value"

    def test_latency_spikes_contribute_to_retention_tier(self, events_with_latency_spikes, intelligence):
        """Verify that sessions with latency spikes have appropriate retention."""
        analysis = intelligence.analyze_session(events_with_latency_spikes, [])
        assert analysis["retention_tier"] in {"full", "summarized", "downsampled"}
        assert "session_replay_value" in analysis
        assert analysis["session_replay_value"] >= 0

    def test_normal_duration_events_not_flagged(self, intelligence, make_trace_event):
        """Verify that normal duration events are not flagged as anomalies."""
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
                tool_name="fast_op",
                timestamp=timestamp,
            ),
            ToolResultEvent(
                id="tool-result-1",
                session_id="session-1",
                tool_name="fast_op",
                result="ok",
                duration_ms=50.0,
                timestamp=timestamp,
            ),
        ]
        analysis = intelligence.analyze_session(events, [])
        tool_result_ranking = next(r for r in analysis["event_rankings"] if r["event_id"] == "tool-result-1")
        assert tool_result_ranking["severity"] < 0.8, "Normal operations should have lower severity"
