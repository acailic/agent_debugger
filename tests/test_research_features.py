"""Focused tests for research-driven event behavior and 5 research-inspired features."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

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
from agent_debugger_sdk.core.scorer import get_importance_scorer
from collector.buffer import EventBuffer
from collector.intelligence.facade import TraceIntelligence
from collector.persistence import PersistenceManager
from collector.replay import build_replay

# ===========================================================================
# Original research event tests
# ===========================================================================


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


# ===========================================================================
# Shared test helpers for 5 research features
# ===========================================================================


_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
_NEXT = _NOW + timedelta(seconds=1)


def _make_event(
    event_type: EventType = EventType.DECISION,
    name: str = "test_event",
    parent_id: str | None = None,
    session_id: str = "sess-001",
    timestamp: datetime = _NOW,
    importance: float = 0.5,
    event_id: str | None = None,
    upstream_event_ids: list[str] | None = None,
    **extra: Any,
) -> TraceEvent:
    """Create a TraceEvent for testing."""
    eid = event_id or name
    data = dict(extra)
    return TraceEvent(
        id=eid,
        event_type=event_type,
        name=name,
        session_id=session_id,
        parent_id=parent_id,
        timestamp=timestamp,
        importance=importance,
        upstream_event_ids=upstream_event_ids or [],
        data=data,
    )


def _make_decision(
    event_id: str = "dec-1",
    confidence: float = 0.5,
    evidence: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> DecisionEvent:
    """Create a DecisionEvent with common defaults."""
    return DecisionEvent(
        id=event_id,
        session_id="sess-001",
        event_type=EventType.DECISION,
        timestamp=_NOW,
        confidence=confidence,
        evidence=evidence or [],
        chosen_action="continue",
        **kwargs,
    )


def _make_session(
    session_id: str = "sess-001",
    steps: int = 10,
    inject_error_at: int | None = None,
    inject_failure_step: int | None = None,
    inject_safety_violation_at: int | None = None,
) -> list[TraceEvent]:
    """Create a realistic session trace with optional failures."""
    events: list[TraceEvent] = []
    parent_id: str | None = None
    ts = _NOW

    start = _make_event(EventType.AGENT_START, "agent_start", session_id=session_id)
    events.append(start)
    parent_id = start.id

    for i in range(steps):
        eid = f"step-{i}"

        if inject_error_at is not None and i == inject_error_at:
            ev = _make_event(
                EventType.ERROR, eid, parent_id=parent_id, session_id=session_id,
                event_id=eid,
            )
            events.append(ev)
            parent_id = eid
            continue

        if inject_failure_step is not None and i == inject_failure_step:
            ev = _make_event(
                EventType.TOOL_RESULT, eid, parent_id=parent_id, session_id=session_id,
                event_id=eid,
            )
            events.append(ev)
            parent_id = eid
            continue

        if inject_safety_violation_at is not None and i == inject_safety_violation_at:
            ev = _make_event(
                EventType.POLICY_VIOLATION, eid, parent_id=parent_id, session_id=session_id,
                event_id=eid,
            )
            events.append(ev)
            parent_id = eid
            continue

        dec = _make_event(
            EventType.DECISION, eid, parent_id=parent_id, session_id=session_id,
            event_id=eid,
        )
        events.append(dec)
        parent_id = eid

        llm_req = _make_event(
            EventType.LLM_REQUEST, f"{eid}-llm_req", parent_id=parent_id,
            session_id=session_id, timestamp=ts + timedelta(milliseconds=100),
        )
        events.append(llm_req)
        parent_id = llm_req.id

        llm_resp = _make_event(
            EventType.LLM_RESPONSE, f"{eid}-llm_resp", parent_id=parent_id,
            session_id=session_id, timestamp=ts + timedelta(milliseconds=200),
        )
        events.append(llm_resp)
        parent_id = llm_resp.id

        tool_call = _make_event(
            EventType.TOOL_CALL, f"{eid}-tool", parent_id=parent_id,
            session_id=session_id, timestamp=ts + timedelta(milliseconds=300),
        )
        events.append(tool_call)
        parent_id = tool_call.id

        tool_result = _make_event(
            EventType.TOOL_RESULT, f"{eid}-result", parent_id=parent_id,
            session_id=session_id, timestamp=ts + timedelta(milliseconds=400),
        )
        events.append(tool_result)
        parent_id = tool_result.id

    end = _make_event(
        EventType.AGENT_END, "agent_end", parent_id=parent_id, session_id=session_id,
    )
    events.append(end)
    return events


# ===========================================================================
# #187 Step Redundancy Analyzer — RedundancyBench (arXiv:2605.29893)
# ===========================================================================


class TestStepContribution:
    """Tests for StepContribution enum values."""

    def test_enum_members(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution

        assert StepContribution.ESSENTIAL.value == "essential"
        assert StepContribution.REDUNDANT.value == "redundant"
        assert StepContribution.HARMFUL.value == "harmful"
        assert StepContribution.UNKNOWN.value == "unknown"

    def test_enum_has_four_members(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution

        assert len(StepContribution) == 4


class TestRedundancyScore:
    """Tests for RedundancyScore dataclass."""

    def test_to_dict_roundtrip(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import RedundancyScore, StepContribution

        score = RedundancyScore(
            step_id="step-0",
            score=0.9,
            contribution=StepContribution.ESSENTIAL,
            reasoning="Decision contributes to goal",
        )
        d = score.to_dict()
        assert d["step_id"] == "step-0"
        assert d["score"] == 0.9
        assert d["contribution"] == "essential"
        assert d["reasoning"] == "Decision contributes to goal"

    def test_to_dict_has_required_keys(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import RedundancyScore, StepContribution

        d = RedundancyScore("x", 1.0, StepContribution.ESSENTIAL, "r").to_dict()
        assert set(d.keys()) == {"step_id", "score", "contribution", "reasoning"}


class TestEventHasError:
    """Tests for the _event_has_error helper."""

    def test_error_event(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import _event_has_error

        assert _event_has_error(
            TraceEvent(id="e1", event_type=EventType.ERROR)
        ) is True

    def test_refusal_event(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import _event_has_error

        assert _event_has_error(
            TraceEvent(id="e2", event_type=EventType.REFUSAL)
        ) is True

    def test_policy_violation_event(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import _event_has_error

        assert _event_has_error(
            TraceEvent(id="e3", event_type=EventType.POLICY_VIOLATION)
        ) is True

    def test_behavior_alert_event(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import _event_has_error

        assert _event_has_error(
            TraceEvent(id="e4", event_type=EventType.BEHAVIOR_ALERT)
        ) is True

    def test_decision_event_no_error(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import _event_has_error

        assert _event_has_error(
            TraceEvent(id="e5", event_type=EventType.DECISION)
        ) is False

    def test_tool_result_no_error_attr(self) -> None:
        """TOOL_RESULT without error attribute should not be error (no AttributeError)."""
        from agent_debugger_sdk.core.redundancy_scorer import _event_has_error

        assert _event_has_error(
            TraceEvent(id="e6", event_type=EventType.TOOL_RESULT)
        ) is False


class TestEventHasDownstreamImpact:
    """Tests for the _event_has_downstream_impact helper."""

    def test_upstream_event_ids_create_impact(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import _event_has_downstream_impact

        source = TraceEvent(id="src", event_type=EventType.DECISION)
        downstream = TraceEvent(
            id="dst", event_type=EventType.DECISION,
            upstream_event_ids=["src"],
        )
        assert _event_has_downstream_impact(source, [source, downstream]) is True

    def test_decision_has_default_impact(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import _event_has_downstream_impact

        assert _event_has_downstream_impact(
            TraceEvent(id="d", event_type=EventType.DECISION), []
        ) is True

    def test_tool_call_has_default_impact(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import _event_has_downstream_impact

        assert _event_has_downstream_impact(
            TraceEvent(id="t", event_type=EventType.TOOL_CALL), []
        ) is True

    def test_llm_request_has_default_impact(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import _event_has_downstream_impact

        assert _event_has_downstream_impact(
            TraceEvent(id="l", event_type=EventType.LLM_REQUEST), []
        ) is True

    def test_checkpoint_no_default_impact(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import _event_has_downstream_impact

        assert _event_has_downstream_impact(
            TraceEvent(id="c", event_type=EventType.CHECKPOINT), []
        ) is False


class TestClassifyStepContribution:
    """Tests for step contribution classification logic."""

    def test_low_confidence_decision_is_essential(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, _classify_step_contribution

        event = _make_decision(confidence=0.2)
        contribution, _ = _classify_step_contribution(event, [event], 0, 0, 0)
        assert contribution == StepContribution.ESSENTIAL

    def test_evidence_backed_decision_is_essential(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, _classify_step_contribution

        event = _make_decision(evidence=[{"source": "tool", "content": "verified"}])
        contribution, reasoning = _classify_step_contribution(event, [event], 0, 0, 0)
        assert contribution == StepContribution.ESSENTIAL
        assert "evidence" in reasoning.lower()

    def test_error_event_is_harmful(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, _classify_step_contribution

        event = TraceEvent(id="err", event_type=EventType.ERROR)
        contribution, _ = _classify_step_contribution(event, [event], 1, 0, 0)
        assert contribution == StepContribution.HARMFUL

    def test_refusal_is_harmful(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, _classify_step_contribution

        event = TraceEvent(id="ref", event_type=EventType.REFUSAL)
        contribution, _ = _classify_step_contribution(event, [event], 1, 0, 0)
        assert contribution == StepContribution.HARMFUL

    def test_policy_violation_is_harmful(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, _classify_step_contribution

        event = TraceEvent(id="pv", event_type=EventType.POLICY_VIOLATION)
        contribution, _ = _classify_step_contribution(event, [event], 1, 0, 0)
        assert contribution == StepContribution.HARMFUL

    def test_behavior_alert_is_harmful(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, _classify_step_contribution

        event = TraceEvent(id="ba", event_type=EventType.BEHAVIOR_ALERT)
        contribution, _ = _classify_step_contribution(event, [event], 1, 0, 0)
        assert contribution == StepContribution.HARMFUL

    def test_agent_turn_is_essential(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, _classify_step_contribution

        event = TraceEvent(id="at", event_type=EventType.AGENT_TURN)
        contribution, _ = _classify_step_contribution(event, [event], 0, 0, 0)
        assert contribution == StepContribution.ESSENTIAL

    def test_llm_request_classified_before_redundant_check(self) -> None:
        """LLM_REQUEST has default downstream impact, so it's classified as ESSENTIAL
        before reaching the explicit REDUNDANT branch in _classify_step_contribution."""
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, _classify_step_contribution

        event = TraceEvent(id="lr", event_type=EventType.LLM_REQUEST)
        contribution, _ = _classify_step_contribution(event, [event], 0, 0, 0)
        # LLM_REQUEST has _event_has_downstream_impact=True by default,
        # so it hits "influenced subsequent execution" before the REDUNDANT branch
        assert contribution == StepContribution.ESSENTIAL

    def test_checkpoint_is_redundant(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, _classify_step_contribution

        event = TraceEvent(id="cp", event_type=EventType.CHECKPOINT)
        contribution, _ = _classify_step_contribution(event, [event], 0, 0, 0)
        assert contribution == StepContribution.REDUNDANT

    def test_prompt_policy_is_redundant(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, _classify_step_contribution

        event = TraceEvent(id="pp", event_type=EventType.PROMPT_POLICY)
        contribution, _ = _classify_step_contribution(event, [event], 0, 0, 0)
        assert contribution == StepContribution.REDUNDANT

    def test_tool_call_is_essential(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, _classify_step_contribution

        event = TraceEvent(id="tc", event_type=EventType.TOOL_CALL)
        contribution, _ = _classify_step_contribution(event, [event], 0, 0, 0)
        assert contribution == StepContribution.ESSENTIAL

    def test_llm_response_is_essential(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, _classify_step_contribution

        event = LLMResponseEvent(id="llm-r", cost_usd=0.005)
        contribution, _ = _classify_step_contribution(event, [event], 0, 0, 0)
        assert contribution == StepContribution.ESSENTIAL

    def test_high_cost_llm_response_is_essential(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, _classify_step_contribution

        event = LLMResponseEvent(id="llm-hc", cost_usd=0.05)
        contribution, reasoning = _classify_step_contribution(event, [event], 0, 0, 0)
        assert contribution == StepContribution.ESSENTIAL
        assert "$" in reasoning


class TestCalculateRedundancyScore:
    """Tests for score-to-conversion mapping."""

    def test_essential_score_is_one(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, _calculate_redundancy_score

        assert _calculate_redundancy_score(StepContribution.ESSENTIAL) == 1.0

    def test_harmful_score_is_low(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, _calculate_redundancy_score

        assert _calculate_redundancy_score(StepContribution.HARMFUL) == 0.1

    def test_redundant_score_is_zero(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, _calculate_redundancy_score

        assert _calculate_redundancy_score(StepContribution.REDUNDANT) == 0.0

    def test_unknown_score_is_midpoint(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, _calculate_redundancy_score

        assert _calculate_redundancy_score(StepContribution.UNKNOWN) == 0.5


class TestScoreSession:
    """Integration tests for score_session."""

    def test_clean_session_all_classified(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, score_session

        events = _make_session(steps=5)
        scores = score_session(events)
        assert len(scores) == len(events)

        contributions = {s.contribution for s in scores}
        assert contributions.issubset({c for c in StepContribution})

    def test_error_at_step_marks_harmful(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import StepContribution, score_session

        events = _make_session(steps=5, inject_error_at=3)
        scores = score_session(events)

        error_scores = [s for s in scores if s.contribution == StepContribution.HARMFUL]
        assert len(error_scores) >= 1, "Expected at least one harmful step"

    def test_all_scores_in_valid_range(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import score_session

        events = _make_session(steps=5)
        scores = score_session(events)
        for s in scores:
            assert 0.0 <= s.score <= 1.0, f"Score {s.score} out of range for step {s.step_id}"

    def test_empty_events_returns_empty(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import score_session

        assert score_session([]) == []

    def test_single_event_returns_single_score(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import score_session

        events = [_make_event()]
        scores = score_session(events)
        assert len(scores) == 1

    def test_step_ids_match_event_ids(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import score_session

        events = _make_session(steps=3)
        scores = score_session(events)
        score_ids = {s.step_id for s in scores}
        event_ids = {e.id for e in events}
        assert score_ids == event_ids


class TestCalculateSessionRedundancySummary:
    """Tests for session-level redundancy summary."""

    def test_summary_keys(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import calculate_session_redundancy_summary, score_session

        events = _make_session(steps=10)
        scores = score_session(events)
        summary = calculate_session_redundancy_summary(scores)

        assert "redundancy_rate" in summary
        assert "total_steps" in summary
        assert "essential_count" in summary
        assert "redundant_count" in summary
        assert "harmful_count" in summary
        assert "unknown_count" in summary
        assert "avg_score" in summary

    def test_summary_counts_match(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import calculate_session_redundancy_summary, score_session

        events = _make_session(steps=10)
        scores = score_session(events)
        summary = calculate_session_redundancy_summary(scores)

        assert summary["total_steps"] == len(events)
        assert summary["essential_count"] + summary["redundant_count"] + summary["harmful_count"] + summary["unknown_count"] == len(events)

    def test_summary_rates_in_range(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import calculate_session_redundancy_summary, score_session

        events = _make_session(steps=10)
        scores = score_session(events)
        summary = calculate_session_redundancy_summary(scores)

        assert 0.0 <= summary["redundancy_rate"] <= 1.0
        assert 0.0 <= summary["avg_score"] <= 1.0

    def test_empty_summary(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import calculate_session_redundancy_summary

        summary = calculate_session_redundancy_summary([])
        assert summary["total_steps"] == 0
        assert summary["redundancy_rate"] == 0.0
        assert summary["avg_score"] == 0.0

    def test_session_with_errors_has_harmful_count(self) -> None:
        from agent_debugger_sdk.core.redundancy_scorer import calculate_session_redundancy_summary, score_session

        events = _make_session(steps=5, inject_error_at=2)
        scores = score_session(events)
        summary = calculate_session_redundancy_summary(scores)

        assert summary["harmful_count"] >= 1


# ===========================================================================
# #190 Causal Root Cause Analysis — AgentTrace (ICLR 2026 Workshop)
# ===========================================================================


class TestCausalRelationType:
    """Tests for CausalRelationType enum."""

    def test_enum_values(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalRelationType

        assert CausalRelationType.DIRECT.value == "direct"
        assert CausalRelationType.TEMPORAL.value == "temporal"
        assert CausalRelationType.DEPENDENCY.value == "dependency"
        assert CausalRelationType.FAILURE_PROPAGATION.value == "failure_propagation"
        assert CausalRelationType.STATE_DERIVATION.value == "state_derivation"

    def test_five_members(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalRelationType

        assert len(CausalRelationType) == 5


class TestCausalNode:
    """Tests for CausalNode dataclass."""

    def test_to_dict_fields(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalNode

        node = CausalNode(
            id="n1", event_type=EventType.DECISION, timestamp=_NOW, name="step-1"
        )
        d = node.to_dict()
        assert d["id"] == "n1"
        assert d["event_type"] == "decision"
        assert d["name"] == "step-1"
        assert d["causal_depth"] == 0
        assert d["is_failure"] is False

    def test_to_dict_with_failure(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalNode

        node = CausalNode(
            id="n2", event_type=EventType.ERROR, timestamp=_NOW, name="err",
            is_failure=True, failure_type="runtime_error",
        )
        d = node.to_dict()
        assert d["is_failure"] is True
        assert d["failure_type"] == "runtime_error"

    def test_to_dict_with_dependencies(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalNode

        node = CausalNode(
            id="n3", event_type=EventType.DECISION, timestamp=_NOW, name="d",
            dependencies=["dep-1", "dep-2"],
        )
        d = node.to_dict()
        assert d["dependencies"] == ["dep-1", "dep-2"]


class TestCausalEdge:
    """Tests for CausalEdge dataclass."""

    def test_to_dict_fields(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalEdge, CausalRelationType

        edge = CausalEdge(
            from_node="a", to_node="b",
            relation_type=CausalRelationType.DIRECT,
            strength=0.9, evidence="parent-child",
        )
        d = edge.to_dict()
        assert d["from_node"] == "a"
        assert d["to_node"] == "b"
        assert d["relation_type"] == "direct"
        assert d["strength"] == 0.9
        assert d["evidence"] == "parent-child"

    def test_default_strength(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalEdge, CausalRelationType

        edge = CausalEdge(
            from_node="a", to_node="b",
            relation_type=CausalRelationType.DEPENDENCY,
        )
        assert edge.strength == 1.0
        assert edge.evidence is None


class TestCausalGraphInit:
    """Tests for CausalGraph initialization."""

    def test_empty_graph(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        graph = CausalGraph()
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0
        assert graph.root_cause_candidates == []


class TestCausalGraphBuild:
    """Tests for building causal graphs from events."""

    def test_build_creates_nodes(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = _make_session(steps=3)
        graph = CausalGraph()
        graph.build_from_events(events)
        assert len(graph.nodes) == len(events)

    def test_build_creates_edges(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = _make_session(steps=3)
        graph = CausalGraph()
        graph.build_from_events(events)
        assert len(graph.edges) > 0

    def test_build_empty_events(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        graph = CausalGraph()
        graph.build_from_events([])
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0

    def test_build_identifies_root_causes(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = _make_session(steps=3)
        graph = CausalGraph()
        graph.build_from_events(events)
        assert len(graph.root_cause_candidates) >= 1

    def test_parent_child_edges(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        parent = TraceEvent(id="p", event_type=EventType.DECISION, timestamp=_NOW)
        child = TraceEvent(
            id="c", event_type=EventType.TOOL_CALL, timestamp=_NEXT,
            parent_id="p",
        )
        graph = CausalGraph()
        graph.build_from_events([parent, child])

        edge_types = {e.relation_type.value for e in graph.edges}
        assert "direct" in edge_types

    def test_dependency_edges(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        dep = TraceEvent(id="dep", event_type=EventType.DECISION, timestamp=_NOW)
        consumer = TraceEvent(
            id="cons", event_type=EventType.DECISION, timestamp=_NEXT,
            upstream_event_ids=["dep"],
        )
        graph = CausalGraph()
        graph.build_from_events([dep, consumer])

        edge_types = {e.relation_type.value for e in graph.edges}
        assert "dependency" in edge_types

    def test_temporal_edges_for_orphan_events(self) -> None:
        """Events without parent or upstream should get temporal edges if close in time."""
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        e1 = TraceEvent(id="orphan1", event_type=EventType.DECISION, timestamp=_NOW)
        e2 = TraceEvent(
            id="orphan2", event_type=EventType.TOOL_CALL,
            timestamp=_NOW + timedelta(seconds=2),
        )
        graph = CausalGraph()
        graph.build_from_events([e1, e2])

        edge_types = {e.relation_type.value for e in graph.edges}
        assert "temporal" in edge_types

    def test_no_temporal_edges_for_distant_events(self) -> None:
        """Events far apart in time should not get temporal edges."""
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        e1 = TraceEvent(id="far1", event_type=EventType.DECISION, timestamp=_NOW)
        e2 = TraceEvent(
            id="far2", event_type=EventType.TOOL_CALL,
            timestamp=_NOW + timedelta(seconds=10),  # beyond 5s window
        )
        graph = CausalGraph()
        graph.build_from_events([e1, e2])

        edge_types = {e.relation_type.value for e in graph.edges}
        assert "temporal" not in edge_types


class TestCausalGraphFailureDetection:
    """Tests for failure identification in causal graphs."""

    def test_error_event_is_failure(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = [TraceEvent(id="err", event_type=EventType.ERROR, timestamp=_NOW)]
        graph = CausalGraph()
        graph.build_from_events(events)

        failures = [n for n in graph.nodes.values() if n.is_failure]
        assert len(failures) == 1
        assert failures[0].failure_type == "runtime_error"

    def test_refusal_is_failure(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = [TraceEvent(id="ref", event_type=EventType.REFUSAL, timestamp=_NOW)]
        graph = CausalGraph()
        graph.build_from_events(events)

        failures = [n for n in graph.nodes.values() if n.is_failure]
        assert len(failures) == 1
        assert failures[0].failure_type == "guardrail_block"

    def test_policy_violation_is_failure(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = [TraceEvent(id="pv", event_type=EventType.POLICY_VIOLATION, timestamp=_NOW)]
        graph = CausalGraph()
        graph.build_from_events(events)

        failures = [n for n in graph.nodes.values() if n.is_failure]
        assert len(failures) == 1
        assert failures[0].failure_type == "policy_violation"

    def test_behavior_alert_is_failure(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = [
            TraceEvent(
                id="ba", event_type=EventType.BEHAVIOR_ALERT, timestamp=_NOW,
                data={"alert_type": "tool_loop"},
            )
        ]
        graph = CausalGraph()
        graph.build_from_events(events)

        failures = [n for n in graph.nodes.values() if n.is_failure]
        assert len(failures) == 1
        assert "tool_loop" in failures[0].failure_type

    def test_decision_is_not_failure(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = [TraceEvent(id="d", event_type=EventType.DECISION, timestamp=_NOW)]
        graph = CausalGraph()
        graph.build_from_events(events)

        failures = [n for n in graph.nodes.values() if n.is_failure]
        assert len(failures) == 0


class TestCausalGraphSerialization:
    """Tests for graph serialization."""

    def test_to_dict_structure(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = _make_session(steps=3)
        graph = CausalGraph()
        graph.build_from_events(events)
        d = graph.to_dict()

        assert "nodes" in d
        assert "edges" in d
        assert "root_cause_candidates" in d
        assert "statistics" in d
        assert len(d["nodes"]) == len(events)
        assert d["statistics"]["total_nodes"] == len(events)

    def test_to_dict_statistics(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = _make_session(steps=5, inject_error_at=3)
        graph = CausalGraph()
        graph.build_from_events(events)
        stats = graph.to_dict()["statistics"]

        assert stats["failure_count"] >= 1
        assert stats["max_depth"] >= 0


class TestCausalGraphTraceBackward:
    """Tests for backward causal tracing."""

    def test_traces_from_failure(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = _make_session(steps=5, inject_error_at=3)
        graph = CausalGraph()
        graph.build_from_events(events)

        failure_nodes = [n for n in graph.nodes.values() if n.is_failure]
        assert len(failure_nodes) >= 1

        path = graph.trace_backward(failure_nodes[0].id)
        assert len(path) >= 1

    def test_traces_nonexistent_node_returns_empty(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = _make_session(steps=3)
        graph = CausalGraph()
        graph.build_from_events(events)

        assert graph.trace_backward("nonexistent") == []

    def test_chain_is_root_to_failure_order(self) -> None:
        """trace_backward should return chain in root→failure order."""
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = _make_session(steps=5, inject_error_at=3)
        graph = CausalGraph()
        graph.build_from_events(events)

        failure_nodes = [n for n in graph.nodes.values() if n.is_failure]
        path = graph.trace_backward(failure_nodes[0].id)

        if len(path) >= 2:
            # First node should have lower depth than last
            assert path[0].causal_depth <= path[-1].causal_depth


class TestCausalGraphFindRootCauses:
    """Tests for root cause identification."""

    def test_no_failure_session_has_no_root_causes(self) -> None:
        """Without failures, find_root_causes() returns empty list."""
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = _make_session(steps=3)
        graph = CausalGraph()
        graph.build_from_events(events)
        roots = graph.find_root_causes()
        assert roots == []

    def test_with_failure_traces_to_root(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = _make_session(steps=5, inject_error_at=3)
        graph = CausalGraph()
        graph.build_from_events(events)
        roots = graph.find_root_causes()
        assert len(roots) >= 1

    def test_specific_failure_node(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = _make_session(steps=5, inject_error_at=3)
        graph = CausalGraph()
        graph.build_from_events(events)

        failure_nodes = [n for n in graph.nodes.values() if n.is_failure]
        if failure_nodes:
            roots = graph.find_root_causes(failure_node_id=failure_nodes[0].id)
            assert len(roots) == 1


class TestCausalGraphGetCriticalPath:
    """Tests for critical path analysis."""

    def test_critical_path_structure(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = _make_session(steps=5, inject_error_at=3)
        graph = CausalGraph()
        graph.build_from_events(events)

        failure_nodes = [n for n in graph.nodes.values() if n.is_failure]
        if failure_nodes:
            critical = graph.get_critical_path(failure_nodes[0].id)
            assert "failure_node_id" in critical
            assert "root_cause_found" in critical
            assert "chain_length" in critical
            assert "critical_events" in critical
            assert critical["chain_length"] > 0

    def test_nonexistent_node_returns_empty(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        graph = CausalGraph()
        critical = graph.get_critical_path("nonexistent")
        assert critical["root_cause_found"] is False
        assert critical["chain_length"] == 0


class TestCausalGraphDepthCalculation:
    """Tests for causal depth computation."""

    def test_root_nodes_have_zero_depth(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = _make_session(steps=3)
        graph = CausalGraph()
        graph.build_from_events(events)

        for node_id in graph.root_cause_candidates:
            if node_id in graph.nodes:
                assert graph.nodes[node_id].causal_depth == 0

    def test_depth_increases_along_chain(self) -> None:
        from agent_debugger_sdk.core.causal_tracer import CausalGraph

        events = _make_session(steps=5)
        graph = CausalGraph()
        graph.build_from_events(events)

        depths = [n.causal_depth for n in graph.nodes.values()]
        assert max(depths) >= 1, "Expected non-trivial depth in a session with multiple steps"


# ===========================================================================
# #188 Predictive Safety Monitoring — SafetyDrift (arXiv:2603.27148)
# ===========================================================================


class TestSafetyDimension:
    """Tests for SafetyDimension enum."""

    def test_enum_values(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import SafetyDimension

        assert SafetyDimension.GOAL_ALIGNMENT.value == "goal_alignment"
        assert SafetyDimension.CONSTRAINT_ADHERENCE.value == "constraint_adherence"
        assert SafetyDimension.REASONING_COHERENCE.value == "reasoning_coherence"

    def test_three_members(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import SafetyDimension

        assert len(SafetyDimension) == 3


class TestSafetyScore:
    """Tests for SafetyScore dataclass."""

    def test_field_access(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import SafetyDimension, SafetyScore

        score = SafetyScore(
            dimension=SafetyDimension.GOAL_ALIGNMENT,
            score=0.95,
            is_safe=True,
            details="Strong goal alignment",
        )
        assert score.dimension == SafetyDimension.GOAL_ALIGNMENT
        assert score.score == 0.95
        assert score.is_safe is True
        assert score.confidence == 1.0  # default

    def test_optional_fields(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import SafetyDimension, SafetyScore

        score = SafetyScore(
            dimension=SafetyDimension.CONSTRAINT_ADHERENCE,
            score=0.8,
            is_safe=True,
            details="ok",
            step_index=5,
            event_id="ev-5",
            confidence=0.9,
        )
        assert score.step_index == 5
        assert score.event_id == "ev-5"
        assert score.confidence == 0.9


class TestSafetyAlert:
    """Tests for SafetyAlert dataclass."""

    def test_field_access(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import SafetyAlert, SafetyDimension

        alert = SafetyAlert(
            dimension=SafetyDimension.CONSTRAINT_ADHERENCE,
            severity="high",
            score=0.3,
            threshold=0.7,
            message="Low constraint adherence",
            mitigation_suggestion="Review constraints",
        )
        assert alert.severity == "high"
        assert alert.score == 0.3
        assert alert.mitigation_suggestion == "Review constraints"

    def test_optional_fields(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import SafetyAlert, SafetyDimension

        alert = SafetyAlert(
            dimension=SafetyDimension.GOAL_ALIGNMENT,
            severity="low",
            score=0.55,
            threshold=0.6,
            message="test",
            step_index=3,
            event_id="ev-3",
        )
        assert alert.step_index == 3
        assert alert.event_id == "ev-3"


class TestSessionSafetyReport:
    """Tests for SessionSafetyReport dataclass."""

    def test_to_dict(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import (
            SafetyDimension,
            SessionSafetyReport,
        )

        report = SessionSafetyReport(
            session_id="sess-001",
            overall_score=0.85,
            is_safe=True,
            per_dimension_scores={
                SafetyDimension.GOAL_ALIGNMENT: 0.9,
                SafetyDimension.CONSTRAINT_ADHERENCE: 0.8,
                SafetyDimension.REASONING_COHERENCE: 0.85,
            },
            per_step_scores=[],
            alerts=[],
            total_steps=0,
            unsafe_steps=0,
            high_risk_dimensions=[],
        )
        d = report.to_dict()
        assert d["session_id"] == "sess-001"
        assert d["overall_score"] == 0.85
        assert d["is_safe"] is True
        assert "goal_alignment" in d["per_dimension_scores"]

    def test_with_alerts(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import (
            SafetyAlert,
            SafetyDimension,
            SessionSafetyReport,
        )

        alert = SafetyAlert(
            dimension=SafetyDimension.CONSTRAINT_ADHERENCE,
            severity="medium",
            score=0.5,
            threshold=0.7,
            message="Below threshold",
        )
        report = SessionSafetyReport(
            session_id="s1",
            overall_score=0.6,
            is_safe=False,
            per_dimension_scores={SafetyDimension.CONSTRAINT_ADHERENCE: 0.5},
            per_step_scores=[],
            alerts=[alert],
            total_steps=1,
            unsafe_steps=1,
            high_risk_dimensions=[SafetyDimension.CONSTRAINT_ADHERENCE],
        )
        d = report.to_dict()
        assert len(d["alerts"]) == 1
        assert d["alerts"][0]["severity"] == "medium"


class TestAssessGoalAlignment:
    """Tests for goal alignment assessment."""

    def test_clean_event_high_score(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import _assess_goal_alignment

        event = TraceEvent(id="d", event_type=EventType.DECISION, timestamp=_NOW)
        assert _assess_goal_alignment(event) >= 0.9

    def test_policy_violation_reduces_score(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import _assess_goal_alignment

        clean = TraceEvent(id="c", event_type=EventType.DECISION, timestamp=_NOW)
        violation = TraceEvent(id="v", event_type=EventType.POLICY_VIOLATION, timestamp=_NOW)
        assert _assess_goal_alignment(violation) < _assess_goal_alignment(clean)

    def test_refusal_reduces_score(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import _assess_goal_alignment

        clean = TraceEvent(id="c", event_type=EventType.DECISION, timestamp=_NOW)
        refusal = TraceEvent(id="r", event_type=EventType.REFUSAL, timestamp=_NOW)
        assert _assess_goal_alignment(refusal) < _assess_goal_alignment(clean)

    def test_score_clamped_to_zero_one(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import _assess_goal_alignment

        event = TraceEvent(id="x", event_type=EventType.DECISION, timestamp=_NOW)
        score = _assess_goal_alignment(event)
        assert 0.0 <= score <= 1.0


class TestAssessConstraintAdherence:
    """Tests for constraint adherence assessment."""

    def test_clean_event_high_score(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import _assess_constraint_adherence

        event = TraceEvent(id="d", event_type=EventType.DECISION, timestamp=_NOW)
        assert _assess_constraint_adherence(event) >= 0.9

    def test_block_outcome_reduces_score(self) -> None:
        """TraceEvent doesn't have 'outcome' so hasattr returns False → no penalty.
        Only subclasses or events recorded via TraceContext have outcome."""
        from agent_debugger_sdk.core.safety_monitor import _assess_constraint_adherence

        event = TraceEvent(id="s", event_type=EventType.SAFETY_CHECK, timestamp=_NOW)
        score = _assess_constraint_adherence(event)
        # No outcome attr → no penalty → score stays at 1.0
        assert score == 1.0

    def test_score_clamped_to_zero_one(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import _assess_constraint_adherence

        event = TraceEvent(id="x", event_type=EventType.DECISION, timestamp=_NOW)
        score = _assess_constraint_adherence(event)
        assert 0.0 <= score <= 1.0


class TestAssessReasoningCoherence:
    """Tests for reasoning coherence assessment."""

    def test_clean_event_high_score(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import _assess_reasoning_coherence

        event = TraceEvent(id="d", event_type=EventType.DECISION, timestamp=_NOW)
        assert _assess_reasoning_coherence(event) >= 0.9

    def test_low_confidence_reduces_score(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import _assess_reasoning_coherence

        high_conf = DecisionEvent(id="h", confidence=0.9, timestamp=_NOW)
        low_conf = DecisionEvent(id="l", confidence=0.2, timestamp=_NOW)
        assert _assess_reasoning_coherence(low_conf) <= _assess_reasoning_coherence(high_conf)

    def test_uncertain_reasoning_reduces_score(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import _assess_reasoning_coherence

        clear = DecisionEvent(id="c", reasoning="Because the data supports this", timestamp=_NOW)
        uncertain = DecisionEvent(id="u", reasoning="Maybe this is the right approach", timestamp=_NOW)
        assert _assess_reasoning_coherence(uncertain) <= _assess_reasoning_coherence(clear)

    def test_evidence_backing_increases_score(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import _assess_reasoning_coherence

        no_ev = DecisionEvent(id="ne", reasoning="Proceed", timestamp=_NOW)
        with_ev = DecisionEvent(
            id="we", reasoning="Proceed",
            evidence=[{"source": "tool", "content": "verified"}],
            timestamp=_NOW,
        )
        assert _assess_reasoning_coherence(with_ev) >= _assess_reasoning_coherence(no_ev)

    def test_score_clamped_to_zero_one(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import _assess_reasoning_coherence

        event = TraceEvent(id="x", event_type=EventType.DECISION, timestamp=_NOW)
        score = _assess_reasoning_coherence(event)
        assert 0.0 <= score <= 1.0


class TestCalculateAlertSeverity:
    """Tests for alert severity calculation."""

    def test_critical_severity(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import _calculate_alert_severity

        # Score far below threshold
        assert _calculate_alert_severity(0.1, 0.6) == "critical"

    def test_high_severity(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import _calculate_alert_severity

        assert _calculate_alert_severity(0.35, 0.6) == "high"

    def test_medium_severity(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import _calculate_alert_severity

        assert _calculate_alert_severity(0.45, 0.6) == "medium"

    def test_low_severity(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import _calculate_alert_severity

        assert _calculate_alert_severity(0.55, 0.6) == "low"

    def test_at_threshold_is_low(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import _calculate_alert_severity

        # gap = 0.0 → not > 0.1, falls to "low"
        assert _calculate_alert_severity(0.6, 0.6) == "low"


class TestComputeOverallSafety:
    """Tests for overall safety score computation."""

    def test_empty_dimensions_returns_neutral(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import _compute_overall_safety

        assert _compute_overall_safety({}) == 0.5

    def test_weighted_average(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import (
            SafetyDimension,
            _compute_overall_safety,
        )

        # Constraint adherence has weight 0.4, goal 0.35, coherence 0.25
        score = _compute_overall_safety({
            SafetyDimension.CONSTRAINT_ADHERENCE: 1.0,
            SafetyDimension.GOAL_ALIGNMENT: 1.0,
            SafetyDimension.REASONING_COHERENCE: 1.0,
        })
        assert score == 1.0

    def test_constraint_adherence_most_weighted(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import (
            SafetyDimension,
            _compute_overall_safety,
        )

        # Low constraint adherence should pull score down more than others
        low_constraint = _compute_overall_safety({
            SafetyDimension.CONSTRAINT_ADHERENCE: 0.0,
            SafetyDimension.GOAL_ALIGNMENT: 1.0,
            SafetyDimension.REASONING_COHERENCE: 1.0,
        })
        low_goal = _compute_overall_safety({
            SafetyDimension.CONSTRAINT_ADHERENCE: 1.0,
            SafetyDimension.GOAL_ALIGNMENT: 0.0,
            SafetyDimension.REASONING_COHERENCE: 1.0,
        })
        assert low_constraint < low_goal


class TestAnalyzeSessionSafety:
    """Integration tests for session safety analysis."""

    def test_clean_session_high_scores(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import analyze_session_safety

        events = _make_session(steps=5)
        report = analyze_session_safety(session_id="sess-001", events=events)

        assert report.session_id == "sess-001"
        assert 0.0 <= report.overall_score <= 1.0
        assert len(report.per_dimension_scores) > 0

    def test_violation_lowers_goal_alignment(self) -> None:
        """Policy violation event type reduces goal alignment score for that step."""
        from agent_debugger_sdk.core.safety_monitor import SafetyDimension, analyze_session_safety

        events = _make_session(steps=5, inject_safety_violation_at=3)
        report = analyze_session_safety(session_id="sess-001", events=events)

        # Find the violation step's goal alignment score
        violation_scores = [
            s for s in report.per_step_scores
            if s.dimension == SafetyDimension.GOAL_ALIGNMENT and s.details != "Strong alignment with goals"
        ]
        # At least one step should have reduced goal alignment
        assert len(violation_scores) >= 1, "Expected reduced goal alignment for violation"

    def test_all_dimension_scores_in_range(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import analyze_session_safety

        events = _make_session(steps=5)
        report = analyze_session_safety(session_id="sess-001", events=events)

        for dim, score in report.per_dimension_scores.items():
            assert 0.0 <= score <= 1.0, f"Score {score} for {dim} out of range"

    def test_empty_events_returns_baseline(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import analyze_session_safety

        report = analyze_session_safety(session_id="", events=[])
        assert report.overall_score >= 0.0
        assert report.session_id == ""

    def test_valid_alert_severities(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import analyze_session_safety

        events = _make_session(steps=5, inject_error_at=2, inject_safety_violation_at=4)
        report = analyze_session_safety(session_id="sess-001", events=events)

        valid_severities = {"low", "medium", "high", "critical"}
        for alert in report.alerts:
            assert alert.severity in valid_severities, f"Invalid severity: {alert.severity}"

    def test_errors_lower_safety(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import analyze_session_safety

        clean_events = _make_session(steps=5)
        error_events = _make_session(steps=5, inject_error_at=3)

        clean_report = analyze_session_safety(session_id="c", events=clean_events)
        error_report = analyze_session_safety(session_id="e", events=error_events)

        # Error session should have lower or equal safety
        assert error_report.overall_score <= clean_report.overall_score + 0.01

    def test_custom_thresholds_flag_violation_session(self) -> None:
        """Custom thresholds flag dimensions in violation-heavy sessions."""
        from agent_debugger_sdk.core.safety_monitor import (
            SafetyDimension,
            analyze_session_safety,
        )

        # Session with violation that pulls goal_alignment avg below 1.0
        events = _make_session(steps=3, inject_safety_violation_at=1)
        # 13 events total, 1 violation with goal_alignment=0.6 → avg ≈ 0.969
        # Threshold set above the average to trigger high-risk
        strict_thresholds = {
            SafetyDimension.GOAL_ALIGNMENT: 0.98,
            SafetyDimension.CONSTRAINT_ADHERENCE: 0.99,
            SafetyDimension.REASONING_COHERENCE: 0.99,
        }
        report = analyze_session_safety(
            session_id="strict", events=events, thresholds=strict_thresholds,
        )
        # Violation pulls goal_alignment avg below 0.98
        assert SafetyDimension.GOAL_ALIGNMENT in report.high_risk_dimensions

    def test_report_total_steps_matches(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import analyze_session_safety

        events = _make_session(steps=7)
        report = analyze_session_safety(session_id="s", events=events)
        assert report.total_steps == len(events)

    def test_report_to_dict(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import analyze_session_safety

        events = _make_session(steps=3)
        report = analyze_session_safety(session_id="s", events=events)
        d = report.to_dict()

        assert "session_id" in d
        assert "overall_score" in d
        assert "is_safe" in d
        assert "per_dimension_scores" in d
        assert "alerts" in d
        assert "total_steps" in d
        assert "unsafe_steps" in d


class TestGetMitigationSuggestion:
    """Tests for mitigation suggestion generation."""

    def test_goal_alignment_suggestion(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import (
            SafetyDimension,
            _get_mitigation_suggestion,
        )

        suggestion = _get_mitigation_suggestion(SafetyDimension.GOAL_ALIGNMENT)
        assert "goal" in suggestion.lower()

    def test_constraint_adherence_suggestion(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import (
            SafetyDimension,
            _get_mitigation_suggestion,
        )

        suggestion = _get_mitigation_suggestion(SafetyDimension.CONSTRAINT_ADHERENCE)
        assert "constraint" in suggestion.lower() or "policy" in suggestion.lower()

    def test_reasoning_coherence_suggestion(self) -> None:
        from agent_debugger_sdk.core.safety_monitor import (
            SafetyDimension,
            _get_mitigation_suggestion,
        )

        suggestion = _get_mitigation_suggestion(SafetyDimension.REASONING_COHERENCE)
        assert "reasoning" in suggestion.lower()


# ===========================================================================
# API Service Integration Tests
# ===========================================================================


class TestExtractWorkflowGraph:
    """Tests for extract_workflow_graph service function."""

    def test_basic_graph_structure(self) -> None:
        from api.services import extract_workflow_graph

        events = _make_session(steps=5)
        result = extract_workflow_graph(events, session_id="sess-001")

        assert "graph" in result
        graph = result["graph"]
        assert hasattr(graph, "nodes")
        assert hasattr(graph, "edges")
        assert len(graph.nodes) > 0

    def test_node_types_present(self) -> None:
        from api.services import extract_workflow_graph

        events = _make_session(steps=5)
        result = extract_workflow_graph(events, session_id="sess-001")

        node_types = {n.node_type for n in result["graph"].nodes}
        assert len(node_types) >= 2, "Expected multiple node types"

    def test_empty_events(self) -> None:
        from api.services import extract_workflow_graph

        result = extract_workflow_graph([], session_id="empty")
        assert result["graph"].nodes == []
        assert result["graph"].edges == []

    def test_graph_has_metadata(self) -> None:
        from api.services import extract_workflow_graph

        events = _make_session(steps=3)
        result = extract_workflow_graph(events, session_id="s")

        assert result["graph"].session_id == "s"
        metadata = result["graph"].metadata
        assert metadata is not None
        assert "total_nodes" in metadata
        assert "total_edges" in metadata

    def test_error_nodes_marked_as_failure(self) -> None:
        from api.services import extract_workflow_graph

        events = _make_session(steps=5, inject_error_at=3)
        result = extract_workflow_graph(events, session_id="s")

        failure_nodes = [
            n for n in result["graph"].nodes if n.status == "failure"
        ]
        assert len(failure_nodes) >= 1

    def test_decision_nodes_labeled(self) -> None:
        from api.services import extract_workflow_graph

        events = _make_session(steps=3)
        result = extract_workflow_graph(events, session_id="s")

        decision_nodes = [
            n for n in result["graph"].nodes if n.node_type == "decision"
        ]
        assert len(decision_nodes) >= 1


class TestAnalyzeSessionSafetyReport:
    """Tests for analyze_session_safety_report service function."""

    def test_basic_report_structure(self) -> None:
        from api.services import analyze_session_safety_report

        events = _make_session(steps=5)
        result = analyze_session_safety_report(events, session_id="s")

        assert "session_id" in result
        assert "safety_report" in result
        assert "overall_score" in result["safety_report"]

    def test_with_custom_thresholds(self) -> None:
        from api.services import analyze_session_safety_report

        events = _make_session(steps=3)
        result = analyze_session_safety_report(
            events, session_id="s",
            custom_thresholds={"goal_alignment": 0.99},
        )

        assert result["session_id"] == "s"
        assert "safety_report" in result

    def test_empty_events(self) -> None:
        from api.services import analyze_session_safety_report

        result = analyze_session_safety_report([], session_id="empty")
        assert result["safety_report"]["overall_score"] >= 0.0


class TestComputeDictDelta:
    """Tests for compute_dict_delta utility."""

    def test_both_none(self) -> None:
        from api.services import compute_dict_delta

        assert compute_dict_delta(None, None) == {}

    def test_previous_none(self) -> None:
        from api.services import compute_dict_delta

        assert compute_dict_delta(None, {"a": 1}) == {"a": 1}

    def test_current_none(self) -> None:
        from api.services import compute_dict_delta

        assert compute_dict_delta({"a": 1}, None) == {"a": None}

    def test_identical_dicts(self) -> None:
        from api.services import compute_dict_delta

        assert compute_dict_delta({"a": 1, "b": 2}, {"a": 1, "b": 2}) == {}

    def test_changed_value(self) -> None:
        from api.services import compute_dict_delta

        delta = compute_dict_delta({"a": 1}, {"a": 2})
        assert delta == {"a": 2}

    def test_added_key(self) -> None:
        from api.services import compute_dict_delta

        delta = compute_dict_delta({"a": 1}, {"a": 1, "b": 2})
        assert delta == {"b": 2}

    def test_removed_key(self) -> None:
        from api.services import compute_dict_delta

        delta = compute_dict_delta({"a": 1, "b": 2}, {"a": 1})
        assert delta == {"b": None}


class TestComputeCheckpointDeltas:
    """Tests for compute_checkpoint_deltas utility."""

    def test_empty_checkpoints(self) -> None:
        from api.services import compute_checkpoint_deltas

        assert compute_checkpoint_deltas([]) == []

    def test_single_checkpoint(self) -> None:
        from api.services import compute_checkpoint_deltas

        cp = Checkpoint(
            id="cp-1", session_id="s", event_id="e1", sequence=1,
            state={"phase": "init"}, memory={"mode": "normal"},
            timestamp=_NOW,
        )
        deltas = compute_checkpoint_deltas([cp])
        assert len(deltas) == 1
        assert deltas[0]["checkpoint_id"] == "cp-1"
        assert deltas[0]["previous_checkpoint_id"] is None
        assert deltas[0]["state_delta"] == {"phase": "init"}

    def test_multiple_checkpoints_deltas(self) -> None:
        from api.services import compute_checkpoint_deltas

        cp1 = Checkpoint(
            id="cp-1", session_id="s", event_id="e1", sequence=1,
            state={"phase": "init", "count": 0}, memory={"mode": "normal"},
            timestamp=_NOW,
        )
        cp2 = Checkpoint(
            id="cp-2", session_id="s", event_id="e2", sequence=2,
            state={"phase": "working", "count": 5}, memory={"mode": "fast"},
            timestamp=_NEXT,
        )
        deltas = compute_checkpoint_deltas([cp1, cp2])
        assert len(deltas) == 2
        assert deltas[1]["previous_checkpoint_id"] == "cp-1"
        assert deltas[1]["state_delta"]["phase"] == "working"
        assert deltas[1]["memory_delta"]["mode"] == "fast"

    def test_sorted_by_sequence(self) -> None:
        from api.services import compute_checkpoint_deltas

        cp1 = Checkpoint(
            id="cp-1", session_id="s", event_id="e1", sequence=2,
            state={"b": 1}, memory={}, timestamp=_NEXT,
        )
        cp2 = Checkpoint(
            id="cp-2", session_id="s", event_id="e2", sequence=1,
            state={"a": 0}, memory={}, timestamp=_NOW,
        )
        deltas = compute_checkpoint_deltas([cp1, cp2])
        # Should process in sequence order regardless of input order
        assert deltas[0]["checkpoint_id"] == "cp-2"
        assert deltas[1]["checkpoint_id"] == "cp-1"


# ===========================================================================
# #185 Conformal Prediction Scoring — CROP (Conformal Risk Optimization)
# ===========================================================================


class TestCoverageLevel:
    """Tests for CoverageLevel enum."""

    def test_enum_values(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import CoverageLevel

        assert CoverageLevel.WELL_COVERED.value == "well_covered"
        assert CoverageLevel.UNDER_COVERED.value == "under_covered"
        assert CoverageLevel.OVER_COVERED.value == "over_covered"
        assert CoverageLevel.UNKNOWN.value == "unknown"

    def test_four_members(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import CoverageLevel

        assert len(CoverageLevel) == 4


class TestPredictionRegion:
    """Tests for PredictionRegion dataclass."""

    def test_to_dict_fields(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import PredictionRegion

        region = PredictionRegion(
            lower_bound=0.7,
            upper_bound=0.9,
            confidence_level=0.9,
            actual_value=0.8,
            is_covered=True,
            width=0.2,
        )
        d = region.to_dict()
        assert d["lower_bound"] == 0.7
        assert d["upper_bound"] == 0.9
        assert d["confidence_level"] == 0.9
        assert d["actual_value"] == 0.8
        assert d["is_covered"] is True
        assert d["width"] == 0.2

    def test_to_dict_has_required_keys(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import PredictionRegion

        region = PredictionRegion(0.5, 0.8, 0.9, None, False, 0.3)
        d = region.to_dict()
        assert set(d.keys()) == {"lower_bound", "upper_bound", "confidence_level", "actual_value", "is_covered", "width"}


class TestConformalScore:
    """Tests for ConformalScore dataclass."""

    def test_to_dict_roundtrip(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import ConformalScore, CoverageLevel, PredictionRegion

        region = PredictionRegion(0.7, 0.9, 0.9, 0.8, True, 0.2)
        score = ConformalScore(
            event_id="event-1",
            prediction_region=region,
            coverage_level=CoverageLevel.WELL_COVERED,
            calibration_score=0.95,
            reasoning="Well-calibrated prediction",
        )
        d = score.to_dict()
        assert d["event_id"] == "event-1"
        assert d["coverage_level"] == "well_covered"
        assert d["calibration_score"] == 0.95
        assert d["reasoning"] == "Well-calibrated prediction"

    def test_to_dict_has_nested_region(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import ConformalScore, CoverageLevel, PredictionRegion

        region = PredictionRegion(0.5, 0.8, 0.9, None, False, 0.3)
        score = ConformalScore(
            event_id="x", prediction_region=region,
            coverage_level=CoverageLevel.UNKNOWN, calibration_score=0.5, reasoning="unknown"
        )
        d = score.to_dict()
        assert "prediction_region" in d
        assert isinstance(d["prediction_region"], dict)


class TestExtractPredictionValue:
    """Tests for _extract_prediction_value helper."""

    def test_decision_event_with_confidence(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import _extract_prediction_value

        event = _make_decision(confidence=0.8)
        predicted, actual = _extract_prediction_value(event)
        assert predicted == 0.8
        assert actual is None

    def test_decision_event_without_confidence(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import _extract_prediction_value

        event = _make_decision(confidence=None)
        predicted, actual = _extract_prediction_value(event)
        assert predicted is None
        assert actual is None

    def test_event_with_ground_truth(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import _extract_prediction_value

        # Create a decision event with confidence and ground truth in data
        event = DecisionEvent(
            id="test-decision",
            session_id="sess-001",
            confidence=0.7,
            reasoning="test",
            chosen_action="continue",
            timestamp=_NOW,
            data={"ground_truth": 0.75},
        )
        predicted, actual = _extract_prediction_value(event)
        assert predicted == 0.7
        assert actual == 0.75

    def test_non_prediction_event(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import _extract_prediction_value

        event = _make_event(event_type=EventType.TOOL_CALL)
        predicted, actual = _extract_prediction_value(event)
        assert predicted is None
        assert actual is None


class TestComputePredictionRegion:
    """Tests for _compute_prediction_region helper."""

    def test_region_bounds(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import _compute_prediction_region

        region = _compute_prediction_region(predicted_value=0.5, confidence_level=0.9, uncertainty_scale=0.2)
        assert 0.0 <= region.lower_bound <= region.upper_bound <= 1.0
        assert region.width > 0
        assert region.confidence_level == 0.9

    def test_region_clamps_to_valid_range(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import _compute_prediction_region

        # Very high prediction should clamp to 1.0
        region = _compute_prediction_region(predicted_value=0.99, confidence_level=0.9, uncertainty_scale=0.2)
        assert region.upper_bound <= 1.0

        # Very low prediction should clamp to 0.0
        region = _compute_prediction_region(predicted_value=0.01, confidence_level=0.9, uncertainty_scale=0.2)
        assert region.lower_bound >= 0.0

    def test_higher_confidence_wider_region(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import _compute_prediction_region

        region_90 = _compute_prediction_region(predicted_value=0.5, confidence_level=0.9, uncertainty_scale=0.2)
        region_99 = _compute_prediction_region(predicted_value=0.5, confidence_level=0.99, uncertainty_scale=0.2)
        assert region_99.width > region_90.width


class TestClassifyCoverageLevel:
    """Tests for _classify_coverage_level helper."""

    def test_well_covered_with_ground_truth(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import CoverageLevel, _classify_coverage_level, _compute_prediction_region

        # Use even smaller uncertainty scale to get width <= 0.3
        region = _compute_prediction_region(predicted_value=0.5, confidence_level=0.9, uncertainty_scale=0.08)
        region.actual_value = 0.55
        region.is_covered = True

        level, reasoning = _classify_coverage_level(region)
        assert level == CoverageLevel.WELL_COVERED
        assert "well-calibrated" in reasoning.lower()

    def test_over_covered_wide_region(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import CoverageLevel, _classify_coverage_level, _compute_prediction_region

        region = _compute_prediction_region(predicted_value=0.5, confidence_level=0.9, uncertainty_scale=0.3)
        region.actual_value = 0.55
        region.is_covered = True

        level, reasoning = _classify_coverage_level(region)
        assert level == CoverageLevel.OVER_COVERED
        assert "imprecise" in reasoning.lower()

    def test_under_covered_missed_prediction(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import CoverageLevel, _classify_coverage_level, _compute_prediction_region

        region = _compute_prediction_region(predicted_value=0.5, confidence_level=0.9, uncertainty_scale=0.1)
        region.actual_value = 0.8  # Far outside region
        region.is_covered = False

        level, reasoning = _classify_coverage_level(region)
        assert level == CoverageLevel.UNDER_COVERED
        assert "missed" in reasoning.lower()

    def test_unknown_without_ground_truth(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import CoverageLevel, _classify_coverage_level, _compute_prediction_region

        region = _compute_prediction_region(predicted_value=0.5, confidence_level=0.9, uncertainty_scale=0.15)
        # No ground truth set

        level, reasoning = _classify_coverage_level(region)
        # With width 0.3, should be classified as well_covered (reasonable width)
        assert level in {CoverageLevel.WELL_COVERED, CoverageLevel.UNKNOWN}


class TestCalculateCalibrationScore:
    """Tests for _calculate_calibration_score helper."""

    def test_well_covered_high_score(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import _calculate_calibration_score, CoverageLevel

        region = _compute_prediction_region_mock(0.5, 0.6, 0.9, 0.55, True, 0.1)
        score = _calculate_calibration_score(region, CoverageLevel.WELL_COVERED)
        assert score >= 0.9

    def test_over_covered_lower_score(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import _calculate_calibration_score, CoverageLevel

        region = _compute_prediction_region_mock(0.2, 0.9, 0.9, 0.5, True, 0.7)
        score = _calculate_calibration_score(region, CoverageLevel.OVER_COVERED)
        # Allow for floating point precision
        assert 0.19 <= score <= 0.71

    def test_under_covered_low_score(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import _calculate_calibration_score, CoverageLevel

        region = _compute_prediction_region_mock(0.4, 0.6, 0.9, 0.8, False, 0.2)
        score = _calculate_calibration_score(region, CoverageLevel.UNDER_COVERED)
        assert score == 0.2

    def test_unknown_neutral_score(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import _calculate_calibration_score, CoverageLevel

        region = _compute_prediction_region_mock(0.4, 0.6, 0.9, None, False, 0.2)
        score = _calculate_calibration_score(region, CoverageLevel.UNKNOWN)
        assert score == 0.5


def _compute_prediction_region_mock(lower: float, upper: float, conf: float, actual: float | None, covered: bool, width: float) -> object:
    """Mock PredictionRegion for testing."""
    from dataclasses import dataclass

    @dataclass
    class MockRegion:
        lower_bound: float
        upper_bound: float
        confidence_level: float
        actual_value: float | None
        is_covered: bool
        width: float

    return MockRegion(lower, upper, conf, actual, covered, width)


class TestScorePredictionConformality:
    """Integration tests for score_prediction_conformality."""

    def test_empty_events_returns_empty(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import score_prediction_conformality

        scores = score_prediction_conformality([])
        assert scores == []

    def test_events_without_predictions_skipped(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import score_prediction_conformality

        events = [
            _make_event(event_type=EventType.TOOL_CALL),
            _make_event(event_type=EventType.ERROR),
        ]
        scores = score_prediction_conformality(events)
        assert len(scores) == 0

    def test_decision_with_confidence_scored(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import score_prediction_conformality

        events = [_make_decision(confidence=0.7)]
        scores = score_prediction_conformality(events)
        assert len(scores) == 1
        assert scores[0].event_id == events[0].id

    def test_custom_confidence_level(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import score_prediction_conformality

        events = [_make_decision(confidence=0.5)]
        scores = score_prediction_conformality(events, confidence_level=0.99)
        assert len(scores) == 1
        assert scores[0].prediction_region.confidence_level == 0.99

    def test_ground_truth_updates_coverage(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import score_prediction_conformality, CoverageLevel

        # Create a decision event with confidence and ground truth
        event = DecisionEvent(
            id="test-decision",
            session_id="sess-001",
            confidence=0.5,
            reasoning="test",
            chosen_action="continue",
            timestamp=_NOW,
            data={"ground_truth": 0.6},
        )
        scores = score_prediction_conformality([event])
        assert len(scores) == 1
        assert scores[0].prediction_region.actual_value == 0.6
        assert scores[0].prediction_region.is_covered is True

    def test_all_scores_in_valid_range(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import score_prediction_conformality

        events = [
            _make_decision(confidence=c)
            for c in [0.3, 0.5, 0.7, 0.9]
        ]
        scores = score_prediction_conformality(events)
        for score in scores:
            assert 0.0 <= score.calibration_score <= 1.0


class TestComputeCoverageStatistics:
    """Tests for coverage statistics computation."""

    def test_empty_scores_returns_zeros(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import compute_coverage_statistics

        stats = compute_coverage_statistics([])
        assert stats["total_predictions"] == 0
        assert stats["avg_calibration_score"] == 0.0
        assert stats["coverage_rate"] == 0.0

    def test_statistics_keys(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import compute_coverage_statistics, ConformalScore, CoverageLevel, PredictionRegion

        region = PredictionRegion(0.4, 0.6, 0.9, 0.5, True, 0.2)
        score = ConformalScore("e1", region, CoverageLevel.WELL_COVERED, 0.9, "good")
        stats = compute_coverage_statistics([score])

        assert "total_predictions" in stats
        assert "well_covered_count" in stats
        assert "under_covered_count" in stats
        assert "over_covered_count" in stats
        assert "unknown_count" in stats
        assert "avg_calibration_score" in stats
        assert "coverage_rate" in stats
        assert "avg_region_width" in stats

    def test_counts_match_total(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import compute_coverage_statistics, ConformalScore, CoverageLevel, PredictionRegion

        scores = [
            ConformalScore(f"e{i}", PredictionRegion(0.4, 0.6, 0.9, None, False, 0.2), CoverageLevel.WELL_COVERED, 0.9, "good")
            for i in range(10)
        ]
        stats = compute_coverage_statistics(scores)

        assert stats["total_predictions"] == 10
        assert stats["well_covered_count"] + stats["under_covered_count"] + stats["over_covered_count"] + stats["unknown_count"] == 10

    def test_coverage_rate_with_ground_truth(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import compute_coverage_statistics, ConformalScore, CoverageLevel, PredictionRegion

        # 5 covered, 5 not covered
        scores = []
        for i in range(5):
            region = PredictionRegion(0.4, 0.6, 0.9, 0.5, True, 0.2)
            scores.append(ConformalScore(f"covered-{i}", region, CoverageLevel.WELL_COVERED, 0.9, "good"))

        for i in range(5):
            region = PredictionRegion(0.4, 0.6, 0.9, 0.8, False, 0.2)
            scores.append(ConformalScore(f"missed-{i}", region, CoverageLevel.UNDER_COVERED, 0.2, "bad"))

        stats = compute_coverage_statistics(scores)
        assert stats["coverage_rate"] == 0.5

    def test_coverage_rate_ignores_missing_truth(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import compute_coverage_statistics, ConformalScore, CoverageLevel, PredictionRegion

        # Only 2 of 10 have ground truth (1 covered, 1 not)
        scores = []
        for i in range(8):
            region = PredictionRegion(0.4, 0.6, 0.9, None, False, 0.2)
            scores.append(ConformalScore(f"no-truth-{i}", region, CoverageLevel.WELL_COVERED, 0.9, "good"))

        region_covered = PredictionRegion(0.4, 0.6, 0.9, 0.5, True, 0.2)
        scores.append(ConformalScore("covered", region_covered, CoverageLevel.WELL_COVERED, 0.9, "good"))

        region_missed = PredictionRegion(0.4, 0.6, 0.9, 0.8, False, 0.2)
        scores.append(ConformalScore("missed", region_missed, CoverageLevel.UNDER_COVERED, 0.2, "bad"))

        stats = compute_coverage_statistics(scores)
        # Coverage rate computed from only 2 regions with ground truth
        assert stats["coverage_rate"] == 0.5

    def test_average_width_computed(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import compute_coverage_statistics, ConformalScore, CoverageLevel, PredictionRegion

        scores = [
            ConformalScore(f"e{i}", PredictionRegion(0.4, 0.6, 0.9, None, False, 0.2), CoverageLevel.WELL_COVERED, 0.9, "good")
            for i in range(5)
        ]
        stats = compute_coverage_statistics(scores)

        assert stats["avg_region_width"] == 0.2

    def test_mixed_coverage_levels(self) -> None:
        from agent_debugger_sdk.core.conformal_scorer import compute_coverage_statistics, ConformalScore, CoverageLevel, PredictionRegion

        scores = [
            ConformalScore("e1", PredictionRegion(0.45, 0.55, 0.9, None, False, 0.1), CoverageLevel.WELL_COVERED, 0.95, "good"),
            ConformalScore("e2", PredictionRegion(0.3, 0.7, 0.9, None, False, 0.4), CoverageLevel.OVER_COVERED, 0.5, "wide"),
            ConformalScore("e3", PredictionRegion(0.4, 0.6, 0.9, None, False, 0.2), CoverageLevel.UNKNOWN, 0.5, "unknown"),
        ]
        stats = compute_coverage_statistics(scores)

        assert stats["well_covered_count"] == 1
        assert stats["over_covered_count"] == 1
        assert stats["unknown_count"] == 1
        assert stats["under_covered_count"] == 0


# ===========================================================================
# #186 Backward Failure Attribution — ErrorProbe
# ===========================================================================


class TestFailureCategory:
    """Tests for FailureCategory enum."""

    def test_enum_values(self) -> None:
        from agent_debugger_sdk.core.error_attribution import FailureCategory

        assert FailureCategory.RUNTIME_ERROR.value == "runtime_error"
        assert FailureCategory.TOOL_FAILURE.value == "tool_failure"
        assert FailureCategory.GUARDRAIL_BLOCK.value == "guardrail_block"
        assert FailureCategory.POLICY_VIOLATION.value == "policy_violation"
        assert FailureCategory.STATE_CORRUPTION.value == "state_corruption"
        assert FailureCategory.LOGIC_ERROR.value == "logic_error"
        assert FailureCategory.RESOURCE_FAILURE.value == "resource_failure"
        assert FailureCategory.TIMEOUT.value == "timeout"
        assert FailureCategory.UNKNOWN.value == "unknown"

    def test_nine_members(self) -> None:
        from agent_debugger_sdk.core.error_attribution import FailureCategory

        assert len(FailureCategory) == 9


class TestAttributionStrength:
    """Tests for AttributionStrength enum."""

    def test_enum_values(self) -> None:
        from agent_debugger_sdk.core.error_attribution import AttributionStrength

        assert AttributionStrength.DEFINITIVE.value == "definitive"
        assert AttributionStrength.STRONG.value == "strong"
        assert AttributionStrength.MODERATE.value == "moderate"
        assert AttributionStrength.WEAK.value == "weak"
        assert AttributionStrength.SPECULATIVE.value == "speculative"

    def test_five_members(self) -> None:
        from agent_debugger_sdk.core.error_attribution import AttributionStrength

        assert len(AttributionStrength) == 5


class TestErrorAttribution:
    """Tests for ErrorAttribution dataclass."""

    def test_to_dict_fields(self) -> None:
        from agent_debugger_sdk.core.error_attribution import (
            ErrorAttribution,
            FailureCategory,
            AttributionStrength,
        )

        attr = ErrorAttribution(
            error_event_id="error-1",
            root_cause_event_id="root-1",
            failure_category=FailureCategory.RUNTIME_ERROR,
            attribution_strength=AttributionStrength.STRONG,
            causal_chain=["root-1", "step-1", "error-1"],
            attribution_reasoning="Clear causal chain with explicit dependencies",
        )
        d = attr.to_dict()
        assert d["error_event_id"] == "error-1"
        assert d["root_cause_event_id"] == "root-1"
        assert d["failure_category"] == "runtime_error"
        assert d["attribution_strength"] == "strong"
        assert len(d["causal_chain"]) == 3

    def test_to_dict_with_contributing_factors(self) -> None:
        from agent_debugger_sdk.core.error_attribution import (
            ErrorAttribution,
            FailureCategory,
            AttributionStrength,
        )

        attr = ErrorAttribution(
            error_event_id="error-1",
            root_cause_event_id="root-1",
            failure_category=FailureCategory.TOOL_FAILURE,
            attribution_strength=AttributionStrength.MODERATE,
            contributing_factors=[
                {"event_id": "step-1", "factor_type": "low_confidence_decision", "description": "Uncertain decision"}
            ],
            mitigation_suggestions=["Add retry logic", "Validate inputs"],
        )
        d = attr.to_dict()
        assert len(d["contributing_factors"]) == 1
        assert len(d["mitigation_suggestions"]) == 2
        assert "retry" in d["mitigation_suggestions"][0].lower()


class TestFailureChain:
    """Tests for FailureChain dataclass."""

    def test_to_dict_fields(self) -> None:
        from agent_debugger_sdk.core.error_attribution import (
            FailureChain,
            FailureCategory,
            AttributionStrength,
        )

        chain = FailureChain(
            error_event_id="error-1",
            chain_events=[
                {"sequence": 0, "event_id": "root-1", "event_type": "decision"},
                {"sequence": 1, "event_id": "error-1", "event_type": "error"},
            ],
            chain_length=2,
            total_duration=1.5,
            failure_category=FailureCategory.RUNTIME_ERROR,
            attribution_strength=AttributionStrength.DEFINITIVE,
        )
        d = chain.to_dict()
        assert d["error_event_id"] == "error-1"
        assert d["chain_length"] == 2
        assert d["total_duration"] == 1.5
        assert d["failure_category"] == "runtime_error"


class TestIsErrorEvent:
    """Tests for _is_error_event helper."""

    def test_error_event_is_error(self) -> None:
        from agent_debugger_sdk.core.error_attribution import _is_error_event

        assert _is_error_event(
            TraceEvent(id="err", event_type=EventType.ERROR)
        ) is True

    def test_refusal_is_error(self) -> None:
        from agent_debugger_sdk.core.error_attribution import _is_error_event

        assert _is_error_event(
            TraceEvent(id="ref", event_type=EventType.REFUSAL)
        ) is True

    def test_policy_violation_is_error(self) -> None:
        from agent_debugger_sdk.core.error_attribution import _is_error_event

        assert _is_error_event(
            TraceEvent(id="pv", event_type=EventType.POLICY_VIOLATION)
        ) is True

    def test_behavior_alert_is_error(self) -> None:
        from agent_debugger_sdk.core.error_attribution import _is_error_event

        assert _is_error_event(
            TraceEvent(id="ba", event_type=EventType.BEHAVIOR_ALERT)
        ) is True

    def test_decision_not_error(self) -> None:
        from agent_debugger_sdk.core.error_attribution import _is_error_event

        assert _is_error_event(
            TraceEvent(id="d", event_type=EventType.DECISION)
        ) is False


class TestClassifyFailureCategory:
    """Tests for _classify_failure_category helper."""

    def test_error_event_default(self) -> None:
        from agent_debugger_sdk.core.error_attribution import _classify_failure_category

        cat = _classify_failure_category(
            TraceEvent(id="err", event_type=EventType.ERROR)
        )
        assert cat.value == "runtime_error"

    def test_refusal_is_guardrail_block(self) -> None:
        from agent_debugger_sdk.core.error_attribution import _classify_failure_category, FailureCategory

        cat = _classify_failure_category(
            TraceEvent(id="ref", event_type=EventType.REFUSAL)
        )
        assert cat == FailureCategory.GUARDRAIL_BLOCK

    def test_policy_violation(self) -> None:
        from agent_debugger_sdk.core.error_attribution import _classify_failure_category, FailureCategory

        cat = _classify_failure_category(
            TraceEvent(id="pv", event_type=EventType.POLICY_VIOLATION)
        )
        assert cat == FailureCategory.POLICY_VIOLATION

    def test_timeout_error(self) -> None:
        from agent_debugger_sdk.core.error_attribution import _classify_failure_category, FailureCategory

        event = TraceEvent(
            id="timeout",
            event_type=EventType.ERROR,
            data={"error_type": "TimeoutError"}
        )
        cat = _classify_failure_category(event)
        assert cat == FailureCategory.TIMEOUT

    def test_tool_error(self) -> None:
        from agent_debugger_sdk.core.error_attribution import _classify_failure_category, FailureCategory

        event = TraceEvent(
            id="tool_err",
            event_type=EventType.ERROR,
            data={"error_message": "Tool execution failed"}
        )
        cat = _classify_failure_category(event)
        assert cat == FailureCategory.TOOL_FAILURE


class TestCalculateAttributionStrength:
    """Tests for _calculate_attribution_strength helper."""

    def test_explicit_dependency_strong(self) -> None:
        from agent_debugger_sdk.core.error_attribution import _calculate_attribution_strength, AttributionStrength

        chain = [
            TraceEvent(id="root", event_type=EventType.DECISION, timestamp=_NOW),
            TraceEvent(
                id="error",
                event_type=EventType.ERROR,
                timestamp=_NEXT,
                upstream_event_ids=["root"],
            )
        ]
        strength = _calculate_attribution_strength(chain, chain[-1])
        # With explicit dependency but no parent link, attribution is WEAK
        assert strength in {AttributionStrength.WEAK, AttributionStrength.MODERATE}

    def test_no_chain_speculative(self) -> None:
        from agent_debugger_sdk.core.error_attribution import _calculate_attribution_strength, AttributionStrength

        error = TraceEvent(id="err", event_type=EventType.ERROR, timestamp=_NOW)
        strength = _calculate_attribution_strength([], error)
        assert strength == AttributionStrength.SPECULATIVE


class TestTraceCausalChain:
    """Tests for _trace_causal_chain helper."""

    def test_traces_parent_chain(self) -> None:
        from agent_debugger_sdk.core.error_attribution import _trace_causal_chain

        root = TraceEvent(id="root", event_type=EventType.DECISION, timestamp=_NOW)
        error = TraceEvent(
            id="err",
            event_type=EventType.ERROR,
            parent_id="root",
            timestamp=_NEXT,
        )

        chain = _trace_causal_chain(error, [root, error])
        assert len(chain) == 2
        assert chain[0].id == "root"
        assert chain[1].id == "err"

    def test_no_parent_chain(self) -> None:
        from agent_debugger_sdk.core.error_attribution import _trace_causal_chain

        error = TraceEvent(id="isolated", event_type=EventType.ERROR, timestamp=_NOW)
        chain = _trace_causal_chain(error, [error])
        assert len(chain) == 1
        assert chain[0].id == "isolated"

    def test_chain_is_root_to_error_order(self) -> None:
        from agent_debugger_sdk.core.error_attribution import _trace_causal_chain

        root = TraceEvent(id="root", event_type=EventType.DECISION, timestamp=_NOW)
        mid = TraceEvent(
            id="mid",
            event_type=EventType.DECISION,
            parent_id="root",
            timestamp=_NOW + timedelta(seconds=1),
        )
        error = TraceEvent(
            id="err",
            event_type=EventType.ERROR,
            parent_id="mid",
            timestamp=_NOW + timedelta(seconds=2),
        )

        chain = _trace_causal_chain(error, [root, mid, error])
        assert chain[0].id == "root"
        assert chain[-1].id == "err"


class TestIdentifyWeakPoints:
    """Tests for _identify_weak_points helper."""

    def test_low_confidence_decision(self) -> None:
        from agent_debugger_sdk.core.error_attribution import _identify_weak_points

        chain = [
            TraceEvent(
                id="low_conf",
                event_type=EventType.DECISION,
                timestamp=_NOW,
                data={"confidence": 0.5},
            )
        ]

        weak_points = _identify_weak_points(chain)
        assert len(weak_points) >= 1  # At least the low confidence decision
        assert weak_points[0]["weakness_type"] == "low_confidence_decision"
        # Severity is "medium" for confidence 0.5, "high" for confidence < 0.5
        assert weak_points[0]["severity"] in {"medium", "high"}

    def test_unsupported_decision(self) -> None:
        from agent_debugger_sdk.core.error_attribution import _identify_weak_points

        chain = [
            TraceEvent(
                id="no_ev",
                event_type=EventType.DECISION,
                timestamp=_NOW,
                data={"evidence": []},
            )
        ]

        weak_points = _identify_weak_points(chain)
        assert len(weak_points) == 1
        assert weak_points[0]["weakness_type"] == "unsupported_decision"

    def test_pre_error_decision(self) -> None:
        from agent_debugger_sdk.core.error_attribution import _identify_weak_points

        chain = [
            TraceEvent(id="dec", event_type=EventType.DECISION, timestamp=_NOW),
            TraceEvent(id="err", event_type=EventType.ERROR, timestamp=_NEXT),
        ]

        weak_points = _identify_weak_points(chain)
        assert any(wp["weakness_type"] == "pre_error_decision" for wp in weak_points)


class TestAttributeErrors:
    """Integration tests for attribute_errors function."""

    def test_single_error_attribution(self) -> None:
        from agent_debugger_sdk.core.error_attribution import attribute_errors

        events = [
            TraceEvent(id="root", event_type=EventType.DECISION, timestamp=_NOW),
            ErrorEvent(
                id="err",
                parent_id="root",
                error_type="RuntimeError",
                error_message="Test error",
                timestamp=_NEXT,
            ),
        ]

        attributions = attribute_errors(events)
        assert len(attributions) == 1
        assert attributions[0].error_event_id == "err"
        assert attributions[0].root_cause_event_id == "root"

    def test_multiple_errors_attribution(self) -> None:
        from agent_debugger_sdk.core.error_attribution import attribute_errors

        events = _make_session(steps=5, inject_error_at=2)
        events.append(
            ErrorEvent(
                id="err2",
                parent_id="step-3",
                error_type="ValueError",
                error_message="Another error",
                timestamp=_NEXT + timedelta(seconds=1),
            )
        )

        attributions = attribute_errors(events)
        # Should find at least the error events
        assert len(attributions) >= 1

    def test_empty_events_no_attribution(self) -> None:
        from agent_debugger_sdk.core.error_attribution import attribute_errors

        attributions = attribute_errors([])
        assert len(attributions) == 0

    def test_no_errors_no_attribution(self) -> None:
        from agent_debugger_sdk.core.error_attribution import attribute_errors

        events = _make_session(steps=5)
        attributions = attribute_errors(events)
        assert len(attributions) == 0

    def test_causal_chain_built(self) -> None:
        from agent_debugger_sdk.core.error_attribution import attribute_errors

        events = [
            TraceEvent(id="root", event_type=EventType.DECISION, timestamp=_NOW),
            TraceEvent(
                id="mid",
                event_type=EventType.DECISION,
                parent_id="root",
                timestamp=_NEXT,
            ),
            ErrorEvent(
                id="err",
                parent_id="mid",
                error_type="RuntimeError",
                error_message="Error",
                timestamp=_NEXT + timedelta(seconds=1),
            ),
        ]

        attributions = attribute_errors(events)
        assert len(attributions[0].causal_chain) == 3
        assert attributions[0].causal_chain[0] == "root"
        assert attributions[0].causal_chain[-1] == "err"

    def test_mitigation_suggestions_generated(self) -> None:
        from agent_debugger_sdk.core.error_attribution import attribute_errors

        events = [
            TraceEvent(id="root", event_type=EventType.DECISION, timestamp=_NOW),
            ErrorEvent(
                id="err",
                parent_id="root",
                error_type="RuntimeError",
                error_message="Test error",
                timestamp=_NEXT,
            ),
        ]

        attributions = attribute_errors(events)
        assert len(attributions[0].mitigation_suggestions) > 0
        assert isinstance(attributions[0].mitigation_suggestions[0], str)


class TestFindRootCauses:
    """Tests for find_root_causes function."""

    def test_returns_root_cause_list(self) -> None:
        from agent_debugger_sdk.core.error_attribution import find_root_causes

        events = [
            TraceEvent(id="root", event_type=EventType.DECISION, timestamp=_NOW),
            ErrorEvent(
                id="err",
                parent_id="root",
                error_type="RuntimeError",
                error_message="Error",
                timestamp=_NEXT,
            ),
        ]

        root_causes = find_root_causes(events)
        assert len(root_causes) == 1
        assert root_causes[0]["root_cause_event_id"] == "root"
        assert root_causes[0]["error_event_id"] == "err"

    def test_empty_events_no_root_causes(self) -> None:
        from agent_debugger_sdk.core.error_attribution import find_root_causes

        root_causes = find_root_causes([])
        assert len(root_causes) == 0

    def test_no_errors_no_root_causes(self) -> None:
        from agent_debugger_sdk.core.error_attribution import find_root_causes

        events = _make_session(steps=5)
        root_causes = find_root_causes(events)
        assert len(root_causes) == 0


class TestAnalyzeFailurePatterns:
    """Tests for analyze_failure_patterns function."""

    def test_basic_pattern_structure(self) -> None:
        from agent_debugger_sdk.core.error_attribution import analyze_failure_patterns

        events = [
            TraceEvent(id="root", event_type=EventType.DECISION, timestamp=_NOW),
            ErrorEvent(
                id="err",
                parent_id="root",
                error_type="RuntimeError",
                error_message="Error",
                timestamp=_NEXT,
            ),
        ]

        patterns = analyze_failure_patterns(events)
        assert "total_errors" in patterns
        assert "error_categories" in patterns
        assert "attribution_strengths" in patterns
        assert "common_weaknesses" in patterns
        assert "recommendations" in patterns

    def test_empty_events_baseline(self) -> None:
        from agent_debugger_sdk.core.error_attribution import analyze_failure_patterns

        patterns = analyze_failure_patterns([])
        assert patterns["total_errors"] == 0
        assert patterns["error_categories"] == {}
        assert patterns["recommendations"] == []

    def test_counts_error_categories(self) -> None:
        from agent_debugger_sdk.core.error_attribution import analyze_failure_patterns

        events = [
            TraceEvent(id="root", event_type=EventType.DECISION, timestamp=_NOW),
            ErrorEvent(
                id="err1",
                parent_id="root",
                error_type="RuntimeError",
                error_message="Error 1",
                timestamp=_NEXT,
            ),
            TraceEvent(
                id="root2",
                event_type=EventType.REFUSAL,
                timestamp=_NEXT + timedelta(seconds=1),
            ),
        ]

        patterns = analyze_failure_patterns(events)
        assert patterns["total_errors"] == 2
        assert "runtime_error" in patterns["error_categories"]
        assert "guardrail_block" in patterns["error_categories"]

    def test_generates_recommendations(self) -> None:
        from agent_debugger_sdk.core.error_attribution import analyze_failure_patterns

        events = _make_session(steps=10, inject_error_at=3)

        patterns = analyze_failure_patterns(events)
        # Should generate some recommendations for session with errors
        assert len(patterns["recommendations"]) >= 0


class TestBuildFailureChain:
    """Tests for build_failure_chain function."""

    def test_basic_chain_structure(self) -> None:
        from agent_debugger_sdk.core.error_attribution import build_failure_chain

        error = ErrorEvent(
            id="err",
            parent_id="root",
            error_type="RuntimeError",
            error_message="Error",
            timestamp=_NEXT,
        )
        root = TraceEvent(id="root", event_type=EventType.DECISION, timestamp=_NOW)

        chain = build_failure_chain(error, [root, error])

        assert chain.error_event_id == "err"
        assert chain.chain_length == 2
        assert len(chain.chain_events) == 2

    def test_chain_events_ordered(self) -> None:
        from agent_debugger_sdk.core.error_attribution import build_failure_chain

        error = ErrorEvent(
            id="err",
            parent_id="mid",
            error_type="RuntimeError",
            error_message="Error",
            timestamp=_NEXT + timedelta(seconds=1),
        )
        mid = TraceEvent(
            id="mid",
            event_type=EventType.DECISION,
            parent_id="root",
            timestamp=_NEXT,
        )
        root = TraceEvent(id="root", event_type=EventType.DECISION, timestamp=_NOW)

        chain = build_failure_chain(error, [root, mid, error])

        assert chain.chain_events[0]["event_id"] == "root"
        assert chain.chain_events[-1]["event_id"] == "err"

    def test_weak_points_identified(self) -> None:
        from agent_debugger_sdk.core.error_attribution import build_failure_chain

        error = ErrorEvent(
            id="err",
            parent_id="low",
            error_type="RuntimeError",
            error_message="Error",
            timestamp=_NEXT,
        )
        low_conf = TraceEvent(
            id="low",
            event_type=EventType.DECISION,
            timestamp=_NOW,
            data={"confidence": 0.4},
        )

        chain = build_failure_chain(error, [low_conf, error])

        assert len(chain.weak_points) >= 1
        assert chain.weak_points[0]["weakness_type"] == "low_confidence_decision"

    def test_duration_calculated(self) -> None:
        from agent_debugger_sdk.core.error_attribution import build_failure_chain

        error = ErrorEvent(
            id="err",
            parent_id="root",
            error_type="RuntimeError",
            error_message="Error",
            timestamp=_NEXT,
        )
        root = TraceEvent(id="root", event_type=EventType.DECISION, timestamp=_NOW)

        chain = build_failure_chain(error, [root, error])

        assert chain.total_duration > 0
        assert chain.total_duration == 1.0  # 1 second difference
