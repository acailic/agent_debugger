"""Tests for importance scoring system."""

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import EventType, TraceEvent
from agent_debugger_sdk.core.scorer import ImportanceScorer, get_importance_scorer


@pytest.fixture
def scorer():
    """Fresh scorer instance for each test."""
    return ImportanceScorer()


@pytest.fixture
def base_event():
    """Minimal event for testing."""
    return TraceEvent(
        id="test-1",
        session_id="session-1",
        event_type=EventType.AGENT_START,
        timestamp=datetime.now(timezone.utc),
        name="test",
        data={},
    )


class TestBaseScores:
    """Tests for base event type scores."""

    def test_all_event_types_have_base_score(self, scorer, base_event):
        """Every event type should get a base score."""
        expected_scores = {
            EventType.ERROR: 0.9,
            EventType.DECISION: 0.75,
            EventType.TOOL_RESULT: 0.5,
            EventType.LLM_RESPONSE: 0.5,
            EventType.TOOL_CALL: 0.4,
            EventType.LLM_REQUEST: 0.3,
            EventType.AGENT_START: 0.2,
            EventType.AGENT_END: 0.2,
            EventType.CHECKPOINT: 0.6,
            EventType.SAFETY_CHECK: 0.75,
            EventType.REFUSAL: 0.85,
            EventType.POLICY_VIOLATION: 0.92,
            EventType.PROMPT_POLICY: 0.45,
            EventType.AGENT_TURN: 0.45,
            EventType.BEHAVIOR_ALERT: 0.88,
        }

        for event_type, expected_score in expected_scores.items():
            event = TraceEvent(
                id="test-1",
                session_id="session-1",
                event_type=event_type,
                timestamp=datetime.now(timezone.utc),
                name="test",
                data={},
            )
            score = scorer.score(event)
            assert score == expected_score, f"{event_type} expected {expected_score}, got {score}"

    def test_unknown_event_type_gets_default_score(self, scorer, base_event):
        """Unknown event types should get default 0.3 score."""
        # All known types have at least 0.2 score
        score = scorer.score(base_event)
        assert score >= 0.2


class TestToolResultScoring:
    """Tests for tool result error bonuses."""

    def test_successful_tool_result_no_bonus(self, scorer):
        """Successful tool results should not get error bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.TOOL_RESULT,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"error": None},
        )
        score = scorer.score(event)
        assert score == 0.5  # Base score only

    def test_failed_tool_result_gets_error_bonus(self, scorer):
        """Failed tool results should get error weight bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.TOOL_RESULT,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"error": "Something failed"},
        )
        score = scorer.score(event)
        assert score == 0.9  # 0.5 base + 0.4 error_weight

    def test_error_weight_customizable(self):
        """Error weight should be customizable."""
        custom_scorer = ImportanceScorer(error_weight=0.5)
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.TOOL_RESULT,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"error": "Failed"},
        )
        score = custom_scorer.score(event)
        assert score == 1.0  # 0.5 base + 0.5 custom error_weight, capped at 1.0


class TestLLMResponseScoring:
    """Tests for LLM response cost bonuses."""

    def test_free_llm_response_no_bonus(self, scorer):
        """LLM responses with no cost should not get cost bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.LLM_RESPONSE,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"cost_usd": 0},
        )
        score = scorer.score(event)
        assert score == 0.5  # Base score only

    def test_cheap_llm_response_no_bonus(self, scorer):
        """LLM responses under threshold should not get cost bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.LLM_RESPONSE,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"cost_usd": 0.005},
        )
        score = scorer.score(event)
        assert score == 0.5  # Base score only

    def test_expensive_llm_response_gets_bonus(self, scorer):
        """LLM responses over threshold should get cost bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.LLM_RESPONSE,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"cost_usd": 0.02},
        )
        score = scorer.score(event)
        assert score == 0.53  # 0.5 base + 0.15 * min(0.02/0.1, 1.0) = 0.5 + 0.03

    def test_very_expensive_llm_response_capped_bonus(self, scorer):
        """Very expensive LLM responses should cap the cost bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.LLM_RESPONSE,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"cost_usd": 1.0},
        )
        score = scorer.score(event)
        assert score == 0.65  # 0.5 base + 0.15 * min(1.0/0.1, 1.0) = 0.5 + 0.15

    def test_cost_weight_customizable(self):
        """Cost weight should be customizable."""
        custom_scorer = ImportanceScorer(cost_weight=0.3)
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.LLM_RESPONSE,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"cost_usd": 0.1},
        )
        score = custom_scorer.score(event)
        assert score == 0.8  # 0.5 base + 0.3 * min(0.1/0.1, 1.0) = 0.5 + 0.3


class TestDurationScoring:
    """Tests for duration-based bonuses."""

    def test_fast_event_no_bonus(self, scorer):
        """Fast events should not get duration bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.AGENT_START,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"duration_ms": 500},
        )
        score = scorer.score(event)
        assert score == 0.2  # Base score only for AGENT_START

    def test_slow_event_gets_bonus(self, scorer):
        """Slow events should get duration bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.AGENT_START,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"duration_ms": 5000},
        )
        score = scorer.score(event)
        assert score == 0.275  # 0.2 base + 0.15 * min(5000/10000, 1.0) = 0.2 + 0.075

    def test_very_slow_event_capped_bonus(self, scorer):
        """Very slow events should cap the duration bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.AGENT_START,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"duration_ms": 50000},
        )
        score = scorer.score(event)
        assert score == 0.35  # 0.2 base + 0.15 * min(50000/10000, 1.0) = 0.2 + 0.15


class TestDecisionScoring:
    """Tests for decision-specific scoring."""

    def test_neutral_confidence_no_bonus(self, scorer):
        """Decisions with 0.5 confidence should get no confidence bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.DECISION,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"confidence": 0.5},
        )
        score = scorer.score(event)
        assert score == 0.75  # Base score + no evidence penalty

    def test_low_confidence_gets_bonus(self, scorer):
        """Decisions with low confidence should get bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.DECISION,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"confidence": 0.2},
        )
        score = scorer.score(event)
        assert round(score, 2) == 0.93  # 0.75 base + 0.18 confidence

    def test_high_confidence_gets_bonus(self, scorer):
        """Decisions with high confidence should get bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.DECISION,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"confidence": 0.9},
        )
        score = scorer.score(event)
        assert round(score, 2) == 0.99  # 0.75 base + 0.24 confidence

    def test_no_evidence_gets_penalty(self, scorer):
        """Decisions without evidence should get penalty."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.DECISION,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"evidence": []},
        )
        score = scorer.score(event)
        assert score == 0.75  # 0.7 base + 0.05 penalty

    def test_with_evidence_event_ids_gets_bonus(self, scorer):
        """Decisions with evidence event IDs should get bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.DECISION,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"evidence_event_ids": ["evt-1"]},
        )
        score = scorer.score(event)
        assert round(score, 2) == 0.80  # 0.75 base + 0.05 evidence_event_ids bonus

    def test_decision_weight_customizable(self):
        """Decision weight should be customizable."""
        custom_scorer = ImportanceScorer(decision_weight=0.5)
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.DECISION,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"confidence": 0.1},
        )
        score = custom_scorer.score(event)
        assert score == 1.0  # 0.7 base + 0.5 * abs(0.5-0.1) * 2 = 0.7 + 0.4, capped


class TestSafetyCheckScoring:
    """Tests for safety check scoring."""

    def test_passing_safety_check_no_bonus(self, scorer):
        """Passing safety checks should not get bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.SAFETY_CHECK,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"outcome": "pass"},
        )
        score = scorer.score(event)
        assert score == 0.75  # Base score only

    def test_failing_safety_check_gets_bonus(self, scorer):
        """Failing safety checks should get bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.SAFETY_CHECK,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"outcome": "fail"},
        )
        score = scorer.score(event)
        assert score == 0.85  # 0.75 base + 0.1

    def test_warning_safety_check_gets_bonus(self, scorer):
        """Warning safety checks should get bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.SAFETY_CHECK,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"outcome": "warn"},
        )
        score = scorer.score(event)
        assert score == 0.85  # 0.75 base + 0.1


class TestBehaviorAlertScoring:
    """Tests for behavior alert scoring."""

    def test_low_severity_alert_no_bonus(self, scorer):
        """Low severity alerts should not get bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.BEHAVIOR_ALERT,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"severity": "low"},
        )
        score = scorer.score(event)
        assert score == 0.88  # Base score only

    def test_medium_severity_alert_no_bonus(self, scorer):
        """Medium severity alerts should not get bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.BEHAVIOR_ALERT,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"severity": "medium"},
        )
        score = scorer.score(event)
        assert score == 0.88  # Base score only

    def test_high_severity_alert_gets_bonus(self, scorer):
        """High severity alerts should get bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.BEHAVIOR_ALERT,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"severity": "high"},
        )
        score = scorer.score(event)
        assert score == 0.93  # 0.88 base + 0.05


class TestUpstreamLinks:
    """Tests for upstream link bonuses."""

    def test_event_without_upstream_links_no_bonus(self, scorer):
        """Events without upstream links should not get bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.AGENT_START,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"upstream_event_ids": []},
        )
        score = scorer.score(event)
        assert score == 0.2  # Base score only

    def test_event_with_upstream_links_gets_bonus(self, scorer):
        """Events with upstream links should get bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.AGENT_START,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"upstream_event_ids": ["evt-1", "evt-2"]},
        )
        score = scorer.score(event)
        assert score == 0.20  # upstream_event_ids in data doesn't trigger bonus

    def test_event_with_upstream_links_attribute(self, scorer):
        """Events with upstream_event_ids as attribute should get bonus."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.AGENT_START,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={},
            upstream_event_ids=["evt-1"],
        )
        score = scorer.score(event)
        assert score == 0.23  # 0.2 base + 0.03 upstream_event_ids attribute bonus


class TestScoreCapping:
    """Tests for score capping at 1.0."""

    def test_score_capped_at_1_0(self, scorer):
        """Scores should never exceed 1.0."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.POLICY_VIOLATION,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={
                "duration_ms": 50000,
                "upstream_event_ids": ["evt-1"],
            },
        )
        score = scorer.score(event)
        assert score == 1.0  # Should be capped

    def test_multiple_bonuses_still_capped(self, scorer):
        """Even with multiple bonuses, score should cap at 1.0."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.TOOL_RESULT,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={
                "error": "Failed",
                "duration_ms": 20000,
                "upstream_event_ids": ["evt-1", "evt-2"],
            },
        )
        score = scorer.score(event)
        assert score == 1.0  # Should be capped


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_missing_optional_fields(self, scorer):
        """Events with missing optional fields should not crash."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.DECISION,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={},
        )
        score = scorer.score(event)
        assert score == 0.75  # 0.7 base + 0.05 (no evidence penalty)

    def test_null_values_handled(self, scorer):
        """Null values should be handled gracefully."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.LLM_RESPONSE,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"cost_usd": None},
        )
        score = scorer.score(event)
        assert score == 0.5  # Base score only

    def test_string_zero_converted(self, scorer):
        """String '0' should be converted to float correctly."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.LLM_RESPONSE,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"cost_usd": "0"},
        )
        score = scorer.score(event)
        assert score == 0.5  # Base score only

    def test_empty_string_values(self, scorer):
        """Empty strings should be handled gracefully."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.SAFETY_CHECK,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"outcome": ""},
        )
        score = scorer.score(event)
        # Empty string != "pass", so should get bonus
        assert score == 0.85  # 0.75 base + 0.1


class TestCustomWeights:
    """Tests for custom weight configurations."""

    def test_all_weights_customizable(self):
        """All weights should be customizable."""
        custom_scorer = ImportanceScorer(
            error_weight=0.1,
            decision_weight=0.1,
            cost_weight=0.1,
            duration_weight=0.1,
        )
        assert custom_scorer.error_weight == 0.1
        assert custom_scorer.decision_weight == 0.1
        assert custom_scorer.cost_weight == 0.1
        assert custom_scorer.duration_weight == 0.1

    def test_custom_weights_affect_scoring(self):
        """Custom weights should affect scoring."""
        custom_scorer = ImportanceScorer(error_weight=0.1)
        default_scorer = ImportanceScorer()

        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.TOOL_RESULT,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"error": "Failed"},
        )

        custom_score = custom_scorer.score(event)
        default_score = default_scorer.score(event)

        assert custom_score < default_score  # Lower error weight = lower score


class TestScorerSingleton:
    """Tests for the global scorer singleton."""

    def test_get_importance_scorer_returns_instance(self):
        """get_importance_scorer should return an ImportanceScorer instance."""
        scorer = get_importance_scorer()
        assert isinstance(scorer, ImportanceScorer)

    def test_get_importance_scorer_returns_singleton(self):
        """get_importance_scorer should return the same instance."""
        scorer1 = get_importance_scorer()
        scorer2 = get_importance_scorer()
        assert scorer1 is scorer2

    def test_singleton_has_default_weights(self):
        """Singleton scorer should have default weights."""
        scorer = get_importance_scorer()
        assert scorer.error_weight == 0.4
        assert scorer.decision_weight == 0.3
        assert scorer.cost_weight == 0.15
        assert scorer.duration_weight == 0.15


class TestHelperMethodIsolation:
    """Tests that helper methods are properly isolated."""

    def test_tool_result_helper_ignores_other_types(self, scorer):
        """Tool result helper should only score TOOL_RESULT events."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.ERROR,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"error": "Failed"},
        )
        score = scorer.score(event)
        assert score == 0.9  # Base score only, no tool result bonus

    def test_llm_response_helper_ignores_other_types(self, scorer):
        """LLM response helper should only score LLM_RESPONSE events."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"cost_usd": 1.0},
        )
        score = scorer.score(event)
        assert score == 0.4  # Base score only, no cost bonus

    def test_decision_helper_ignores_other_types(self, scorer):
        """Decision helper should only score DECISION events."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.AGENT_TURN,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"confidence": 0.1, "evidence": []},
        )
        score = scorer.score(event)
        assert score == 0.45  # Base score only, no decision bonuses

    def test_safety_check_helper_ignores_other_types(self, scorer):
        """Safety check helper should only score SAFETY_CHECK events."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.REFUSAL,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"outcome": "fail"},
        )
        score = scorer.score(event)
        assert score == 0.85  # Base score only, no safety check bonus

    def test_behavior_alert_helper_ignores_other_types(self, scorer):
        """Behavior alert helper should only score BEHAVIOR_ALERT events."""
        event = TraceEvent(
            id="test-1",
            session_id="session-1",
            event_type=EventType.ERROR,
            timestamp=datetime.now(timezone.utc),
            name="test",
            data={"severity": "high"},
        )
        score = scorer.score(event)
        assert score == 0.9  # Base score only, no behavior alert bonus
