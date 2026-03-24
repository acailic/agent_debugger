"""Auto-patch package for zero-instrumentation LLM tracing.

At import time this module reads the following environment variables and,
when ``PEAKY_PEEK_AUTO_PATCH`` is set, automatically activates patching:

``PEAKY_PEEK_AUTO_PATCH``
    Set to ``"all"`` to patch every available adapter, or a comma-separated
    list of adapter names to patch only those (e.g. ``"openai,anthropic"``).

``PEAKY_PEEK_SERVER_URL``
    Base URL of the Peaky Peek collector.  Defaults to
    ``"http://localhost:8000"``.

``PEAKY_PEEK_CAPTURE_CONTENT``
    Set to ``"true"`` to capture full message/response content.  Defaults to
    ``"false"`` for privacy.

Public API::

    from agent_debugger_sdk.auto_patch import activate, deactivate, PatchConfig

    activate()                          # uses env vars / defaults
    activate(PatchConfig(...))          # explicit config
    deactivate()                        # undo all patching
"""
from __future__ import annotations

import logging
import os

from agent_debugger_sdk.auto_patch._transport import reset_session
from agent_debugger_sdk.auto_patch.registry import PatchConfig, PatchRegistry, get_registry

logger = logging.getLogger("agent_debugger.auto_patch")

__all__ = ["PatchConfig", "activate", "deactivate"]

# ---------------------------------------------------------------------------
# Adapter catalogue — add new adapters here as they are implemented.
# Adapters are never auto-discovered; they must be explicitly listed.
# ---------------------------------------------------------------------------
_ADAPTER_NAMES: list[str] = []  # e.g. ["openai", "anthropic"]


def _build_config_from_env() -> PatchConfig:
    """Construct a PatchConfig from environment variables."""
    server_url = os.environ.get("PEAKY_PEEK_SERVER_URL", "http://localhost:8000")
    capture_raw = os.environ.get("PEAKY_PEEK_CAPTURE_CONTENT", "false").strip().lower()
    capture_content = capture_raw == "true"
    return PatchConfig(server_url=server_url, capture_content=capture_content)


def _load_adapters(registry: PatchRegistry) -> None:
    """Import and register all known adapters into *registry*.

    Adapters are imported lazily here (not at module top-level) so that
    missing optional dependencies only raise an error if that adapter is
    actually requested, not on every import.
    """
    # Future adapters will be imported and registered here, e.g.:
    #   from agent_debugger_sdk.auto_patch.adapters.openai import OpenAIAdapter
    #   registry.register(OpenAIAdapter())
    pass


def activate(config: PatchConfig | None = None) -> None:
    """Activate auto-patching with the given (or environment-derived) config.

    Can be called multiple times; subsequent calls will re-apply all adapters
    using the new config.  Existing patches are first removed via
    :func:`deactivate`.

    Args:
        config: Explicit :class:`PatchConfig`.  When ``None`` (default) the
                configuration is read from environment variables.
    """
    if config is None:
        config = _build_config_from_env()

    registry = get_registry()
    _load_adapters(registry)

    auto_patch_env = os.environ.get("PEAKY_PEEK_AUTO_PATCH", "")
    names: list[str] | None = None
    if auto_patch_env and auto_patch_env.lower() != "all":
        names = [n.strip() for n in auto_patch_env.split(",") if n.strip()]

    # Remove any previously applied patches before re-applying.
    registry.unapply()
    registry.apply(config, names=names)

    if registry.patched_names():
        logger.info("Peaky Peek auto-patch active for: %s", registry.patched_names())
    else:
        logger.debug("Peaky Peek auto-patch: no adapters were patched (none available or listed)")


def deactivate() -> None:
    """Remove all auto-patch hooks and restore original library behaviour."""
    get_registry().unapply()
    reset_session()
    logger.info("Peaky Peek auto-patch deactivated")


# ---------------------------------------------------------------------------
# Auto-activation on import
# ---------------------------------------------------------------------------
_auto_patch_env = os.environ.get("PEAKY_PEEK_AUTO_PATCH", "")
if _auto_patch_env:
    activate()
