"""Unit tests for intelligence compute, event_utils, and helpers modules."""

from __future__ import annotations

from collections import Counter

import pytest

from agent_debugger_sdk.core.events import Checkpoint, EventType, TraceEvent
from collector.intelligence.compute import (
    compute_checkpoint_rankings,
    compute_event_ranking,
    detect_tool_loop,
)
from collector.intelligence.event_utils import event_headline, fingerprint, retention_tier
from collector.intelligence.helpers import event_value, mean


def _make_event(event_type: EventType = EventType.TOOL_CALL, session_id: str = "s1", **overrides) -> TraceEvent:
    # Don't set name if it's in overrides
    if "name" not in overrides:
        overrides = {**overrides, "name": event_type.value}
    return TraceEvent(
        session_id=session_id,
        event_type=event_type,
        **overrides,
    )


def _make_checkpoint(
    session_id: str = "s1", event_id: str = "e1", sequence: int = 1, importance: float = 0.5
) -> Checkpoint:
    return Checkpoint(
        session_id=session_id,
        event_id=event_id,
        sequence=sequence,
        importance=importance,
    )


class TestComputeEventRanking:
    """Tests for compute_event_ranking function."""

    def test_high_severity_event_produces_high_replay_value(self):
        """High severity events should have elevated replay_value."""
        event = _make_event(EventType.ERROR, data={"error_message": "critical failure"})
        fp = fingerprint(event)
        counts = Counter({fp: 3})

        result = compute_event_ranking(
            event=event,
            fingerprint=fp,
            counts=counts,
            total_events=10,
            checkpoint_event_ids=set(),
            severity_fn=lambda e: 0.95,
        )

        assert result["severity"] == 0.95
        assert result["replay_value"] >= 0.5  # severity * 0.55

    def test_novelty_decreases_with_recurrence(self):
        """Novelty should decrease as recurrence_count increases."""
        event = _make_event()
        fp = "test:fingerprint"

        # First occurrence
        result1 = compute_event_ranking(
            event=event,
            fingerprint=fp,
            counts=Counter({fp: 1}),
            total_events=10,
            checkpoint_event_ids=set(),
            severity_fn=lambda e: 0.5,
        )
        assert result1["novelty"] == 1.0

        # Fifth occurrence
        result5 = compute_event_ranking(
            event=event,
            fingerprint=fp,
            counts=Counter({fp: 5}),
            total_events=10,
            checkpoint_event_ids=set(),
            severity_fn=lambda e: 0.5,
        )
        assert result5["novelty"] == 0.2  # 1/5

    def test_recurrence_scales_with_total_events(self):
        """Recurrence should be bounded between 0 and 1 based on total_events."""
        event = _make_event()
        fp = "test:fp"

        # Low total_events -> higher recurrence ratio
        result_low = compute_event_ranking(
            event=event,
            fingerprint=fp,
            counts=Counter({fp: 5}),
            total_events=10,
            checkpoint_event_ids=set(),
            severity_fn=lambda e: 0.5,
        )
        # (5-1)/10 = 0.4
        assert result_low["recurrence"] == 0.4

        # High total_events -> lower recurrence ratio
        result_high = compute_event_ranking(
            event=event,
            fingerprint=fp,
            counts=Counter({fp: 5}),
            total_events=100,
            checkpoint_event_ids=set(),
            severity_fn=lambda e: 0.5,
        )
        # (5-1)/100 = 0.04
        assert result_high["recurrence"] == 0.04

    def test_checkpoint_event_boosts_replay_value(self):
        """Events in checkpoint_event_ids should get replay_value boost."""
        event = _make_event()
        fp = "test:fp"

        result_with_checkpoint = compute_event_ranking(
            event=event,
            fingerprint=fp,
            counts=Counter({fp: 1}),  # Must have count > 0 to avoid ZeroDivisionError
            total_events=10,
            checkpoint_event_ids={event.id},
            severity_fn=lambda e: 0.5,
        )

        result_without_checkpoint = compute_event_ranking(
            event=event,
            fingerprint=fp,
            counts=Counter({fp: 1}),
            total_events=10,
            checkpoint_event_ids=set(),
            severity_fn=lambda e: 0.5,
        )

        assert result_with_checkpoint["replay_value"] > result_without_checkpoint["replay_value"]

    def test_decision_refusal_policy_violation_boost(self):
        """DECISION, REFUSAL, POLICY_VIOLATION events get replay_value boost."""
        for event_type in [EventType.DECISION, EventType.REFUSAL, EventType.POLICY_VIOLATION]:
            event = _make_event(event_type)
            fp = fingerprint(event)

            result = compute_event_ranking(
                event=event,
                fingerprint=fp,
                counts=Counter({fp: 1}),  # Must have count > 0
                total_events=10,
                checkpoint_event_ids=set(),
                severity_fn=lambda e: 0.5,
            )

            assert result["replay_value"] >= 0.1  # gets the boost

    def test_upstream_and_evidence_events_boost(self):
        """Events with upstream_event_ids or evidence_event_ids get boost."""
        # Set upstream_event_ids as an attribute since event_value checks attributes first
        event_with_upstream = _make_event()
        event_with_upstream.upstream_event_ids = ["e1", "e2"]

        event_with_evidence = _make_event(data={"evidence_event_ids": ["e3"]})
        fp = "test:fp"

        result_upstream = compute_event_ranking(
            event=event_with_upstream,
            fingerprint=fp,
            counts=Counter({fp: 1}),  # Must have count > 0
            total_events=10,
            checkpoint_event_ids=set(),
            severity_fn=lambda e: 0.5,
        )

        result_evidence = compute_event_ranking(
            event=event_with_evidence,
            fingerprint=fp,
            counts=Counter({fp: 1}),  # Must have count > 0
            total_events=10,
            checkpoint_event_ids=set(),
            severity_fn=lambda e: 0.5,
        )

        assert result_upstream["replay_value"] >= 0.1
        assert result_evidence["replay_value"] >= 0.1

    def test_composite_is_bounded(self):
        """Composite score should always be between 0 and 1."""
        event = _make_event()
        fp = "test:fp"

        result = compute_event_ranking(
            event=event,
            fingerprint=fp,
            counts=Counter({fp: 5}),
            total_events=10,
            checkpoint_event_ids={event.id},
            severity_fn=lambda e: 0.95,
        )

        assert 0.0 <= result["composite"] <= 1.0

    def test_empty_counts_zero_total_events(self):
        """Edge case: empty counts and zero total_events causes ZeroDivisionError in novelty calculation.

        This is a known issue - the function requires at least one occurrence in counts.
        """
        event = _make_event()
        fp = "test:fp"

        # This should raise ZeroDivisionError due to 1.0 / 0 in novelty calculation
        with pytest.raises(ZeroDivisionError):
            compute_event_ranking(
                event=event,
                fingerprint=fp,
                counts=Counter(),  # Empty - causes division by zero
                total_events=0,
                checkpoint_event_ids=set(),
                severity_fn=lambda e: 0.5,
            )

    def test_returns_all_expected_fields(self):
        """Result should include all expected ranking fields."""
        event = _make_event()
        fp = "test:fp"

        result = compute_event_ranking(
            event=event,
            fingerprint=fp,
            counts=Counter({fp: 1}),  # Must have count > 0
            total_events=10,
            checkpoint_event_ids=set(),
            severity_fn=lambda e: 0.5,
        )

        expected_keys = {
            "event_id",
            "event_type",
            "fingerprint",
            "severity",
            "novelty",
            "recurrence",
            "replay_value",
            "composite",
        }
        assert set(result.keys()) == expected_keys


class TestDetectToolLoop:
    """Tests for detect_tool_loop function."""

    def test_three_consecutive_same_tool_triggers_alert(self):
        """Three consecutive TOOL_CALL events with same tool_name should trigger alert."""
        tool_name = "search"
        events = [
            _make_event(EventType.TOOL_CALL, data={"tool_name": tool_name}),
            _make_event(EventType.TOOL_CALL, data={"tool_name": tool_name}),
            _make_event(EventType.TOOL_CALL, data={"tool_name": tool_name}),
        ]

        # First call
        counter, prev_tool, alerts = detect_tool_loop(events[0], 0, None)
        assert counter == 1
        assert prev_tool == tool_name
        assert len(alerts) == 0

        # Second call
        counter, prev_tool, alerts = detect_tool_loop(events[1], counter, prev_tool)
        assert counter == 2
        assert len(alerts) == 0

        # Third call - should trigger alert
        counter, prev_tool, alerts = detect_tool_loop(events[2], counter, prev_tool)
        assert counter == 3
        assert len(alerts) == 1
        assert alerts[0]["alert_type"] == "tool_loop"
        assert alerts[0]["severity"] == "high"
        assert tool_name in alerts[0]["signal"]

    def test_different_tool_resets_counter(self):
        """Different tool_name should reset consecutive counter to 1."""
        event1 = _make_event(EventType.TOOL_CALL, data={"tool_name": "search"})
        event2 = _make_event(EventType.TOOL_CALL, data={"tool_name": "read_file"})

        counter, prev_tool, alerts = detect_tool_loop(event1, 2, "search")
        assert counter == 3

        counter, prev_tool, alerts = detect_tool_loop(event2, counter, prev_tool)
        assert counter == 1  # reset to 1
        assert prev_tool == "read_file"
        assert len(alerts) == 0

    def test_non_tool_call_resets_state(self):
        """Non-TOOL_CALL events should reset counter and return None for tool_name."""
        decision_event = _make_event(EventType.DECISION)

        counter, prev_tool, alerts = detect_tool_loop(decision_event, 2, "search")

        assert counter == 0
        assert prev_tool is None
        assert len(alerts) == 0

    def test_tool_result_resets_counter(self):
        """TOOL_RESULT events should reset the loop counter."""
        tool_result_event = _make_event(EventType.TOOL_RESULT, data={"tool_name": "search"})

        counter, prev_tool, alerts = detect_tool_loop(tool_result_event, 2, "search")

        assert counter == 0
        assert prev_tool is None

    def test_empty_tool_name_resets(self):
        """TOOL_CALL with empty tool_name should reset."""
        event_no_name = _make_event(EventType.TOOL_CALL, data={})

        counter, prev_tool, alerts = detect_tool_loop(event_no_name, 2, "search")

        assert counter == 0
        assert prev_tool is None

    def test_alert_includes_event_id(self):
        """Generated alert should include the triggering event's ID."""
        tool_name = "write_file"
        event = _make_event(EventType.TOOL_CALL, data={"tool_name": tool_name})

        counter, prev_tool, alerts = detect_tool_loop(event, 2, tool_name)

        assert len(alerts) == 1
        assert alerts[0]["event_id"] == event.id


class TestComputeCheckpointRankings:
    """Tests for compute_checkpoint_rankings function."""

    def test_ranks_checkpoints_by_restore_value(self):
        """Checkpoints should be sorted by restore_value descending."""
        checkpoints = [
            _make_checkpoint(event_id="e1", sequence=1, importance=0.3),
            _make_checkpoint(event_id="e2", sequence=2, importance=0.9),
            _make_checkpoint(event_id="e3", sequence=3, importance=0.5),
        ]

        ranking_by_event_id = {
            "e1": {"replay_value": 0.8, "composite": 0.7, "severity": 0.5},
            "e2": {"replay_value": 0.4, "composite": 0.3, "severity": 0.5},
            "e3": {"replay_value": 0.6, "composite": 0.5, "severity": 0.5},
        }

        rankings, values = compute_checkpoint_rankings(
            checkpoints=checkpoints,
            ranking_by_event_id=ranking_by_event_id,
            representative_failure_ids=[],
        )

        # Sorted by (-restore_value, -importance, -sequence)
        # Weights: event_replay*0.40 + event_composite*0.20 + importance*0.20 + sequence_weight*0.10 + session_replay*0.10
        # e1: 0.8*0.40 + 0.7*0.20 + 0.3*0.20 + (1/3)*0.10 = 0.32 + 0.14 + 0.06 + 0.033 = 0.553
        # e2: 0.4*0.40 + 0.3*0.20 + 0.9*0.20 + (2/3)*0.10 = 0.16 + 0.06 + 0.18 + 0.067 = 0.467
        # e3: 0.6*0.40 + 0.5*0.20 + 0.5*0.20 + (3/3)*0.10 = 0.24 + 0.10 + 0.10 + 0.10 = 0.540
        # So order should be e1, e3, e2
        assert rankings[0]["event_id"] == "e1"
        assert rankings[1]["event_id"] == "e3"
        assert rankings[2]["event_id"] == "e2"

    def test_representative_failure_indicator(self):
        """Checkpoints with event_id in representative_failure_ids get indicator."""
        checkpoints = [
            _make_checkpoint(event_id="e1", sequence=1, importance=0.1),
            _make_checkpoint(event_id="e2", sequence=2, importance=0.1),
        ]

        ranking_by_event_id = {
            "e1": {"replay_value": 0.5, "composite": 0.5, "severity": 0.5},
            "e2": {"replay_value": 0.1, "composite": 0.1, "severity": 0.5},  # Very low replay_value
        }

        rankings, values = compute_checkpoint_rankings(
            checkpoints=checkpoints,
            ranking_by_event_id=ranking_by_event_id,
            representative_failure_ids=["e1"],
        )

        # e1 has failure_cluster_indicator=1
        # restore_value: 0.5*0.40 + 0.5*0.2 + 0.1*0.2 + (1/2)*0.10 + 0*0.10 = 0.20 + 0.10 + 0.02 + 0.05 = 0.37
        # retention_tier: 0.37 >= 0.42? No. failure_cluster_count=1 -> "summarized"
        # e2 has very low replay_value and no failure cluster
        # restore_value: 0.1*0.40 + 0.1*0.2 + 0.1*0.2 + (2/2)*0.10 + 0*0.10 = 0.04 + 0.02 + 0.02 + 0.10 = 0.18
        # retention_tier: 0.18 < 0.42 and failure_cluster_count=0 -> "downsampled"
        tier_e1 = next(r["retention_tier"] for r in rankings if r["event_id"] == "e1")
        tier_e2 = next(r["retention_tier"] for r in rankings if r["event_id"] == "e2")
        assert tier_e1 == "summarized"
        assert tier_e2 == "downsampled"

    def test_high_severity_indicator(self):
        """Checkpoints with severity >= 0.92 get high_severity_indicator."""
        checkpoints = [
            _make_checkpoint(event_id="e1", sequence=1, importance=0.1),
            _make_checkpoint(event_id="e2", sequence=2, importance=0.1),
        ]

        ranking_by_event_id = {
            "e1": {"replay_value": 0.5, "composite": 0.5, "severity": 0.95},
            "e2": {"replay_value": 0.1, "composite": 0.1, "severity": 0.5},  # Very low replay_value
        }

        rankings, values = compute_checkpoint_rankings(
            checkpoints=checkpoints,
            ranking_by_event_id=ranking_by_event_id,
            representative_failure_ids=[],
        )

        # e1 has high_severity_indicator=1, which triggers "full" tier regardless of restore_value
        tier_e1 = next(r["retention_tier"] for r in rankings if r["event_id"] == "e1")
        tier_e2 = next(r["retention_tier"] for r in rankings if r["event_id"] == "e2")
        assert tier_e1 == "full"
        # e2 has low severity (0.5 < 0.92) and low restore_value (0.18 < 0.42)
        # retention_tier: 0.18 < 0.42 -> "downsampled"
        assert tier_e2 == "downsampled"

    def test_sequence_weight_in_restore_value(self):
        """Sequence weight should factor into restore_value calculation."""
        checkpoints = [
            _make_checkpoint(event_id="e1", sequence=1, importance=0.5),
            _make_checkpoint(event_id="e2", sequence=10, importance=0.5),
        ]

        ranking_by_event_id = {
            "e1": {"replay_value": 0.5, "composite": 0.5, "severity": 0.5},
            "e2": {"replay_value": 0.5, "composite": 0.5, "severity": 0.5},
        }

        rankings, values = compute_checkpoint_rankings(
            checkpoints=checkpoints,
            ranking_by_event_id=ranking_by_event_id,
            representative_failure_ids=[],
        )

        # e2 has higher sequence, so higher sequence_weight
        assert values[1] > values[0]

    def test_empty_checkpoints(self):
        """Empty checkpoint list should return empty results."""
        rankings, values = compute_checkpoint_rankings(
            checkpoints=[],
            ranking_by_event_id={},
            representative_failure_ids=[],
        )

        assert rankings == []
        assert values == []

    def test_missing_event_ranking(self):
        """Checkpoints without event rankings should use zero values."""
        checkpoints = [
            _make_checkpoint(event_id="e1", sequence=1),
        ]

        rankings, values = compute_checkpoint_rankings(
            checkpoints=checkpoints,
            ranking_by_event_id={},  # e1 not in rankings
            representative_failure_ids=[],
        )

        assert rankings[0]["replay_value"] == 0.0
        assert values[0] >= 0.0  # should still compute based on sequence/importance

    def test_restore_value_components(self):
        """Restore value should combine event_replay, event_composite, importance, sequence_weight."""
        checkpoints = [
            _make_checkpoint(event_id="e1", sequence=5, importance=0.8),
        ]

        ranking_by_event_id = {
            "e1": {"replay_value": 0.7, "composite": 0.6, "severity": 0.5},
        }

        rankings, values = compute_checkpoint_rankings(
            checkpoints=checkpoints,
            ranking_by_event_id=ranking_by_event_id,
            representative_failure_ids=[],
        )

        # restore_value = event_replay * 0.40 + event_composite * 0.2 + importance * 0.2 + sequence_weight * 0.10 + session_replay * 0.10
        # With max_sequence=5, sequence_weight = 5/5 = 1.0, session_replay_value defaults to 0.0
        # = 0.7*0.40 + 0.6*0.2 + 0.8*0.2 + 1.0*0.10 + 0.0*0.10
        # = 0.28 + 0.12 + 0.16 + 0.10 = 0.66
        expected = 0.7 * 0.40 + 0.6 * 0.2 + 0.8 * 0.2 + 1.0 * 0.10
        assert abs(values[0] - expected) < 0.001

    def test_returns_all_expected_fields(self):
        """Each ranking should include all expected fields."""
        checkpoints = [
            _make_checkpoint(event_id="e1", sequence=1, importance=0.5),
        ]

        ranking_by_event_id = {
            "e1": {"replay_value": 0.5, "composite": 0.5, "severity": 0.5},
        }

        rankings, values = compute_checkpoint_rankings(
            checkpoints=checkpoints,
            ranking_by_event_id=ranking_by_event_id,
            representative_failure_ids=[],
        )

        expected_keys = {
            "checkpoint_id",
            "event_id",
            "sequence",
            "importance",
            "replay_value",
            "restore_value",
            "retention_tier",
        }
        assert set(rankings[0].keys()) == expected_keys


class TestEventHeadline:
    """Tests for event_headline function."""

    def test_decision_event_shows_chosen_action(self):
        """DECISION events should show chosen_action."""
        event = _make_event(EventType.DECISION, data={"chosen_action": "proceed"})

        headline = event_headline(event)

        assert headline == "proceed"

    def test_decision_event_fallback_to_name(self):
        """DECISION without chosen_action should fall back to name."""
        event = _make_event(EventType.DECISION, name="my_decision", data={})

        headline = event_headline(event)

        assert headline == "my_decision"

    def test_tool_call_shows_tool_name(self):
        """TOOL_CALL events should show tool_name."""
        event = _make_event(EventType.TOOL_CALL, data={"tool_name": "search"})

        headline = event_headline(event)

        assert headline == "search"

    def test_tool_result_shows_tool_name(self):
        """TOOL_RESULT events should show tool_name."""
        event = _make_event(EventType.TOOL_RESULT, data={"tool_name": "write_file"})

        headline = event_headline(event)

        assert headline == "write_file"

    def test_error_shows_error_type(self):
        """ERROR events should show error_type."""
        event = _make_event(EventType.ERROR, data={"error_type": "ValueError"})

        headline = event_headline(event)

        assert headline == "ValueError"

    def test_error_fallback_to_name(self):
        """ERROR without error_type should fall back to name."""
        event = _make_event(EventType.ERROR, name="error occurred", data={})

        headline = event_headline(event)

        assert headline == "error occurred"

    def test_safety_check_shows_policy_and_outcome(self):
        """SAFETY_CHECK should show policy_name -> outcome."""
        event = _make_event(EventType.SAFETY_CHECK, data={"policy_name": "harm_check", "outcome": "block"})

        headline = event_headline(event)

        assert headline == "harm_check -> block"

    def test_refusal_shows_reason(self):
        """REFUSAL events should show reason."""
        event = _make_event(EventType.REFUSAL, data={"reason": "safety concern"})

        headline = event_headline(event)

        assert headline == "safety concern"

    def test_policy_violation_shows_violation_type(self):
        """POLICY_VIOLATION should show violation_type."""
        event = _make_event(EventType.POLICY_VIOLATION, data={"violation_type": "PII disclosure"})

        headline = event_headline(event)

        assert headline == "PII disclosure"

    def test_behavior_alert_shows_alert_type(self):
        """BEHAVIOR_ALERT should show alert_type."""
        event = _make_event(EventType.BEHAVIOR_ALERT, data={"alert_type": "tool_loop"})

        headline = event_headline(event)

        assert headline == "tool_loop"

    def test_agent_turn_shows_speaker(self):
        """AGENT_TURN should show speaker."""
        event = _make_event(EventType.AGENT_TURN, data={"speaker": "user"})

        headline = event_headline(event)

        assert headline == "user"

    def test_agent_turn_fallback_to_agent_id(self):
        """AGENT_TURN without speaker falls back to agent_id."""
        event = _make_event(EventType.AGENT_TURN, data={"agent_id": "agent-1"})

        headline = event_headline(event)

        assert headline == "agent-1"

    def test_llm_request_fallback(self):
        """LLM_REQUEST should fall back to event_type string."""
        event = _make_event(EventType.LLM_REQUEST)

        headline = event_headline(event)

        assert headline == "llm_request"

    def test_llm_response_fallback(self):
        """LLM_RESPONSE should fall back to event_type string."""
        event = _make_event(EventType.LLM_RESPONSE)

        headline = event_headline(event)

        assert headline == "llm_response"


class TestFingerprint:
    """Tests for fingerprint function."""

    def test_error_fingerprint_includes_error_type_and_message(self):
        """ERROR fingerprint should include error_type and error_message."""
        event = _make_event(EventType.ERROR, data={"error_type": "ValueError", "error_message": "invalid input"})

        fp = fingerprint(event)

        assert fp == "error:ValueError:invalid input"

    def test_error_fingerprint_defaults(self):
        """ERROR without fields should use defaults."""
        event = _make_event(EventType.ERROR, data={})

        fp = fingerprint(event)

        assert fp == "error:unknown:"

    def test_tool_result_fingerprint_includes_tool_name_and_error_flag(self):
        """TOOL_RESULT fingerprint should include tool_name and error boolean."""
        event = _make_event(EventType.TOOL_RESULT, data={"tool_name": "search", "error": "timeout"})

        fp = fingerprint(event)

        assert fp == "tool:search:True"

    def test_tool_result_no_error(self):
        """TOOL_RESULT without error should have False flag."""
        event = _make_event(EventType.TOOL_RESULT, data={"tool_name": "read_file"})

        fp = fingerprint(event)

        assert fp == "tool:read_file:False"

    def test_refusal_fingerprint_includes_policy_and_risk(self):
        """REFUSAL fingerprint includes policy_name and risk_level."""
        event = _make_event(EventType.REFUSAL, data={"policy_name": "safety", "risk_level": "high"})

        fp = fingerprint(event)

        assert fp == "refusal:safety:high"

    def test_policy_violation_fingerprint(self):
        """POLICY_VIOLATION fingerprint includes policy_name and violation_type."""
        event = _make_event(EventType.POLICY_VIOLATION, data={"policy_name": "PII", "violation_type": "disclosure"})

        fp = fingerprint(event)

        assert fp == "policy:PII:disclosure"

    def test_behavior_alert_fingerprint(self):
        """BEHAVIOR_ALERT fingerprint includes alert_type."""
        event = _make_event(EventType.BEHAVIOR_ALERT, data={"alert_type": "tool_loop"})

        fp = fingerprint(event)

        assert fp == "alert:tool_loop"

    def test_safety_check_fingerprint(self):
        """SAFETY_CHECK fingerprint includes policy_name and outcome."""
        event = _make_event(EventType.SAFETY_CHECK, data={"policy_name": "harm", "outcome": "pass"})

        fp = fingerprint(event)

        assert fp == "safety:harm:pass"

    def test_decision_fingerprint(self):
        """DECISION fingerprint includes chosen_action."""
        event = _make_event(EventType.DECISION, data={"chosen_action": "stop"})

        fp = fingerprint(event)

        assert fp == "decision:stop"

    def test_different_events_produce_different_fingerprints(self):
        """Different event types/contents should produce different fingerprints."""
        event1 = _make_event(EventType.ERROR, data={"error_type": "ValueError"})
        event2 = _make_event(EventType.TOOL_RESULT, data={"tool_name": "search"})

        fp1 = fingerprint(event1)
        fp2 = fingerprint(event2)

        assert fp1 != fp2

    def test_same_events_produce_same_fingerprints(self):
        """Identical events should produce identical fingerprints."""
        event1 = _make_event(EventType.ERROR, data={"error_type": "ValueError", "error_message": "fail"})
        event2 = _make_event(EventType.ERROR, data={"error_type": "ValueError", "error_message": "fail"})

        fp1 = fingerprint(event1)
        fp2 = fingerprint(event2)

        assert fp1 == fp2

    def test_fallback_fingerprint(self):
        """Unknown event types should use event_type:name pattern."""
        event = _make_event(EventType.LLM_REQUEST, name="my_request")

        fp = fingerprint(event)

        assert fp == "llm_request:my_request"


class TestRetentionTier:
    """Tests for retention_tier function."""

    def test_high_replay_value_returns_full(self):
        """replay_value >= 0.72 should return 'full'."""
        tier = retention_tier(
            replay_value=0.8,
            high_severity_count=0,
            failure_cluster_count=0,
            behavior_alert_count=0,
        )

        assert tier == "full"

    def test_boundary_at_072(self):
        """replay_value at exactly 0.72 should return 'full'."""
        tier = retention_tier(
            replay_value=0.72,
            high_severity_count=0,
            failure_cluster_count=0,
            behavior_alert_count=0,
        )

        assert tier == "full"

    def test_high_severity_returns_full(self):
        """high_severity_count > 0 should return 'full' regardless of replay_value."""
        tier = retention_tier(
            replay_value=0.3,
            high_severity_count=1,
            failure_cluster_count=0,
            behavior_alert_count=0,
        )

        assert tier == "full"

    def test_two_or_more_failure_clusters_returns_full(self):
        """failure_cluster_count >= 2 should return 'full'."""
        tier = retention_tier(
            replay_value=0.5,
            high_severity_count=0,
            failure_cluster_count=2,
            behavior_alert_count=0,
        )

        assert tier == "full"

    def test_medium_replay_value_returns_summarized(self):
        """replay_value >= 0.42 should return 'summarized'."""
        tier = retention_tier(
            replay_value=0.5,
            high_severity_count=0,
            failure_cluster_count=0,
            behavior_alert_count=0,
        )

        assert tier == "summarized"

    def test_boundary_at_042(self):
        """replay_value at exactly 0.42 should return 'summarized'."""
        tier = retention_tier(
            replay_value=0.42,
            high_severity_count=0,
            failure_cluster_count=0,
            behavior_alert_count=0,
        )

        assert tier == "summarized"

    def test_behavior_alert_returns_summarized(self):
        """behavior_alert_count > 0 should return 'summarized'."""
        tier = retention_tier(
            replay_value=0.3,
            high_severity_count=0,
            failure_cluster_count=0,
            behavior_alert_count=1,
        )

        assert tier == "summarized"

    def test_one_failure_cluster_returns_summarized(self):
        """failure_cluster_count == 1 should return 'summarized'."""
        tier = retention_tier(
            replay_value=0.3,
            high_severity_count=0,
            failure_cluster_count=1,
            behavior_alert_count=0,
        )

        assert tier == "summarized"

    def test_low_replay_value_returns_downsampled(self):
        """Low replay_value with no other signals should return 'downsampled'."""
        tier = retention_tier(
            replay_value=0.3,
            high_severity_count=0,
            failure_cluster_count=0,
            behavior_alert_count=0,
        )

        assert tier == "downsampled"

    def test_very_low_replay_value(self):
        """Very low replay_value should return 'downsampled'."""
        tier = retention_tier(
            replay_value=0.0,
            high_severity_count=0,
            failure_cluster_count=0,
            behavior_alert_count=0,
        )

        assert tier == "downsampled"

    def test_priority_high_severity_over_replay_value(self):
        """High severity should trigger 'full' even with low replay_value."""
        tier = retention_tier(
            replay_value=0.1,
            high_severity_count=1,
            failure_cluster_count=0,
            behavior_alert_count=0,
        )

        assert tier == "full"


class TestEventValue:
    """Tests for event_value function."""

    def test_extract_from_attribute(self):
        """Should extract value from event attribute if present."""
        event = _make_event()
        event.custom_field = "custom_value"

        value = event_value(event, "custom_field", "default")

        assert value == "custom_value"

    def test_extract_from_data_dict(self):
        """Should extract from data dict if attribute not found."""
        event = _make_event(data={"my_key": "my_value"})

        value = event_value(event, "my_key", "default")

        assert value == "my_value"

    def test_attribute_takes_precedence_over_data(self):
        """Attribute should take precedence over data dict."""
        event = _make_event(data={"conflict": "from_data"})
        event.conflict = "from_attr"

        value = event_value(event, "conflict", "default")

        assert value == "from_attr"

    def test_missing_key_returns_default(self):
        """Missing key should return default value."""
        event = _make_event()

        value = event_value(event, "nonexistent", "default_value")

        assert value == "default_value"

    def test_none_event_returns_default(self):
        """None event should return default."""
        value = event_value(None, "any_key", "default")

        assert value == "default"

    def test_default_none(self):
        """Default should be None if not specified."""
        event = _make_event()

        value = event_value(event, "nonexistent")

        assert value is None

    def test_data_dict_get_with_nested_key(self):
        """Should work with nested data dict values."""
        event = _make_event(data={"nested": {"key": "value"}})

        # Only gets top-level keys
        value = event_value(event, "nested", "default")

        assert value == {"key": "value"}

    def test_upstream_event_ids_extraction(self):
        """Should extract upstream_event_ids."""
        event = _make_event()
        event.upstream_event_ids = ["e1", "e2"]

        value = event_value(event, "upstream_event_ids", [])

        assert value == ["e1", "e2"]


class TestMean:
    """Tests for mean function."""

    def test_normal_list(self):
        """Should calculate mean of normal list."""
        result = mean([1.0, 2.0, 3.0, 4.0, 5.0])

        assert result == 3.0

    def test_empty_list_returns_zero(self):
        """Empty list should return 0.0."""
        result = mean([])

        assert result == 0.0

    def test_single_element(self):
        """Single element list should return that element."""
        result = mean([5.5])

        assert result == 5.5

    def test_negative_numbers(self):
        """Should handle negative numbers."""
        result = mean([-2.0, 2.0])

        assert result == 0.0

    def test_various_types_convert_to_float(self):
        """Should convert integers to float."""
        result = mean([1, 2, 3, 4])

        assert result == 2.5

    def test_fractional_values(self):
        """Should handle fractional values."""
        result = mean([0.5, 1.5, 2.5])

        assert result == 1.5

    def test_large_values(self):
        """Should handle large values."""
        result = mean([1000000.0, 2000000.0, 3000000.0])

        assert result == 2000000.0

    def test_all_zeros(self):
        """All zeros should return zero."""
        result = mean([0.0, 0.0, 0.0])

        assert result == 0.0

    def test_mixed_positive_and_negative(self):
        """Should average mixed positive and negative values."""
        result = mean([-10.0, 0.0, 10.0])

        assert result == 0.0
