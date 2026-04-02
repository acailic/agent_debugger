"""Tests for collector/causal_analysis.py — Causal analysis and failure root cause ranking."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.causal_analysis import CausalAnalyzer, _event_value

# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------


def _event(
    event_id: str,
    event_type: EventType,
    session_id: str = "test-session",
    parent_id: str | None = None,
    upstream_event_ids: list[str] | None = None,
    **data,
) -> TraceEvent:
    """Create a test TraceEvent with common defaults."""
    return TraceEvent(
        id=event_id,
        session_id=session_id,
        parent_id=parent_id,
        name=f"test_{event_type}",
        event_type=event_type,
        timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        data=data,
        upstream_event_ids=upstream_event_ids or [],
    )


# ---------------------------------------------------------------------------
# Tests for _event_value helper
# ---------------------------------------------------------------------------


class TestEventValue:
    """Tests for _event_value helper function."""

    def test_returns_data_value_when_key_exists(self) -> None:
        """Should return value from event.data dict when key exists."""
        event = _event("ev1", EventType.TOOL_CALL, tool_name="search")
        assert _event_value(event, "tool_name") == "search"

    def test_returns_attribute_when_key_exists_as_attribute(self) -> None:
        """Should return value from event attribute when key exists."""
        event = _event("ev1", EventType.ERROR, error_type="TimeoutError")
        # error_type is in data, not an attribute
        assert _event_value(event, "error_type") == "TimeoutError"

    def test_returns_default_when_event_is_none(self) -> None:
        """Should return default value when event is None."""
        assert _event_value(None, "tool_name", "default") == "default"

    def test_returns_default_when_key_not_found(self) -> None:
        """Should return default value when key doesn't exist."""
        event = _event("ev1", EventType.TOOL_CALL)
        assert _event_value(event, "missing_key", "default") == "default"

    def test_returns_none_default_when_no_default_provided(self) -> None:
        """Should return None when key doesn't exist and no default provided."""
        event = _event("ev1", EventType.TOOL_CALL)
        assert _event_value(event, "missing_key") is None


# ---------------------------------------------------------------------------
# Tests for CausalAnalyzer initialization
# ---------------------------------------------------------------------------


class TestCausalAnalyzerInit:
    """Tests for CausalAnalyzer initialization and configuration."""

    def test_default_severity_weights(self) -> None:
        """Should initialize with default severity weights."""
        analyzer = CausalAnalyzer()
        assert analyzer.severity_weights is not None
        assert EventType.ERROR in analyzer.severity_weights
        assert analyzer.severity_weights[EventType.ERROR] == 1.0
        assert analyzer.severity_weights[EventType.DECISION] == 0.72

    def test_custom_severity_weights(self) -> None:
        """Should accept custom severity weights."""
        custom_weights = {
            EventType.ERROR: 0.9,
            EventType.DECISION: 0.5,
            EventType.TOOL_CALL: 0.3,
        }
        analyzer = CausalAnalyzer(severity_weights=custom_weights)
        assert analyzer.severity_weights == custom_weights

    def test_empty_severity_weights(self) -> None:
        """Should handle empty severity weights dict."""
        analyzer = CausalAnalyzer(severity_weights={})
        assert analyzer.severity_weights == {}


# ---------------------------------------------------------------------------
# Tests for relation_label method
# ---------------------------------------------------------------------------


class TestRelationLabel:
    """Tests for relation_label method."""

    def test_parent_relation_label(self) -> None:
        """Should return human-readable label for parent relation."""
        analyzer = CausalAnalyzer()
        assert analyzer.relation_label("parent") == "parent link"

    def test_upstream_relation_label(self) -> None:
        """Should return human-readable label for upstream relation."""
        analyzer = CausalAnalyzer()
        assert analyzer.relation_label("upstream") == "upstream dependency"

    def test_inferred_relation_label(self) -> None:
        """Should return human-readable label for inferred relations."""
        analyzer = CausalAnalyzer()
        assert analyzer.relation_label("inferred_tool_call") == "inferred tool invocation"
        assert analyzer.relation_label("inferred_decision") == "inferred decision"

    def test_unknown_relation_label(self) -> None:
        """Should convert unknown relation to readable format."""
        analyzer = CausalAnalyzer()
        assert analyzer.relation_label("custom_relation") == "custom relation"


# ---------------------------------------------------------------------------
# Tests for severity method
# ---------------------------------------------------------------------------


class TestSeverity:
    """Tests for severity calculation."""

    def test_error_event_severity(self) -> None:
        """ERROR events should have high severity."""
        analyzer = CausalAnalyzer()
        event = _event("ev1", EventType.ERROR)
        assert analyzer.severity(event) == 1.0

    def test_decision_event_with_high_confidence(self) -> None:
        """DECISION events with high confidence should have lower severity."""
        analyzer = CausalAnalyzer()
        event = _event("ev1", EventType.DECISION, confidence=0.9, evidence=["fact1"])
        severity = analyzer.severity(event)
        # Base severity 0.72 + low penalty for high confidence
        assert severity < 0.8

    def test_decision_event_with_low_confidence(self) -> None:
        """DECISION events with low confidence should have higher severity."""
        analyzer = CausalAnalyzer()
        event = _event("ev1", EventType.DECISION, confidence=0.2, evidence=[])
        severity = analyzer.severity(event)
        # Base severity 0.72 + high penalty for low confidence + penalty for no evidence
        assert severity > 0.8

    def test_tool_result_with_error(self) -> None:
        """TOOL_RESULT events with errors should have increased severity."""
        analyzer = CausalAnalyzer()
        event = _event("ev1", EventType.TOOL_RESULT, error="Connection failed")
        severity = analyzer.severity(event)
        # Base severity 0.58 + 0.28 error penalty = 0.86
        assert severity == 0.86

    def test_safety_check_with_failure(self) -> None:
        """SAFETY_CHECK events with non-pass outcome should have increased severity."""
        analyzer = CausalAnalyzer()
        event = _event("ev1", EventType.SAFETY_CHECK, outcome="fail")
        severity = analyzer.severity(event)
        # Base severity 0.8 + 0.15 failure penalty = 0.95
        assert severity == pytest.approx(0.95)

    def test_unknown_event_type_severity(self) -> None:
        """Unknown event types should get default low severity."""
        analyzer = CausalAnalyzer()
        event = _event("ev1", EventType.AGENT_START)
        # AGENT_START has base severity 0.2
        assert analyzer.severity(event) == 0.2


# ---------------------------------------------------------------------------
# Tests for _find_previous_event method
# ---------------------------------------------------------------------------


class TestFindPreviousEvent:
    """Tests for _find_previous_event helper."""

    def test_finds_event_within_window(self) -> None:
        """Should find event that matches predicate within max_distance."""
        analyzer = CausalAnalyzer()
        events = [
            _event("ev1", EventType.AGENT_START),
            _event("ev2", EventType.DECISION),
            _event("ev3", EventType.TOOL_CALL),
        ]
        result = analyzer._find_previous_event(
            events,
            start_index=2,
            predicate=lambda e: e.event_type == EventType.DECISION,
            max_distance=6,
        )
        assert result is not None
        assert result.id == "ev2"

    def test_returns_none_when_no_match(self) -> None:
        """Should return None when no event matches predicate."""
        analyzer = CausalAnalyzer()
        events = [
            _event("ev1", EventType.AGENT_START),
            _event("ev2", EventType.TOOL_CALL),
        ]
        result = analyzer._find_previous_event(
            events,
            start_index=1,
            predicate=lambda e: e.event_type == EventType.DECISION,
            max_distance=6,
        )
        assert result is None

    def test_respects_max_distance(self) -> None:
        """Should only search within max_distance events."""
        analyzer = CausalAnalyzer()
        events = [
            _event("ev1", EventType.DECISION),
            _event("ev2", EventType.TOOL_CALL),
            _event("ev3", EventType.TOOL_CALL),
            _event("ev4", EventType.TOOL_CALL),
        ]
        # DECISION at index 0 is too far from index 3 with max_distance=2
        result = analyzer._find_previous_event(
            events,
            start_index=3,
            predicate=lambda e: e.event_type == EventType.DECISION,
            max_distance=2,
        )
        assert result is None

    def test_finds_closest_match(self) -> None:
        """Should find the closest matching event (not necessarily the first)."""
        analyzer = CausalAnalyzer()
        events = [
            _event("ev1", EventType.DECISION),
            _event("ev2", EventType.TOOL_CALL),
            _event("ev3", EventType.DECISION),  # This is closer to index 4
            _event("ev4", EventType.TOOL_CALL),
            _event("ev5", EventType.TOOL_CALL),
        ]
        result = analyzer._find_previous_event(
            events,
            start_index=4,
            predicate=lambda e: e.event_type == EventType.DECISION,
            max_distance=6,
        )
        assert result is not None
        assert result.id == "ev3"  # Should find ev3, not ev1


# ---------------------------------------------------------------------------
# Tests for iter_direct_causes method (complexity 12)
# ---------------------------------------------------------------------------


class TestIterDirectCauses:
    """Tests for iter_direct_causes method."""

    def test_empty_events_list(self) -> None:
        """Should handle empty events list gracefully."""
        analyzer = CausalAnalyzer()
        event = _event("ev1", EventType.ERROR)
        causes = analyzer.iter_direct_causes(
            event,
            events=[],
            id_lookup={},
            index_lookup={},
        )
        assert causes == []

    def test_explicit_parent_relationship(self) -> None:
        """Should identify explicit parent relationships."""
        analyzer = CausalAnalyzer()
        parent = _event("parent", EventType.DECISION)
        child = _event("child", EventType.ERROR, parent_id="parent")

        events = [parent, child]
        id_lookup = {e.id: e for e in events}
        index_lookup = {e.id: i for i, e in enumerate(events)}

        causes = analyzer.iter_direct_causes(
            child,
            events=events,
            id_lookup=id_lookup,
            index_lookup=index_lookup,
        )
        assert len(causes) == 1
        assert causes[0][0].id == "parent"
        assert causes[0][1] == "parent"
        assert causes[0][2] is True  # explicit
        assert causes[0][3] == 0.86  # weight

    def test_explicit_upstream_relationships(self) -> None:
        """Should identify explicit upstream relationships."""
        analyzer = CausalAnalyzer()
        upstream = _event("upstream", EventType.TOOL_CALL)
        downstream = _event("downstream", EventType.DECISION, upstream_event_ids=["upstream"])

        events = [upstream, downstream]
        id_lookup = {e.id: e for e in events}
        index_lookup = {e.id: i for i, e in enumerate(events)}

        causes = analyzer.iter_direct_causes(
            downstream,
            events=events,
            id_lookup=id_lookup,
            index_lookup=index_lookup,
        )
        assert len(causes) == 1
        assert causes[0][0].id == "upstream"
        assert causes[0][1] == "upstream"
        assert causes[0][2] is True  # explicit
        assert causes[0][3] == 0.98  # weight

    def test_explicit_evidence_relationships(self) -> None:
        """Should identify explicit evidence relationships."""
        analyzer = CausalAnalyzer()
        evidence = _event("evidence", EventType.LLM_RESPONSE)
        decision = _event("decision", EventType.DECISION, evidence_event_ids=["evidence"])

        events = [evidence, decision]
        id_lookup = {e.id: e for e in events}
        index_lookup = {e.id: i for i, e in enumerate(events)}

        causes = analyzer.iter_direct_causes(
            decision,
            events=events,
            id_lookup=id_lookup,
            index_lookup=index_lookup,
        )
        assert len(causes) == 1
        assert causes[0][0].id == "evidence"
        assert causes[0][1] == "evidence"
        assert causes[0][2] is True  # explicit
        assert causes[0][3] == 0.94  # weight

    def test_inferred_tool_call_for_tool_result_error(self) -> None:
        """Should infer tool call as cause for tool result errors."""
        analyzer = CausalAnalyzer()
        tool_call = _event("tool1", EventType.TOOL_CALL, tool_name="search")
        tool_result = _event("result1", EventType.TOOL_RESULT, tool_name="search", error="Timeout")

        events = [tool_call, tool_result]
        id_lookup = {e.id: e for e in events}
        index_lookup = {e.id: i for i, e in enumerate(events)}

        causes = analyzer.iter_direct_causes(
            tool_result,
            events=events,
            id_lookup=id_lookup,
            index_lookup=index_lookup,
        )
        # Should find inferred_tool_call
        tool_call_causes = [c for c in causes if c[1] == "inferred_tool_call"]
        assert len(tool_call_causes) == 1
        assert tool_call_causes[0][0].id == "tool1"
        assert tool_call_causes[0][2] is False  # inferred

    def test_inferred_decision_for_error_events(self) -> None:
        """Should infer decision as cause for error events."""
        analyzer = CausalAnalyzer()
        decision = _event("dec1", EventType.DECISION)
        error = _event("err1", EventType.ERROR)

        events = [decision, error]
        id_lookup = {e.id: e for e in events}
        index_lookup = {e.id: i for i, e in enumerate(events)}

        causes = analyzer.iter_direct_causes(
            error,
            events=events,
            id_lookup=id_lookup,
            index_lookup=index_lookup,
        )
        # Should find inferred_decision
        decision_causes = [c for c in causes if c[1] == "inferred_decision"]
        assert len(decision_causes) == 1
        assert decision_causes[0][0].id == "dec1"
        assert decision_causes[0][2] is False  # inferred

    def test_circular_reference_handling(self) -> None:
        """Should handle circular references without infinite loops."""
        analyzer = CausalAnalyzer()
        event1 = _event("ev1", EventType.DECISION)
        event2 = _event("ev2", EventType.ERROR, parent_id="ev2")  # Self-reference

        events = [event1, event2]
        id_lookup = {e.id: e for e in events}
        index_lookup = {e.id: i for i, e in enumerate(events)}

        # Should not crash or include self-reference
        causes = analyzer.iter_direct_causes(
            event2,
            events=events,
            id_lookup=id_lookup,
            index_lookup=index_lookup,
        )
        # Should not include event2 as its own cause
        assert all(c[0].id != "ev2" for c in causes)

    def test_orphan_events(self) -> None:
        """Should handle events with no valid causes."""
        analyzer = CausalAnalyzer()
        orphan = _event("orphan", EventType.ERROR, parent_id="nonexistent")

        events = [orphan]
        id_lookup = {e.id: e for e in events}
        index_lookup = {e.id: i for i, e in enumerate(events)}

        causes = analyzer.iter_direct_causes(
            orphan,
            events=events,
            id_lookup=id_lookup,
            index_lookup=index_lookup,
        )
        # Should return empty list when no valid causes exist
        assert causes == []

    def test_single_event_chain(self) -> None:
        """Should handle single-event chains."""
        analyzer = CausalAnalyzer()
        single = _event("single", EventType.ERROR)

        events = [single]
        id_lookup = {e.id: e for e in events}
        index_lookup = {e.id: i for i, e in enumerate(events)}

        causes = analyzer.iter_direct_causes(
            single,
            events=events,
            id_lookup=id_lookup,
            index_lookup=index_lookup,
        )
        assert causes == []

    def test_duplicate_causes_deduplication(self) -> None:
        """Should deduplicate causes that appear via multiple paths."""
        analyzer = CausalAnalyzer()
        decision = _event("dec1", EventType.DECISION)
        error = _event(
            "err1",
            EventType.ERROR,
            parent_id="dec1",
            upstream_event_ids=["dec1"],  # Same as parent
        )

        events = [decision, error]
        id_lookup = {e.id: e for e in events}
        index_lookup = {e.id: i for i, e in enumerate(events)}

        causes = analyzer.iter_direct_causes(
            error,
            events=events,
            id_lookup=id_lookup,
            index_lookup=index_lookup,
        )
        # Should only include dec1 once, even though it's both parent and upstream
        dec1_causes = [c for c in causes if c[0].id == "dec1"]
        assert len(dec1_causes) == 1


# ---------------------------------------------------------------------------
# Tests for candidate_rationale method
# ---------------------------------------------------------------------------


class TestCandidateRationale:
    """Tests for candidate_rationale method."""

    def test_explicit_parent_rationale(self) -> None:
        """Should generate rationale for explicit parent relationship."""
        analyzer = CausalAnalyzer()
        event = _event("ev1", EventType.DECISION)
        rationale = analyzer.candidate_rationale(event, "parent", True)
        assert "Explicit parent link" in rationale

    def test_inferred_relation_rationale(self) -> None:
        """Should generate rationale for inferred relationship."""
        analyzer = CausalAnalyzer()
        event = _event("ev1", EventType.DECISION)
        rationale = analyzer.candidate_rationale(event, "inferred_decision", False)
        # The rationale includes "Inferred" prefix plus the relation label "inferred decision"
        assert "inferred decision" in rationale

    def test_decision_with_low_confidence_rationale(self) -> None:
        """Should include low confidence in rationale for decisions."""
        analyzer = CausalAnalyzer()
        event = _event("ev1", EventType.DECISION, confidence=0.3)
        rationale = analyzer.candidate_rationale(event, "inferred_decision", False)
        assert "low confidence 0.30" in rationale

    def test_decision_without_evidence_rationale(self) -> None:
        """Should include missing evidence in rationale for decisions."""
        analyzer = CausalAnalyzer()
        event = _event("ev1", EventType.DECISION, confidence=0.8, evidence=[])
        rationale = analyzer.candidate_rationale(event, "inferred_decision", False)
        assert "missing evidence" in rationale

    def test_error_event_rationale(self) -> None:
        """Should include error type in rationale for error events."""
        analyzer = CausalAnalyzer()
        event = _event("ev1", EventType.ERROR, error_type="ValueError")
        rationale = analyzer.candidate_rationale(event, "inferred_decision", False)
        assert "ValueError" in rationale

    def test_safety_check_rationale(self) -> None:
        """Should include outcome in rationale for safety checks."""
        analyzer = CausalAnalyzer()
        event = _event("ev1", EventType.SAFETY_CHECK, outcome="fail")
        rationale = analyzer.candidate_rationale(event, "inferred_decision", False)
        assert "outcome fail" in rationale


# ---------------------------------------------------------------------------
# Tests for rank_failure_candidates method
# ---------------------------------------------------------------------------


class TestRankFailureCandidates:
    """Tests for rank_failure_candidates BFS ranking."""

    def test_empty_events_returns_empty_candidates(self) -> None:
        """Should return empty list when no events exist."""
        analyzer = CausalAnalyzer()
        failure = _event("fail", EventType.ERROR)

        candidates = analyzer.rank_failure_candidates(
            failure,
            events=[],
            id_lookup={},
            index_lookup={},
            ranking_by_event_id={},
            event_headline_fn=lambda e: f"Event {e.id}",
        )
        assert candidates == []

    def test_no_causes_returns_empty_candidates(self) -> None:
        """Should return empty list when failure has no causes."""
        analyzer = CausalAnalyzer()
        failure = _event("fail", EventType.ERROR)

        events = [failure]
        id_lookup = {e.id: e for e in events}
        index_lookup = {e.id: i for i, e in enumerate(events)}

        candidates = analyzer.rank_failure_candidates(
            failure,
            events=events,
            id_lookup=id_lookup,
            index_lookup=index_lookup,
            ranking_by_event_id={},
            event_headline_fn=lambda e: f"Event {e.id}",
        )
        assert candidates == []

    def test_returns_top_three_candidates(self) -> None:
        """Should return at most 3 candidates sorted by score."""
        analyzer = CausalAnalyzer()
        causes = [_event(f"cause{i}", EventType.DECISION) for i in range(5)]
        failure = _event("fail", EventType.ERROR, parent_id="cause0")

        events = causes + [failure]
        id_lookup = {e.id: e for e in events}
        index_lookup = {e.id: i for i, e in enumerate(events)}

        candidates = analyzer.rank_failure_candidates(
            failure,
            events=events,
            id_lookup=id_lookup,
            index_lookup=index_lookup,
            ranking_by_event_id={},
            event_headline_fn=lambda e: f"Event {e.id}",
        )
        # Should return at most 3 candidates
        assert len(candidates) <= 3

    def test_candidates_sorted_by_score(self) -> None:
        """Should return candidates sorted by score in descending order."""
        analyzer = CausalAnalyzer()
        cause1 = _event("cause1", EventType.DECISION)
        cause2 = _event("cause2", EventType.ERROR)
        failure = _event("fail", EventType.ERROR, parent_id="cause1")

        events = [cause1, cause2, failure]
        id_lookup = {e.id: e for e in events}
        index_lookup = {e.id: i for i, e in enumerate(events)}

        candidates = analyzer.rank_failure_candidates(
            failure,
            events=events,
            id_lookup=id_lookup,
            index_lookup=index_lookup,
            ranking_by_event_id={},
            event_headline_fn=lambda e: f"Event {e.id}",
        )
        if len(candidates) > 1:
            # Should be sorted by score (highest first)
            scores = [float(c["score"]) for c in candidates]
            assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Tests for malformed data handling
# ---------------------------------------------------------------------------


class TestMalformedDataHandling:
    """Tests for handling malformed event data."""

    def test_missing_optional_fields(self) -> None:
        """Should handle events with missing optional fields."""
        analyzer = CausalAnalyzer()
        event = _event("ev1", EventType.TOOL_CALL)  # No tool_name

        # Should not crash when accessing tool_name
        severity = analyzer.severity(event)
        assert isinstance(severity, float)

    def test_none_values_in_data(self) -> None:
        """Should handle None values in event data."""
        analyzer = CausalAnalyzer()
        event = _event("ev1", EventType.DECISION, confidence=None, evidence=None)

        # Should not crash
        severity = analyzer.severity(event)
        assert isinstance(severity, float)

    def test_invalid_event_types_in_severity_weights(self) -> None:
        """Should handle event types not in severity weights."""
        # All event types should be in default weights, but test with custom empty weights
        analyzer_empty = CausalAnalyzer(severity_weights={})
        event = _event("ev1", EventType.AGENT_TURN)

        severity = analyzer_empty.severity(event)
        # Should return default low severity
        assert severity == 0.3  # Default from code

    def test_nonexistent_parent_id(self) -> None:
        """Should handle nonexistent parent IDs gracefully."""
        analyzer = CausalAnalyzer()
        event = _event("ev1", EventType.ERROR, parent_id="nonexistent")

        events = [event]
        id_lookup = {e.id: e for e in events}
        index_lookup = {e.id: i for i, e in enumerate(events)}

        causes = analyzer.iter_direct_causes(
            event,
            events=events,
            id_lookup=id_lookup,
            index_lookup=index_lookup,
        )
        # Should not crash, just not include the nonexistent parent
        assert causes == []
