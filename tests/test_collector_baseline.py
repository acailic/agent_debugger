"""Unit tests for collector/baseline.py internal helper functions and edge cases."""

from __future__ import annotations

from datetime import datetime, timezone

from agent_debugger_sdk.core.events import (
    AgentTurnEvent,
    DecisionEvent,
    EventType,
    PromptPolicyEvent,
    RefusalEvent,
    SafetyCheckEvent,
    Session,
    ToolResultEvent,
    TraceEvent,
)
from collector.baseline import (
    CRITICAL_THRESHOLD,
    WARNING_THRESHOLD,
    AgentBaseline,
    _build_multi_agent_metrics,
    _collect_session_event_metrics,
    _get_policy_template,
    _get_session_scalars,
    _get_speaker,
    _process_decision,
    _process_tool_result,
    _safe_div,
    _track_policy_shift,
    compute_baseline_from_sessions,
    detect_drift,
)


class TestSafeDiv:
    """Tests for _safe_div helper function."""

    def test_normal_division(self):
        """Normal division should work correctly."""
        assert _safe_div(10.0, 2) == 5.0
        assert _safe_div(7.0, 4) == 1.75

    def test_zero_denominator_returns_default(self):
        """Zero denominator should return default value."""
        assert _safe_div(10.0, 0) == 0.0
        assert _safe_div(10.0, 0, default=99.0) == 99.0

    def test_negative_numbers(self):
        """Negative numbers should divide correctly."""
        assert _safe_div(-10.0, 2) == -5.0
        assert _safe_div(10.0, -2) == -5.0

    def test_zero_numerator(self):
        """Zero numerator should return zero."""
        assert _safe_div(0.0, 5) == 0.0


class TestProcessDecision:
    """Tests for _process_decision helper function."""

    def test_decision_with_confidence_in_data(self):
        """Should extract confidence from data dict."""
        event = TraceEvent(
            id="ev1",
            session_id="s1",
            event_type=EventType.DECISION,
            name="decision",
        )
        data = {"confidence": 0.85, "evidence_event_ids": ["e1", "e2"]}

        confidence, low_conf, grounded = _process_decision(event, data)

        assert confidence == 0.85
        assert low_conf == 0  # confidence >= 0.5
        assert grounded == 1  # has evidence_event_ids

    def test_decision_with_low_confidence(self):
        """Should flag low confidence decisions."""
        event = TraceEvent(
            id="ev1",
            session_id="s1",
            event_type=EventType.DECISION,
            name="decision",
        )
        data = {"confidence": 0.3, "evidence_event_ids": []}

        confidence, low_conf, grounded = _process_decision(event, data)

        assert confidence == 0.3
        assert low_conf == 1  # confidence < 0.5
        assert grounded == 0  # no evidence_event_ids

    def test_decision_falls_back_to_event_attribute(self):
        """Should fall back to event attribute when data missing."""
        event = DecisionEvent(
            id="ev1",
            session_id="s1",
            confidence=0.75,
            evidence_event_ids=["e1"],
        )
        data = {}

        confidence, low_conf, grounded = _process_decision(event, data)

        assert confidence == 0.75
        assert low_conf == 0
        assert grounded == 1

    def test_decision_default_confidence(self):
        """Should use default confidence when not found."""
        event = TraceEvent(
            id="ev1",
            session_id="s1",
            event_type=EventType.DECISION,
            name="decision",
        )
        data = {}

        confidence, low_conf, grounded = _process_decision(event, data)

        assert confidence == 0.5  # default
        assert low_conf == 0  # 0.5 is not < 0.5
        assert grounded == 0

    def test_decision_with_none_confidence_in_data(self):
        """Should handle None confidence in data."""
        event = DecisionEvent(
            id="ev1",
            session_id="s1",
            confidence=0.9,
        )
        data = {"confidence": None}

        confidence, low_conf, grounded = _process_decision(event, data)

        assert confidence == 0.9  # falls back to attribute
        assert low_conf == 0
        assert grounded == 0


class TestProcessToolResult:
    """Tests for _process_tool_result helper function."""

    def test_tool_result_with_success(self):
        """Should extract duration and no error for successful result."""
        event = TraceEvent(
            id="ev1",
            session_id="s1",
            event_type=EventType.TOOL_RESULT,
            name="tool_result",
        )
        data = {"duration_ms": 123.5, "error": None}

        duration, error = _process_tool_result(event, data)

        assert duration == 123.5
        assert error == 0  # no error

    def test_tool_result_with_error(self):
        """Should extract duration and flag error."""
        event = TraceEvent(
            id="ev1",
            session_id="s1",
            event_type=EventType.TOOL_RESULT,
            name="tool_result",
        )
        data = {"duration_ms": 456.0, "error": "API timeout"}

        duration, error = _process_tool_result(event, data)

        assert duration == 456.0
        assert error == 1  # has error

    def test_tool_result_falls_back_to_event_attributes(self):
        """Should fall back to event attributes when data missing."""
        event = ToolResultEvent(
            id="ev1",
            session_id="s1",
            tool_name="search",
            result=["ok"],
            duration_ms=789.0,
            error="failed",
        )
        data = {}

        duration, error = _process_tool_result(event, data)

        assert duration == 789.0
        assert error == 1

    def test_tool_result_with_empty_string_error(self):
        """Should treat empty string error as no error."""
        event = TraceEvent(
            id="ev1",
            session_id="s1",
            event_type=EventType.TOOL_RESULT,
            name="tool_result",
        )
        data = {"duration_ms": 100.0, "error": ""}

        duration, error = _process_tool_result(event, data)

        assert duration == 100.0
        assert error == 0  # empty string is falsy

    def test_tool_result_with_zero_duration(self):
        """Should handle zero duration correctly."""
        event = TraceEvent(
            id="ev1",
            session_id="s1",
            event_type=EventType.TOOL_RESULT,
            name="tool_result",
        )
        data = {"duration_ms": 0.0, "error": None}

        duration, error = _process_tool_result(event, data)

        assert duration == 0.0
        assert error == 0


class TestGetSpeaker:
    """Tests for _get_speaker helper function."""

    def test_speaker_from_data_speaker_key(self):
        """Should extract speaker from 'speaker' key in data."""
        event = TraceEvent(
            id="ev1",
            session_id="s1",
            event_type=EventType.AGENT_TURN,
            name="turn",
        )
        data = {"speaker": "agent-1", "agent_id": "agent-2"}

        speaker = _get_speaker(event, data)

        assert speaker == "agent-1"

    def test_speaker_from_data_agent_id_key(self):
        """Should extract speaker from 'agent_id' key when 'speaker' missing."""
        event = TraceEvent(
            id="ev1",
            session_id="s1",
            event_type=EventType.AGENT_TURN,
            name="turn",
        )
        data = {"agent_id": "agent-2"}

        speaker = _get_speaker(event, data)

        assert speaker == "agent-2"

    def test_speaker_falls_back_to_event_attribute(self):
        """Should fall back to event attribute."""
        event = AgentTurnEvent(
            id="ev1",
            session_id="s1",
            speaker="agent-3",
            turn_index=1,
        )
        data = {}

        speaker = _get_speaker(event, data)

        assert speaker == "agent-3"

    def test_speaker_returns_none_when_not_found(self):
        """Should return None when speaker not found anywhere."""
        event = TraceEvent(
            id="ev1",
            session_id="s1",
            event_type=EventType.AGENT_TURN,
            name="turn",
        )
        data = {"other": "value"}

        speaker = _get_speaker(event, data)

        assert speaker is None


class TestGetPolicyTemplate:
    """Tests for _get_policy_template helper function."""

    def test_template_from_template_id_key(self):
        """Should extract template_id from data."""
        event = TraceEvent(
            id="ev1",
            session_id="s1",
            event_type=EventType.PROMPT_POLICY,
            name="policy",
        )
        data = {"template_id": "tpl-1", "name": "fallback"}

        template = _get_policy_template(event, data)

        assert template == "tpl-1"

    def test_template_falls_back_to_name_key(self):
        """Should fall back to 'name' key when template_id missing."""
        event = TraceEvent(
            id="ev1",
            session_id="s1",
            event_type=EventType.PROMPT_POLICY,
            name="policy",
        )
        data = {"name": "policy-name"}

        template = _get_policy_template(event, data)

        assert template == "policy-name"

    def test_template_falls_back_to_event_attribute(self):
        """Should fall back to event attribute."""
        event = PromptPolicyEvent(
            id="ev1",
            session_id="s1",
            template_id="tpl-event",
        )
        data = {}

        template = _get_policy_template(event, data)

        assert template == "tpl-event"

    def test_template_returns_none_when_not_found(self):
        """Should return None when template not found."""
        event = TraceEvent(
            id="ev1",
            session_id="s1",
            event_type=EventType.PROMPT_POLICY,
            name="policy",
        )
        data = {"other": "value"}

        template = _get_policy_template(event, data)

        assert template is None


class TestTrackPolicyShift:
    """Tests for _track_policy_shift helper function."""

    def test_first_template_sets_prev(self):
        """First template should set prev_template without incrementing count."""
        prev_template, shift_count = _track_policy_shift(None, None, 0)

        assert prev_template is None
        assert shift_count == 0

        prev_template, shift_count = _track_policy_shift("tpl-a", prev_template, shift_count)

        assert prev_template == "tpl-a"
        assert shift_count == 0

    def test_same_template_no_shift(self):
        """Same template should not increment shift count."""
        prev_template, shift_count = _track_policy_shift("tpl-a", "tpl-a", 0)

        assert prev_template == "tpl-a"
        assert shift_count == 0

    def test_different_template_increments_shift(self):
        """Different template should increment shift count."""
        prev_template, shift_count = _track_policy_shift("tpl-b", "tpl-a", 0)

        assert prev_template == "tpl-b"
        assert shift_count == 1

    def test_none_template_preserves_state(self):
        """None template should preserve previous state."""
        prev_template, shift_count = _track_policy_shift(None, "tpl-a", 5)

        assert prev_template == "tpl-a"
        assert shift_count == 5

    def test_multiple_shifts_accumulate(self):
        """Multiple shifts should accumulate count."""
        _, shift_count = _track_policy_shift("tpl-b", "tpl-a", 0)
        _, shift_count = _track_policy_shift("tpl-c", "tpl-b", shift_count)
        _, shift_count = _track_policy_shift("tpl-a", "tpl-c", shift_count)

        assert shift_count == 3


class TestGetSessionScalars:
    """Tests for _get_session_scalars helper function."""

    def test_extracts_all_scalars_from_session(self):
        """Should extract cost, tokens, and replay value from session."""
        session = Session(
            id="s1",
            agent_name="test",
            framework="test",
            total_cost_usd=1.23,
            total_tokens=456,
            replay_value=0.78,
        )

        cost, tokens, replay = _get_session_scalars(session)

        assert cost == 1.23
        assert tokens == 456
        assert replay == 0.78

    def test_handles_missing_attributes_with_defaults(self):
        """Should use defaults when attributes missing."""
        session = Session(
            id="s1",
            agent_name="test",
            framework="test",
        )

        cost, tokens, replay = _get_session_scalars(session)

        assert cost == 0
        assert tokens == 0
        assert replay == 0.0

    def test_handles_zero_values(self):
        """Should handle zero values correctly."""
        session = Session(
            id="s1",
            agent_name="test",
            framework="test",
            total_cost_usd=0.0,
            total_tokens=0,
            replay_value=0.0,
        )

        cost, tokens, replay = _get_session_scalars(session)

        assert cost == 0.0
        assert tokens == 0
        assert replay == 0.0


class TestBuildMultiAgentMetrics:
    """Tests for _build_multi_agent_metrics helper function."""

    def test_builds_metrics_with_all_values(self):
        """Should build metrics with all provided values."""
        metrics = _build_multi_agent_metrics(
            total_policy_shifts=10,
            total_turns=50,
            total_speakers=15,
            escalation_sessions=3,
            grounded_decisions=20,
            decision_count=25,
            session_count=5,
        )

        assert metrics.avg_policy_shifts_per_session == 2.0
        assert metrics.avg_turns_per_session == 10
        assert metrics.avg_speaker_count == 3.0
        assert metrics.escalation_pattern_rate == 0.6
        assert metrics.evidence_grounding_rate == 0.8

    def test_handles_zero_session_count(self):
        """Should handle zero session count with safe_div."""
        metrics = _build_multi_agent_metrics(
            total_policy_shifts=10,
            total_turns=50,
            total_speakers=15,
            escalation_sessions=3,
            grounded_decisions=20,
            decision_count=25,
            session_count=0,
        )

        assert metrics.avg_policy_shifts_per_session == 0.0
        assert metrics.avg_turns_per_session == 0
        assert metrics.avg_speaker_count == 0.0
        assert metrics.escalation_pattern_rate == 0.0
        assert metrics.evidence_grounding_rate == 0.8  # decision_count > 0

    def test_handles_zero_decision_count(self):
        """Should handle zero decision count for grounding rate."""
        metrics = _build_multi_agent_metrics(
            total_policy_shifts=10,
            total_turns=50,
            total_speakers=15,
            escalation_sessions=3,
            grounded_decisions=0,
            decision_count=0,
            session_count=5,
        )

        assert metrics.evidence_grounding_rate == 0.0


class TestCollectSessionEventMetrics:
    """Tests for _collect_session_event_metrics function."""

    def test_aggregates_decision_events(self):
        """Should aggregate decision confidence and counts."""
        events = [
            DecisionEvent(
                id="ev1",
                session_id="s1",
                confidence=0.8,
                evidence_event_ids=["e1"],
            ),
            DecisionEvent(
                id="ev2",
                session_id="s1",
                confidence=0.3,
                evidence_event_ids=[],
            ),
            DecisionEvent(
                id="ev3",
                session_id="s1",
                confidence=0.6,
                evidence_event_ids=["e2", "e3"],
            ),
        ]

        metrics = _collect_session_event_metrics(events)

        assert metrics["decision_count"] == 3
        assert metrics["decision_confidence"] == 0.8 + 0.3 + 0.6
        assert metrics["low_confidence_count"] == 1  # only 0.3
        assert metrics["grounded_decisions"] == 2  # ev1 and ev3

    def test_aggregates_tool_result_events(self):
        """Should aggregate tool duration and errors."""
        events = [
            ToolResultEvent(
                id="ev1",
                session_id="s1",
                tool_name="search",
                result=["ok"],
                duration_ms=100.0,
            ),
            ToolResultEvent(
                id="ev2",
                session_id="s1",
                tool_name="browse",
                result=[],
                error="timeout",
                duration_ms=200.0,
            ),
            ToolResultEvent(
                id="ev3",
                session_id="s1",
                tool_name="parse",
                result=["data"],
                duration_ms=150.0,
            ),
        ]

        metrics = _collect_session_event_metrics(events)

        assert metrics["tool_result_count"] == 3
        assert metrics["tool_duration"] == 450.0
        assert metrics["tool_error_count"] == 1  # only ev2

    def test_detects_refusal_events(self):
        """Should detect refusal and policy violation events."""
        events = [
            RefusalEvent(
                id="ev1",
                session_id="s1",
                reason="unsafe",
                policy_name="safety",
                risk_level="high",
            ),
            TraceEvent(
                id="ev2",
                session_id="s1",
                event_type=EventType.POLICY_VIOLATION,
                name="violation",
                data={"policy_name": "policy"},
            ),
            ToolResultEvent(
                id="ev3",
                session_id="s1",
                tool_name="test",
                result=[],
            ),
        ]

        metrics = _collect_session_event_metrics(events)

        assert metrics["has_refusal"] is True

    def test_detects_tool_loop_from_behavior_alert(self):
        """Should detect tool loop from behavior alert events."""
        events = [
            TraceEvent(
                id="ev1",
                session_id="s1",
                event_type=EventType.BEHAVIOR_ALERT,
                name="alert",
                data={"alert_type": "tool_loop"},
            ),
            TraceEvent(
                id="ev2",
                session_id="s1",
                event_type=EventType.BEHAVIOR_ALERT,
                name="alert",
                data={"alert_type": "oscillation"},
            ),
        ]

        metrics = _collect_session_event_metrics(events)

        assert metrics["has_tool_loop"] is True

    def test_aggregates_agent_turn_events(self):
        """Should aggregate agent turn speakers and count."""
        events = [
            AgentTurnEvent(
                id="ev1",
                session_id="s1",
                speaker="agent-1",
                turn_index=1,
            ),
            AgentTurnEvent(
                id="ev2",
                session_id="s1",
                speaker="agent-2",
                turn_index=2,
            ),
            AgentTurnEvent(
                id="ev3",
                session_id="s1",
                speaker="agent-1",
                turn_index=3,
            ),
            AgentTurnEvent(
                id="ev4",
                session_id="s1",
                speaker=None,
                turn_index=4,
            ),
        ]

        metrics = _collect_session_event_metrics(events)

        assert metrics["turn_count"] == 4
        assert metrics["speakers"] == {"agent-1", "agent-2"}  # None excluded

    def test_tracks_policy_shifts(self):
        """Should track policy template shifts."""
        events = [
            PromptPolicyEvent(
                id="ev1",
                session_id="s1",
                template_id="tpl-a",
            ),
            PromptPolicyEvent(
                id="ev2",
                session_id="s1",
                template_id="tpl-a",
            ),
            PromptPolicyEvent(
                id="ev3",
                session_id="s1",
                template_id="tpl-b",
            ),
            PromptPolicyEvent(
                id="ev4",
                session_id="s1",
                template_id="tpl-a",
            ),
        ]

        metrics = _collect_session_event_metrics(events)

        assert metrics["policy_shift_count"] == 2  # a->b, b->a

    def test_detects_escalation_events(self):
        """Should detect safety check and policy violation events."""
        events = [
            SafetyCheckEvent(
                id="ev1",
                session_id="s1",
                policy_name="safety",
                outcome="warn",
                risk_level="medium",
                blocked_action="send",
            ),
            TraceEvent(
                id="ev2",
                session_id="s1",
                event_type=EventType.POLICY_VIOLATION,
                name="violation",
            ),
        ]

        metrics = _collect_session_event_metrics(events)

        assert metrics["has_escalation"] is True

    def test_handles_empty_event_list(self):
        """Should handle empty event list."""
        metrics = _collect_session_event_metrics([])

        assert metrics["decision_count"] == 0
        assert metrics["tool_result_count"] == 0
        assert metrics["turn_count"] == 0
        assert metrics["decision_confidence"] == 0.0
        assert metrics["has_refusal"] is False
        assert metrics["has_tool_loop"] is False
        assert metrics["has_escalation"] is False
        assert metrics["speakers"] == set()
        assert metrics["policy_shift_count"] == 0

    def test_ignores_events_without_data(self):
        """Should handle events with missing data gracefully."""
        events = [
            TraceEvent(
                id="ev1",
                session_id="s1",
                event_type=EventType.DECISION,
                name="decision",
                data=None,
            ),
            TraceEvent(
                id="ev2",
                session_id="s1",
                event_type=EventType.TOOL_RESULT,
                name="tool",
            ),
        ]

        metrics = _collect_session_event_metrics(events)

        # Should not crash, just use empty data
        assert metrics["decision_count"] == 1  # ev1 counted


class TestComputeBaselineFromSessionsEdgeCases:
    """Tests for compute_baseline_from_sessions edge cases."""

    def test_computed_at_defaults_to_now(self):
        """Should use current time when computed_at not provided."""
        before = datetime.now(timezone.utc)
        baseline = compute_baseline_from_sessions(
            agent_name="test",
            sessions=[],
            events_by_session={},
        )
        after = datetime.now(timezone.utc)

        assert before <= baseline.computed_at <= after

    def test_uses_provided_computed_at(self):
        """Should use provided computed_at timestamp."""
        computed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        baseline = compute_baseline_from_sessions(
            agent_name="test",
            sessions=[],
            events_by_session={},
            computed_at=computed_at,
        )

        assert baseline.computed_at == computed_at

    def test_sessions_with_no_events(self):
        """Should handle sessions with no events."""
        sessions = [
            Session(
                id="s1",
                agent_name="test",
                framework="test",
                total_tokens=100,
                total_cost_usd=0.01,
            ),
            Session(
                id="s2",
                agent_name="test",
                framework="test",
                total_tokens=200,
                total_cost_usd=0.02,
            ),
        ]

        baseline = compute_baseline_from_sessions(
            agent_name="test",
            sessions=sessions,
            events_by_session={},
        )

        assert baseline.session_count == 2
        assert baseline.avg_tokens_per_session == 150
        assert baseline.avg_cost_per_session == 0.015
        assert baseline.avg_decision_confidence == 0.0  # no decisions

    def test_events_for_nonexistent_session(self):
        """Should ignore events for sessions not in the sessions list."""
        session = Session(
            id="s1",
            agent_name="test",
            framework="test",
        )
        events = [
            DecisionEvent(
                id="ev1",
                session_id="s1",
                confidence=0.8,
            ),
            DecisionEvent(
                id="ev2",
                session_id="s2",  # not in sessions list
                confidence=0.5,
            ),
        ]

        baseline = compute_baseline_from_sessions(
            agent_name="test",
            sessions=[session],
            events_by_session={"s1": events, "s2": [events[1]]},
        )

        # Should only count ev1 from s1
        assert baseline.session_count == 1
        # ev2 for s2 should be ignored since s2 not in sessions

    def test_escalation_detection_with_policy_shifts(self):
        """Should detect escalation when policy_shift_count > 2."""
        session = Session(
            id="s1",
            agent_name="test",
            framework="test",
        )
        events = [
            PromptPolicyEvent(id=f"ev{i}", session_id="s1", template_id=f"tpl-{i % 3}")
            for i in range(5)  # 4 shifts
        ]

        baseline = compute_baseline_from_sessions(
            agent_name="test",
            sessions=[session],
            events_by_session={"s1": events},
            include_multi_agent=True,
        )

        # Should trigger escalation due to > 2 policy shifts
        assert baseline.multi_agent_metrics is not None
        assert baseline.multi_agent_metrics.escalation_pattern_rate == 1.0

    def test_tool_loop_rate_calculation(self):
        """Should correctly calculate tool loop rate."""
        sessions = []
        events_by_session = {}
        for i in range(5):
            session = Session(id=f"s{i}", agent_name="test", framework="test")
            sessions.append(session)
            events = [
                TraceEvent(
                    id=f"ev{i}",
                    session_id=session.id,
                    event_type=EventType.BEHAVIOR_ALERT,
                    name="alert",
                    data={"alert_type": "tool_loop"},
                )
                if i < 2
                else TraceEvent(
                    id=f"ev{i}",
                    session_id=session.id,
                    event_type=EventType.DECISION,
                    name="decision",
                )
            ]
            events_by_session[session.id] = events

        baseline = compute_baseline_from_sessions(
            agent_name="test",
            sessions=sessions,
            events_by_session=events_by_session,
        )

        assert baseline.tool_loop_rate == 0.4  # 2 out of 5 sessions

    def test_refusal_rate_calculation(self):
        """Should correctly calculate refusal rate."""
        sessions = []
        events_by_session = {}
        for i in range(4):
            session = Session(id=f"s{i}", agent_name="test", framework="test")
            sessions.append(session)
            events = (
                [
                    RefusalEvent(
                        id=f"ev{i}",
                        session_id=session.id,
                        reason="unsafe",
                        policy_name="policy",
                        risk_level="high",
                    )
                ]
                if i < 1
                else [
                    DecisionEvent(
                        id=f"ev{i}",
                        session_id=session.id,
                        confidence=0.8,
                    )
                ]
            )
            events_by_session[session.id] = events

        baseline = compute_baseline_from_sessions(
            agent_name="test",
            sessions=sessions,
            events_by_session=events_by_session,
        )

        assert baseline.refusal_rate == 0.25  # 1 out of 4 sessions


class TestDetectDriftEdgeCases:
    """Tests for detect_drift edge cases and thresholds."""

    def test_warning_threshold_constant(self):
        """WARNING_THRESHOLD should be 0.25 (25%)."""
        assert WARNING_THRESHOLD == 0.25

    def test_critical_threshold_constant(self):
        """CRITICAL_THRESHOLD should be 0.50 (50%)."""
        assert CRITICAL_THRESHOLD == 0.50

    def test_custom_thresholds(self):
        """Should use custom thresholds when provided."""
        baseline = AgentBaseline(
            agent_name="test",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.8,
        )
        current = AgentBaseline(
            agent_name="test",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.5,  # 37.5% decrease
        )

        # With default thresholds (25% warning, 50% critical)
        alerts_default = detect_drift(baseline, current)
        assert len(alerts_default) == 1
        assert alerts_default[0].severity == "warning"

        # With custom thresholds (10% warning, 20% critical)
        alerts_custom = detect_drift(baseline, current, warning_threshold=0.10, critical_threshold=0.20)
        assert len(alerts_custom) == 1
        assert alerts_custom[0].severity == "critical"

    def test_negative_baseline_skips_drift(self):
        """Should skip drift detection for negative baseline values."""
        baseline = AgentBaseline(
            agent_name="test",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=-0.1,  # negative - invalid
        )
        current = AgentBaseline(
            agent_name="test",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.8,
        )

        alerts = detect_drift(baseline, current)

        assert len(alerts) == 0  # negative baseline skipped

    def test_negative_current_skips_drift(self):
        """Should skip drift detection for negative current values."""
        baseline = AgentBaseline(
            agent_name="test",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.8,
        )
        current = AgentBaseline(
            agent_name="test",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=-0.1,  # negative - invalid
        )

        alerts = detect_drift(baseline, current)

        assert len(alerts) == 0  # negative current skipped

    def test_both_zero_no_drift(self):
        """Should not trigger drift when both values are zero."""
        baseline = AgentBaseline(
            agent_name="test",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            tool_loop_rate=0.0,
        )
        current = AgentBaseline(
            agent_name="test",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            tool_loop_rate=0.0,
        )

        alerts = detect_drift(baseline, current)

        assert len(alerts) == 0

    def test_exact_warning_threshold_boundary(self):
        """Should trigger warning at exact warning threshold."""
        baseline = AgentBaseline(
            agent_name="test",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.8,
        )
        # 0.8 * 0.25 = 0.2, so 0.6 is exactly at warning threshold
        current = AgentBaseline(
            agent_name="test",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.6,  # 25% decrease
        )

        alerts = detect_drift(baseline, current)

        assert len(alerts) == 1
        assert alerts[0].severity == "warning"

    def test_exact_critical_threshold_boundary(self):
        """Should trigger critical at exact critical threshold."""
        baseline = AgentBaseline(
            agent_name="test",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.8,
        )
        # 0.8 * 0.5 = 0.4, so 0.4 is exactly at critical threshold
        current = AgentBaseline(
            agent_name="test",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.4,  # 50% decrease
        )

        alerts = detect_drift(baseline, current)

        assert len(alerts) == 1
        assert alerts[0].severity == "critical"

    def test_alert_description_format(self):
        """Alert descriptions should be formatted correctly."""
        baseline = AgentBaseline(
            agent_name="test",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.8,
        )
        current = AgentBaseline(
            agent_name="test",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.4,
        )

        alerts = detect_drift(baseline, current)

        assert len(alerts) == 1
        assert "decreased" in alerts[0].description.lower()
        assert "0.8" in alerts[0].description
        assert "0.4" in alerts[0].description

    def test_alert_includes_likely_cause(self):
        """Alerts should include likely cause when provided."""
        baseline = AgentBaseline(
            agent_name="test",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            error_rate=0.1,
        )
        current = AgentBaseline(
            agent_name="test",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            error_rate=0.2,
        )

        alerts = detect_drift(baseline, current)

        assert len(alerts) == 1
        assert alerts[0].likely_cause is not None
        assert "API" in alerts[0].likely_cause or "degradation" in alerts[0].likely_cause

    def test_alert_sorting_by_change_percent(self):
        """Alerts of same severity should be sorted by change percent."""
        baseline = AgentBaseline(
            agent_name="test",
            session_count=5,
            computed_at=datetime.now(timezone.utc),
            refusal_rate=0.1,
            tool_loop_rate=0.1,
        )
        current = AgentBaseline(
            agent_name="test",
            session_count=3,
            computed_at=datetime.now(timezone.utc),
            refusal_rate=0.3,  # 200% increase
            tool_loop_rate=0.2,  # 100% increase
        )

        alerts = detect_drift(baseline, current)

        assert len(alerts) == 2
        # Both critical, refusal_rate has higher change percent
        assert alerts[0].metric == "refusal_rate"
        assert alerts[1].metric == "tool_loop_rate"


class TestIntegrationScenarios:
    """Integration tests combining multiple features."""

    def test_full_multi_agent_session_workflow(self):
        """Test full workflow with multi-agent session data."""
        sessions = [
            Session(
                id="s1",
                agent_name="multi-agent",
                framework="autogen",
                total_tokens=2000,
                total_cost_usd=0.05,
                replay_value=0.7,
            ),
            Session(
                id="s2",
                agent_name="multi-agent",
                framework="autogen",
                total_tokens=1500,
                total_cost_usd=0.03,
                replay_value=0.6,
            ),
        ]

        events_by_session = {
            "s1": [
                AgentTurnEvent(id="ev1", session_id="s1", speaker="agent-1", turn_index=1),
                AgentTurnEvent(id="ev2", session_id="s1", speaker="agent-2", turn_index=2),
                DecisionEvent(id="ev3", session_id="s1", confidence=0.8, evidence_event_ids=["e1"]),
                PromptPolicyEvent(id="ev4", session_id="s1", template_id="tpl-a"),
                PromptPolicyEvent(id="ev5", session_id="s1", template_id="tpl-b"),
                ToolResultEvent(id="ev6", session_id="s1", tool_name="search", result=["ok"], duration_ms=100),
            ],
            "s2": [
                AgentTurnEvent(id="ev7", session_id="s2", speaker="agent-1", turn_index=1),
                DecisionEvent(id="ev8", session_id="s2", confidence=0.3),
                SafetyCheckEvent(
                    id="ev9",
                    session_id="s2",
                    policy_name="safety",
                    outcome="warn",
                    risk_level="medium",
                    blocked_action="send",
                ),
                ToolResultEvent(
                    id="ev10", session_id="s2", tool_name="browse", result=[], error="fail", duration_ms=200
                ),
            ],
        }

        baseline = compute_baseline_from_sessions(
            agent_name="multi-agent",
            sessions=sessions,
            events_by_session=events_by_session,
            include_multi_agent=True,
        )

        assert baseline.session_count == 2
        assert baseline.avg_decision_confidence == 0.55  # (0.8 + 0.3) / 2
        assert baseline.low_confidence_rate == 0.5  # 1 out of 2
        assert baseline.avg_tokens_per_session == 1750  # (2000 + 1500) / 2
        assert baseline.avg_cost_per_session == 0.04  # (0.05 + 0.03) / 2
        assert baseline.error_rate == 0.5  # 1 out of 2 tool results
        assert baseline.multi_agent_metrics is not None
        assert baseline.multi_agent_metrics.avg_turns_per_session == 1  # (2 + 0) / 2
        assert baseline.multi_agent_metrics.avg_speaker_count == 1.5  # (2 + 1) / 2
        assert baseline.multi_agent_metrics.escalation_pattern_rate == 0.5  # 1 out of 2
        assert baseline.multi_agent_metrics.avg_policy_shifts_per_session == 0.5  # (1 + 0) / 2

    def test_drift_detection_comprehensive_scenario(self):
        """Test drift detection with multiple metrics."""
        baseline = AgentBaseline(
            agent_name="test",
            session_count=10,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.8,
            low_confidence_rate=0.1,
            avg_tool_duration_ms=100.0,
            error_rate=0.05,
            avg_cost_per_session=0.10,
            tool_loop_rate=0.0,
            refusal_rate=0.0,
        )

        current = AgentBaseline(
            agent_name="test",
            session_count=10,
            computed_at=datetime.now(timezone.utc),
            avg_decision_confidence=0.5,  # 37.5% decrease - warning
            avg_tool_duration_ms=150.0,  # 50% increase - critical
            error_rate=0.08,  # 60% increase - critical
            avg_cost_per_session=0.12,  # 20% increase - no alert (below warning)
            tool_loop_rate=0.3,  # zero to non-zero - warning
            refusal_rate=0.2,  # zero to non-zero - warning
        )

        alerts = detect_drift(baseline, current)

        # Should have 5 alerts (low_confidence_rate is not checked by detect_drift)
        assert len(alerts) == 5

        # Check that criticals come first
        critical_count = sum(1 for a in alerts if a.severity == "critical")
        warning_count = sum(1 for a in alerts if a.severity == "warning")
        assert critical_count == 2
        assert warning_count == 3

        # Verify sorting: criticals first, then by change percent
        for i in range(critical_count - 1):
            assert alerts[i].severity == "critical"
        for i in range(critical_count, len(alerts)):
            assert alerts[i].severity == "warning"
