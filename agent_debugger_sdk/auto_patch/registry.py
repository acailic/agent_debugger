"""Auto-patch registry: PatchConfig, BaseAdapter, and PatchRegistry."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger("peaky_peek.auto_patch")


@dataclass
class PatchConfig:
    """Configuration for the auto-patch system.

    Attributes:
        server_url: Base URL of the Peaky Peek collector server.
        capture_content: Whether to capture full message/response content.
            Disabled by default for privacy.
    """

    server_url: str = "http://localhost:8000"
    capture_content: bool = False


class BaseAdapter(ABC):
    """Abstract base class for framework auto-patch adapters.

    Each adapter wraps a specific LLM library (e.g. openai, anthropic) and
    knows how to monkey-patch it to emit trace events with zero user code changes.

    Class Attributes:
        name: Short identifier for this adapter (e.g. "openai", "anthropic").
    """

    name: str  # class-level attribute, must be set by subclasses

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the target library is importable in the current env."""

    @abstractmethod
    def patch(self, config: PatchConfig) -> None:
        """Apply monkey-patching to the target library.

        Args:
            config: Active patch configuration.
        """

    @abstractmethod
    def unpatch(self) -> None:
        """Restore the original library behaviour (undo patching)."""


class PatchRegistry:
    """Central registry that manages a collection of BaseAdapter instances.

    Adapters are registered explicitly (no auto-discovery).  At activation
    time, :meth:`apply` iterates registered adapters, checks availability,
    and calls :meth:`BaseAdapter.patch` on eligible ones.
    """

    def __init__(self) -> None:
        self._adapters: list[BaseAdapter] = []
        self._patched: list[BaseAdapter] = []

    def register(self, adapter: BaseAdapter) -> None:
        """Add an adapter to the registry.

        Args:
            adapter: The adapter instance to register.
        """
        self._adapters.append(adapter)

    def apply(self, config: PatchConfig, names: list[str] | None = None) -> None:
        """Patch all eligible adapters.

        An adapter is eligible if :meth:`BaseAdapter.is_available` returns
        ``True`` and, when *names* is provided, the adapter's :attr:`name`
        appears in that list.  Unavailable adapters are silently skipped.

        Args:
            config: Patch configuration to pass to each adapter.
            names: Optional list of adapter names to restrict patching to.
                   When ``None`` all available adapters are patched.
        """
        for adapter in self._adapters:
            if names is not None and adapter.name not in names:
                continue
            if not adapter.is_available():
                logger.debug("Adapter %r not available — skipping", adapter.name)
                continue
            try:
                adapter.patch(config)
                self._patched.append(adapter)
                logger.info("Auto-patched adapter: %s", adapter.name)
            except Exception:
                logger.warning("Failed to patch adapter %r", adapter.name, exc_info=True)

    def unapply(self) -> None:
        """Undo patching for all currently patched adapters."""
        for adapter in list(self._patched):
            try:
                adapter.unpatch()
                logger.info("Unpatched adapter: %s", adapter.name)
            except Exception:
                logger.warning("Failed to unpatch adapter %r", adapter.name, exc_info=True)
        self._patched.clear()

    def patched_names(self) -> list[str]:
        """Return the names of all currently patched adapters.

        Returns:
            List of adapter name strings.
        """
        return [a.name for a in self._patched]


_registry = PatchRegistry()


def get_registry() -> PatchRegistry:
    """Return the global singleton PatchRegistry.

    Returns:
        The module-level PatchRegistry instance shared across all adapters.
    """
    return _registry
