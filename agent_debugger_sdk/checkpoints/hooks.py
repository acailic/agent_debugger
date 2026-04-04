"""Restore hooks for per-framework state reconstruction."""

from __future__ import annotations

import copy
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class RestoreHook(Protocol):
    """Protocol for framework-specific restore hooks.

    A restore hook receives a checkpoint state and a target agent object,
    reconstructs the agent's state from the checkpoint, and returns the
    modified target.

    Example:
        async def my_hook(state, target):
            target.messages = state.messages
            return target
    """

    async def __call__(self, state: Any, target: Any) -> Any:
        """Apply the checkpoint state to the target agent object.

        Args:
            state: The checkpoint state (e.g. LangChainCheckpointState).
            target: The agent object to restore state into.

        Returns:
            The modified target with restored state.
        """
        ...


# Registry mapping framework names to restore hooks.
# Hooks are async callables: (state, target) -> target
RESTORE_HOOK_REGISTRY: dict[str, Callable[..., Awaitable[Any]]] = {}


async def _langchain_restore_hook(state: Any, target: Any) -> Any:
    """Default LangChain restore hook.

    Restores messages and intermediate_steps from checkpoint state.
    Shallow-copies mutable containers so later mutations on the restored
    target do not corrupt the checkpoint snapshot.
    """
    if hasattr(state, "messages") and hasattr(target, "messages"):
        target.messages = copy.deepcopy(state.messages)
    if hasattr(state, "intermediate_steps") and hasattr(target, "intermediate_steps"):
        target.intermediate_steps = copy.deepcopy(state.intermediate_steps)
    return target


async def _generic_restore_hook(state: Any, target: Any) -> Any:
    """Generic fallback restore hook for unknown frameworks.

    Copies well-known attributes (messages, intermediate_steps, data) from
    state to target when both objects carry the attribute. Mutable containers
    are shallow-copied so the checkpoint snapshot is not aliased.
    """
    for attr in ("messages", "intermediate_steps", "data"):
        if hasattr(state, attr) and hasattr(target, attr):
            val = getattr(state, attr)
            setattr(target, attr, copy.deepcopy(val) if isinstance(val, (list, dict)) else val)
    return target


async def apply_restore_hook(framework: str, state: Any, target: Any) -> Any:
    """Apply the registered restore hook for a framework.

    Looks up the hook in RESTORE_HOOK_REGISTRY. Falls back to a generic
    hook that copies common attributes when no framework-specific hook
    is registered.

    Args:
        framework: Framework identifier (e.g. "langchain", "custom").
        state: Checkpoint state to restore from.
        target: Agent object to restore state into.

    Returns:
        The target with restored state applied.
    """
    hook = RESTORE_HOOK_REGISTRY.get(framework)
    if hook is None:
        # Use built-in langchain hook for langchain framework
        if framework == "langchain":
            hook = _langchain_restore_hook
        else:
            hook = _generic_restore_hook

    try:
        result = await hook(state, target)
    except Exception:
        logger.exception("Restore hook for framework %r raised an error", framework)
        return target
    if result is None:
        logger.warning("Restore hook for framework %r returned None; using original target", framework)
        return target
    return result


class AutoReplayManager:
    """Replays a filtered slice of events after checkpoint restoration.

    Filters the provided event list to those after ``checkpoint_sequence``
    that meet the importance threshold, then invokes ``on_event`` for each
    one in order. Return ``False`` from ``on_event`` to stop early.

    Args:
        events: Full list of events (pre- and post-checkpoint).
        checkpoint_sequence: Sequence number of the restored checkpoint.
            Events at or below this sequence are skipped.
        importance_threshold: Minimum importance score for events to replay.
        on_event: Optional sync or async callback called for each event.
            Return ``False`` to stop replay after the current event.
    """

    def __init__(
        self,
        events: list[dict[str, Any]],
        checkpoint_sequence: int = 0,
        importance_threshold: float = 0.0,
        on_event: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self._all_events = events
        self._checkpoint_sequence = checkpoint_sequence
        self._importance_threshold = importance_threshold
        self._on_event = on_event
        self.replayed_events: list[dict[str, Any]] = []

    def _filter_events(self) -> list[dict[str, Any]]:
        """Return events after checkpoint_sequence meeting importance threshold."""
        result = []
        for event in self._all_events:
            # Sequence may live under metadata (SDK emitter) or at the top level.
            metadata_seq = event.get("metadata", {}).get("sequence")
            seq = metadata_seq if metadata_seq is not None else event.get("sequence", self._checkpoint_sequence + 1)
            if seq <= self._checkpoint_sequence:
                continue
            importance = event.get("importance", 1.0)
            if importance < self._importance_threshold:
                continue
            result.append(event)
        return result

    async def replay(self) -> list[dict[str, Any]]:
        """Execute the replay, calling on_event for each event.

        Returns:
            List of replayed events (filtered, post-checkpoint).
        """
        filtered = self._filter_events()
        for event in filtered:
            if self._on_event is not None:
                result = self._on_event(event)
                if inspect.isawaitable(result):
                    result = await result
                if result is False:
                    self.replayed_events.append(event)
                    break
            self.replayed_events.append(event)
        return self.replayed_events
