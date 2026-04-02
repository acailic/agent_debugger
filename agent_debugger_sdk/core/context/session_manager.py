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


class _CheckpointRestoreError(Exception):
    """Raised when checkpoint restoration fails."""

    pass


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

        Raises:
            _CheckpointRestoreError: If checkpoint restoration fails due to
                network errors, invalid checkpoint ID, or server errors.

        Example:
            >>> session, state = await SessionManager.restore_from_checkpoint("ckpt_123")
        """
        from agent_debugger_sdk.checkpoints import validate_checkpoint_state
        from agent_debugger_sdk.config import get_config

        if server_url is None:
            config = get_config()
            server_url = config.endpoint or "http://localhost:8000"

        # Fetch checkpoint data using a temporary client (avoids connection leaks)
        # All processing happens inside the context manager to ensure checkpoint_data is in scope
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{server_url}/api/checkpoints/{checkpoint_id}")
                response.raise_for_status()
                checkpoint_data = response.json()
            except httpx.HTTPStatusError as e:
                raise _CheckpointRestoreError(
                    f"Failed to restore checkpoint {checkpoint_id!r} from {server_url}: "
                    f"{e.response.status_code} {e.response.reason_phrase}"
                ) from e
            except httpx.RequestError as e:
                raise _CheckpointRestoreError(
                    f"Network error while restoring checkpoint {checkpoint_id!r} from {server_url}: {e}"
                ) from e
            except Exception as e:
                # Catch any other unexpected errors and wrap them
                raise _CheckpointRestoreError(
                    f"Unexpected error while restoring checkpoint {checkpoint_id!r} from {server_url}: {e}"
                ) from e

            # Process the checkpoint data inside the context manager where checkpoint_data is in scope
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
