"""Session lifecycle management for TraceContext."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from agent_debugger_sdk.checkpoints import BaseCheckpointState

from agent_debugger_sdk.core.events import Session, SessionStatus


class _CheckpointRestoreError(Exception):
    """Raised when checkpoint restoration fails."""

    pass


def _resolve_restore_server_url(server_url: str | None) -> str:
    """Resolve the checkpoint restore server URL."""
    if server_url is not None:
        return server_url

    from agent_debugger_sdk.config import get_config

    config = get_config()
    return config.endpoint or "http://localhost:8000"


async def _fetch_checkpoint_payload(
    client: httpx.AsyncClient,
    checkpoint_id: str,
    server_url: str,
) -> dict[str, Any]:
    """Fetch and decode checkpoint payload data from the server."""
    try:
        response = await client.get(f"{server_url}/api/checkpoints/{checkpoint_id}")
        response.raise_for_status()
        payload = response.json()
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
        raise _CheckpointRestoreError(
            f"Unexpected error while restoring checkpoint {checkpoint_id!r} from {server_url}: {e}"
        ) from e

    if not isinstance(payload, dict):
        raise _CheckpointRestoreError(
            f"Unexpected checkpoint payload type for {checkpoint_id!r} from {server_url}: "
            f"{type(payload).__name__}"
        )

    return payload


def _build_restored_session(
    checkpoint_id: str,
    checkpoint_data: dict[str, Any],
    *,
    session_id: str | None = None,
    label: str = "",
) -> tuple[Session, BaseCheckpointState | None]:
    """Build a restored Session and validated checkpoint state from payload data."""
    from agent_debugger_sdk.checkpoints import validate_checkpoint_state

    state_dict = checkpoint_data.get("state", {})
    original_session_id = checkpoint_data.get("session_id", "")

    session = Session(
        id=session_id or str(uuid.uuid4()),
        agent_name=label or f"restored from {checkpoint_id[:8]}",
        framework=state_dict.get("framework", "custom"),
        config={
            "restored_from_checkpoint": checkpoint_id,
            "original_session_id": original_session_id,
            "checkpoint_sequence": checkpoint_data.get("sequence", 0),
        },
    )

    restored_state = validate_checkpoint_state(state_dict)
    return session, restored_state


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
        resolved_server_url = _resolve_restore_server_url(server_url)

        async with httpx.AsyncClient() as client:
            checkpoint_data = await _fetch_checkpoint_payload(client, checkpoint_id, resolved_server_url)

        return _build_restored_session(checkpoint_id, checkpoint_data, session_id=session_id, label=label)
