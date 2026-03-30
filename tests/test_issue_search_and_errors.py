"""Regression tests for Issue #1 (search returns no results) and Issue #2 (error count semantic mismatch).

These tests document the expected behavior. They will FAIL with the current codebase
and should pass once the issues are fixed.

ISSUE #1: Search returns no results
- Events and sessions should be searchable by their content
- search_events() uses SQL LIKE against EventModel.name, event_type, data, event_metadata
- search_sessions() uses bag-of-words cosine similarity

ISSUE #2: Error count semantic mismatch
- The Session.errors field should represent ERROR-type events, not policy_violation events
- When viewing sessions in the UI, policy_violation events should not inflate the error count
- This is about session enrichment/summary logic counting errors correctly
"""

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import (
    EventType,
    Session,
    SessionStatus,
    TraceEvent,
)
from storage.repository import TraceRepository

# =============================================================================
# ISSUE #1: Search returns no results
# =============================================================================


@pytest.mark.asyncio
async def test_issue_1_event_search_finds_policy_injection_text(db_session):
    """Regression test for Issue #1: Event search should find events with 'policy injection' text.

    Expected behavior:
    - Create events containing "policy injection" in their data/name fields
    - search_events("policy injection") should return these events
    - Uses SQL LIKE against EventModel.name, event_type, data, event_metadata

    Current behavior: Search returns no results (FAILS)
    Expected behavior: Search returns matching events (PASSES after fix)
    """
    repo = TraceRepository(db_session, tenant_id="tenant-search-issue-1")

    # Create a session
    session = Session(
        id="session-policy-injection-test",
        agent_name="test_agent",
        framework="pytest",
        started_at=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
        status=SessionStatus.COMPLETED,
    )
    await repo.create_session(session)

    # Create an event with "policy injection" in the name
    # Use plain TraceEvent to avoid SafetyOutcome validation issues
    event1 = TraceEvent(
        id="event-policy-injection-1",
        session_id="session-policy-injection-test",
        name="policy injection detected",
        event_type=EventType.SAFETY_CHECK,
        timestamp=datetime(2026, 3, 30, 10, 1, tzinfo=timezone.utc),
        data={
            "check_type": "policy_injection",
            "outcome": "block",
            "details": "Detected policy injection attempt in user prompt",
        },
        metadata={"severity": "high"},
    )
    await repo.add_event(event1)

    # Create another event with "policy injection" in the data
    event2 = TraceEvent(
        id="event-policy-injection-2",
        session_id="session-policy-injection-test",
        name="safety_check",
        event_type=EventType.SAFETY_CHECK,
        timestamp=datetime(2026, 3, 30, 10, 2, tzinfo=timezone.utc),
        data={
            "check_type": "content_filter",
            "threat": "policy injection attempt detected",
        },
    )
    await repo.add_event(event2)

    await repo.commit()

    # Search for "policy injection" - should find at least one event
    results = await repo.search_events("policy injection")

    # CURRENTLY FAILS: results is empty
    # EXPECTED: Should find at least 1 event
    assert len(results) >= 1, f"Expected at least 1 result for 'policy injection' search, got {len(results)}"

    # Verify the events we created are in the results
    result_ids = {r.id for r in results}
    assert "event-policy-injection-1" in result_ids or "event-policy-injection-2" in result_ids


@pytest.mark.asyncio
async def test_issue_1_session_search_finds_safety_content(db_session):
    """Regression test for Issue #1: Session search should find sessions with 'safety' content.

    Expected behavior:
    - Create sessions with events containing "safety" related content
    - search_sessions("safety") should return these sessions
    - Uses bag-of-words cosine similarity against embedded session event fields
    - Searches across: event_type, name, error_type, error_message, tool_name, model

    Current behavior: Search returns no results (FAILS)
    Expected behavior: Search returns matching sessions (PASSES after fix)
    """
    repo = TraceRepository(db_session, tenant_id="tenant-safety-search")

    # Create a session with safety-related events
    session = Session(
        id="session-safety-test",
        agent_name="safety_agent",
        framework="pytest",
        started_at=datetime(2026, 3, 30, 11, 0, tzinfo=timezone.utc),
        status=SessionStatus.COMPLETED,
    )
    await repo.create_session(session)

    # Create events with safety-related content
    safety_event = TraceEvent(
        id="event-safety-1",
        session_id="session-safety-test",
        name="safety check performed",
        event_type=EventType.SAFETY_CHECK,
        timestamp=datetime(2026, 3, 30, 11, 1, tzinfo=timezone.utc),
        data={
            "check_type": "harmful_content",
            "outcome": "pass",
            "model": "gpt-4",
        },
    )
    await repo.add_event(safety_event)

    # Another event with "safety" in the data
    tool_event = TraceEvent(
        id="event-safety-2",
        session_id="session-safety-test",
        name="tool_call",
        event_type=EventType.TOOL_CALL,
        timestamp=datetime(2026, 3, 30, 11, 2, tzinfo=timezone.utc),
        data={
            "tool_name": "safety_validator",
            "model": "gpt-4",
        },
    )
    await repo.add_event(tool_event)

    await repo.commit()

    # Search for "safety" - should find the session
    results = await repo.search_sessions("safety")

    # CURRENTLY FAILS: results is empty
    # EXPECTED: Should find at least 1 session
    assert len(results) >= 1, f"Expected at least 1 result for 'safety' search, got {len(results)}"

    # Verify the session we created is in the results
    result_ids = {r.id for r in results}
    assert "session-safety-test" in result_ids


# =============================================================================
# ISSUE #2: Error count semantic mismatch
# =============================================================================


@pytest.mark.asyncio
async def test_issue_2_session_with_policy_violations_shows_zero_errors(db_session):
    """Regression test for Issue #2: Sessions with only policy_violation events should show errors=0.

    This test documents the semantic issue where sessions containing policy_violation
    events (but NO actual ERROR events) should display errors=0 in the UI.

    The issue is that session enrichment/summary logic may incorrectly count
    policy_violation events as errors when computing the Session.errors field.

    Expected behavior:
    - Create a session with policy_violation events but NO error-type events
    - When the session is retrieved, errors field should be 0
    - Only EventType.ERROR events should count toward the errors field

    Reference: Session model errors field is at agent_debugger_sdk/core/events/session.py line 47
    Reference: Seed script shows manual error setting in scripts/seed_demo_sessions.py

    Note: This test documents the EXPECTED behavior. The actual issue is in how
    sessions are created/enriched, not in the repository itself.
    """
    repo = TraceRepository(db_session, tenant_id="tenant-error-count-issue")

    # Create a session with errors=0 (as would be set by session enrichment logic)
    session = Session(
        id="session-policy-violation-only",
        agent_name="test_agent",
        framework="pytest",
        started_at=datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc),
        status=SessionStatus.COMPLETED,
        errors=0,  # Correctly set to 0 since there are no ERROR events
    )
    await repo.create_session(session)

    # Create policy_violation events (NOT error events)
    # These should NOT cause the errors field to be incremented
    policy_violation_1 = TraceEvent(
        id="event-policy-1",
        session_id="session-policy-violation-only",
        name="policy violation",
        event_type=EventType.POLICY_VIOLATION,
        timestamp=datetime(2026, 3, 30, 12, 1, tzinfo=timezone.utc),
        data={
            "violation_type": "content_policy",
            "severity": "high",
        },
    )
    await repo.add_event(policy_violation_1)

    policy_violation_2 = TraceEvent(
        id="event-policy-2",
        session_id="session-policy-violation-only",
        name="another policy violation",
        event_type=EventType.POLICY_VIOLATION,
        timestamp=datetime(2026, 3, 30, 12, 2, tzinfo=timezone.utc),
        data={
            "violation_type": "safety_policy",
            "severity": "medium",
        },
    )
    await repo.add_event(policy_violation_2)

    await repo.commit()

    # Retrieve the session - errors should still be 0
    retrieved_session = await repo.get_session("session-policy-violation-only")

    assert retrieved_session is not None, "Session should exist"
    assert retrieved_session.errors == 0, (
        f"Sessions with only policy_violation events (no ERROR events) should have errors=0. "
        f"Got errors={retrieved_session.errors}. "
        f"This ensures policy violations are not semantically counted as errors."
    )


@pytest.mark.asyncio
async def test_issue_2_session_with_actual_errors_shows_correct_count(db_session):
    """Regression test for Issue #2: Sessions with ERROR events should show the correct error count.

    Expected behavior:
    - Create a session with EventType.ERROR events
    - Set the errors field to match the number of ERROR events
    - When retrieved, the errors field should reflect the ERROR event count

    This test confirms that ERROR events are what should count toward the errors field.
    """
    repo = TraceRepository(db_session, tenant_id="tenant-error-count-positive")

    # Create a session with errors=0 — auto-incremented by add_event for each ERROR event
    session = Session(
        id="session-with-errors",
        agent_name="test_agent",
        framework="pytest",
        started_at=datetime(2026, 3, 30, 13, 0, tzinfo=timezone.utc),
        status=SessionStatus.ERROR,
        errors=0,
    )
    await repo.create_session(session)

    # Create actual ERROR events
    error_1 = TraceEvent(
        id="event-error-1",
        session_id="session-with-errors",
        name="error occurred",
        event_type=EventType.ERROR,
        timestamp=datetime(2026, 3, 30, 13, 1, tzinfo=timezone.utc),
        data={
            "error_type": "ValueError",
            "error_message": "Invalid input value",
        },
    )
    await repo.add_event(error_1)

    error_2 = TraceEvent(
        id="event-error-2",
        session_id="session-with-errors",
        name="another error",
        event_type=EventType.ERROR,
        timestamp=datetime(2026, 3, 30, 13, 2, tzinfo=timezone.utc),
        data={
            "error_type": "RuntimeError",
            "error_message": "Connection failed",
        },
    )
    await repo.add_event(error_2)

    error_3 = TraceEvent(
        id="event-error-3",
        session_id="session-with-errors",
        name="third error",
        event_type=EventType.ERROR,
        timestamp=datetime(2026, 3, 30, 13, 3, tzinfo=timezone.utc),
        data={
            "error_type": "TimeoutError",
            "error_message": "Request timed out",
        },
    )
    await repo.add_event(error_3)

    await repo.commit()

    # Retrieve the session and verify errors field is correct
    retrieved_session = await repo.get_session("session-with-errors")

    assert retrieved_session is not None, "Session should exist"
    assert retrieved_session.errors == 3, (
        f"Sessions with 3 ERROR events should have errors=3. "
        f"Got errors={retrieved_session.errors}. "
        f"This confirms ERROR events are what should count toward the errors field."
    )


@pytest.mark.asyncio
async def test_issue_2_session_with_mixed_events_errors_count_only_errors(db_session):
    """Regression test for Issue #2: Mixed events - only ERROR events should count toward errors field.

    Expected behavior:
    - Create a session with policy_violation, ERROR, and other event types
    - The errors field should equal ONLY the count of EventType.ERROR events
    - policy_violation and other event types should NOT affect the errors count

    This test documents the semantic boundary: errors != violations != other events.
    """
    repo = TraceRepository(db_session, tenant_id="tenant-mixed-events")

    # Create a session with errors=0 — auto-incremented by add_event for each ERROR event
    session = Session(
        id="session-mixed-events",
        agent_name="test_agent",
        framework="pytest",
        started_at=datetime(2026, 3, 30, 14, 0, tzinfo=timezone.utc),
        status=SessionStatus.ERROR,
        errors=0,
    )
    await repo.create_session(session)

    # Create policy_violation events (should NOT count toward errors)
    for i in range(2):
        policy_event = TraceEvent(
            id=f"event-policy-{i}",
            session_id="session-mixed-events",
            name="policy violation",
            event_type=EventType.POLICY_VIOLATION,
            timestamp=datetime(2026, 3, 30, 14, i, tzinfo=timezone.utc),
            data={"violation_type": f"policy_{i}"},
        )
        await repo.add_event(policy_event)

    # Create ERROR events (SHOULD count toward errors)
    for i in range(3):
        error_event = TraceEvent(
            id=f"event-error-{i}",
            session_id="session-mixed-events",
            name="error occurred",
            event_type=EventType.ERROR,
            timestamp=datetime(2026, 3, 30, 14, 2 + i, tzinfo=timezone.utc),
            data={"error_type": f"Error{i}", "error_message": f"Message {i}"},
        )
        await repo.add_event(error_event)

    # Create other event types (should NOT count toward errors)
    tool_event = TraceEvent(
        id="event-tool-1",
        session_id="session-mixed-events",
        name="tool call",
        event_type=EventType.TOOL_CALL,
        timestamp=datetime(2026, 3, 30, 14, 5, tzinfo=timezone.utc),
        data={"tool_name": "test_tool"},
    )
    await repo.add_event(tool_event)

    await repo.commit()

    # Retrieve the session and verify errors count is correct
    retrieved_session = await repo.get_session("session-mixed-events")

    assert retrieved_session is not None, "Session should exist"
    assert retrieved_session.errors == 3, (
        f"Sessions with mixed events should count ONLY ERROR events toward errors field. "
        f"Got errors={retrieved_session.errors}, expected 3 (from 3 ERROR events, ignoring "
        f"2 policy_violation events and 1 tool_call event). "
        f"This documents the semantic: policy_violation != error."
    )
