"""Unit tests for the TraceIntelligence facade in collector/intelligence/.

These tests exercise the facade directly with pure inputs, no app_context
or database required.
"""

from __future__ import annotations

from agent_debugger_sdk.core.events import Checkpoint, EventType, TraceEvent
from collector.intelligence import TraceIntelligence


def _make_event(event_type: EventType = EventType.TOOL_CALL, session_id: str = "s1", **overrides) -> TraceEvent:
    return TraceEvent(
        session_id=session_id,
        event_type=event_type,
        name=event_type.value,
        **overrides,
    )


def _make_checkpoint(session_id: str = "s1", event_id: str = "e1", sequence: int = 1) -> Checkpoint:
    return Checkpoint(
        session_id=session_id,
        event_id=event_id,
        sequence=sequence,
    )


class TestAnalyzeSessionEmpty:
    """Edge case: empty event list."""

    def test_returns_zero_replay_value(self):
        intel = TraceIntelligence()
        result = intel.analyze_session([], [])

        assert result["session_replay_value"] == 0.0
        assert result["retention_tier"] == "downsampled"

    def test_returns_empty_rankings(self):
        intel = TraceIntelligence()
        result = intel.analyze_session([], [])

        assert result["event_rankings"] == []
        assert result["failure_clusters"] == []
        assert result["behavior_alerts"] == []

    def test_returns_empty_live_summary(self):
        intel = TraceIntelligence()
        result = intel.analyze_session([], [])

        assert result["live_summary"]["event_count"] == 0
        assert result["live_summary"]["checkpoint_count"] == 0


class TestAnalyzeSessionWithEvents:
    """Happy path: events produce rankings and metrics."""

    def test_single_event_produces_one_ranking(self):
        intel = TraceIntelligence()
        events = [_make_event(EventType.TOOL_CALL)]
        result = intel.analyze_session(events, [])

        assert len(result["event_rankings"]) == 1
        assert result["session_summary"]["failure_count"] == 0

    def test_error_event_produces_failure_cluster(self):
        intel = TraceIntelligence()
        events = [_make_event(EventType.ERROR, data={"error_message": "boom"})]
        result = intel.analyze_session(events, [])

        # Error events should have high severity and appear in failure analysis
        ranking = result["event_rankings"][0]
        assert ranking["severity"] >= 0.9

    def test_multiple_events_sorted_by_composite(self):
        intel = TraceIntelligence()
        events = [
            _make_event(EventType.TOOL_CALL),
            _make_event(EventType.ERROR, data={"error_message": "fail"}),
            _make_event(EventType.DECISION),
        ]
        result = intel.analyze_session(events, [])

        assert len(result["event_rankings"]) == 3
        # Error should have highest composite
        composites = [r["composite"] for r in result["event_rankings"]]
        assert max(composites) == composites[1]  # error is index 1

    def test_replay_value_between_zero_and_one(self):
        intel = TraceIntelligence()
        events = [_make_event(EventType.ERROR), _make_event(EventType.TOOL_CALL)]
        result = intel.analyze_session(events, [])

        assert 0.0 <= result["session_replay_value"] <= 1.0


class TestAnalyzeSessionToolLoops:
    """Tool loop detection should produce behavior alerts."""

    def test_repeated_tool_calls_trigger_alert(self):
        intel = TraceIntelligence()
        events = [
            _make_event(EventType.TOOL_CALL, data={"tool_name": "search", "arguments": {"q": "test"}}),
            _make_event(EventType.TOOL_CALL, data={"tool_name": "search", "arguments": {"q": "test"}}),
            _make_event(EventType.TOOL_CALL, data={"tool_name": "search", "arguments": {"q": "test"}}),
        ]
        result = intel.analyze_session(events, [])

        assert len(result["behavior_alerts"]) > 0


class TestAnalyzeSessionWithCheckpoints:
    """Checkpoints should appear in rankings and summary."""

    def test_checkpoint_count_in_summary(self):
        intel = TraceIntelligence()
        events = [_make_event()]
        checkpoints = [_make_checkpoint(sequence=1), _make_checkpoint(sequence=2)]
        result = intel.analyze_session(events, checkpoints)

        assert result["session_summary"]["checkpoint_count"] == 2

    def test_checkpoint_rankings_produced(self):
        intel = TraceIntelligence()
        events = [_make_event()]  # id is auto-generated
        event_id = events[0].id
        checkpoints = [_make_checkpoint(event_id=event_id)]
        result = intel.analyze_session(events, checkpoints)

        assert len(result["checkpoint_rankings"]) == 1


class TestBuildLiveSummary:
    """Live summary construction."""

    def test_event_count_matches(self):
        intel = TraceIntelligence()
        events = [_make_event(), _make_event()]
        result = intel.build_live_summary(events, [])

        assert result["event_count"] == 2

    def test_checkpoint_count_matches(self):
        intel = TraceIntelligence()
        checkpoints = [_make_checkpoint(), _make_checkpoint()]
        result = intel.build_live_summary([], checkpoints)

        assert result["checkpoint_count"] == 2


class TestUtilityMethods:
    """Individual facade utility methods."""

    def test_fingerprint_returns_string(self):
        intel = TraceIntelligence()
        event = _make_event(EventType.ERROR)
        fp = intel.fingerprint(event)
        assert isinstance(fp, str)
        assert len(fp) > 0

    def test_severity_error_high(self):
        intel = TraceIntelligence()
        event = _make_event(EventType.ERROR)
        assert intel.severity(event) >= 0.9

    def test_severity_tool_call_low(self):
        intel = TraceIntelligence()
        event = _make_event(EventType.TOOL_CALL)
        assert intel.severity(event) < 0.5

    def test_event_headline_returns_string(self):
        intel = TraceIntelligence()
        event = _make_event(EventType.TOOL_CALL)
        headline = intel.event_headline(event)
        assert isinstance(headline, str)

    def test_is_failure_event_true_for_error(self):
        intel = TraceIntelligence()
        event = _make_event(EventType.ERROR)
        assert intel.is_failure_event(event) is True

    def test_is_failure_event_false_for_tool_call(self):
        intel = TraceIntelligence()
        event = _make_event(EventType.TOOL_CALL)
        assert intel.is_failure_event(event) is False

    def test_retention_tier_full_for_high_replay_value(self):
        intel = TraceIntelligence()
        tier = intel.retention_tier(
            replay_value=0.8,
            high_severity_count=1,
            failure_cluster_count=1,
            behavior_alert_count=0,
        )
        assert tier == "full"

    def test_retention_tier_downsampled_for_low_replay_value(self):
        intel = TraceIntelligence()
        tier = intel.retention_tier(
            replay_value=0.1,
            high_severity_count=0,
            failure_cluster_count=0,
            behavior_alert_count=0,
        )
        assert tier == "downsampled"
