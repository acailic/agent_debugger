"""Restore hooks for per-framework agent state reconstruction."""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from .schemas import BaseCheckpointState, CustomCheckpointState, LangChainCheckpointState

logger = logging.getLogger(__name__)


@runtime_checkable
class RestoreHook(Protocol):
    """Protocol for framework-specific restore hooks.

    A RestoreHook takes a checkpoint state and a target agent object,
    reconstructs the appropriate agent state, and returns the updated target.

    Example::

        async def my_hook(state: BaseCheckpointState, target: Any) -> Any:
            target.messages = state.messages
            return target

        RESTORE_HOOK_REGISTRY["my_framework"] = my_hook
    """

    async def __call__(self, state: BaseCheckpointState, target: Any) -> Any:
        """Apply the restore hook.

        Args:
            state: The checkpoint state to restore from.
            target: The agent object to restore state into.

        Returns:
            The updated target with state restored.
        """
        ...


async def _langchain_hook(state: BaseCheckpointState, target: Any) -> Any:
    """Default LangChain restore hook.

    Restores messages and intermediate_steps from a LangChainCheckpointState.
    """
    if isinstance(state, LangChainCheckpointState):
        target.messages = state.messages
        target.intermediate_steps = state.intermediate_steps
    return target


async def _generic_hook(state: BaseCheckpointState, target: Any) -> Any:
    """Generic fallback hook for unknown frameworks.

    Copies data from CustomCheckpointState, otherwise returns target unchanged.
    """
    if isinstance(state, CustomCheckpointState):
        target.data = state.data
    return target


# Registry mapping framework name to restore hook callable
RESTORE_HOOK_REGISTRY: dict[str, RestoreHook] = {
    "langchain": _langchain_hook,
}


async def apply_restore_hook(
    framework: str,
    state: BaseCheckpointState,
    target: Any,
) -> Any:
    """Apply the registered restore hook for the given framework.

    Looks up the framework in RESTORE_HOOK_REGISTRY. Falls back to the
    generic hook if no matching hook is found.

    Args:
        framework: The framework identifier (e.g. "langchain", "custom").
        state: The checkpoint state to restore from.
        target: The agent object to restore state into.

    Returns:
        The updated target with state restored.
    """
    hook = RESTORE_HOOK_REGISTRY.get(framework, _generic_hook)
    try:
        return await hook(state, target)
    except Exception:
        logger.exception("Restore hook for %r failed", framework)
        return target


class AutoReplayManager:
    """Orchestrates automatic event replay after checkpoint restoration.

    Filters events by sequence/importance and invokes a per-event callback during
    replay, allowing early termination via the callback's return value.

    Args:
        events: List of events to replay (already filtered by sequence/importance).
        framework: Framework identifier for hook lookup.
        on_event: Optional callback invoked per event; return False to stop.
    """

    def __init__(
        self,
        events: list[dict[str, Any]],
        framework: str = "custom",
        on_event: Any | None = None,
    ) -> None:
        self.events = events
        self.framework = framework
        self.on_event = on_event
        self.replayed: list[dict[str, Any]] = []

    async def run(self) -> list[dict[str, Any]]:
        """Execute the replay sequence.

        Returns:
            List of events that were successfully replayed.
        """
        for event in self.events:
            if self.on_event is not None:
                result = self.on_event(event)
                if result is False:
                    break
            self.replayed.append(event)
        return self.replayed
