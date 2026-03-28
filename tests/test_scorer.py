"""Comprehensive tests for importance scoring.

This test module covers:
- Base scores for all event types
- Event-type-specific modifiers (tool_result, llm_response, decision, safety_check, behavior_alert)
- Universal modifiers (duration, upstream_event_ids)
- Custom weight configuration
- Edge cases and score capping
"""

from __future__ import annotations

from agent_debugger_sdk.core.events import (
    BehaviorAlertEvent,
    DecisionEvent,
    ErrorEvent,
    EventType,
    LLMResponseEvent,
    SafetyCheckEvent,
    ToolCallEvent,
    ToolResultEvent,
    TraceEvent,
)
from agent_debugger_sdk.core.scorer import ImportanceScorer, get_importance_scorer

# ==============================================================================
# Base Score Tests
# ==============================================================================

def test_base_scores_for_all_event_types():
    """Verify base scores are applied correctly for all event types."""
    scorer = ImportanceScorer()

    base_scores = {
        EventType.ERROR: 0.9,
        EventType.DECISION: 0.7,
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

    for event_type, expected_score in base_scores.items():
        event = TraceEvent(event_type=event_type, name=f"test_{event_type}")
        score = scorer.score(event)
        assert score == expected_score, f"Event type {event_type} expected {expected_score}, got {score}"


def test_default_score_for_unknown_event_type():
    """Verify unknown event types get a default score of 0.3."""
    scorer = ImportanceScorer()
    # Create event with a valid enum but ensure it's not in _BASE_SCORES
    # Since all enum values are covered, we test the default behavior
    event = TraceEvent(event_type=EventType.AGENT_START, name="test")
    # Remove this event type from base scores to test default
    original_scores = scorer._BASE_SCORES.copy()
    scorer._BASE_SCORES.clear()
    try:
        score = scorer.score(event)
        assert score == 0.3, f"Expected default score 0.3, got {score}"
    finally:
        scorer._BASE_SCORES.update(original_scores)


# ==============================================================================
# Tool Result Modifier Tests
# ==============================================================================

def test_tool_result_with_error_increases_score():
    """Verify tool_result events with errors get increased score."""
    scorer = ImportanceScorer()

    event = ToolResultEvent(
        name="tool_result_error",
        data={"error": "Tool failed"},
        session_id="test_session",
    )
    score = scorer.score(event)

    expected = 0.5 + scorer.error_weight  # base_score + error_weight
    assert score == expected, f"Expected {expected}, got {score}"


def test_tool_result_without_error_unchanged():
    """Verify tool_result events without errors keep base score."""
    scorer = ImportanceScorer()

    event = ToolResultEvent(
        name="tool_result_success",
        data={"result": "success"},
        session_id="test_session",
    )
    score = scorer.score(event)

    assert score == 0.5, f"Expected 0.5, got {score}"


# ==============================================================================
# LLM Response Modifier Tests
# ==============================================================================

def test_llm_response_with_high_cost_increases_score():
    """Verify llm_response events with high cost get increased score."""
    scorer = ImportanceScorer()

    event = LLMResponseEvent(
        name="llm_response",
        data={"cost_usd": 0.05},
        session_id="test_session",
    )
    score = scorer.score(event)

    expected = 0.5 + scorer.cost_weight * min(0.05 / 0.1, 1.0)
    assert score == expected, f"Expected {expected}, got {score}"


def test_llm_response_with_low_cost_unchanged():
    """Verify llm_response events with low cost (<=0.01) keep base score."""
    scorer = ImportanceScorer()

    event = LLMResponseEvent(
        name="llm_response",
        data={"cost_usd": 0.005},
        session_id="test_session",
    )
    score = scorer.score(event)

    assert score == 0.5, f"Expected 0.5, got {score}"


def test_llm_response_cost_modifier_capped():
    """Verify cost modifier is capped at cost_weight."""
    scorer = ImportanceScorer()

    event = LLMResponseEvent(
        name="llm_response",
        data={"cost_usd": 1.0},  # Very high cost
        session_id="test_session",
    )
    score = scorer.score(event)

    expected = 0.5 + scorer.cost_weight  # Capped at 1.0 multiplier
    assert score == expected, f"Expected {expected}, got {score}"


# ==============================================================================
# Duration Modifier Tests
# ==============================================================================

def test_duration_modifier_applies_to_long_events():
    """Verify events with duration > 1000ms get increased score."""
    scorer = ImportanceScorer()

    event = TraceEvent(
        event_type=EventType.TOOL_CALL,
        name="long_tool_call",
        data={"duration_ms": 5000},
    )
    score = scorer.score(event)

    expected = 0.4 + scorer.duration_weight * min(5000 / 10000, 1.0)
    assert score == expected, f"Expected {expected}, got {score}"


def test_duration_modifier_not_applied_to_short_events():
    """Verify events with duration <= 1000ms keep base score."""
    scorer = ImportanceScorer()

    event = TraceEvent(
        event_type=EventType.TOOL_CALL,
        name="short_tool_call",
        data={"duration_ms": 500},
    )
    score = scorer.score(event)

    assert score == 0.4, f"Expected 0.4, got {score}"


def test_duration_modifier_capped():
    """Verify duration modifier is capped at duration_weight."""
    scorer = ImportanceScorer()

    event = TraceEvent(
        event_type=EventType.TOOL_CALL,
        name="very_long_tool_call",
        data={"duration_ms": 50000},  # Very long duration
    )
    score = scorer.score(event)

    expected = 0.4 + scorer.duration_weight  # Capped at 1.0 multiplier
    assert score == expected, f"Expected {expected}, got {score}"


# ==============================================================================
# Decision Modifier Tests
# ==============================================================================

def test_decision_with_low_confidence_increases_score():
    """Verify decisions with low confidence get increased score."""
    scorer = ImportanceScorer()

    event = DecisionEvent(
        name="decision",
        data={"confidence": 0.1},
        session_id="test_session",
    )
    score = scorer.score(event)

    # base_score + decision_weight * abs(0.5 - 0.1) * 2 + no_evidence_penalty
    expected = 0.7 + scorer.decision_weight * abs(0.5 - 0.1) * 2 + 0.05
    assert score == expected, f"Expected {expected}, got {score}"


def test_decision_with_no_evidence_increases_score():
    """Verify decisions without evidence get increased score."""
    scorer = ImportanceScorer()

    event = DecisionEvent(
        name="decision",
        data={"confidence": 0.5, "evidence": []},
        session_id="test_session",
    )
    score = scorer.score(event)

    expected = 0.7 + 0.05
    assert score == expected, f"Expected {expected}, got {score}"


def test_decision_with_evidence_event_ids_increases_score():
    """Verify decisions with evidence_event_ids get increased score."""
    scorer = ImportanceScorer()

    event = DecisionEvent(
        name="decision",
        data={
            "confidence": 0.5,
            "evidence": ["some evidence"],
            "evidence_event_ids": ["evt1", "evt2"],
        },
        session_id="test_session",
    )
    score = scorer.score(event)

    expected = 0.7 + 0.05
    assert score == expected, f"Expected {expected}, got {score}"


def test_decision_with_high_confidence_no_modifiers():
    """Verify decisions with confidence=0.5 and all evidence get only base score."""
    scorer = ImportanceScorer()

    event = DecisionEvent(
        name="decision",
        data={
            "confidence": 0.5,
            "evidence": ["evidence1"],
            "evidence_event_ids": [],
        },
        session_id="test_session",
    )
    score = scorer.score(event)

    assert score == 0.7, f"Expected 0.7, got {score}"


# ==============================================================================
# Safety Check Modifier Tests
# ==============================================================================

def test_safety_check_non_pass_increases_score():
    """Verify safety_check events with non-pass outcome get increased score."""
    scorer = ImportanceScorer()

    for outcome in ["fail", "warn", "block", "other"]:
        event = SafetyCheckEvent(
            name="safety_check",
            data={"outcome": outcome},
            session_id="test_session",
        )
        score = scorer.score(event)
        expected = 0.75 + 0.1
        assert score == expected, f"Outcome {outcome}: expected {expected}, got {score}"


def test_safety_check_pass_unchanged():
    """Verify safety_check events with pass outcome keep base score."""
    scorer = ImportanceScorer()

    event = SafetyCheckEvent(
        name="safety_check",
        data={"outcome": "pass"},
        session_id="test_session",
    )
    score = scorer.score(event)

    assert score == 0.75, f"Expected 0.75, got {score}"


# ==============================================================================
# Behavior Alert Modifier Tests
# ==============================================================================

def test_behavior_alert_high_severity_increases_score():
    """Verify behavior_alert events with high severity get increased score."""
    scorer = ImportanceScorer()

    event = BehaviorAlertEvent(
        name="behavior_alert",
        data={"severity": "high"},
        session_id="test_session",
    )
    score = scorer.score(event)

    expected = 0.88 + 0.05
    assert score == expected, f"Expected {expected}, got {score}"


def test_behavior_alert_medium_severity_unchanged():
    """Verify behavior_alert events with medium/low severity keep base score."""
    scorer = ImportanceScorer()

    for severity in ["low", "medium", "critical"]:
        event = BehaviorAlertEvent(
            name="behavior_alert",
            data={"severity": severity},
            session_id="test_session",
        )
        score = scorer.score(event)
        assert score == 0.88, f"Severity {severity}: expected 0.88, got {score}"


# ==============================================================================
# Upstream Event Modifier Tests
# ==============================================================================

def test_upstream_event_ids_increases_score():
    """Verify events with upstream_event_ids get increased score."""
    scorer = ImportanceScorer()

    event = ToolCallEvent(
        name="tool_call",
        session_id="test_session",
        upstream_event_ids=["evt1", "evt2"],
    )
    score = scorer.score(event)

    expected = 0.4 + 0.03
    assert score == expected, f"Expected {expected}, got {score}"


def test_no_upstream_event_ids_unchanged():
    """Verify events without upstream_event_ids keep base score."""
    scorer = ImportanceScorer()

    event = ToolCallEvent(
        name="tool_call",
        session_id="test_session",
    )
    score = scorer.score(event)

    assert score == 0.4, f"Expected 0.4, got {score}"


# ==============================================================================
# Score Capping Tests
# ==============================================================================

def test_score_capped_at_1_0():
    """Verify scores are capped at 1.0 even with multiple modifiers."""
    scorer = ImportanceScorer()

    # Create an event that would exceed 1.0
    event = ErrorEvent(
        name="error",
        session_id="test_session",
        upstream_event_ids=["evt1"],
        data={"duration_ms": 20000},
    )
    score = scorer.score(event)

    assert score == 1.0, f"Expected 1.0 (capped), got {score}"


# ==============================================================================
# Custom Weight Configuration Tests
# ==============================================================================

def test_custom_error_weight():
    """Verify custom error_weight affects tool_result error scoring."""
    scorer = ImportanceScorer(error_weight=0.5)

    event = ToolResultEvent(
        name="tool_result_error",
        data={"error": "Tool failed"},
        session_id="test_session",
    )
    score = scorer.score(event)

    expected = 0.5 + 0.5
    assert score == expected, f"Expected {expected}, got {score}"


def test_custom_decision_weight():
    """Verify custom decision_weight affects decision scoring."""
    scorer = ImportanceScorer(decision_weight=0.5)

    event = DecisionEvent(
        name="decision",
        data={"confidence": 0.1},
        session_id="test_session",
    )
    score = scorer.score(event)

    expected = 0.7 + 0.5 * abs(0.5 - 0.1) * 2 + 0.05
    # Score is capped at 1.0
    assert score == min(expected, 1.0), f"Expected {min(expected, 1.0)}, got {score}"


def test_custom_cost_and_duration_weights():
    """Verify custom cost_weight and duration_weight affect scoring."""
    scorer = ImportanceScorer(cost_weight=0.2, duration_weight=0.2)

    event = LLMResponseEvent(
        name="llm_response",
        data={"cost_usd": 0.05, "duration_ms": 5000},
        session_id="test_session",
    )
    score = scorer.score(event)

    expected = 0.5 + 0.2 * min(0.05 / 0.1, 1.0) + 0.2 * min(5000 / 10000, 1.0)
    assert score == expected, f"Expected {expected}, got {score}"


# ==============================================================================
# Singleton Tests
# ==============================================================================

def test_get_importance_scorer_returns_singleton():
    """Verify get_importance_scorer returns the same instance."""
    scorer1 = get_importance_scorer()
    scorer2 = get_importance_scorer()

    assert scorer1 is scorer2, "get_importance_scorer should return the same instance"


def test_get_importance_scorer_has_default_weights():
    """Verify singleton scorer has default weights."""
    scorer = get_importance_scorer()

    assert scorer.error_weight == 0.4
    assert scorer.decision_weight == 0.3
    assert scorer.cost_weight == 0.15
    assert scorer.duration_weight == 0.15


# ==============================================================================
# Edge Cases Tests
# ==============================================================================

def test_event_with_missing_data_fields():
    """Verify events with missing data fields don't crash."""
    scorer = ImportanceScorer()

    event = TraceEvent(
        event_type=EventType.TOOL_CALL,
        name="tool_call",
        data={},  # Empty data
    )
    score = scorer.score(event)

    assert score == 0.4, f"Expected 0.4, got {score}"


def test_event_with_none_values():
    """Verify events with None values in data are handled."""
    scorer = ImportanceScorer()

    event = LLMResponseEvent(
        name="llm_response",
        data={"cost_usd": None, "duration_ms": None},
        session_id="test_session",
    )
    score = scorer.score(event)

    assert score == 0.5, f"Expected 0.5, got {score}"


def test_all_event_types_have_base_scores():
    """Verify all EventType enum values have base scores defined."""
    scorer = ImportanceScorer()

    for event_type in EventType:
        base_score = scorer._BASE_SCORES.get(event_type)
        assert base_score is not None, f"Event type {event_type} missing base score"
        assert 0.0 <= base_score <= 1.0, f"Event type {event_type} has invalid base score: {base_score}"


# ==============================================================================
# Combined Modifier Tests
# ==============================================================================

def test_multiple_modifiers_combine_correctly():
    """Verify multiple modifiers apply and combine correctly."""
    scorer = ImportanceScorer()

    # LLM response with high cost and long duration
    event = LLMResponseEvent(
        name="llm_response",
        data={"cost_usd": 0.05, "duration_ms": 5000},
        session_id="test_session",
        upstream_event_ids=["evt1"],
    )
    score = scorer.score(event)

    expected = (
        0.5  # base score
        + scorer.cost_weight * min(0.05 / 0.1, 1.0)  # cost modifier
        + scorer.duration_weight * min(5000 / 10000, 1.0)  # duration modifier
        + 0.03  # upstream modifier
    )
    assert score == expected, f"Expected {expected}, got {score}"


def test_decision_with_all_modifiers():
    """Verify decision events with all applicable modifiers."""
    scorer = ImportanceScorer()

    event = DecisionEvent(
        name="decision",
        data={
            "confidence": 0.1,
            "evidence": [],
            "evidence_event_ids": ["evt1"],
            "duration_ms": 5000,
        },
        session_id="test_session",
        upstream_event_ids=["evt2"],
    )
    score = scorer.score(event)

    expected = (
        0.7  # base score
        + scorer.decision_weight * abs(0.5 - 0.1) * 2  # confidence modifier
        + 0.05  # no evidence modifier
        + 0.05  # has evidence_event_ids modifier
        + scorer.duration_weight * min(5000 / 10000, 1.0)  # duration modifier
        + 0.03  # upstream modifier
    )
    # Score is capped at 1.0
    assert score == min(expected, 1.0), f"Expected {min(expected, 1.0)}, got {score}"
