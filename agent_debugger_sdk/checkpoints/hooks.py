"""Restore hooks for per-framework state reconstruction."""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class RestoreHook(Protocol):
    """Protocol for framework-specific restore hooks.

    A restore hook receives a checkpoint state and a target object and
    reconstructs the target's state from the checkpoint data.
    """

    async def __call__(self, state: Any, target: Any) -> Any:
        """Apply checkpoint state to target and return the updated target."""
        ...


RESTORE_HOOK_REGISTRY: dict[str, Any] = {}


async def _langchain_restore_hook(state: Any, target: Any) -> Any:
    """Built-in LangChain restore hook."""
    if hasattr(state, "messages") and hasattr(target, "messages"):
        target.messages = state.messages
    elif hasattr(state, "messages"):
        target.messages = state.messages
    if hasattr(state, "intermediate_steps") and hasattr(target, "intermediate_steps"):
        target.intermediate_steps = state.intermediate_steps
    elif hasattr(state, "intermediate_steps"):
        target.intermediate_steps = state.intermediate_steps
    return target


async def _generic_restore_hook(state: Any, target: Any) -> Any:
    """Generic fallback restore hook — returns target unchanged."""
    return target


# Register built-in hooks
RESTORE_HOOK_REGISTRY["langchain"] = _langchain_restore_hook


async def apply_restore_hook(framework: str, checkpoint_state: Any, target: Any) -> Any:
    """Apply the registered restore hook for the given framework.

    Falls back to the generic hook if no specific hook is registered.

    Args:
        framework: Framework identifier (e.g., "langchain", "custom").
        checkpoint_state: The checkpoint state to restore from.
        target: The target object to restore state into.

    Returns:
        The updated target object.
    """
    hook = RESTORE_HOOK_REGISTRY.get(framework, _generic_restore_hook)
    return await hook(checkpoint_state, target)


class AutoReplayManager:
    """Orchestrates automatic event replay after checkpoint restoration.

    Fetches events recorded after the checkpoint was taken and replays
    them in sequence, optionally applying importance filters.
    """

    def __init__(
        self,
        checkpoint_sequence: int,
        session_id: str,
        server_url: str,
    ) -> None:
        self.checkpoint_sequence = checkpoint_sequence
        self.session_id = session_id
        self.server_url = server_url

    async def fetch_post_checkpoint_events(
        self,
        *,
        importance_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch and filter events recorded after the checkpoint.

        Args:
            importance_threshold: Only return events at or above this importance.

        Returns:
            Filtered list of event dicts ordered by sequence.
        """
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.server_url}/api/sessions/{self.session_id}/events"
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            logger.warning("Failed to fetch post-checkpoint events: %s", exc)
            return []

        events: list[dict[str, Any]] = data.get("events", []) if isinstance(data, dict) else []

        events = [e for e in events if e.get("sequence", 0) > self.checkpoint_sequence]

        if importance_threshold is not None:
            events = [e for e in events if e.get("importance", 1.0) >= importance_threshold]

        return events
