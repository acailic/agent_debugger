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
RESTORE_HOOK_REGISTRY: dict[str, Any] = {}


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
            return await hook(checkpoint_state, target)
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
