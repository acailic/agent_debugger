"""Focused tests for research-driven event behavior."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.context import TraceContext
from agent_debugger_sdk.core.events import (
    Checkpoint,
    DecisionEvent,
    ErrorEvent,
    EventType,
    LLMResponseEvent,
    ToolCallEvent,
    TraceEvent,
)
from collector.buffer import EventBuffer
from collector.intelligence import TraceIntelligence
from collector.persistence import PersistenceManager
from collector.replay import build_replay
from collector.scorer import get_importance_scorer


@pytest.mark.asyncio
async def test_trace_context_records_research_events():
    """Safety, refusal, and prompt-policy events should be first-class trace data."""
    async with TraceContext(session_id="research-events", agent_name="agent", framework="test") as ctx:
        await ctx.record_safety_check(
            policy_name="tool_guard",
            outcome="block",
            risk_level="high",
            rationale="Sensitive tool requested without authorization",
            blocked_action="call_sensitive_tool",
            evidence=[{"source": "classifier", "content": "sensitive capability"}],
        )
        await ctx.record_refusal(
            reason="Unsafe tool request",
            policy_name="tool_guard",
            risk_level="high",
            blocked_action="call_sensitive_tool",
            safe_alternative="answer without tool use",
        )
        await ctx.record_prompt_policy(
            template_id="planner-v2",
            policy_parameters={"tone": "strict", "budget": 3},
            speaker="planner",
            state_summary="risk elevated",
            goal="refuse unsafe request",
        )
        events = await ctx.get_events()

    event_types = [event.event_type for event in events if hasattr(event, "event_type")]
    assert EventType.SAFETY_CHECK in event_types
    assert EventType.REFUSAL in event_types
    assert EventType.PROMPT_POLICY in event_types


def test_importance_scorer_reads_structured_fields():
    """Structured event attributes should influence scoring before persistence."""
    scorer = get_importance_scorer()

    expensive_response = scorer.score(
        LLMResponseEvent(
            model="gpt-4o",
            content="ok",
            cost_usd=0.05,
            duration_ms=2500,
        )
    )
    grounded_decision = scorer.score(
        DecisionEvent(
            reasoning="Use verified tool output",
            confidence=0.9,
            evidence=[{"source": "tool", "content": "verified"}],
            evidence_event_ids=["tool-1"],
            chosen_action="continue",
        )
    )
    unsupported_decision = scorer.score(
        DecisionEvent(
            reasoning="Guess and continue",
            confidence=0.1,
            evidence=[],
            chosen_action="continue",
        )
    )
    severe_alert = scorer.score(
        TraceEvent(
            event_type=EventType.BEHAVIOR_ALERT,
            data={"severity": "high"},
            upstream_event_ids=["decision-1"],
        )
    )

    assert expensive_response > 0.5
    assert grounded_decision > 0.9
    assert unsupported_decision >= grounded_decision
    assert severe_alert > 0.9


@pytest.mark.asyncio
async def test_persistence_manager_flushes_buffer_without_async_type_errors(tmp_path):
    """PersistenceManager should flush buffered events using the buffer's sync API."""
    buffer = EventBuffer()
    manager = PersistenceManager(buffer, storage_path=tmp_path)

    async with TraceContext(session_id="persisted-session", agent_name="agent", framework="test", event_buffer=buffer):
        pass

    await manager.flush()

    session_file = tmp_path / "persisted-session.json"
    assert session_file.exists()

    lines = session_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2

    first_event = json.loads(lines[0])
    assert first_event["event_type"] == "agent_start"


def test_build_replay_scopes_focus_to_relevant_branch():
    """Focus replay should include the selected branch, not unrelated sibling work."""
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = [
        TraceEvent(id="root", session_id="session-1", name="root", timestamp=timestamp),
        DecisionEvent(
            id="left-decision",
            session_id="session-1",
            parent_id="root",
            name="left",
            chosen_action="call left tool",
            timestamp=timestamp,
        ),
        ToolCallEvent(
            id="left-tool",
            session_id="session-1",
            parent_id="left-decision",
            name="search left",
            tool_name="search",
            timestamp=timestamp,
        ),
        ErrorEvent(
            id="left-error",
            session_id="session-1",
            parent_id="left-tool",
            name="tool failed",
            error_type="ToolFailure",
            error_message="boom",
            timestamp=timestamp,
        ),
        DecisionEvent(
            id="right-decision",
            session_id="session-1",
            parent_id="root",
            name="right",
            chosen_action="call right tool",
            timestamp=timestamp,
        ),
        ToolCallEvent(
            id="right-tool",
            session_id="session-1",
            parent_id="right-decision",
            name="search right",
            tool_name="search",
            timestamp=timestamp,
        ),
    ]
    checkpoints = [
        Checkpoint(
            id="checkpoint-root",
            session_id="session-1",
            event_id="root",
            sequence=1,
            state={"phase": "root"},
            memory={"branch": "unknown"},
            timestamp=timestamp,
        )
    ]

    replay = build_replay(
        events,
        checkpoints,
        mode="focus",
        focus_event_id="left-error",
    )

    assert [event["id"] for event in replay["events"]] == [
        "root",
        "left-decision",
        "left-tool",
        "left-error",
    ]
    assert replay["nearest_checkpoint"]["event_id"] == "root"
    assert replay["checkpoints"][0]["event_id"] == "root"


def test_trace_intelligence_emits_session_and_checkpoint_rankings():
    """Adaptive analysis should surface session replay value and ranked checkpoints."""
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = [
        TraceEvent(id="root", session_id="session-2", name="root", timestamp=timestamp),
        DecisionEvent(
            id="decision-1",
            session_id="session-2",
            parent_id="root",
            name="gate",
            chosen_action="deny",
            confidence=0.22,
            evidence=[],
            timestamp=timestamp,
        ),
        ErrorEvent(
            id="error-1",
            session_id="session-2",
            parent_id="decision-1",
            name="failure",
            error_type="RuntimeError",
            error_message="crash",
            timestamp=timestamp,
        ),
    ]
    checkpoints = [
        Checkpoint(
            id="checkpoint-1",
            session_id="session-2",
            event_id="decision-1",
            sequence=1,
            state={"step": "pre-error"},
            memory={"risk": "high"},
            importance=0.9,
            timestamp=timestamp,
        )
    ]

    analysis = TraceIntelligence().analyze_session(events, checkpoints)

    assert analysis["session_replay_value"] > 0.4
    assert analysis["retention_tier"] in {"full", "summarized"}
    assert analysis["checkpoint_rankings"][0]["checkpoint_id"] == "checkpoint-1"
    # restore_value combines replay_value (weight 0.40) with other factors;
    # it may be less than raw replay_value for low-composite events
    assert analysis["checkpoint_rankings"][0]["restore_value"] > 0
    assert analysis["session_summary"]["checkpoint_count"] == 1


def test_trace_intelligence_builds_backend_live_summary():
    """Live summary should expose backend-native recent alerts and latest event ids."""
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = [
        TraceEvent(id="root", session_id="session-3", name="root", timestamp=timestamp),
        ToolCallEvent(
            id="tool-1",
            session_id="session-3",
            parent_id="root",
            name="search one",
            tool_name="search",
            timestamp=timestamp,
        ),
        ToolCallEvent(
            id="tool-2",
            session_id="session-3",
            parent_id="root",
            name="search two",
            tool_name="search",
            timestamp=timestamp,
        ),
        ToolCallEvent(
            id="tool-3",
            session_id="session-3",
            parent_id="root",
            name="search three",
            tool_name="search",
            timestamp=timestamp,
        ),
        DecisionEvent(
            id="decision-2",
            session_id="session-3",
            parent_id="root",
            name="route",
            chosen_action="handoff to reviewer",
            reasoning="Need a second pass",
            timestamp=timestamp,
        ),
    ]
    checkpoints = [
        Checkpoint(
            id="checkpoint-live",
            session_id="session-3",
            event_id="decision-2",
            sequence=1,
            state={"step": "after-decision"},
            memory={"mode": "review"},
            timestamp=timestamp,
        )
    ]

    live_summary = TraceIntelligence().build_live_summary(events, checkpoints)

    assert live_summary["latest"]["decision_event_id"] == "decision-2"
    assert live_summary["latest"]["checkpoint_id"] == "checkpoint-live"
    assert any(alert["alert_type"] == "tool_loop" for alert in live_summary["recent_alerts"])
    assert live_summary["rolling_summary"]
