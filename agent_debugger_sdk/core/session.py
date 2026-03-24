"""Session management utilities for agent debugging.

This module provides session lifecycle management for tracking agent
execution sessions. The database-backed repository is the authoritative
runtime path now; this module remains as an in-memory compatibility helper.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from .events import Session, SessionStatus


class SessionManager:
    """Manages agent debugging sessions.

    Handles creation, tracking, and lifecycle of debugging sessions.
    Sessions are stored in memory and are not the source of truth used by
    the API or trace persistence pipeline.

    Example:
        >>> manager = SessionManager()
        >>> session = manager.create_session(
        ...     agent_name="my_agent",
        ...     framework="pydantic_ai",
        ...     tags=["production"]
        ... )
        >>> manager.get_active_sessions()
        [Session(id='...', agent_name='my_agent', ...)]
        >>> manager.end_session(session.id)
    """

    def __init__(self) -> None:
        """Initialize the session manager with empty session storage."""
        self._sessions: dict[str, Session] = {}

    def create_session(
        self,
        agent_name: str,
        framework: str,
        config: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> Session:
        """Create a new debugging session.

        Args:
            agent_name: Name/identifier of the agent being debugged
            framework: The agent framework (pydantic_ai, langchain, autogen)
            config: Optional agent configuration settings
            tags: Optional tags for categorizing the session

        Returns:
            The newly created Session instance
        """
        session = Session(
            id=str(uuid.uuid4()),
            agent_name=agent_name,
            framework=framework,
            started_at=datetime.now(timezone.utc),
            status=SessionStatus.RUNNING,
            config=config or {},
            tags=tags or [],
        )
        self._sessions[session.id] = session
        return session

    def end_session(
        self,
        session_id: str,
        status: SessionStatus = SessionStatus.COMPLETED,
    ) -> Session | None:
        """End an active session.

        Args:
            session_id: ID of the session to end
            status: Final status (completed, error, cancelled)

        Returns:
            The updated Session, or None if not found
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None

        session.ended_at = datetime.now(timezone.utc)
        session.status = SessionStatus(status)
        return session

    def get_session(self, session_id: str) -> Session | None:
        """Retrieve a session by ID.

        Args:
            session_id: ID of the session to retrieve

        Returns:
            The Session if found, None otherwise
        """
        return self._sessions.get(session_id)

    def get_active_sessions(self) -> list[Session]:
        """Get all currently active (running) sessions.

        Returns:
            List of sessions with status='running'
        """
        return [s for s in self._sessions.values() if s.status == SessionStatus.RUNNING]

    def update_session_stats(self, session_id: str, **stats: Any) -> None:
        """Update statistics for a session.

        Allows incrementing counters like total_tokens, tool_calls, etc.

        Args:
            session_id: ID of the session to update
            **stats: Stat name and value pairs to update

        Example:
            >>> manager.update_session_stats(
            ...     session_id,
            ...     total_tokens=1500,
            ...     tool_calls=3
            ... )
        """
        session = self._sessions.get(session_id)
        if session is None:
            return

        for key, value in stats.items():
            if hasattr(session, key):
                current = getattr(session, key, 0)
                if isinstance(current, int | float) and isinstance(value, int | float):
                    setattr(session, key, current + value)
                else:
                    setattr(session, key, value)


_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """Get the global session manager singleton.

    Creates the manager on first call, returns existing instance thereafter.

    Returns:
        The global SessionManager instance
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


current_session_id: ContextVar[str | None] = ContextVar("current_session_id", default=None)
