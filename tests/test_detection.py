"""Tests for collector/detection.py oscillation detection module."""

from __future__ import annotations

from datetime import datetime, timezone

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.detection import (
    _build_oscillation_sequence,
    _create_oscillation_alert,
    _detect_pattern_repeats,
    _extract_event_key,
    detect_oscillation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_event(
    event_type: EventType = EventType.TOOL_CALL,
    name: str = "",
    data: dict | None = None,
    event_id: str | None = None,
) -> TraceEvent:
    return TraceEvent(
        id=event_id or f"evt-{name or str(event_type)}",
        session_id="sess-1",
        event_type=event_type,
        timestamp=datetime.now(timezone.utc),
        name=name,
        data=data or {},
    )


def make_tool_call(tool_name: str, event_id: str | None = None) -> TraceEvent:
    return make_event(
        event_type=EventType.TOOL_CALL,
        name="",
        data={"tool_name": tool_name},
        event_id=event_id or f"evt-{tool_name}",
    )


def make_decision(chosen_action: str, event_id: str | None = None) -> TraceEvent:
    return make_event(
        event_type=EventType.DECISION,
        name="",
        data={"chosen_action": chosen_action},
        event_id=event_id or f"evt-{chosen_action}",
    )


def make_agent_turn(name: str = "turn", event_id: str | None = None) -> TraceEvent:
    return make_event(
        event_type=EventType.AGENT_TURN,
        name=name,
        event_id=event_id or f"evt-{name}",
    )


# ---------------------------------------------------------------------------
# _extract_event_key
# ---------------------------------------------------------------------------

class TestExtractEventKey:
    def test_returns_name_for_generic_event(self):
        event = make_event(EventType.AGENT_TURN, name="my-turn")
        assert _extract_event_key(event) == "my-turn"

    def test_returns_event_type_string_when_no_name(self):
        event = make_event(EventType.AGENT_TURN, name="")
        assert _extract_event_key(event) == str(EventType.AGENT_TURN)

    def test_tool_call_uses_tool_name(self):
        event = make_tool_call("search_web")
        assert _extract_event_key(event) == "search_web"

    def test_tool_call_falls_back_to_name_when_no_tool_name(self):
        event = make_event(EventType.TOOL_CALL, name="fallback-name", data={})
        assert _extract_event_key(event) == "fallback-name"

    def test_decision_uses_chosen_action(self):
        event = make_decision("retry")
        assert _extract_event_key(event) == "retry"

    def test_decision_falls_back_to_name_when_no_chosen_action(self):
        event = make_event(EventType.DECISION, name="decide-name", data={})
        assert _extract_event_key(event) == "decide-name"


# ---------------------------------------------------------------------------
# _build_oscillation_sequence
# ---------------------------------------------------------------------------

class TestBuildOscillationSequence:
    def test_filters_irrelevant_event_types(self):
        events = [
            make_event(EventType.ERROR, name="err"),
            make_event(EventType.LLM_RESPONSE, name="llm"),
            make_tool_call("search"),
        ]
        seq, emap = _build_oscillation_sequence(events)
        assert len(seq) == 1
        assert seq[0][1] == "search"

    def test_includes_tool_call_decision_agent_turn(self):
        events = [
            make_tool_call("tool_a"),
            make_decision("action_b"),
            make_agent_turn("turn_c"),
        ]
        seq, emap = _build_oscillation_sequence(events)
        assert len(seq) == 3
        assert len(emap) == 3

    def test_returns_empty_for_no_relevant_events(self):
        events = [
            make_event(EventType.ERROR),
            make_event(EventType.LLM_RESPONSE),
        ]
        seq, emap = _build_oscillation_sequence(events)
        assert seq == []
        assert emap == []

    def test_empty_event_list(self):
        seq, emap = _build_oscillation_sequence([])
        assert seq == []
        assert emap == []


# ---------------------------------------------------------------------------
# _detect_pattern_repeats
# ---------------------------------------------------------------------------

class TestDetectPatternRepeats:
    def test_returns_none_for_sequence_too_short(self):
        seq = [("tool_call", "A"), ("tool_call", "B")]  # len 2 < pattern_len*2=4
        assert _detect_pattern_repeats(seq, 2) is None

    def test_detects_simple_ab_ab_pattern(self):
        seq = [
            ("tool_call", "A"),
            ("tool_call", "B"),
            ("tool_call", "A"),
            ("tool_call", "B"),
        ]
        result = _detect_pattern_repeats(seq, 2)
        assert result is not None
        repeats, matched = result
        assert repeats == 2
        assert matched == [0, 1, 2, 3]

    def test_detects_three_repeats(self):
        seq = [
            ("tool_call", "A"),
            ("tool_call", "B"),
            ("tool_call", "A"),
            ("tool_call", "B"),
            ("tool_call", "A"),
            ("tool_call", "B"),
        ]
        result = _detect_pattern_repeats(seq, 2)
        assert result is not None
        repeats, _ = result
        assert repeats == 3

    def test_no_repeat_for_non_oscillating_sequence(self):
        seq = [
            ("tool_call", "A"),
            ("tool_call", "B"),
            ("tool_call", "C"),
            ("tool_call", "D"),
        ]
        result = _detect_pattern_repeats(seq, 2)
        assert result is None

    def test_returns_none_when_only_one_occurrence(self):
        seq = [
            ("tool_call", "A"),
            ("tool_call", "B"),
            ("tool_call", "C"),
            ("tool_call", "D"),
        ]
        assert _detect_pattern_repeats(seq, 4) is None  # exactly one pattern, need at least 2


# ---------------------------------------------------------------------------
# _create_oscillation_alert
# ---------------------------------------------------------------------------

class TestCreateOscillationAlert:
    def test_creates_correct_pattern_string(self):
        pattern = [("tool_call", "search"), ("tool_call", "scrape")]
        events = [make_tool_call("search", "e1"), make_tool_call("scrape", "e2")]
        alert = _create_oscillation_alert(pattern, 2, [0, 1], events)
        assert alert.pattern == "search->scrape"

    def test_severity_scales_with_repeats(self):
        pattern = [("tool_call", "A"), ("tool_call", "B")]
        events = [make_tool_call("A", "e1"), make_tool_call("B", "e2")]
        alert2 = _create_oscillation_alert(pattern, 2, [0, 1], events)
        alert3 = _create_oscillation_alert(pattern, 3, [0, 1], events)
        assert alert3.severity > alert2.severity

    def test_severity_capped_at_one(self):
        pattern = [("tool_call", "A")]
        events = [make_tool_call("A", "e1")]
        alert = _create_oscillation_alert(pattern, 100, [0], events)
        assert alert.severity <= 1.0

    def test_event_ids_populated(self):
        pattern = [("tool_call", "A"), ("tool_call", "B")]
        events = [make_tool_call("A", "id-a"), make_tool_call("B", "id-b")]
        alert = _create_oscillation_alert(pattern, 2, [0, 1], events)
        assert "id-a" in alert.event_ids
        assert "id-b" in alert.event_ids


# ---------------------------------------------------------------------------
# detect_oscillation (integration)
# ---------------------------------------------------------------------------

class TestDetectOscillation:
    def test_returns_none_for_fewer_than_four_events(self):
        events = [make_tool_call("A"), make_tool_call("B"), make_tool_call("A")]
        assert detect_oscillation(events) is None

    def test_returns_none_for_empty_events(self):
        assert detect_oscillation([]) is None

    def test_returns_none_for_single_event(self):
        assert detect_oscillation([make_tool_call("A")]) is None

    def test_detects_tool_call_oscillation(self):
        events = [
            make_tool_call("search", "e1"),
            make_tool_call("scrape", "e2"),
            make_tool_call("search", "e3"),
            make_tool_call("scrape", "e4"),
        ]
        alert = detect_oscillation(events)
        assert alert is not None
        assert "search" in alert.pattern
        assert "scrape" in alert.pattern
        assert alert.repeat_count >= 2

    def test_detects_decision_oscillation(self):
        events = [
            make_decision("retry", "e1"),
            make_decision("abort", "e2"),
            make_decision("retry", "e3"),
            make_decision("abort", "e4"),
        ]
        alert = detect_oscillation(events)
        assert alert is not None
        assert alert.repeat_count >= 2

    def test_no_oscillation_for_varied_sequence(self):
        events = [
            make_tool_call("search"),
            make_tool_call("read"),
            make_tool_call("write"),
            make_tool_call("email"),
            make_tool_call("post"),
        ]
        alert = detect_oscillation(events)
        assert alert is None

    def test_window_limits_events_considered(self):
        # window=4 takes exactly the last 4 events [A,B,A,B] — detectable
        prefix = [make_tool_call(f"unique_{i}") for i in range(20)]
        oscillating = [
            make_tool_call("A", "osc-1"),
            make_tool_call("B", "osc-2"),
            make_tool_call("A", "osc-3"),
            make_tool_call("B", "osc-4"),
        ]
        alert = detect_oscillation(prefix + oscillating, window=4)
        assert alert is not None

    def test_window_excludes_early_oscillation(self):
        # Oscillation at the start is pushed out of a small window — not detected
        oscillating = [
            make_tool_call("A"),
            make_tool_call("B"),
            make_tool_call("A"),
            make_tool_call("B"),
        ]
        suffix = [make_tool_call(f"unique_{i}") for i in range(10)]
        # window=4 takes last 4 unique events — no oscillation present
        alert = detect_oscillation(oscillating + suffix, window=4)
        assert alert is None

    def test_returns_none_when_sequence_too_short_after_filtering(self):
        # Only LLM response events — none pass the filter → sequence length < 4
        events = [make_event(EventType.LLM_RESPONSE) for _ in range(10)]
        assert detect_oscillation(events) is None

    def test_alert_severity_is_non_negative(self):
        events = [
            make_tool_call("A"),
            make_tool_call("B"),
            make_tool_call("A"),
            make_tool_call("B"),
        ]
        alert = detect_oscillation(events)
        assert alert is not None
        assert alert.severity >= 0.0

    def test_alert_event_type_matches_pattern_first_element(self):
        events = [
            make_tool_call("X"),
            make_tool_call("Y"),
            make_tool_call("X"),
            make_tool_call("Y"),
        ]
        alert = detect_oscillation(events)
        assert alert is not None
        assert alert.event_type == str(EventType.TOOL_CALL)
