"""Tests for session fix_note functionality (failure memory feature)."""

from datetime import datetime, timezone

import pytest

from agent_debugger_sdk.core.events import Session
from storage.repository import TraceRepository


def _make_session(session_id: str = "session-1") -> Session:
    return Session(
        id=session_id,
        agent_name="agent",
        framework="pytest",
        started_at=datetime(2026, 3, 23, 10, 0, tzinfo=timezone.utc),
        config={"mode": "test"},
        tags=["coverage"],
    )


@pytest.mark.asyncio
async def test_add_fix_note_to_session(db_session):
    """Test adding a fix note to a session."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    session = _make_session()
    await repo.create_session(session)

    note = "Fixed by updating the timeout configuration"
    result = await repo.add_fix_note(session.id, note)

    assert result is not None
    assert result.fix_note == note

    # Verify it was persisted
    fetched = await repo.get_session(session.id)
    assert fetched is not None
    assert fetched.fix_note == note


@pytest.mark.asyncio
async def test_add_fix_note_nonexistent_session(db_session):
    """Test adding a fix note to a non-existent session returns None."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    result = await repo.add_fix_note("nonexistent-session", "Some note")
    assert result is None


@pytest.mark.asyncio
async def test_update_fix_note_overwrites(db_session):
    """Test that adding a second fix note overwrites the first."""
    repo = TraceRepository(db_session, tenant_id="tenant-a")
    session = _make_session()
    await repo.create_session(session)

    first_note = "First fix attempt"
    await repo.add_fix_note(session.id, first_note)

    second_note = "Second fix attempt that worked"
    result = await repo.add_fix_note(session.id, second_note)

    assert result is not None
    assert result.fix_note == second_note

    # Verify the first note was overwritten
    fetched = await repo.get_session(session.id)
    assert fetched is not None
    assert fetched.fix_note == second_note
    assert fetched.fix_note != first_note


@pytest.mark.asyncio
async def test_add_fix_note_scoped_to_tenant(db_session):
    """Test that fix notes are scoped to tenant_id."""
    repo_a = TraceRepository(db_session, tenant_id="tenant-a")
    repo_b = TraceRepository(db_session, tenant_id="tenant-b")

    session_a = _make_session("session-a")
    session_b = _make_session("session-b")

    await repo_a.create_session(session_a)
    await repo_b.create_session(session_b)

    # Add a note from tenant-a
    note_a = "Fixed from tenant-a perspective"
    result_a = await repo_a.add_fix_note(session_a.id, note_a)
    assert result_a is not None
    assert result_a.fix_note == note_a

    # Tenant-b should not be able to see tenant-a's session
    fetched_by_b = await repo_b.get_session(session_a.id)
    assert fetched_by_b is None

    # Verify tenant-a can still see their session with the note
    fetched_by_a = await repo_a.get_session(session_a.id)
    assert fetched_by_a is not None
    assert fetched_by_a.fix_note == note_a
