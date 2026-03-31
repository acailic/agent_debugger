"""Session lifecycle management for TraceContext."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from agent_debugger_sdk.checkpoints import BaseCheckpointState

from agent_debugger_sdk.core.events import Session, SessionStatus

# Shared AsyncClient for checkpoint restoration to avoid creating new clients
_shared_async_client: httpx.AsyncClient | None = None


class SessionManager:
    """Manage session lifecycle for TraceContext.

    Responsibilities:
    - Create and configure Session objects
    - Manage session start/end hooks
    - Handle session restoration from checkpoints
    """

    def __init__(
        self,
        session: Session,
        session_start_hook: Callable[[Session], Awaitable[None]] | None = None,
        session_update_hook: Callable[[Session], Awaitable[None]] | None = None,
    ) -> None:
        self.session = session
        self._session_start_hook = session_start_hook
        self._session_update_hook = session_update_hook

    async def start(self) -> None:
        """Execute session start hook if configured."""
        if self._session_start_hook is not None:
            await self._session_start_hook(self.session)

    async def update(self, status: SessionStatus) -> None:
        """Update session status and trigger update hook."""
        self.session.status = status
        self.session.ended_at = datetime.now(timezone.utc)
        if self._session_update_hook is not None:
            await self._session_update_hook(self.session)

    @classmethod
    async def restore_from_checkpoint(
        cls,
        checkpoint_id: str,
        *,
        session_id: str | None = None,
        server_url: str | None = None,
        label: str = "",
    ) -> tuple[Session, BaseCheckpointState | None]:
        """Restore session from a checkpoint.

        Args:
            checkpoint_id: ID of checkpoint to restore from
            session_id: Optional new session ID (generates UUID if None)
            server_url: Server URL (uses config endpoint if None)
            label: Label for restored session

        Returns:
            Tuple of (Session, restored_state)
        """
        global _shared_async_client

        from agent_debugger_sdk.checkpoints import validate_checkpoint_state
        from agent_debugger_sdk.config import get_config

        if server_url is None:
            config = get_config()
            server_url = config.endpoint or "http://localhost:8000"

        # Use shared client for better performance
        if _shared_async_client is None:
            _shared_async_client = httpx.AsyncClient()

        response = await _shared_async_client.get(f"{server_url}/api/checkpoints/{checkpoint_id}")
        response.raise_for_status()
        checkpoint_data = response.json()

        state_dict = checkpoint_data.get("state", {})
        original_session_id = checkpoint_data.get("session_id", "")

        session = Session(
            id=session_id or str(uuid.uuid4()),
            agent_name=label or f"restored from {checkpoint_id[:8]}",
            framework=state_dict.get("framework", "custom"),
            config={
                "restored_from_checkpoint": checkpoint_id,
                "original_session_id": original_session_id,
            },
        )

        restored_state = validate_checkpoint_state(state_dict)
        return session, restored_state

    @classmethod
    async def close_shared_client(cls) -> None:
        """Close the shared AsyncClient. Call when shutting down the application."""
        global _shared_async_client
        if _shared_async_client is not None:
            await _shared_async_client.aclose()
            _shared_async_client = None
