"""Restore hooks for framework-specific checkpoint state reconstruction.

A restore hook is a callable that takes a checkpoint state and a target
agent object, applies the state, and returns the target. Hooks are looked
up by framework name via RESTORE_HOOK_REGISTRY.

Usage::

    from agent_debugger_sdk.checkpoints import RESTORE_HOOK_REGISTRY, apply_restore_hook

    # Register a custom hook
    async def my_hook(state, target):
        target.history = state.messages
        return target

    RESTORE_HOOK_REGISTRY["my_framework"] = my_hook

    # Apply during restore
    await apply_restore_hook("my_framework", checkpoint_state, agent)
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class AutoReplayManager:
    """Orchestrates automatic event replay after checkpoint restoration.

    Fetches post-checkpoint events from the server, applies sequence and
    importance filters, and makes them available for the restored context.

    Usage::

        manager = AutoReplayManager(
            server_url="http://localhost:8000",
            original_session_id="sess-abc",
            checkpoint_sequence=5,
            importance_threshold=0.5,
        )
        events = await manager.fetch_and_filter()
    """

    def __init__(
        self,
        server_url: str,
        original_session_id: str,
        checkpoint_sequence: int,
        importance_threshold: float | None = None,
    ) -> None:
        self._server_url = server_url
        self._original_session_id = original_session_id
        self._checkpoint_sequence = checkpoint_sequence
        self._importance_threshold = importance_threshold

    async def fetch_and_filter(self) -> list[dict[str, Any]]:
        """Fetch post-checkpoint events and apply sequence/importance filters.

        Returns events with sequence > checkpoint_sequence, optionally
        filtered by importance_threshold. Network errors are logged and
        an empty list is returned so callers are not crashed.
        """
        if not self._original_session_id:
            return []

        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._server_url}/api/sessions/{self._original_session_id}/events"
                )
                response.raise_for_status()
                payload = response.json()
                events: list[dict[str, Any]] = (
                    payload.get("events", [payload])
                    if isinstance(payload, dict)
                    else list(payload)
                )
        except Exception:
            logger.warning(
                "Failed to fetch replay events for session %r; continuing without replay",
                self._original_session_id,
            )
            return []

        # Keep only events recorded after the checkpoint
        threshold_seq = self._checkpoint_sequence
        events = [
            e
            for e in events
            if e.get("sequence", threshold_seq + 1) > threshold_seq
        ]

        # Optionally filter by importance
        if self._importance_threshold is not None:
            min_importance = self._importance_threshold
            events = [e for e in events if e.get("importance", 1.0) >= min_importance]

        return events


@runtime_checkable
class RestoreHook(Protocol):
    """Protocol for callables that reconstruct agent state from a checkpoint.

    Implementations receive the typed checkpoint state and the live agent
    object, apply the state, and return the (modified) agent object.
    """

    async def __call__(self, state: Any, target: Any) -> Any:
        """Apply *state* to *target* and return the modified target."""
        ...  # pragma: no cover


# Registry mapping framework name → RestoreHook callable.
# Users and adapters can register hooks at import time or at runtime.
RESTORE_HOOK_REGISTRY: dict[str, RestoreHook] = {}


async def apply_restore_hook(
    framework: str,
    checkpoint_state: Any,
    target: Any,
) -> Any:
    """Apply the registered hook for *framework* to reconstruct *target*.

    If no hook is registered for *framework*, a generic fallback copies
    well-known fields (``messages``, ``intermediate_steps``, ``data``) from
    *checkpoint_state* to *target* when both objects carry the attribute.

    Hook failures are caught and logged; the unmodified *target* is returned
    so callers are not crashed by a broken hook.

    Args:
        framework: Framework identifier (e.g. "langchain", "custom").
        checkpoint_state: The typed checkpoint state to apply.
        target: The agent or state object to reconstruct.

    Returns:
        The (possibly modified) *target* object.
    """
    hook = RESTORE_HOOK_REGISTRY.get(framework)

    if hook is not None:
        try:
            restored_target = await hook(checkpoint_state, target)
            if restored_target is None:
                logger.warning(
                    "Restore hook for framework %r returned None; using original target",
                    framework,
                )
                return target
            return restored_target
        except Exception:
            logger.exception(
                "Restore hook for framework %r raised an error; skipping hook application",
                framework,
            )
            return target

    # Generic fallback — copy common fields when present on both sides.
    for attr in ("messages", "intermediate_steps", "data"):
        src = getattr(checkpoint_state, attr, None)
        if src is not None and hasattr(target, attr):
            setattr(target, attr, src)

    return target
