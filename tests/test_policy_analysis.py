"""Tests for policy analysis module."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from collector.policy_analysis import (
    ParameterChange,
    PolicyShift,
    _compute_parameter_magnitude,
    _compute_shift_magnitude,
    _get_template_id,
    analyze_policy_sequence,
)


def make_policy_event(
    event_id: str,
    template_id: str | None = None,
    name: str | None = None,
    policy_parameters: dict | None = None,
    timestamp: datetime | None = None,
) -> MagicMock:
    """Create a mock policy event."""
    event = MagicMock()
    event.id = event_id
    event.template_id = template_id
    event.name = name or f"policy_{event_id}"
    event.policy_parameters = policy_parameters or {}
    event.timestamp = timestamp
    event.data = {"policy_parameters": policy_parameters or {}}
    return event


def make_turn_event(
    event_id: str,
    timestamp: datetime | None = None,
    speaker: str = "agent",
) -> MagicMock:
    """Create a mock turn event."""
    event = MagicMock()
    event.id = event_id
    event.timestamp = timestamp
    event.speaker = speaker
    event.agent_id = speaker
    return event


class TestAnalyzePolicySequence:
    """Tests for analyze_policy_sequence function."""

    def test_empty_policies_returns_empty(self):
        """Empty policy list should return empty shifts."""
        assert analyze_policy_sequence([], []) == []

    def test_single_policy_returns_empty(self):
        """Single policy should not produce any shifts."""
        policy = make_policy_event("p1", template_id="t1")
        assert analyze_policy_sequence([policy], []) == []

    def test_detects_template_change(self):
        """Should detect template changes between policies."""
        p1 = make_policy_event("p1", template_id="template_a")
        p2 = make_policy_event("p2", template_id="template_b")

        shifts = analyze_policy_sequence([p1, p2], [])

        assert len(shifts) == 1
        assert shifts[0].previous_template == "template_a"
        assert shifts[0].new_template == "template_b"
        assert shifts[0].event_id == "p2"

    def test_detects_name_change_when_no_template_id(self):
        """Should fall back to name when template_id is not set."""
        p1 = make_policy_event("p1", template_id=None, name="policy_a")
        p2 = make_policy_event("p2", template_id=None, name="policy_b")

        shifts = analyze_policy_sequence([p1, p2], [])

        assert len(shifts) == 1
        assert shifts[0].previous_template == "policy_a"
        assert shifts[0].new_template == "policy_b"

    def test_detects_parameter_changes(self):
        """Should detect parameter changes between policies."""
        p1 = make_policy_event("p1", template_id="t1", policy_parameters={"temperature": 0.7, "max_tokens": 1000})
        p2 = make_policy_event(
            "p2",
            template_id="t1",  # Same template
            policy_parameters={"temperature": 0.9, "max_tokens": 1000},  # temperature changed
        )

        shifts = analyze_policy_sequence([p1, p2], [])

        assert len(shifts) == 1
        assert "temperature" in shifts[0].parameter_changes
        assert "max_tokens" not in shifts[0].parameter_changes

    def test_no_shift_when_identical(self):
        """Should not produce shift for identical consecutive policies."""
        p1 = make_policy_event("p1", template_id="t1", policy_parameters={"temp": 0.5})
        p2 = make_policy_event("p2", template_id="t1", policy_parameters={"temp": 0.5})

        shifts = analyze_policy_sequence([p1, p2], [])

        assert len(shifts) == 0

    def test_links_to_nearest_turn(self):
        """Should link policy shift to nearest turn."""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        t1 = make_turn_event("turn1", timestamp=base_time)
        t2 = make_turn_event("turn2", timestamp=datetime(2024, 1, 1, 12, 1, 0, tzinfo=timezone.utc))

        p1 = make_policy_event("p1", template_id="t1", timestamp=base_time)
        p2 = make_policy_event("p2", template_id="t2", timestamp=datetime(2024, 1, 1, 12, 0, 30, tzinfo=timezone.utc))

        shifts = analyze_policy_sequence([p1, p2], [t1, t2])

        assert len(shifts) == 1
        # Should link to nearest turn (closer to t1 than t2)
        assert shifts[0].turn_index in [0, 1]


class TestComputeParameterMagnitude:
    """Tests for _compute_parameter_magnitude function."""

    def test_identical_values_returns_zero(self):
        """Identical values should return zero magnitude."""
        assert _compute_parameter_magnitude("key", 0.5, 0.5) == 0.0
        assert _compute_parameter_magnitude("key", "same", "same") == 0.0

    def test_numeric_change_computes_relative(self):
        """Numeric changes should compute relative magnitude."""
        magnitude = _compute_parameter_magnitude("temperature", 0.5, 1.0)
        # (1.0 - 0.5) / 0.5 = 1.0, but capped and weighted
        assert magnitude > 0.0
        assert magnitude <= 1.0

    def test_zero_base_value_handles_gracefully(self):
        """Should handle zero base value without division issues."""
        magnitude = _compute_parameter_magnitude("key", 0, 5)
        assert magnitude > 0.0

    def test_string_change_computes_difference(self):
        """String changes should compute character difference."""
        magnitude = _compute_parameter_magnitude("key", "abc", "xyz")
        assert magnitude > 0.0

    def test_type_change_returns_importance(self):
        """Type changes should return parameter importance."""
        magnitude = _compute_parameter_magnitude("temperature", "string", 0.5)
        # Temperature has high importance (0.9)
        assert magnitude > 0.0

    def test_none_to_value_returns_magnitude(self):
        """None to value change should return magnitude."""
        magnitude = _compute_parameter_magnitude("key", None, "value")
        assert magnitude > 0.0


class TestComputeShiftMagnitude:
    """Tests for _compute_shift_magnitude function."""

    def test_template_change_gives_base_score(self):
        """Template change should give base score of 0.6."""
        magnitude = _compute_shift_magnitude(template_changed=True, param_changes={})
        assert magnitude == 0.6

    def test_no_changes_returns_zero(self):
        """No changes should return zero."""
        magnitude = _compute_shift_magnitude(template_changed=False, param_changes={})
        assert magnitude == 0.0

    def test_parameter_changes_add_to_score(self):
        """Parameter changes should add to the score."""
        param_changes = {"temp": ParameterChange(old_value=0.5, new_value=1.0, magnitude=0.5)}
        magnitude = _compute_shift_magnitude(template_changed=False, param_changes=param_changes)
        # Should be > 0 due to parameter contribution
        assert magnitude > 0.0

    def test_combined_changes_capped_at_one(self):
        """Combined changes should be capped at 1.0."""
        param_changes = {"temp": ParameterChange(old_value=0.0, new_value=1.0, magnitude=1.0)}
        magnitude = _compute_shift_magnitude(template_changed=True, param_changes=param_changes)
        assert magnitude <= 1.0


class TestPolicyShiftDataclass:
    """Tests for PolicyShift dataclass."""

    def test_to_dict_serializes_correctly(self):
        """to_dict should serialize all fields correctly."""
        shift = PolicyShift(
            event_id="event_123",
            turn_index=2,
            previous_template="old_template",
            new_template="new_template",
            parameter_changes={"temp": ParameterChange(old_value=0.5, new_value=0.9, magnitude=0.8)},
            shift_magnitude=0.75,
            triggering_turn_id="turn_2",
        )

        result = shift.to_dict()

        assert result["event_id"] == "event_123"
        assert result["turn_index"] == 2
        assert result["previous_template"] == "old_template"
        assert result["new_template"] == "new_template"
        assert "temp" in result["parameter_changes"]
        assert result["shift_magnitude"] == 0.75
        assert result["triggering_turn_id"] == "turn_2"


class TestGetTemplateId:
    """Tests for _get_template_id helper."""

    def test_returns_template_id_when_set(self):
        """Should return template_id when set on event."""
        event = MagicMock()
        event.template_id = "template_123"
        event.name = "some_name"
        event.data = {}

        result = _get_template_id(event)

        assert result == "template_123"

    def test_falls_back_to_name(self):
        """Should fall back to name when template_id not set."""
        event = MagicMock()
        event.template_id = None
        event.name = "policy_name"
        event.data = {}

        result = _get_template_id(event)

        assert result == "policy_name"

    def test_returns_unknown_when_nothing_set(self):
        """Should return 'unknown' when neither is set."""
        event = MagicMock()
        event.template_id = None
        event.name = None
        event.data = {}

        result = _get_template_id(event)

        assert result == "unknown"
