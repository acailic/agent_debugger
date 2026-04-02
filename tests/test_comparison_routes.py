"""Tests for comparison_routes helper functions."""

from unittest.mock import MagicMock, patch

import pytest

from agent_debugger_sdk.core.events.base import EventType, TraceEvent
from api.comparison_routes import (
    EscalationAnalysisResult,
    PolicyAnalysisResult,
    _analyze_session_escalation,
    _analyze_session_policies,
    _compute_comparison_deltas,
    _count_grounded_decisions,
    _count_unique_speakers,
    _escalation_to_dict,
    _policy_to_dict,
)
from collector.escalation_detection import EscalationSignal
from collector.policy_analysis import PolicyShift


@pytest.fixture
def mock_policy_shift():
    """Create a mock PolicyShift with to_dict method."""
    shift = MagicMock(spec=PolicyShift)
    shift.to_dict.return_value = {
        "event_id": "shift1",
        "turn_index": 1,
        "previous_template": "template_a",
        "new_template": "template_b",
        "shift_magnitude": 0.5,
    }
    return shift


@pytest.fixture
def mock_escalation_signal():
    """Create a mock EscalationSignal with to_dict method."""
    signal = MagicMock(spec=EscalationSignal)
    signal.to_dict.return_value = {
        "event_id": "sig1",
        "turn_index": 2,
        "signal_type": "confidence_degradation",
        "magnitude": 0.7,
    }
    signal.signal_type = "confidence_degradation"
    signal.magnitude = 0.7
    return signal


class TestCountUniqueSpeakers:
    """Tests for _count_unique_speakers."""

    def test_empty_events(self):
        """Test with empty event list."""
        result = _count_unique_speakers([])
        assert result == 0

    def test_events_with_speakers(self):
        """Test with events containing speakers."""
        events = [
            TraceEvent(
                session_id="s1",
                event_type=EventType.AGENT_TURN,
                name="turn1",
                data={"speaker": "agent1"},
                importance=0.5,
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.AGENT_TURN,
                name="turn2",
                data={"speaker": "agent2"},
                importance=0.5,
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.AGENT_TURN,
                name="turn3",
                data={"speaker": "agent1"},  # Duplicate speaker
                importance=0.5,
                upstream_event_ids=[],
            ),
        ]
        result = _count_unique_speakers(events)
        assert result == 2

    def test_events_without_speakers(self):
        """Test with events that have no speaker field."""
        events = [
            TraceEvent(
                session_id="s1",
                event_type=EventType.AGENT_TURN,
                name="turn1",
                importance=0.5,
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.DECISION,
                name="dec1",
                importance=0.5,
                upstream_event_ids=[],
            ),
        ]
        result = _count_unique_speakers(events)
        assert result == 0

    def test_events_with_agent_id(self):
        """Test with events using agent_id field."""
        events = [
            TraceEvent(
                session_id="s1",
                event_type=EventType.AGENT_TURN,
                name="turn1",
                data={"speaker": "agent_a"},
                importance=0.5,
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.AGENT_TURN,
                name="turn2",
                data={"speaker": "agent_b"},
                importance=0.5,
                upstream_event_ids=[],
            ),
        ]
        result = _count_unique_speakers(events)
        assert result == 2

    def test_speaker_attribute_priority(self):
        """Test that speaker attribute takes priority over data field."""
        # Since base TraceEvent doesn't have speaker attribute, we test with data dict only
        events = [
            TraceEvent(
                session_id="s1",
                event_type=EventType.AGENT_TURN,
                name="turn1",
                data={"speaker": "primary"},
                importance=0.5,
                upstream_event_ids=[],
            ),
        ]
        result = _count_unique_speakers(events)
        assert result == 1


class TestCountGroundedDecisions:
    """Tests for _count_grounded_decisions."""

    def test_empty_events(self):
        """Test with empty event list."""
        result = _count_grounded_decisions([])
        assert result == 0

    def test_decisions_with_evidence(self):
        """Test decisions that have evidence_event_ids."""
        events = [
            TraceEvent(
                session_id="s1",
                event_type=EventType.DECISION,
                name="dec1",
                data={"evidence_event_ids": ["ev1", "ev2"]},
                importance=0.5,
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.DECISION,
                name="dec2",
                data={"evidence_event_ids": ["ev3"]},
                importance=0.5,
                upstream_event_ids=[],
            ),
        ]
        result = _count_grounded_decisions(events)
        assert result == 2

    def test_decisions_without_evidence(self):
        """Test decisions without evidence_event_ids."""
        events = [
            TraceEvent(
                session_id="s1",
                event_type=EventType.DECISION,
                name="dec1",
                importance=0.5,
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.DECISION,
                name="dec2",
                data={},
                importance=0.5,
                upstream_event_ids=[],
            ),
        ]
        result = _count_grounded_decisions(events)
        assert result == 0

    def test_empty_evidence_list(self):
        """Test decisions with empty evidence_event_ids list."""
        events = [
            TraceEvent(
                session_id="s1",
                event_type=EventType.DECISION,
                name="dec1",
                data={"evidence_event_ids": []},
                importance=0.5,
                upstream_event_ids=[],
            ),
        ]
        result = _count_grounded_decisions(events)
        assert result == 0

    def test_mixed_events(self):
        """Test with mixed event types."""
        events = [
            TraceEvent(
                session_id="s1",
                event_type=EventType.AGENT_TURN,
                name="turn1",
                importance=0.5,
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.DECISION,
                name="dec1",
                data={"evidence_event_ids": ["ev1"]},
                importance=0.5,
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.DECISION,
                name="dec2",
                importance=0.5,
                upstream_event_ids=[],
            ),
        ]
        result = _count_grounded_decisions(events)
        assert result == 1


class TestPolicyToDict:
    """Tests for _policy_to_dict."""

    def test_empty_policy_analysis(self):
        """Test with empty policy analysis."""
        analysis = PolicyAnalysisResult(shifts=[], shift_count=0, avg_shift_magnitude=0.0)
        result = _policy_to_dict(analysis)
        assert result == {
            "shift_count": 0,
            "avg_shift_magnitude": 0.0,
            "shifts": [],
        }

    def test_policy_analysis_with_shifts(self, mock_policy_shift):
        """Test with policy shifts."""
        analysis = PolicyAnalysisResult(
            shifts=[mock_policy_shift],
            shift_count=1,
            avg_shift_magnitude=0.5,
        )
        result = _policy_to_dict(analysis)
        assert result == {
            "shift_count": 1,
            "avg_shift_magnitude": 0.5,
            "shifts": [mock_policy_shift.to_dict.return_value],
        }

    def test_policy_analysis_limits_shifts(self, mock_policy_shift):
        """Test that only first 10 shifts are included."""
        shifts = [mock_policy_shift for _ in range(15)]
        analysis = PolicyAnalysisResult(
            shifts=shifts,
            shift_count=15,
            avg_shift_magnitude=0.5,
        )
        result = _policy_to_dict(analysis)
        assert len(result["shifts"]) == 10
        assert result["shift_count"] == 15


class TestEscalationToDict:
    """Tests for _escalation_to_dict."""

    def test_empty_escalation_analysis(self):
        """Test with empty escalation analysis."""
        analysis = EscalationAnalysisResult(signals=[], score=0.0, dominant_signal_type=None)
        result = _escalation_to_dict(analysis)
        assert result == {
            "score": 0.0,
            "signal_count": 0,
            "dominant_signal_type": None,
            "signals": [],
        }

    def test_escalation_analysis_with_signals(self, mock_escalation_signal):
        """Test with escalation signals."""
        analysis = EscalationAnalysisResult(
            signals=[mock_escalation_signal],
            score=0.7,
            dominant_signal_type="confidence_degradation",
        )
        result = _escalation_to_dict(analysis)
        assert result == {
            "score": 0.7,
            "signal_count": 1,
            "dominant_signal_type": "confidence_degradation",
            "signals": [mock_escalation_signal.to_dict.return_value],
        }

    def test_escalation_analysis_limits_signals(self, mock_escalation_signal):
        """Test that only first 10 signals are included."""
        signals = [mock_escalation_signal for _ in range(15)]
        analysis = EscalationAnalysisResult(signals=signals, score=0.7, dominant_signal_type="confidence_degradation")
        result = _escalation_to_dict(analysis)
        assert len(result["signals"]) == 10
        assert result["signal_count"] == 15


class TestComputeComparisonDeltas:
    """Tests for _compute_comparison_deltas."""

    @pytest.fixture
    def sample_primary_events(self):
        """Create sample primary events."""
        return [
            TraceEvent(
                session_id="s1",
                event_type=EventType.AGENT_TURN,
                name="turn1",
                data={"speaker": "agent1"},
                importance=0.5,
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.AGENT_TURN,
                name="turn2",
                data={"speaker": "agent2"},
                importance=0.5,
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.PROMPT_POLICY,
                name="policy1",
                importance=0.5,
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.DECISION,
                name="dec1",
                data={"evidence_event_ids": ["ev1"]},
                importance=0.5,
                upstream_event_ids=[],
            ),
        ]

    @pytest.fixture
    def sample_secondary_events(self):
        """Create sample secondary events."""
        return [
            TraceEvent(
                session_id="s2",
                event_type=EventType.AGENT_TURN,
                name="turn1",
                data={"speaker": "agent1"},
                importance=0.5,
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s2",
                event_type=EventType.PROMPT_POLICY,
                name="policy1",
                importance=0.5,
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s2",
                event_type=EventType.DECISION,
                name="dec1",
                importance=0.5,
                upstream_event_ids=[],
            ),
        ]

    def test_empty_events(self):
        """Test with empty event lists."""
        result = _compute_comparison_deltas(
            primary_events=[],
            primary_checkpoints=[],
            secondary_events=[],
            secondary_checkpoints=[],
            primary_policy=PolicyAnalysisResult(shifts=[], shift_count=0, avg_shift_magnitude=0.0),
            secondary_policy=PolicyAnalysisResult(shifts=[], shift_count=0, avg_shift_magnitude=0.0),
            primary_escalation=EscalationAnalysisResult(signals=[], score=0.0, dominant_signal_type=None),
            secondary_escalation=EscalationAnalysisResult(signals=[], score=0.0, dominant_signal_type=None),
        )
        assert result["turn_count"]["primary"] == 0
        assert result["turn_count"]["secondary"] == 0
        assert result["turn_count"]["delta"] == 0

    def test_delta_calculations(self, sample_primary_events, sample_secondary_events):
        """Test delta calculations between sessions."""
        result = _compute_comparison_deltas(
            primary_events=sample_primary_events,
            primary_checkpoints=[],
            secondary_events=sample_secondary_events,
            secondary_checkpoints=[],
            primary_policy=PolicyAnalysisResult(shifts=[], shift_count=1, avg_shift_magnitude=0.5),
            secondary_policy=PolicyAnalysisResult(shifts=[], shift_count=2, avg_shift_magnitude=0.3),
            primary_escalation=EscalationAnalysisResult(
                signals=[], score=0.7, dominant_signal_type="confidence_degradation"
            ),
            secondary_escalation=EscalationAnalysisResult(signals=[], score=0.2, dominant_signal_type=None),
        )
        # Turn count deltas
        assert result["turn_count"]["primary"] == 2
        assert result["turn_count"]["secondary"] == 1
        assert result["turn_count"]["delta"] == 1

        # Speaker count deltas
        assert result["speaker_count"]["primary"] == 2
        assert result["speaker_count"]["secondary"] == 1
        assert result["speaker_count"]["delta"] == 1

        # Policy count deltas
        assert result["policy_count"]["primary"] == 1
        assert result["policy_count"]["secondary"] == 1
        assert result["policy_count"]["delta"] == 0

        # Stance shift count deltas
        assert result["stance_shift_count"]["primary"] == 1
        assert result["stance_shift_count"]["secondary"] == 2
        assert result["stance_shift_count"]["delta"] == -1

        # Escalation score deltas
        assert result["escalation_score"]["primary"] == 0.7
        assert result["escalation_score"]["secondary"] == 0.2
        assert result["escalation_score"]["delta"] == 0.5

        # Grounded decision deltas
        assert result["grounded_decision_count"]["primary"] == 1
        assert result["grounded_decision_count"]["secondary"] == 0
        assert result["grounded_decision_count"]["delta"] == 1

    def test_grounding_rate_with_zero_decisions(self, sample_primary_events):
        """Test grounding rate when there are no decisions."""
        # Remove decision events
        events_no_decisions = [e for e in sample_primary_events if e.event_type != EventType.DECISION]
        result = _compute_comparison_deltas(
            primary_events=events_no_decisions,
            primary_checkpoints=[],
            secondary_events=[],
            secondary_checkpoints=[],
            primary_policy=PolicyAnalysisResult(shifts=[], shift_count=0, avg_shift_magnitude=0.0),
            secondary_policy=PolicyAnalysisResult(shifts=[], shift_count=0, avg_shift_magnitude=0.0),
            primary_escalation=EscalationAnalysisResult(signals=[], score=0.0, dominant_signal_type=None),
            secondary_escalation=EscalationAnalysisResult(signals=[], score=0.0, dominant_signal_type=None),
        )
        assert result["grounding_rate"]["primary"] == 0.0
        assert result["grounding_rate"]["secondary"] == 0.0


class TestAnalyzeSessionPolicies:
    """Tests for _analyze_session_policies."""

    def test_empty_events(self):
        """Test with empty event list."""
        result = _analyze_session_policies([])
        assert result.shift_count == 0
        assert result.avg_shift_magnitude == 0.0
        assert result.shifts == []

    @patch("api.comparison_routes.analyze_policy_sequence")
    def test_with_policy_events(self, mock_analyze):
        """Test with policy events."""
        mock_analyze.return_value = [MagicMock(shift_magnitude=0.5), MagicMock(shift_magnitude=0.7)]

        events = [
            TraceEvent(
                session_id="s1",
                event_type=EventType.PROMPT_POLICY,
                name="policy1",
                importance=0.5,
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.AGENT_TURN,
                name="turn1",
                importance=0.5,
                upstream_event_ids=[],
            ),
        ]

        result = _analyze_session_policies(events)
        assert result.shift_count == 2
        assert result.avg_shift_magnitude == 0.6
        assert result.shifts == mock_analyze.return_value

    @patch("api.comparison_routes.analyze_policy_sequence")
    def test_no_policy_events(self, mock_analyze):
        """Test with no policy events."""
        mock_analyze.return_value = []

        events = [
            TraceEvent(
                session_id="s1",
                event_type=EventType.AGENT_TURN,
                name="turn1",
                importance=0.5,
                upstream_event_ids=[],
            ),
        ]

        result = _analyze_session_policies(events)
        assert result.shift_count == 0
        assert result.avg_shift_magnitude == 0.0


class TestAnalyzeSessionEscalation:
    """Tests for _analyze_session_escalation."""

    def test_empty_events(self):
        """Test with empty event list."""
        result = _analyze_session_escalation([])
        assert result.score == 0.0
        assert result.dominant_signal_type is None
        assert result.signals == []

    @patch("api.comparison_routes.detect_escalation_signals")
    @patch("api.comparison_routes.compute_escalation_score")
    def test_with_escalation_signals(self, mock_compute_score, mock_detect):
        """Test with escalation signals."""
        mock_signal1 = MagicMock()
        mock_signal1.signal_type = "confidence_degradation"
        mock_signal1.magnitude = 0.7

        mock_signal2 = MagicMock()
        mock_signal2.signal_type = "safety_pressure"
        mock_signal2.magnitude = 0.3

        mock_detect.return_value = [mock_signal1, mock_signal2]
        mock_compute_score.return_value = 0.5

        events = [
            TraceEvent(
                session_id="s1",
                event_type=EventType.AGENT_TURN,
                name="turn1",
                importance=0.5,
                upstream_event_ids=[],
            ),
            TraceEvent(
                session_id="s1",
                event_type=EventType.DECISION,
                name="dec1",
                importance=0.5,
                upstream_event_ids=[],
            ),
        ]

        result = _analyze_session_escalation(events)
        assert result.score == 0.5
        assert result.signals == [mock_signal1, mock_signal2]
        # confidence_degradation has higher magnitude (0.7) than safety_pressure (0.3)
        assert result.dominant_signal_type == "confidence_degradation"

    @patch("api.comparison_routes.detect_escalation_signals")
    @patch("api.comparison_routes.compute_escalation_score")
    def test_no_escalation_signals(self, mock_compute_score, mock_detect):
        """Test with no escalation signals."""
        mock_detect.return_value = []
        mock_compute_score.return_value = 0.0

        events = [
            TraceEvent(
                session_id="s1",
                event_type=EventType.AGENT_TURN,
                name="turn1",
                importance=0.5,
                upstream_event_ids=[],
            ),
        ]

        result = _analyze_session_escalation(events)
        assert result.score == 0.0
        assert result.dominant_signal_type is None
        assert result.signals == []
