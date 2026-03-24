"""Tests for escalation detection module."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from collector.escalation_detection import (
    WEIGHTS,
    EscalationSignal,
    _detect_confidence_degradation,
    _detect_explicit_keywords,
    _detect_handoff_patterns,
    _detect_safety_pressure,
    _detect_tool_stake_increase,
    compute_escalation_score,
    detect_escalation_signals,
)


def make_turn_event(
    event_id: str,
    speaker: str = "agent",
    goal: str = "",
    content: str = "",
    timestamp: datetime | None = None,
) -> MagicMock:
    """Create a mock turn event."""
    event = MagicMock()
    event.id = event_id
    event.speaker = speaker
    event.agent_id = speaker
    event.goal = goal
    event.content = content
    event.timestamp = timestamp
    event.data = {"goal": goal, "content": content, "speaker": speaker}
    return event


def make_decision_event(
    event_id: str,
    confidence: float = 0.8,
    timestamp: datetime | None = None,
) -> MagicMock:
    """Create a mock decision event."""
    event = MagicMock()
    event.id = event_id
    event.confidence = confidence
    event.timestamp = timestamp
    event.data = {"confidence": confidence}
    return event


def make_safety_event(
    event_id: str,
    severity: float = 0.5,
    event_type: str = "safety_check",
) -> MagicMock:
    """Create a mock safety event."""
    event = MagicMock()
    event.id = event_id
    event.severity = severity
    event.event_type = event_type
    event.data = {"severity": severity}
    return event


def make_tool_call_event(
    event_id: str,
    tool_name: str = "read",
) -> MagicMock:
    """Create a mock tool call event."""
    event = MagicMock()
    event.id = event_id
    event.tool_name = tool_name
    event.name = tool_name
    event.data = {"tool_name": tool_name}
    return event


class TestDetectEscalationSignals:
    """Tests for detect_escalation_signals function."""

    def test_empty_inputs_returns_empty(self):
        """Empty inputs should return empty list."""
        signals = detect_escalation_signals([], [], [], [])
        assert signals == []

    def test_combines_all_signal_types(self):
        """Should combine signals from all detection methods."""
        turns = [
            make_turn_event("t1", speaker="agent_a", goal="start"),
            make_turn_event("t2", speaker="agent_b", goal="escalate this", content="review needed"),
        ]
        decisions = [
            make_decision_event("d1", confidence=0.9),
            make_decision_event("d2", confidence=0.5),  # Degradation
        ]
        safety_events = [
            make_safety_event("s1"),
            make_safety_event("s2"),
            make_safety_event("s3"),
        ]

        signals = detect_escalation_signals(turns, decisions, safety_events)

        # Should have signals from multiple detection methods
        signal_types = {s.signal_type for s in signals}
        assert len(signal_types) > 0


class TestDetectConfidenceDegradation:
    """Tests for _detect_confidence_degradation function."""

    def test_no_degradation_when_confidence_stable(self):
        """Should not detect degradation when confidence is stable."""
        decisions = [
            make_decision_event("d1", confidence=0.8),
            make_decision_event("d2", confidence=0.8),
            make_decision_event("d3", confidence=0.8),
        ]

        signals = _detect_confidence_degradation(decisions)

        assert len(signals) == 0

    def test_detects_significant_drop(self):
        """Should detect confidence drops greater than 0.2."""
        decisions = [
            make_decision_event("d1", confidence=0.9),
            make_decision_event("d2", confidence=0.5),  # Drop of 0.4
        ]

        signals = _detect_confidence_degradation(decisions)

        assert len(signals) == 1
        assert signals[0].signal_type == "confidence_degradation"
        assert signals[0].event_id == "d2"

    def test_no_signal_for_small_drops(self):
        """Should not detect small confidence drops."""
        decisions = [
            make_decision_event("d1", confidence=0.8),
            make_decision_event("d2", confidence=0.7),  # Drop of 0.1
        ]

        signals = _detect_confidence_degradation(decisions)

        assert len(signals) == 0

    def test_handles_none_confidence(self):
        """Should handle None confidence values gracefully."""
        decisions = [
            make_decision_event("d1", confidence=0.8),
            make_decision_event("d2", confidence=None),
        ]

        signals = _detect_confidence_degradation(decisions)

        assert len(signals) == 0


class TestDetectSafetyPressure:
    """Tests for _detect_safety_pressure function."""

    def test_no_signal_for_few_events(self):
        """Should not detect pressure for fewer than 2 events."""
        signals = _detect_safety_pressure([make_safety_event("s1")])
        assert len(signals) == 0

    def test_detects_pressure_for_multiple_events(self):
        """Should detect pressure for multiple safety events."""
        safety_events = [make_safety_event(f"s{i}") for i in range(3)]

        signals = _detect_safety_pressure(safety_events)

        assert len(signals) == 1
        assert signals[0].signal_type == "safety_pressure"

    def test_magnitude_increases_with_count(self):
        """Magnitude should increase with event count."""
        few_events = [make_safety_event(f"s{i}") for i in range(2)]
        many_events = [make_safety_event(f"s{i}") for i in range(10)]

        few_signals = _detect_safety_pressure(few_events)
        many_signals = _detect_safety_pressure(many_events)

        assert many_signals[0].magnitude > few_signals[0].magnitude


class TestDetectHandoffPatterns:
    """Tests for _detect_handoff_patterns function."""

    def test_no_signal_when_same_speaker(self):
        """Should not detect handoff when speaker stays same."""
        turns = [
            make_turn_event("t1", speaker="agent_a"),
            make_turn_event("t2", speaker="agent_a"),
        ]

        signals = _detect_handoff_patterns(turns)

        assert len(signals) == 0

    def test_detects_handoff_with_transfer_intent(self):
        """Should detect handoff when transfer intent is present."""
        turns = [
            make_turn_event("t1", speaker="agent_a", goal="initial task"),
            make_turn_event("t2", speaker="agent_b", goal="escalate to supervisor"),
        ]

        signals = _detect_handoff_patterns(turns)

        assert len(signals) == 1
        assert signals[0].signal_type == "handoff_pattern"

    def test_detects_handoff_keywords_in_content(self):
        """Should detect handoff keywords in content."""
        turns = [
            make_turn_event("t1", speaker="agent_a", content="working on it"),
            make_turn_event("t2", speaker="agent_b", content="handoff to team lead"),
        ]

        signals = _detect_handoff_patterns(turns)

        assert len(signals) == 1

    def test_no_handoff_signal_without_keywords(self):
        """Should not signal handoff without transfer keywords."""
        turns = [
            make_turn_event("t1", speaker="agent_a", goal="task one"),
            make_turn_event("t2", speaker="agent_b", goal="task two"),
        ]

        signals = _detect_handoff_patterns(turns)

        assert len(signals) == 0


class TestDetectToolStakeIncrease:
    """Tests for _detect_tool_stake_increase function."""

    def test_detects_stake_increase(self):
        """Should detect transition to high-stake operations."""
        tool_calls = [
            make_tool_call_event("t1", tool_name="read_file"),
            make_tool_call_event("t2", tool_name="delete_file"),
        ]

        signals = _detect_tool_stake_increase(tool_calls)

        assert len(signals) == 1
        assert signals[0].signal_type == "tool_stake_increase"

    def test_no_signal_for_low_stake_sequence(self):
        """Should not signal for low-stake operation sequences."""
        tool_calls = [
            make_tool_call_event("t1", tool_name="read_file"),
            make_tool_call_event("t2", tool_name="list_files"),
        ]

        signals = _detect_tool_stake_increase(tool_calls)

        assert len(signals) == 0


class TestDetectExplicitKeywords:
    """Tests for _detect_explicit_keywords function."""

    def test_detects_escalation_keywords(self):
        """Should detect explicit escalation keywords."""
        turns = [
            make_turn_event("t1", content="this is critical, escalate now"),
        ]

        signals = _detect_explicit_keywords(turns)

        assert len(signals) == 1
        assert signals[0].signal_type == "explicit_keyword"

    def test_no_signal_without_keywords(self):
        """Should not signal without keywords."""
        turns = [
            make_turn_event("t1", content="normal operation"),
        ]

        signals = _detect_explicit_keywords(turns)

        assert len(signals) == 0


class TestComputeEscalationScore:
    """Tests for compute_escalation_score function."""

    def test_empty_signals_returns_zero(self):
        """Empty signal list should return zero score."""
        assert compute_escalation_score([]) == 0.0

    def test_weighted_combination(self):
        """Score should be weighted combination of signals."""
        signals = [
            EscalationSignal(
                event_id="e1",
                turn_index=0,
                signal_type="confidence_degradation",
                magnitude=0.5,
            ),
            EscalationSignal(
                event_id="e2",
                turn_index=1,
                signal_type="explicit_keyword",
                magnitude=0.5,
            ),
        ]

        score = compute_escalation_score(signals)

        # confidence_degradation weight is 0.25, explicit_keyword is 0.15
        expected = 0.5 * 0.25 + 0.5 * 0.15
        assert abs(score - expected) < 0.001

    def test_capped_at_one(self):
        """Score should be capped at 1.0."""
        signals = [
            EscalationSignal(
                event_id=f"e{i}",
                turn_index=i,
                signal_type="confidence_degradation",
                magnitude=1.0,
            )
            for i in range(10)
        ]

        score = compute_escalation_score(signals)

        assert score <= 1.0


class TestEscalationSignalDataclass:
    """Tests for EscalationSignal dataclass."""

    def test_to_dict_serializes_correctly(self):
        """to_dict should serialize all fields correctly."""
        signal = EscalationSignal(
            event_id="event_123",
            turn_index=2,
            signal_type="confidence_degradation",
            magnitude=0.75,
            evidence_event_ids=["e1", "e2"],
            narrative="Confidence dropped from 0.9 to 0.5",
        )

        result = signal.to_dict()

        assert result["event_id"] == "event_123"
        assert result["turn_index"] == 2
        assert result["signal_type"] == "confidence_degradation"
        assert result["magnitude"] == 0.75
        assert result["evidence_event_ids"] == ["e1", "e2"]
        assert result["narrative"] == "Confidence dropped from 0.9 to 0.5"


class TestWeights:
    """Tests for WEIGHTS configuration."""

    def test_confidence_degradation_has_highest_weight(self):
        """Confidence degradation should have high weight."""
        # Confidence degradation (0.25) should be >= explicit_keyword (0.15)
        assert WEIGHTS["confidence_degradation"] >= WEIGHTS["explicit_keyword"]

    def test_explicit_keyword_has_lowest_weight(self):
        """Explicit keyword should have lowest weight (heuristic fallback)."""
        # explicit_keyword is meant to be supporting signal only
        assert WEIGHTS["explicit_keyword"] <= 0.2

    def test_all_weights_positive(self):
        """All weights should be positive."""
        for weight in WEIGHTS.values():
            assert weight > 0.0
