"""Tests for collector/rolling.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent_debugger_sdk.core.events import (
    AgentTurnEvent,
    DecisionEvent,
    ErrorEvent,
    EventType,
    RefusalEvent,
    ToolCallEvent,
    TraceEvent,
)
from collector.rolling import RollingWindowCalculator


def test_compute_rolling_window_aggregates_supported_event_types() -> None:
    calculator = RollingWindowCalculator()
    now = datetime.now(timezone.utc)
    events = [
        ToolCallEvent(
            id="tool-1",
            session_id="session-1",
            tool_name="search",
            timestamp=now - timedelta(seconds=5),
        ),
        TraceEvent(
            id="llm-request",
            session_id="session-1",
            event_type=EventType.LLM_REQUEST,
            timestamp=now - timedelta(seconds=4),
            data={"usage": {"total_tokens": 12}},
        ),
        TraceEvent(
            id="llm-response",
            session_id="session-1",
            event_type=EventType.LLM_RESPONSE,
            timestamp=now - timedelta(seconds=3),
            data={"usage": {"total_tokens": 8}, "cost_usd": 0.25},
        ),
        DecisionEvent(
            id="decision-1",
            session_id="session-1",
            confidence=0.4,
            timestamp=now - timedelta(seconds=2),
        ),
        ErrorEvent(
            id="error-1",
            session_id="session-1",
            error_type="TimeoutError",
            error_message="timed out",
            timestamp=now - timedelta(seconds=1),
        ),
        RefusalEvent(
            id="refusal-1",
            session_id="session-1",
            reason="unsafe",
            policy_name="policy",
            risk_level="high",
            timestamp=now - timedelta(seconds=1),
        ),
        AgentTurnEvent(
            id="turn-1",
            session_id="session-1",
            speaker="assistant",
            timestamp=now,
            data={"state_summary": "gathered evidence"},
        ),
    ]

    window = calculator.compute_rolling_window(events, window_seconds=60)

    assert window.event_count == 7
    assert window.tool_calls == 1
    assert window.llm_calls == 2
    assert window.decisions == 1
    assert window.errors == 1
    assert window.refusals == 1
    assert window.total_tokens == 20
    assert window.total_cost_usd == 0.25
    assert window.unique_tools == {"search"}
    assert window.unique_agents == {"assistant"}
    assert window.state_progression == ["gathered evidence"]
    assert window.avg_confidence == 0.4


def test_compute_rolling_window_ignores_old_and_missing_timestamps() -> None:
    calculator = RollingWindowCalculator()
    now = datetime.now(timezone.utc)
    events = [
        ToolCallEvent(
            id="recent-tool",
            session_id="session-1",
            tool_name="search",
            timestamp=now - timedelta(seconds=5),
        ),
        ToolCallEvent(
            id="old-tool",
            session_id="session-1",
            tool_name="browse",
            timestamp=now - timedelta(minutes=5),
        ),
        TraceEvent(
            id="missing-time",
            session_id="session-1",
            event_type=EventType.ERROR,
            timestamp=None,
        ),
    ]

    window = calculator.compute_rolling_window(events, window_seconds=60)

    assert window.event_count == 1
    assert window.tool_calls == 1
    assert window.unique_tools == {"search"}
