"""Auto-instrumentation registry for framework patching."""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger("agent_debugger")


class AutoInstrumentor:
    """Registry for framework auto-instrumentation hooks.

    Provides a centralized registry for framework-specific auto-instrumentation
    hooks that enable zero-code-change tracing for supported frameworks.

    Example:
        >>> from agent_debugger_sdk.auto_instrument import get_instrumentor
        >>>
        >>> instrumentor = get_instrumentor()
        >>> instrumentor.instrument("langchain")  # Auto-patch LangChain
        >>> instrumentor.instrument_all()  # Auto-patch all registered frameworks
    """

    def __init__(self) -> None:
        """Initialize the auto-instrumentor registry."""
        self._hooks: dict[str, Callable[[], None]] = {}

    def register(self, framework: str, hook: Callable[[], None]) -> None:
        """Register an auto-instrumentation hook for a framework.

        Args:
            framework: Framework identifier (e.g., "langchain", "crewai").
            hook: Callable that performs the auto-patching.
        """
        self._hooks[framework] = hook

    def available(self) -> list[str]:
        """List available frameworks for auto-instrumentation.

        Returns:
            List of framework identifiers that have registered hooks.
        """
        return list(self._hooks.keys())

    def instrument(self, framework: str) -> bool:
        """Apply auto-instrumentation for a specific framework.

        Args:
            framework: Framework identifier to instrument.

        Returns:
            True if instrumentation succeeded, False if it failed or the
            framework is not registered.
        """
        hook = self._hooks.get(framework)
        if not hook:
            logger.warning("No auto-instrumentation hook registered for %s", framework)
            return False
        try:
            hook()
            logger.info("Auto-instrumented %s", framework)
            return True
        except Exception:
            logger.warning("Failed to auto-instrument %s", framework, exc_info=True)
            return False

    def instrument_all(self) -> None:
        """Apply auto-instrumentation for all registered frameworks.

        Note:
            Continues instrumenting remaining frameworks even if one fails.
        """
        for fw in self._hooks:
            self.instrument(fw)


_global_instrumentor = AutoInstrumentor()
_defaults_registered = False


def get_instrumentor() -> AutoInstrumentor:
    """Get the global auto-instrumentor instance.

    Returns:
        The global AutoInstrumentor singleton.
    """
    return _global_instrumentor


def _register_defaults() -> None:
    """Register auto-instrumentation hooks for known frameworks.

    This function is called lazily on first use of get_instrumentor()
    to avoid import-time overhead.
    """
    global _defaults_registered
    if _defaults_registered:
        return

    try:
        import langchain  # noqa: F401

        from agent_debugger_sdk.adapters.langchain import register_auto_patch

        _global_instrumentor.register("langchain", register_auto_patch)
    except ImportError:
        pass

    _defaults_registered = True


def ensure_registered() -> None:
    """Ensure default framework hooks are registered.

    Call this explicitly if you need to guarantee registration before
    calling get_instrumentor().available().
    """
    _register_defaults()


# Lazy registration: register defaults on first access to get_instrumentor()
# rather than at module import time. This reduces import overhead.
