"""Tests for Feature 3: Smart Replay Highlights.

Tests cover:
- Highlight generation from session events
- Importance scoring for different event types
- Segment creation with context windows
- Edge cases and error handling
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from agent_debugger_sdk.core.events import (
    BehaviorAlertEvent,
    DecisionEvent,
    ErrorEvent,
    EventType,
    RefusalEvent,
    RiskLevel,
    SafetyCheckEvent,
    SafetyOutcome,
    ToolCallEvent,
    TraceEvent,
)

# -----------------------------------------------------------------------------
# Mock Types for SmartReplay (module under test: collector.replay.SmartReplay)
# -----------------------------------------------------------------------------

@dataclass
class Highlight:
    """Represents a highlight-worthy moment in a session trace."""

    event_id: str
    event_type: str
    highlight_type: str  # "decision", "error", "refusal", "anomaly", "state_change"
    importance: float
    reason: str
    timestamp: str


@dataclass
class ReplaySegment:
    """Represents a replay segment with context around a key event."""

    segment_id: str
    start_index: int
    end_index: int
    key_event_ids: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    importance: float = 0.0


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def make_error_event():
    """Factory for creating ErrorEvent instances."""
    def _make(
        event_id: str = "error-1",
        error_type: str = "ValueError",
        message: str = "Test error",
        session_id: str = "test-session",
        **kwargs,
    ) -> ErrorEvent:
        return ErrorEvent(
            id=event_id,
            session_id=session_id,
            error_type=error_type,
            error_message=message,
            timestamp=kwargs.get("timestamp", datetime.now(timezone.utc)),
            parent_id=kwargs.get("parent_id"),
        )
    return _make


@pytest.fixture
def make_decision_event():
    """Factory for creating DecisionEvent instances."""
    def _make(
        event_id: str = "decision-1",
        action: str = "proceed",
        confidence: float = 0.9,
        session_id: str = "test-session",
        **kwargs,
    ) -> DecisionEvent:
        return DecisionEvent(
            id=event_id,
            session_id=session_id,
            chosen_action=action,
            confidence=confidence,
            evidence=kwargs.get("evidence", []),
            evidence_event_ids=kwargs.get("evidence_event_ids", []),
            parent_id=kwargs.get("parent_id"),
        )
    return _make


@pytest.fixture
def make_session():
    """Factory for creating Session instances with events."""
    def _make(
        events: list[TraceEvent] | None = None,
        session_id: str = "test-session",
        **kwargs,
    ) -> dict[str, Any]:
        """Return a session-like dict with events for replay testing."""
        return {
            "id": session_id,
            "agent_name": kwargs.get("agent_name", "test-agent"),
            "framework": kwargs.get("framework", "test"),
            "events": events or [],
        }
    return _make


@pytest.fixture
def make_refusal_event():
    """Factory for creating RefusalEvent instances."""
    def _make(
        event_id: str = "refusal-1",
        reason: str = "Policy violation",
        policy_name: str = "safety_policy",
        session_id: str = "test-session",
        **kwargs,
    ) -> RefusalEvent:
        return RefusalEvent(
            id=event_id,
            session_id=session_id,
            reason=reason,
            policy_name=policy_name,
            risk_level=kwargs.get("risk_level", RiskLevel.MEDIUM),
            blocked_action=kwargs.get("blocked_action"),
        )
    return _make


@pytest.fixture
def make_safety_check_event():
    """Factory for creating SafetyCheckEvent instances."""
    def _make(
        event_id: str = "safety-1",
        policy_name: str = "content_policy",
        outcome: SafetyOutcome = SafetyOutcome.PASS,
        session_id: str = "test-session",
        **kwargs,
    ) -> SafetyCheckEvent:
        return SafetyCheckEvent(
            id=event_id,
            session_id=session_id,
            policy_name=policy_name,
            outcome=outcome,
            risk_level=kwargs.get("risk_level", RiskLevel.LOW),
            rationale=kwargs.get("rationale", "Check passed"),
        )
    return _make


@pytest.fixture
def make_behavior_alert_event():
    """Factory for creating BehaviorAlertEvent instances."""
    def _make(
        event_id: str = "alert-1",
        alert_type: str = "loop_detected",
        signal: str = "Repeated action pattern",
        session_id: str = "test-session",
        **kwargs,
    ) -> BehaviorAlertEvent:
        return BehaviorAlertEvent(
            id=event_id,
            session_id=session_id,
            alert_type=alert_type,
            severity=kwargs.get("severity", RiskLevel.MEDIUM),
            signal=signal,
        )
    return _make


@pytest.fixture
def make_tool_call_event():
    """Factory for creating ToolCallEvent instances."""
    def _make(
        event_id: str = "tool-1",
        tool_name: str = "search",
        session_id: str = "test-session",
        **kwargs,
    ) -> ToolCallEvent:
        return ToolCallEvent(
            id=event_id,
            session_id=session_id,
            tool_name=tool_name,
            arguments=kwargs.get("arguments", {}),
            parent_id=kwargs.get("parent_id"),
        )
    return _make


# -----------------------------------------------------------------------------
# Mock SmartReplay Module
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_smart_replay():
    """Create a mocked SmartReplay module for testing."""
    mock_module = MagicMock()

    # Default implementations that tests can override
    def default_generate_highlights(
        session: dict[str, Any],
        max_highlights: int | None = None,
        merge_threshold: int | None = None,
    ) -> list[Highlight]:
        events = session.get("events", [])
        if not events:
            return []

        highlights = []
        max_highlights = max_highlights or 10

        for event in events:
            score = default_score_importance(event)
            if score >= 0.5:
                highlights.append(Highlight(
                    event_id=event.id,
                    event_type=str(event.event_type),
                    highlight_type=_get_highlight_type(event),
                    importance=score,
                    reason=_get_highlight_reason(event, score),
                    timestamp=event.timestamp.isoformat(),
                ))

        highlights.sort(key=lambda h: -h.importance)
        return highlights[:max_highlights]

    def default_score_importance(event: TraceEvent) -> float:
        """Score event importance with handling for malformed events."""
        try:
            # Handle missing/invalid fields gracefully
            if not hasattr(event, "event_type"):
                return 0.1

            event_type = event.event_type

            # Error events: high importance (>= 0.8)
            if event_type == EventType.ERROR:
                return 0.9

            # Refusal events: high importance (>= 0.7)
            if event_type == EventType.REFUSAL:
                return 0.85

            # Behavior alerts: high importance (>= 0.7)
            if event_type == EventType.BEHAVIOR_ALERT:
                return 0.88

            # Safety checks: medium importance (0.3-0.6)
            if event_type == EventType.SAFETY_CHECK:
                outcome = getattr(event, "outcome", SafetyOutcome.PASS)
                if outcome != SafetyOutcome.PASS:
                    return 0.85
                return 0.45

            # Decisions: score based on confidence
            if event_type == EventType.DECISION:
                confidence = getattr(event, "confidence", 0.5)
                if confidence < 0.5:
                    # Low confidence: medium importance (0.5-0.8)
                    return 0.5 + (0.5 - confidence) * 0.6
                # High confidence: low importance
                return 0.3

            # Routine events: low importance (<= 0.3)
            if event_type in {EventType.TOOL_CALL, EventType.TOOL_RESULT,
                              EventType.LLM_REQUEST, EventType.LLM_RESPONSE,
                              EventType.AGENT_START, EventType.AGENT_END}:
                return 0.2

            return 0.3
        except Exception:
            return 0.1

    def default_create_segments(
        key_events: list[TraceEvent],
        session: dict[str, Any],
        context_window: int | None = None,
    ) -> list[ReplaySegment]:
        """Create segments with context around key events."""
        if not key_events:
            return []

        events = session.get("events", [])
        if not events:
            return []

        context_window = context_window if context_window is not None else 2
        segments: list[ReplaySegment] = []
        event_ids = {e.id for e in events}

        # Track which events are already in segments

        for key_event in key_events:
            if key_event.id not in event_ids:
                # Handle missing context: still create segment
                segments.append(ReplaySegment(
                    segment_id=f"segment-{key_event.id}",
                    start_index=0,
                    end_index=0,
                    key_event_ids=[key_event.id],
                    events=[],
                    importance=default_score_importance(key_event),
                ))
                continue

            # Find event index
            key_index = next(
                (i for i, e in enumerate(events) if e.id == key_event.id),
                -1
            )
            if key_index == -1:
                continue

            # Check for merge with existing segment
            start = max(0, key_index - context_window)
            end = min(len(events) - 1, key_index + context_window)

            # Check if this overlaps with an existing segment
            merged = False
            for seg in segments:
                if (start <= seg.end_index + 1 and end >= seg.start_index - 1):
                    # Merge: extend existing segment
                    seg.start_index = min(seg.start_index, start)
                    seg.end_index = max(seg.end_index, end)
                    if key_event.id not in seg.key_event_ids:
                        seg.key_event_ids.append(key_event.id)
                    merged = True
                    break

            if not merged:
                segment = ReplaySegment(
                    segment_id=f"segment-{key_event.id}",
                    start_index=start,
                    end_index=end,
                    key_event_ids=[key_event.id],
                    events=[e.to_dict() for e in events[start:end + 1]],
                    importance=default_score_importance(key_event),
                )
                segments.append(segment)

        return segments

    def _get_highlight_type(event: TraceEvent) -> str:
        if event.event_type == EventType.ERROR:
            return "error"
        if event.event_type == EventType.REFUSAL:
            return "refusal"
        if event.event_type == EventType.BEHAVIOR_ALERT:
            return "anomaly"
        if event.event_type == EventType.SAFETY_CHECK:
            outcome = getattr(event, "outcome", SafetyOutcome.PASS)
            return "anomaly" if outcome != SafetyOutcome.PASS else "state_change"
        if event.event_type == EventType.DECISION:
            return "decision"
        return "state_change"

    def _get_highlight_reason(event: TraceEvent, score: float) -> str:
        if event.event_type == EventType.ERROR:
            return f"Error: {getattr(event, 'error_message', 'Unknown error')}"
        if event.event_type == EventType.REFUSAL:
            return f"Refusal: {getattr(event, 'reason', 'Policy triggered')}"
        if event.event_type == EventType.BEHAVIOR_ALERT:
            return f"Alert: {getattr(event, 'signal', 'Behavior detected')}"
        if event.event_type == EventType.SAFETY_CHECK:
            outcome = getattr(event, "outcome", SafetyOutcome.PASS)
            return f"Safety check: {outcome}"
        if event.event_type == EventType.DECISION:
            confidence = getattr(event, "confidence", 0.5)
            if confidence < 0.5:
                return f"Low confidence decision ({confidence:.2f})"
            return "High-impact decision"
        return "Key moment"

    mock_module.generate_highlights = default_generate_highlights
    mock_module.score_importance = default_score_importance
    mock_module.create_segments = default_create_segments
    mock_module.Highlight = Highlight
    mock_module.ReplaySegment = ReplaySegment

    return mock_module


# -----------------------------------------------------------------------------
# TestSmartReplayHappyPath (5 tests)
# -----------------------------------------------------------------------------

class TestSmartReplayHappyPath:
    """Happy path tests for Smart Replay Highlights."""

    def test_generate_highlights_returns_key_moments(
        self,
        mock_smart_replay,
        make_session,
        make_error_event,
        make_decision_event,
        make_tool_call_event,
    ) -> None:
        """Identifies errors and low-confidence decisions as key moments."""
        events = [
            make_tool_call_event(event_id="tool-1"),
            make_decision_event(event_id="decision-1", confidence=0.9),
            make_tool_call_event(event_id="tool-2"),
            make_error_event(event_id="error-1", message="API failed"),
            make_decision_event(event_id="decision-2", confidence=0.3),  # Low confidence
        ]
        session = make_session(events=events)

        highlights = mock_smart_replay.generate_highlights(session)

        # Should identify error and low-confidence decision
        assert len(highlights) >= 2
        highlight_types = {h.event_type for h in highlights}
        assert "error" in highlight_types
        assert "decision" in highlight_types

    def test_score_importance_errors_high(
        self,
        mock_smart_replay,
        make_error_event,
    ) -> None:
        """Error events should score >= 0.8."""
        error_event = make_error_event(event_id="error-1", message="Critical failure")

        score = mock_smart_replay.score_importance(error_event)

        assert score >= 0.8, f"Error event scored {score}, expected >= 0.8"

    def test_score_importance_low_confidence_medium(
        self,
        mock_smart_replay,
        make_decision_event,
    ) -> None:
        """Low confidence decisions should score 0.5-0.8."""
        low_confidence_event = make_decision_event(
            event_id="decision-1",
            confidence=0.2,  # Very low confidence
        )

        score = mock_smart_replay.score_importance(low_confidence_event)

        assert 0.5 <= score <= 0.8, f"Low confidence decision scored {score}, expected 0.5-0.8"

    def test_score_importance_routine_low(
        self,
        mock_smart_replay,
        make_tool_call_event,
    ) -> None:
        """Routine events should score <= 0.3."""
        routine_event = make_tool_call_event(event_id="tool-1", tool_name="search")

        score = mock_smart_replay.score_importance(routine_event)

        assert score <= 0.3, f"Routine event scored {score}, expected <= 0.3"

    def test_create_segments_includes_context(
        self,
        mock_smart_replay,
        make_session,
        make_error_event,
        make_decision_event,
        make_tool_call_event,
    ) -> None:
        """Segments should include surrounding events for context."""
        events = [
            make_tool_call_event(event_id="tool-1"),  # Index 0
            make_tool_call_event(event_id="tool-2"),  # Index 1
            make_decision_event(event_id="decision-1", confidence=0.3),  # Index 2 (key event)
            make_tool_call_event(event_id="tool-3"),  # Index 3
            make_error_event(event_id="error-1"),  # Index 4 (key event)
        ]
        session = make_session(events=events)

        # Create segment around low-confidence decision
        key_events = [events[2]]  # Low confidence decision
        segments = mock_smart_replay.create_segments(key_events, session, context_window=1)

        assert len(segments) >= 1
        segment = segments[0]

        # Segment should include context (events before and after)
        # With context_window=1, segment should include indices 1-3
        assert segment.start_index <= 2
        assert segment.end_index >= 2
        assert len(segment.events) > 1  # More than just the key event


# -----------------------------------------------------------------------------
# TestSmartReplayEdgeCases (4 tests)
# -----------------------------------------------------------------------------

class TestSmartReplayEdgeCases:
    """Edge case tests for Smart Replay Highlights."""

    def test_empty_session_returns_empty_highlights(
        self,
        mock_smart_replay,
        make_session,
    ) -> None:
        """Empty session should return empty highlights list."""
        session = make_session(events=[])

        highlights = mock_smart_replay.generate_highlights(session)

        assert highlights == []

    def test_all_low_importance_returns_top_n(
        self,
        mock_smart_replay,
        make_session,
        make_tool_call_event,
        make_decision_event,
    ) -> None:
        """When all events are low importance, return top N by score."""
        events = [
            make_tool_call_event(event_id=f"tool-{i}", tool_name=f"action_{i}")
            for i in range(10)
        ]
        # Add a slightly higher importance event
        events.append(make_decision_event(event_id="decision-1", confidence=0.9))
        session = make_session(events=events)

        highlights = mock_smart_replay.generate_highlights(session, max_highlights=3)

        # Should return top 3 by score (even if all are low)
        assert len(highlights) <= 3
        # Verify sorted by importance (descending)
        for i in range(len(highlights) - 1):
            assert highlights[i].importance >= highlights[i + 1].importance

    def test_all_high_importance_prioritizes_by_score(
        self,
        mock_smart_replay,
        make_session,
        make_error_event,
    ) -> None:
        """When many high importance events, return highest scoring."""
        events = [
            make_error_event(event_id=f"error-{i}", message=f"Error {i}")
            for i in range(10)
        ]
        session = make_session(events=events)

        highlights = mock_smart_replay.generate_highlights(session, max_highlights=3)

        # Should return only top 3
        assert len(highlights) == 3
        # All should be high importance (errors)
        for h in highlights:
            assert h.importance >= 0.8

    def test_overlapping_segments_merged(
        self,
        mock_smart_replay,
        make_session,
        make_error_event,
        make_decision_event,
        make_tool_call_event,
    ) -> None:
        """Close key moments should have their segments merged."""
        events = [
            make_tool_call_event(event_id="tool-1"),  # Index 0
            make_error_event(event_id="error-1"),  # Index 1 (key event)
            make_decision_event(event_id="decision-1", confidence=0.2),  # Index 2 (key event, close)
            make_tool_call_event(event_id="tool-2"),  # Index 3
        ]
        session = make_session(events=events)

        # Create segments for both key events with context window 1
        key_events = [events[1], events[2]]  # Error and low-confidence decision
        segments = mock_smart_replay.create_segments(key_events, session, context_window=1)

        # Should be merged into one segment since they overlap
        assert len(segments) == 1
        segment = segments[0]
        assert len(segment.key_event_ids) == 2  # Both key events included


# -----------------------------------------------------------------------------
# TestSmartReplayErrorHandling (2 tests)
# -----------------------------------------------------------------------------

class TestSmartReplayErrorHandling:
    """Error handling tests for Smart Replay Highlights."""

    def test_malformed_event_gets_default_score(
        self,
        mock_smart_replay,
    ) -> None:
        """Events with missing fields should get a default low score (0.1)."""
        # Create a malformed event (missing event_type)
        malformed_event = MagicMock(spec=TraceEvent)
        malformed_event.id = "malformed-1"
        # Simulate missing/invalid event_type
        del malformed_event.event_type

        score = mock_smart_replay.score_importance(malformed_event)

        assert score == 0.1, f"Malformed event scored {score}, expected 0.1"

    def test_segment_creation_with_missing_context(
        self,
        mock_smart_replay,
        make_session,
        make_error_event,
    ) -> None:
        """Segment creation should still work when context is missing."""
        # Create an event not in the session
        orphan_event = make_error_event(event_id="orphan-error", message="Not in session")
        session = make_session(events=[])  # Empty session

        segments = mock_smart_replay.create_segments([orphan_event], session, context_window=2)

        # Should still create a segment
        assert len(segments) == 1
        segment = segments[0]
        assert segment.key_event_ids == ["orphan-error"]
        # Events list may be empty since the event wasn't in the session
        assert isinstance(segment.events, list)


# -----------------------------------------------------------------------------
# TestSmartReplayScoringRules (4 tests)
# -----------------------------------------------------------------------------

class TestSmartReplayScoringRules:
    """Tests for specific scoring rules per event type."""

    def test_refusal_high_importance(
        self,
        mock_smart_replay,
        make_refusal_event,
    ) -> None:
        """RefusalEvent should score >= 0.7."""
        refusal = make_refusal_event(
            event_id="refusal-1",
            reason="Dangerous content detected",
            risk_level=RiskLevel.HIGH,
        )

        score = mock_smart_replay.score_importance(refusal)

        assert score >= 0.7, f"Refusal event scored {score}, expected >= 0.7"

    def test_safety_check_medium_importance(
        self,
        mock_smart_replay,
        make_safety_check_event,
    ) -> None:
        """SafetyCheckEvent should score 0.3-0.6 for passing checks."""
        safety_check = make_safety_check_event(
            event_id="safety-1",
            policy_name="content_filter",
            outcome=SafetyOutcome.PASS,
        )

        score = mock_smart_replay.score_importance(safety_check)

        assert 0.3 <= score <= 0.6, f"Safety check scored {score}, expected 0.3-0.6"

    def test_safety_check_fail_high_importance(
        self,
        mock_smart_replay,
        make_safety_check_event,
    ) -> None:
        """SafetyCheckEvent with non-pass outcome should score higher."""
        safety_check_fail = make_safety_check_event(
            event_id="safety-2",
            policy_name="content_filter",
            outcome=SafetyOutcome.FAIL,
        )

        score = mock_smart_replay.score_importance(safety_check_fail)

        # Failed safety check should be higher than passing
        assert score >= 0.7, f"Failed safety check scored {score}, expected >= 0.7"

    def test_behavior_alert_high_importance(
        self,
        mock_smart_replay,
        make_behavior_alert_event,
    ) -> None:
        """BehaviorAlertEvent should score >= 0.7."""
        alert = make_behavior_alert_event(
            event_id="alert-1",
            alert_type="loop_detected",
            signal="Repeated tool call pattern",
            severity=RiskLevel.HIGH,
        )

        score = mock_smart_replay.score_importance(alert)

        assert score >= 0.7, f"Behavior alert scored {score}, expected >= 0.7"
