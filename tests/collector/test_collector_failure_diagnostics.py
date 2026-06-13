"""Unit tests for collector.failure_diagnostics module."""

from unittest.mock import MagicMock

import pytest

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.failure_diagnostics import FailureDiagnostics


def _make_event(event_type: EventType, event_id: str = "evt-1", **kwargs) -> TraceEvent:
    """Create a TraceEvent for testing."""
    return TraceEvent(
        id=event_id,
        session_id="sess-1",
        timestamp="2026-01-01T00:00:00Z",
        event_type=event_type,
        parent_id=None,
        name="test_event",
        data=kwargs,
        metadata={},
        importance=0.5,
        upstream_event_ids=[],
    )


@pytest.fixture
def mock_causal():
    """Create a mock CausalAnalyzer."""
    causal = MagicMock()
    causal._clip = lambda v, limit=120: str(v or "").strip()
    return causal


@pytest.fixture
def diagnostics(mock_causal):
    """Create a FailureDiagnostics instance with mocked causal analyzer."""
    return FailureDiagnostics(mock_causal)


@pytest.fixture
def mock_headline_fn():
    """Mock event headline function."""
    return lambda event: event.name or "event"


class TestFailureMode:
    """Tests for failure_mode method."""

    def test_behavior_alert_tool_loop(self, diagnostics):
        """BEHAVIOR_ALERT with alert_type='tool_loop' returns 'looping_behavior'."""
        event = _make_event(EventType.BEHAVIOR_ALERT, alert_type="tool_loop")
        result = diagnostics.failure_mode(event, None, {})
        assert result == "looping_behavior"

    def test_behavior_alert_other(self, diagnostics):
        """BEHAVIOR_ALERT without tool_loop returns 'behavior_anomaly'."""
        event = _make_event(EventType.BEHAVIOR_ALERT, alert_type="repetition")
        result = diagnostics.failure_mode(event, None, {})
        assert result == "behavior_anomaly"

    def test_refusal(self, diagnostics):
        """REFUSAL returns 'guardrail_block'."""
        event = _make_event(EventType.REFUSAL)
        result = diagnostics.failure_mode(event, None, {})
        assert result == "guardrail_block"

    def test_safety_check(self, diagnostics):
        """SAFETY_CHECK returns 'guardrail_block'."""
        event = _make_event(EventType.SAFETY_CHECK)
        result = diagnostics.failure_mode(event, None, {})
        assert result == "guardrail_block"

    def test_policy_violation(self, diagnostics):
        """POLICY_VIOLATION returns 'policy_mismatch'."""
        event = _make_event(EventType.POLICY_VIOLATION)
        result = diagnostics.failure_mode(event, None, {})
        assert result == "policy_mismatch"

    def test_tool_result_error_ungrounded_decision_low_confidence(self, diagnostics):
        """TOOL_RESULT with error + DECISION candidate with low confidence returns 'ungrounded_decision'."""
        failure_event = _make_event(EventType.TOOL_RESULT, error="API timeout")
        decision_event = _make_event(EventType.DECISION, event_id="decision-1", confidence=0.3)
        top_candidate = {"event_id": "decision-1"}
        id_lookup = {"decision-1": decision_event}
        result = diagnostics.failure_mode(failure_event, top_candidate, id_lookup)
        assert result == "ungrounded_decision"

    def test_tool_result_error_ungrounded_decision_no_evidence(self, diagnostics):
        """TOOL_RESULT with error + DECISION candidate without evidence returns 'ungrounded_decision'."""
        failure_event = _make_event(EventType.TOOL_RESULT, error="API timeout")
        decision_event = _make_event(EventType.DECISION, event_id="decision-1", confidence=0.8, evidence=[])
        top_candidate = {"event_id": "decision-1"}
        id_lookup = {"decision-1": decision_event}
        result = diagnostics.failure_mode(failure_event, top_candidate, id_lookup)
        assert result == "ungrounded_decision"

    def test_tool_result_error_with_candidate(self, diagnostics):
        """TOOL_RESULT with error + non-DECISION candidate returns 'tool_execution_failure'."""
        failure_event = _make_event(EventType.TOOL_RESULT, error="API timeout")
        tool_event = _make_event(EventType.TOOL_CALL, event_id="tool-1")
        top_candidate = {"event_id": "tool-1"}
        id_lookup = {"tool-1": tool_event}
        result = diagnostics.failure_mode(failure_event, top_candidate, id_lookup)
        assert result == "tool_execution_failure"

    def test_tool_result_error_no_candidate(self, diagnostics):
        """TOOL_RESULT with error but no candidate returns 'tool_execution_failure'."""
        failure_event = _make_event(EventType.TOOL_RESULT, error="API timeout")
        result = diagnostics.failure_mode(failure_event, None, {})
        assert result == "tool_execution_failure"

    def test_error(self, diagnostics):
        """ERROR returns 'upstream_runtime_error'."""
        event = _make_event(EventType.ERROR)
        result = diagnostics.failure_mode(event, None, {})
        assert result == "upstream_runtime_error"

    def test_default_diagnostic_review(self, diagnostics):
        """Unknown event type returns 'diagnostic_review'."""
        event = _make_event(EventType.AGENT_START)
        result = diagnostics.failure_mode(event, None, {})
        assert result == "diagnostic_review"


class TestFailureSymptom:
    """Tests for failure_symptom method."""

    def test_tool_result_error(self, diagnostics, mock_headline_fn):
        """TOOL_RESULT error includes tool name and clipped error message."""
        event = _make_event(EventType.TOOL_RESULT, error="API timeout after 30 seconds")
        result = diagnostics.failure_symptom(event, mock_headline_fn)
        assert result == 'Tool "test_event" failed with API timeout after 30 seconds'

    def test_error_event(self, diagnostics, mock_headline_fn):
        """ERROR event includes error type and message."""
        event = _make_event(EventType.ERROR, error_type="ValueError", error_message="invalid input")
        result = diagnostics.failure_symptom(event, mock_headline_fn)
        assert result == "ValueError raised with invalid input"

    def test_refusal(self, diagnostics, mock_headline_fn):
        """REFUSAL includes reason."""
        event = _make_event(EventType.REFUSAL, reason="unsafe content detected")
        result = diagnostics.failure_symptom(event, mock_headline_fn)
        assert result == "Request was refused: unsafe content detected"

    def test_policy_violation(self, diagnostics, mock_headline_fn):
        """POLICY_VIOLATION includes violation type."""
        event = _make_event(EventType.POLICY_VIOLATION, violation_type="rate_limit_exceeded")
        result = diagnostics.failure_symptom(event, mock_headline_fn)
        assert result == "Policy violation: rate_limit_exceeded"

    def test_behavior_alert(self, diagnostics, mock_headline_fn):
        """BEHAVIOR_ALERT includes signal or name."""
        event = _make_event(EventType.BEHAVIOR_ALERT, signal="repeated_tool_calls")
        result = diagnostics.failure_symptom(event, mock_headline_fn)
        assert result == "repeated_tool_calls"

    def test_safety_check(self, diagnostics, mock_headline_fn):
        """SAFETY_CHECK includes policy name and outcome."""
        event = _make_event(EventType.SAFETY_CHECK, policy_name="content_filter", outcome="fail")
        result = diagnostics.failure_symptom(event, mock_headline_fn)
        assert result == 'Safety check "content_filter" returned fail'

    def test_default_fallback(self, diagnostics, mock_headline_fn):
        """Unknown event type falls back to clipped headline."""
        event = _make_event(EventType.LLM_REQUEST)
        result = diagnostics.failure_symptom(event, mock_headline_fn)
        assert result == "test_event"


class TestIsFailureEvent:
    """Tests for is_failure_event method."""

    def test_error_is_failure(self, diagnostics):
        """ERROR events are failures."""
        event = _make_event(EventType.ERROR)
        assert diagnostics.is_failure_event(event) is True

    def test_refusal_is_failure(self, diagnostics):
        """REFUSAL events are failures."""
        event = _make_event(EventType.REFUSAL)
        assert diagnostics.is_failure_event(event) is True

    def test_policy_violation_is_failure(self, diagnostics):
        """POLICY_VIOLATION events are failures."""
        event = _make_event(EventType.POLICY_VIOLATION)
        assert diagnostics.is_failure_event(event) is True

    def test_behavior_alert_is_failure(self, diagnostics):
        """BEHAVIOR_ALERT events are failures."""
        event = _make_event(EventType.BEHAVIOR_ALERT)
        assert diagnostics.is_failure_event(event) is True

    def test_tool_result_with_error_is_failure(self, diagnostics):
        """TOOL_RESULT with error is a failure."""
        event = _make_event(EventType.TOOL_RESULT, error="timeout")
        assert diagnostics.is_failure_event(event) is True

    def test_tool_result_without_error_is_not_failure(self, diagnostics):
        """TOOL_RESULT without error is not a failure."""
        event = _make_event(EventType.TOOL_RESULT)
        assert diagnostics.is_failure_event(event) is False

    def test_safety_check_fail_is_failure(self, diagnostics):
        """SAFETY_CHECK with non-pass outcome is a failure."""
        event = _make_event(EventType.SAFETY_CHECK, outcome="fail")
        assert diagnostics.is_failure_event(event) is True

    def test_safety_check_warn_is_failure(self, diagnostics):
        """SAFETY_CHECK with warn outcome is a failure."""
        event = _make_event(EventType.SAFETY_CHECK, outcome="warn")
        assert diagnostics.is_failure_event(event) is True

    def test_safety_check_block_is_failure(self, diagnostics):
        """SAFETY_CHECK with block outcome is a failure."""
        event = _make_event(EventType.SAFETY_CHECK, outcome="block")
        assert diagnostics.is_failure_event(event) is True

    def test_safety_check_pass_is_not_failure(self, diagnostics):
        """SAFETY_CHECK with pass outcome is not a failure."""
        event = _make_event(EventType.SAFETY_CHECK, outcome="pass")
        assert diagnostics.is_failure_event(event) is False

    def test_decision_is_not_failure(self, diagnostics):
        """DECISION events are not failures."""
        event = _make_event(EventType.DECISION)
        assert diagnostics.is_failure_event(event) is False

    def test_llm_response_is_not_failure(self, diagnostics):
        """LLM_RESPONSE events are not failures."""
        event = _make_event(EventType.LLM_RESPONSE)
        assert diagnostics.is_failure_event(event) is False


class TestLikelyCauseText:
    """Tests for _likely_cause_text method."""

    def test_no_candidate(self, diagnostics, mock_headline_fn):
        """No candidate returns default message."""
        result = diagnostics._likely_cause_text(None, {}, mock_headline_fn)
        assert result == "No strong upstream cause was identified from the captured links."

    def test_unresolvable_candidate(self, diagnostics, mock_headline_fn):
        """Candidate with missing event returns unresolvable message."""
        candidate = {"event_id": "missing-1", "relation_label": "parent link"}
        result = diagnostics._likely_cause_text(candidate, {}, mock_headline_fn)
        assert result == "Most likely cause event could not be resolved."

    def test_decision_cause_with_confidence_and_evidence(self, diagnostics, mock_headline_fn):
        """DECISION cause includes confidence and evidence note."""
        cause_event = _make_event(EventType.DECISION, event_id="decision-1", confidence=0.85, evidence=["doc1"])
        candidate = {"event_id": "decision-1", "relation_label": "parent link"}
        id_lookup = {"decision-1": cause_event}
        result = diagnostics._likely_cause_text(candidate, id_lookup, mock_headline_fn)
        assert result == 'decision "test_event" appears upstream via parent link at confidence 0.85 with evidence.'

    def test_decision_cause_without_evidence(self, diagnostics, mock_headline_fn):
        """DECISION cause without evidence notes missing evidence."""
        cause_event = _make_event(EventType.DECISION, event_id="decision-1", confidence=0.75, evidence=[])
        candidate = {"event_id": "decision-1", "relation_label": "upstream dependency"}
        id_lookup = {"decision-1": cause_event}
        result = diagnostics._likely_cause_text(candidate, id_lookup, mock_headline_fn)
        assert result == 'decision "test_event" appears upstream via upstream dependency at confidence 0.75 without evidence.'

    def test_tool_result_error_cause(self, diagnostics, mock_headline_fn):
        """TOOL_RESULT with error notes it already failed upstream."""
        cause_event = _make_event(EventType.TOOL_RESULT, event_id="tool-1", error="timeout")
        candidate = {"event_id": "tool-1", "relation_label": "inferred tool invocation"}
        id_lookup = {"tool-1": cause_event}
        result = diagnostics._likely_cause_text(candidate, id_lookup, mock_headline_fn)
        assert result == 'tool result "test_event" already failed upstream via inferred tool invocation.'

    def test_generic_cause(self, diagnostics, mock_headline_fn):
        """Other cause types use generic suspect message."""
        cause_event = _make_event(EventType.LLM_REQUEST, event_id="llm-1")
        candidate = {"event_id": "llm-1", "relation_label": "related event"}
        id_lookup = {"llm-1": cause_event}
        result = diagnostics._likely_cause_text(candidate, id_lookup, mock_headline_fn)
        assert result == 'llm request "test_event" is the strongest upstream suspect via related event.'


class TestBuildFailureExplanations:
    """Tests for build_failure_explanations method."""

    def test_only_failure_events_get_explanations(self, diagnostics, mock_causal, mock_headline_fn):
        """Only failure events receive explanations."""
        failure_event = _make_event(EventType.ERROR, event_id="error-1", error_type="ValueError")
        normal_event = _make_event(EventType.DECISION, event_id="decision-1", confidence=0.9)
        events = [normal_event, failure_event]

        mock_causal.rank_failure_candidates.return_value = []

        explanations = diagnostics.build_failure_explanations(events, {}, mock_headline_fn)

        assert len(explanations) == 1
        assert explanations[0]["failure_event_id"] == "error-1"

    def test_explanation_ordering_by_confidence_then_id(self, diagnostics, mock_causal, mock_headline_fn):
        """Explanations sorted by -confidence, then failure_event_id."""
        error1 = _make_event(EventType.ERROR, event_id="error-1", error_type="ValueError")
        error2 = _make_event(EventType.ERROR, event_id="error-2", error_type="TypeError")
        events = [error2, error1]

        def mock_rank_fn(failure_event, **kwargs):
            if failure_event.id == "error-1":
                return [{"event_id": "cause-1", "score": 0.8, "relation_label": "parent", "supporting_event_ids": []}]
            return [{"event_id": "cause-2", "score": 0.9, "relation_label": "parent", "supporting_event_ids": []}]

        mock_causal.rank_failure_candidates.side_effect = mock_rank_fn

        explanations = diagnostics.build_failure_explanations(events, {}, mock_headline_fn)

        assert len(explanations) == 2
        # Higher confidence first
        assert explanations[0]["failure_event_id"] == "error-2"
        assert explanations[0]["confidence"] == 0.9
        assert explanations[1]["failure_event_id"] == "error-1"
        assert explanations[1]["confidence"] == 0.8

    def test_explanation_structure_with_candidate(self, diagnostics, mock_causal, mock_headline_fn):
        """Full explanation structure when candidate exists."""
        failure_event = _make_event(EventType.ERROR, event_id="error-1", error_type="ValueError", error_message="test error")
        events = [failure_event]

        candidate = {
            "event_id": "decision-1",
            "score": 0.85,
            "relation_label": "parent link",
            "supporting_event_ids": ["decision-1", "error-1"],
        }
        mock_causal.rank_failure_candidates.return_value = [candidate]

        explanations = diagnostics.build_failure_explanations(events, {}, mock_headline_fn)

        assert len(explanations) == 1
        exp = explanations[0]
        assert exp["failure_event_id"] == "error-1"
        assert exp["failure_event_type"] == "error"
        assert exp["failure_headline"] == "test_event"
        assert exp["failure_mode"] == "upstream_runtime_error"
        assert "ValueError raised with test error" in exp["symptom"]
        assert exp["likely_cause_event_id"] == "decision-1"
        assert exp["confidence"] == 0.85
        assert exp["supporting_event_ids"] == ["error-1", "decision-1"]
        assert exp["next_inspection_event_id"] == "decision-1"
        assert "strongest upstream suspect" in exp["narrative"]
        assert exp["candidates"] == [candidate]

    def test_explanation_structure_without_candidate(self, diagnostics, mock_causal, mock_headline_fn):
        """Explanation structure when no candidate exists."""
        failure_event = _make_event(EventType.REFUSAL, event_id="refusal-1", reason="unsafe")
        events = [failure_event]

        mock_causal.rank_failure_candidates.return_value = []

        explanations = diagnostics.build_failure_explanations(events, {}, mock_headline_fn)

        assert len(explanations) == 1
        exp = explanations[0]
        assert exp["failure_event_id"] == "refusal-1"
        assert exp["failure_mode"] == "guardrail_block"
        assert exp["likely_cause_event_id"] is None
        assert exp["confidence"] == 0.0
        assert exp["supporting_event_ids"] == ["refusal-1"]
        assert exp["next_inspection_event_id"] == "refusal-1"
        assert "Inspect the nearest checkpoint" in exp["narrative"]
        assert exp["candidates"] == []

    def test_supporting_event_ids_deduplication(self, diagnostics, mock_causal, mock_headline_fn):
        """Duplicate event IDs in supporting_event_ids are removed."""
        failure_event = _make_event(EventType.TOOL_RESULT, event_id="tool-1", error="timeout")
        events = [failure_event]

        candidate = {
            "event_id": "decision-1",
            "score": 0.7,
            "relation_label": "inferred decision",
            "supporting_event_ids": ["tool-1", "decision-1", "tool-1"],  # Duplicate tool-1
        }
        mock_causal.rank_failure_candidates.return_value = [candidate]

        explanations = diagnostics.build_failure_explanations(events, {}, mock_headline_fn)

        assert len(explanations) == 1
        # tool-1 (failure) comes first, then decision-1, duplicate removed
        assert explanations[0]["supporting_event_ids"] == ["tool-1", "decision-1"]

    def test_mixed_failure_and_non_failure_events(self, diagnostics, mock_causal, mock_headline_fn):
        """Only failure events from mixed list get explanations."""
        failure1 = _make_event(EventType.ERROR, event_id="error-1", error_type="ValueError")
        normal1 = _make_event(EventType.DECISION, event_id="decision-1", confidence=0.9)
        failure2 = _make_event(EventType.REFUSAL, event_id="refusal-1", reason="unsafe")
        normal2 = _make_event(EventType.LLM_RESPONSE, event_id="llm-1")
        events = [normal1, failure1, normal2, failure2]

        def mock_rank_fn(failure_event, **kwargs):
            return [{"event_id": "cause-1", "score": 0.7, "relation_label": "parent", "supporting_event_ids": []}]

        mock_causal.rank_failure_candidates.side_effect = mock_rank_fn

        explanations = diagnostics.build_failure_explanations(events, {}, mock_headline_fn)

        assert len(explanations) == 2
        failure_ids = {exp["failure_event_id"] for exp in explanations}
        assert failure_ids == {"error-1", "refusal-1"}

    def test_calls_rank_failure_candidates_correctly(self, diagnostics, mock_causal, mock_headline_fn):
        """Verifies rank_failure_candidates is called with correct parameters."""
        failure_event = _make_event(EventType.ERROR, event_id="error-1")
        events = [failure_event]

        mock_causal.rank_failure_candidates.return_value = []

        diagnostics.build_failure_explanations(events, {}, mock_headline_fn)

        assert mock_causal.rank_failure_candidates.called
        call_args = mock_causal.rank_failure_candidates.call_args
        # The first positional argument is the failure_event
        assert call_args[0][0] == failure_event
        assert call_args[1]["events"] == events
        assert "id_lookup" in call_args[1]
        assert "index_lookup" in call_args[1]
        assert call_args[1]["event_headline_fn"] == mock_headline_fn
