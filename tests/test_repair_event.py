"""Tests for RepairAttemptEvent.

Based on the FailureMem paper (arXiv:2603.17826), repair attempts are valuable
artifacts that should be tracked and analyzed.
"""

import uuid
from datetime import datetime, timezone

from agent_debugger_sdk.core.events import EventType, RepairAttemptEvent, RepairOutcome
from agent_debugger_sdk.core.events.base import TraceEvent


def test_repair_event_creation_with_all_fields() -> None:
    """Test creating a RepairAttemptEvent with all fields populated."""
    event = RepairAttemptEvent(
        session_id="test-session",
        name="Fix authentication bug",
        attempted_fix="Add missing authentication header to API requests",
        validation_result="All tests passing",
        repair_outcome=RepairOutcome.SUCCESS,
        repair_sequence_id="seq-123",
        repair_diff="+ headers: {'Authorization': 'Bearer token'}",
    )

    assert event.session_id == "test-session"
    assert event.name == "Fix authentication bug"
    assert event.attempted_fix == "Add missing authentication header to API requests"
    assert event.validation_result == "All tests passing"
    assert event.repair_outcome == RepairOutcome.SUCCESS
    assert event.repair_sequence_id == "seq-123"
    assert event.repair_diff == "+ headers: {'Authorization': 'Bearer token'}"
    assert event.event_type == EventType.REPAIR_ATTEMPT


def test_repair_event_creation_with_minimal_fields() -> None:
    """Test creating a RepairAttemptEvent with minimal required fields."""
    event = RepairAttemptEvent(
        session_id="test-session",
        name="Minimal repair",
        attempted_fix="Simple fix",
    )

    assert event.session_id == "test-session"
    assert event.name == "Minimal repair"
    assert event.attempted_fix == "Simple fix"
    assert event.validation_result is None
    assert event.repair_outcome == RepairOutcome.FAILURE  # default
    assert event.repair_sequence_id is None
    assert event.repair_diff is None


def test_repair_outcome_validation_success() -> None:
    """Test that 'success' string is converted to RepairOutcome.SUCCESS enum."""
    event = RepairAttemptEvent(
        session_id="test-session",
        attempted_fix="Fix something",
        repair_outcome="success",  # type: ignore
    )

    assert event.repair_outcome == RepairOutcome.SUCCESS
    assert isinstance(event.repair_outcome, RepairOutcome)


def test_repair_outcome_validation_failure() -> None:
    """Test that 'failure' string is converted to RepairOutcome.FAILURE enum."""
    event = RepairAttemptEvent(
        session_id="test-session",
        attempted_fix="Failed fix",
        repair_outcome="failure",  # type: ignore
    )

    assert event.repair_outcome == RepairOutcome.FAILURE
    assert isinstance(event.repair_outcome, RepairOutcome)


def test_repair_outcome_validation_partial() -> None:
    """Test that 'partial' string is converted to RepairOutcome.PARTIAL enum."""
    event = RepairAttemptEvent(
        session_id="test-session",
        attempted_fix="Partial fix",
        repair_outcome="partial",  # type: ignore
    )

    assert event.repair_outcome == RepairOutcome.PARTIAL
    assert isinstance(event.repair_outcome, RepairOutcome)


def test_repair_outcome_enum_direct() -> None:
    """Test that RepairOutcome enum values work directly."""
    for outcome in [RepairOutcome.SUCCESS, RepairOutcome.FAILURE, RepairOutcome.PARTIAL]:
        event = RepairAttemptEvent(
            session_id="test-session",
            attempted_fix="Test fix",
            repair_outcome=outcome,
        )

        assert event.repair_outcome == outcome


def test_repair_sequence_id_linking_multiple_attempts() -> None:
    """Test that repair_sequence_id can link multiple repair attempts."""
    sequence_id = "repair-sequence-abc-123"

    # First attempt - fails
    attempt1 = RepairAttemptEvent(
        session_id="test-session",
        name="First attempt",
        attempted_fix="Approach A: Fix the symptom",
        repair_outcome=RepairOutcome.FAILURE,
        repair_sequence_id=sequence_id,
    )

    # Second attempt - partial success
    attempt2 = RepairAttemptEvent(
        session_id="test-session",
        name="Second attempt",
        attempted_fix="Approach B: Fix the root cause partially",
        repair_outcome=RepairOutcome.PARTIAL,
        repair_sequence_id=sequence_id,
    )

    # Third attempt - success
    attempt3 = RepairAttemptEvent(
        session_id="test-session",
        name="Third attempt",
        attempted_fix="Approach C: Complete fix",
        repair_outcome=RepairOutcome.SUCCESS,
        repair_sequence_id=sequence_id,
    )

    # All attempts share the same sequence_id
    assert attempt1.repair_sequence_id == sequence_id
    assert attempt2.repair_sequence_id == sequence_id
    assert attempt3.repair_sequence_id == sequence_id

    # Each has a different unique event ID
    assert attempt1.id != attempt2.id != attempt3.id


def test_to_trace_event_conversion() -> None:
    """Test that to_trace_event() produces correct event_type."""
    event = RepairAttemptEvent(
        session_id="test-session",
        name="Test repair",
        attempted_fix="Fix something",
        validation_result="Passed",
        repair_outcome=RepairOutcome.SUCCESS,
        repair_sequence_id="seq-456",
        repair_diff="diff content",
    )

    trace_event = event.to_trace_event()

    assert isinstance(trace_event, TraceEvent)
    assert trace_event.event_type == EventType.REPAIR_ATTEMPT
    assert trace_event.session_id == "test-session"
    assert trace_event.name == "Test repair"

    # Verify that repair-specific fields are merged into data payload
    data = trace_event.data
    assert data["attempted_fix"] == "Fix something"
    assert data["validation_result"] == "Passed"
    assert data["repair_outcome"] == RepairOutcome.SUCCESS
    assert data["repair_sequence_id"] == "seq-456"
    assert data["repair_diff"] == "diff content"


def test_to_trace_event_preserves_base_fields() -> None:
    """Test that to_trace_event() preserves all base TraceEvent fields."""
    parent_id = str(uuid.uuid4())
    metadata = {"key": "value"}
    importance = 0.8
    upstream_ids = [str(uuid.uuid4()), str(uuid.uuid4())]

    event = RepairAttemptEvent(
        session_id="test-session",
        parent_id=parent_id,
        name="Test repair",
        attempted_fix="Fix something",
        metadata=metadata,
        importance=importance,
        upstream_event_ids=upstream_ids,
    )

    trace_event = event.to_trace_event()

    assert trace_event.parent_id == parent_id
    assert trace_event.metadata == metadata
    assert trace_event.importance == importance
    assert trace_event.upstream_event_ids == upstream_ids


def test_repair_event_serialization() -> None:
    """Test that RepairAttemptEvent can be serialized to dict."""
    event = RepairAttemptEvent(
        session_id="test-session",
        name="Serialization test",
        attempted_fix="Test fix",
        repair_outcome=RepairOutcome.SUCCESS,
    )

    event_dict = event.to_dict()

    assert event_dict["session_id"] == "test-session"
    assert event_dict["name"] == "Serialization test"
    assert event_dict["attempted_fix"] == "Test fix"
    assert event_dict["repair_outcome"] == "success"
    assert event_dict["event_type"] == EventType.REPAIR_ATTEMPT


def test_repair_event_with_none_validation_result() -> None:
    """Test that validation_result can be None."""
    event = RepairAttemptEvent(
        session_id="test-session",
        attempted_fix="Fix without validation",
        validation_result=None,
    )

    assert event.validation_result is None


def test_repair_event_with_none_repair_diff() -> None:
    """Test that repair_diff can be None."""
    event = RepairAttemptEvent(
        session_id="test-session",
        attempted_fix="Fix without diff",
        repair_diff=None,
    )

    assert event.repair_diff is None


def test_repair_event_with_none_sequence_id() -> None:
    """Test that repair_sequence_id can be None (isolated repair)."""
    event = RepairAttemptEvent(
        session_id="test-session",
        attempted_fix="Standalone repair",
        repair_sequence_id=None,
    )

    assert event.repair_sequence_id is None


def test_repair_event_timestamp_defaults_to_utc_now() -> None:
    """Test that timestamp defaults to current UTC time."""
    before = datetime.now(timezone.utc)
    event = RepairAttemptEvent(
        session_id="test-session",
        attempted_fix="Test",
    )
    after = datetime.now(timezone.utc)

    assert event.timestamp >= before
    assert event.timestamp <= after


def test_repair_event_id_defaults_to_uuid4() -> None:
    """Test that id defaults to a valid UUID4 string."""
    event = RepairAttemptEvent(
        session_id="test-session",
        attempted_fix="Test",
    )

    # Should be a valid UUID string
    uuid.UUID(event.id)  # Will raise ValueError if invalid


def test_multiple_repair_outcomes_are_distinct() -> None:
    """Test that all RepairOutcome values are distinct."""
    outcomes = [RepairOutcome.SUCCESS, RepairOutcome.FAILURE, RepairOutcome.PARTIAL]

    # All should be different
    assert len(set(outcomes)) == 3

    # All should be string enums
    for outcome in outcomes:
        assert isinstance(outcome, str)
        assert isinstance(outcome, RepairOutcome)


def test_repair_outcome_string_values() -> None:
    """Test that RepairOutcome string values match expected values."""
    assert RepairOutcome.SUCCESS == "success"
    assert RepairOutcome.FAILURE == "failure"
    assert RepairOutcome.PARTIAL == "partial"
