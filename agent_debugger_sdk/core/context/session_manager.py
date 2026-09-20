"""Session lifecycle management for TraceContext.

Checkpoint restoration runs in one of two modes (see
``SessionManager.restore_from_checkpoint``):

- **semantic** (default): an authenticated ``POST`` to the server's semantic
  restore endpoint (``POST /api/checkpoints/{id}/restore``). The server
  creates a NEW session carrying the source session's prefix (copied with
  remapped ids), a leading ``session_restored`` marker event, and an initial
  checkpoint with the source state; the SDK adopts the ids and provenance the
  response returns.
- **legacy** (fallback): when the server cannot serve the semantic route
  (404/405, or the server is unreachable), the SDK reconstructs a local
  Session from ``GET /api/checkpoints/{id}`` and marks the restore
  ``restore_mode="legacy-get"`` so old setups keep working.

Both modes preserve the source session — nothing in it is mutated or deleted
by a restore — and start NO execution: no runner, tool, or model call happens
anywhere in the restore path. Execution continuation from a restored context
is explicitly out of scope for the restore itself.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from agent_debugger_sdk.checkpoints import BaseCheckpointState

from agent_debugger_sdk.core.events import Session, SessionStatus

# Provenance markers for the two restore modes.
RESTORE_MODE_SEMANTIC = "semantic-post"
RESTORE_MODE_LEGACY = "legacy-get"


class _CheckpointRestoreError(Exception):
    """Raised when checkpoint restoration fails."""


@dataclass(frozen=True)
class RestoreProvenance:
    """Provenance of a checkpoint restore, exposed to callers and the UI.

    Attributes:
        restore_mode: ``"semantic-post"`` when the server-side semantic
            restore ran (``POST /api/checkpoints/{id}/restore``) and the ids
            below are authoritative server-minted values; ``"legacy-get"``
            when the SDK fell back to local reconstruction from
            ``GET /api/checkpoints/{id}`` (old server without the semantic
            route). Only ``restore_mode`` / ``source_checkpoint_id`` /
            ``source_session_id`` / ``new_session_id`` are meaningful in
            legacy mode; the server-side fields are ``None``.
        source_checkpoint_id: The checkpoint the restore started from.
        source_session_id: The session the checkpoint belongs to (never
            mutated or deleted by the restore).
        new_session_id: Id of the restored session. Server-assigned in
            semantic mode (adopted verbatim by the SDK).
        new_checkpoint_id: Id of the initial checkpoint created in the new
            session holding the source state (semantic mode only).
        restore_event_id: Id of the leading ``session_restored`` marker event
            in the new session (semantic mode only).
        copied_event_count: How many source events were copied into the new
            session's prefix (semantic mode only).
        restore_token: Server-assigned restore token (semantic mode only).
        restored_at: ISO timestamp of the restore (semantic mode only).
    """

    restore_mode: str
    source_checkpoint_id: str
    source_session_id: str
    new_session_id: str
    new_checkpoint_id: str | None = None
    restore_event_id: str | None = None
    copied_event_count: int | None = None
    restore_token: str | None = None
    restored_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict (stored in ``Session.config``)."""
        return {
            "restore_mode": self.restore_mode,
            "source_checkpoint_id": self.source_checkpoint_id,
            "source_session_id": self.source_session_id,
            "new_session_id": self.new_session_id,
            "new_checkpoint_id": self.new_checkpoint_id,
            "restore_event_id": self.restore_event_id,
            "copied_event_count": self.copied_event_count,
            "restore_token": self.restore_token,
            "restored_at": self.restored_at,
        }


def _resolve_restore_server_url(server_url: str | None) -> str:
    """Resolve the checkpoint restore server URL."""
    if server_url is not None:
        return server_url

    from agent_debugger_sdk.config import get_config

    config = get_config()
    return config.endpoint or "http://localhost:8000"


def _restore_auth_headers() -> dict[str, str]:
    """Authorization headers for restore requests, from the configured API key.

    An endpoint configured without an API key (local collector mode) gets no
    Authorization header at all — restore requests go out unauthenticated,
    matching the SDK's no-key delivery semantics.
    """
    from agent_debugger_sdk.config import get_config

    api_key = getattr(get_config(), "api_key", None)
    if api_key:
        return {"Authorization": f"Bearer {api_key}"}
    return {}


async def _fetch_checkpoint_payload(
    client: httpx.AsyncClient,
    checkpoint_id: str,
    server_url: str,
    *,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fetch and decode checkpoint payload data from the server."""
    request_kwargs: dict[str, Any] = {}
    if headers:
        request_kwargs["headers"] = headers
    try:
        response = await client.get(
            f"{server_url}/api/checkpoints/{checkpoint_id}", **request_kwargs
        )
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


async def _request_semantic_restore(
    client: httpx.AsyncClient,
    checkpoint_id: str,
    server_url: str,
    *,
    session_id: str | None,
    label: str,
    headers: dict[str, str],
) -> dict[str, Any] | None:
    """POST the semantic restore request; return its payload, or None to fall back.

    The server-side semantic restore (``POST /api/checkpoints/{id}/restore``)
    creates a new session copying the source prefix and returns the new
    ids/provenance. ``None`` means "this server cannot serve the semantic
    contract, use the legacy GET path":

    - 404/405: the route does not exist (old server);
    - a transport-level failure: the server is unreachable — the legacy GET
      that follows fails with the same clear error if it is genuinely down;
    - a 2xx body that does not look like a restore response.

    Any other HTTP status (auth failure, validation error, server error)
    propagates as a clear ``_CheckpointRestoreError``.
    """
    request_kwargs: dict[str, Any] = {
        "json": {"session_id": session_id or None, "label": label},
    }
    if headers:
        request_kwargs["headers"] = headers
    try:
        response = await client.post(
            f"{server_url}/api/checkpoints/{checkpoint_id}/restore", **request_kwargs
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (404, 405):
            return None
        raise _CheckpointRestoreError(
            f"Failed to restore checkpoint {checkpoint_id!r} from {server_url}: "
            f"{e.response.status_code} {e.response.reason_phrase}"
        ) from e
    except httpx.RequestError:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict) or not payload.get("new_session_id"):
        return None
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
            "checkpoint_timestamp": checkpoint_data.get("timestamp", ""),
        },
    )

    restored_state = validate_checkpoint_state(state_dict)
    return session, restored_state


def _build_semantic_restored_session(
    checkpoint_id: str,
    restore_payload: dict[str, Any],
    *,
    label: str = "",
) -> tuple[Session, BaseCheckpointState | None, RestoreProvenance]:
    """Build a Session, checkpoint state, and provenance from a semantic restore.

    The response is authoritative for the restored session's identity: the
    new session id, the initial checkpoint id, and the restore marker id were
    minted server-side (together with the copied prefix and the initial
    checkpoint that already exist on the server), so they are adopted
    verbatim instead of being regenerated locally.
    """
    from agent_debugger_sdk.checkpoints import validate_checkpoint_state

    state_dict = restore_payload.get("state")
    if not isinstance(state_dict, dict):
        state_dict = {}
    original_session_id = str(restore_payload.get("original_session_id", ""))
    new_session_id = str(restore_payload.get("new_session_id") or uuid.uuid4())

    session = Session(
        id=new_session_id,
        agent_name=label or f"restored from {checkpoint_id[:8]}",
        framework=state_dict.get("framework", "custom"),
        config={
            "restored_from_checkpoint": checkpoint_id,
            "original_session_id": original_session_id,
            "restore_token": str(restore_payload.get("restore_token") or ""),
        },
    )

    restored_state = validate_checkpoint_state(state_dict)

    copied_count = restore_payload.get("copied_event_count")
    provenance = RestoreProvenance(
        restore_mode=RESTORE_MODE_SEMANTIC,
        source_checkpoint_id=str(restore_payload.get("checkpoint_id") or checkpoint_id),
        source_session_id=original_session_id,
        new_session_id=new_session_id,
        new_checkpoint_id=str(restore_payload["new_checkpoint_id"])
        if restore_payload.get("new_checkpoint_id")
        else None,
        restore_event_id=str(restore_payload["restore_event_id"])
        if restore_payload.get("restore_event_id")
        else None,
        copied_event_count=copied_count if isinstance(copied_count, int) else None,
        restore_token=str(restore_payload["restore_token"])
        if restore_payload.get("restore_token")
        else None,
        restored_at=str(restore_payload["restored_at"])
        if restore_payload.get("restored_at")
        else None,
    )
    return session, restored_state, provenance


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

        Two modes, in order of preference:

        1. **Semantic restore** — POST ``{server_url}/api/checkpoints/{id}/restore``
           (with the configured ``Authorization: Bearer`` header when an API
           key is set; unauthenticated in no-key local mode). The server
           creates a NEW session copying the source prefix (fresh ids,
           remapped references), adds a ``session_restored`` marker event and
           an initial checkpoint, and returns the new ids. The returned
           Session adopts the server-assigned ``new_session_id``, and the
           full provenance is exposed as ``session.restore_provenance``
           (a :class:`RestoreProvenance`) plus a JSON-safe dict in
           ``session.config["restore_provenance"]`` with
           ``restore_mode="semantic-post"``.
        2. **Legacy fallback** — if the server answers 404/405 (old server
           without the semantic route) or is unreachable, the checkpoint is
           fetched via GET and a fresh local Session is reconstructed exactly
           as before, with ``restore_mode="legacy-get"`` provenance so callers
           can tell the modes apart.

        Both modes only read (or copy server-side from) the source session:
        nothing in it is mutated or deleted, and no agent/tool/model
        execution is started — restoring yields state and provenance only.

        Any other HTTP error (e.g. 401/500 from the semantic route) raises
        ``_CheckpointRestoreError`` with a clear message.

        Args:
            checkpoint_id: ID of checkpoint to restore from
            session_id: Optional new session ID (the server mints one if None)
            server_url: Server URL (uses config endpoint if None)
            label: Label for restored session

        Returns:
            Tuple of (Session, restored_state). The Session carries the
            restore provenance (typed attribute ``restore_provenance`` and
            the ``restore_provenance`` entry in its ``config`` dict).

        Raises:
            _CheckpointRestoreError: If checkpoint restoration fails due to
                network errors, invalid checkpoint ID, or server errors.

        Example:
            >>> session, state = await SessionManager.restore_from_checkpoint("ckpt_123")
            >>> session.restore_provenance.restore_mode
            'semantic-post'
        """
        resolved_server_url = _resolve_restore_server_url(server_url)
        auth_headers = _restore_auth_headers()

        async with httpx.AsyncClient(timeout=30.0) as client:
            restore_payload = await _request_semantic_restore(
                client,
                checkpoint_id,
                resolved_server_url,
                session_id=session_id,
                label=label,
                headers=auth_headers,
            )
            if restore_payload is not None:
                session, restored_state, provenance = _build_semantic_restored_session(
                    checkpoint_id, restore_payload, label=label
                )
            else:
                checkpoint_data = await _fetch_checkpoint_payload(
                    client, checkpoint_id, resolved_server_url, headers=auth_headers
                )
                session, restored_state = _build_restored_session(
                    checkpoint_id, checkpoint_data, session_id=session_id, label=label
                )
                provenance = RestoreProvenance(
                    restore_mode=RESTORE_MODE_LEGACY,
                    source_checkpoint_id=checkpoint_id,
                    source_session_id=str(checkpoint_data.get("session_id", "")),
                    new_session_id=session.id,
                )

        session.restore_provenance = provenance  # type: ignore[attr-defined]
        session.config["restore_provenance"] = provenance.to_dict()
        return session, restored_state
