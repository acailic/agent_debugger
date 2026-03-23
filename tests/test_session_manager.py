"""Tests for in-memory session compatibility helpers."""

from __future__ import annotations

from agent_debugger_sdk.core.session import SessionManager


def test_create_and_end_session_lifecycle():
    manager = SessionManager()

    session = manager.create_session(
        agent_name="planner",
        framework="custom",
        config={"mode": "debug"},
        tags=["demo"],
    )

    assert session.agent_name == "planner"
    assert session.framework == "custom"
    assert session.status == "running"
    assert session.config == {"mode": "debug"}
    assert session.tags == ["demo"]
    assert manager.get_session(session.id) is session
    assert manager.get_active_sessions() == [session]

    ended = manager.end_session(session.id, status="error")

    assert ended is session
    assert ended.status == "error"
    assert ended.ended_at is not None
    assert manager.get_active_sessions() == []


def test_end_missing_session_returns_none():
    manager = SessionManager()

    assert manager.end_session("missing") is None


def test_update_session_stats_accumulates_numeric_values_and_replaces_other_fields():
    manager = SessionManager()
    session = manager.create_session(agent_name="worker", framework="custom")

    manager.update_session_stats(
        session.id,
        total_tokens=100,
        tool_calls=2,
        status="paused",
    )
    manager.update_session_stats(
        session.id,
        total_tokens=25,
        tool_calls=1,
    )

    updated = manager.get_session(session.id)
    assert updated is not None
    assert updated.total_tokens == 125
    assert updated.tool_calls == 3
    assert updated.status == "paused"


def test_update_session_stats_ignores_missing_session():
    manager = SessionManager()

    manager.update_session_stats("missing", total_tokens=10)

