"""Auto-patch registry: PatchConfig, BaseAdapter, and PatchRegistry."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_debugger_sdk.auto_patch._transport import SyncTransport

logger = logging.getLogger("agent_debugger.auto_patch")


@dataclass
class PatchConfig:
    """Configuration for the auto-patch system.

    Attributes:
        server_url: Base URL of the Peaky Peek collector server.
        capture_content: Whether to capture full message/response content.
            Disabled by default for privacy.
        agent_name: Logical name for the agent owning these LLM calls.
            Used as the session agent_name in the collector.
    """

    server_url: str = "http://localhost:8000"
    capture_content: bool = False
    agent_name: str = "auto-patched-agent"


class BaseAdapter(ABC):
    """Abstract base class for framework auto-patch adapters.

    Each adapter wraps a specific LLM library (e.g. openai, anthropic) and
    knows how to monkey-patch it to emit trace events with zero user code changes.

    Class Attributes:
        name: Short identifier for this adapter (e.g. "openai", "anthropic").

    Instance Attributes:
        _config: The active patch configuration.
        _transport: The SyncTransport for sending events.
        _session_id: The current session ID.
    """

    name: str  # class-level attribute, must be set by subclasses

    def __init__(self) -> None:
        """Initialize common adapter state."""
        self._config: PatchConfig | None = None
        self._transport: "SyncTransport | None" = None
        self._session_id: str | None = None

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

    # ------------------------------------------------------------------
    # Shared helper methods for adapters
    # ------------------------------------------------------------------

    def _is_patched(self, method: Any) -> bool:
        """Check if a method is already patched.

        Args:
            method: The method to check.

        Returns:
            True if the method has the _peaky_peek_patched attribute set to True.
        """
        return getattr(method, "_peaky_peek_patched", False)

    def _setup_transport_and_session(self, config: PatchConfig) -> None:
        """Create transport and get session ID.

        Args:
            config: The patch configuration.
        """
        from agent_debugger_sdk.auto_patch._transport import SyncTransport, get_or_create_session

        self._config = config
        self._transport = SyncTransport(config.server_url)
        self._session_id = get_or_create_session(self._transport, config.agent_name, self.name)

    def _cleanup_transport(self) -> None:
        """Shutdown transport and clear session state."""
        if self._transport is not None:
            self._transport.shutdown()
            self._transport = None
        self._session_id = None

    def _safe_emit_event(
        self,
        event: Any,
        *,
        event_type_name: str = "event",
    ) -> None:
        """Emit an event with exception handling.

        Args:
            event: The event object to emit (must have to_dict() method).
            event_type_name: Descriptive name for logging (e.g. "AGENT_START").
        """
        try:
            if self._transport is not None:
                self._transport.send_event(event.to_dict())
        except Exception:
            logger.warning(
                "%s: failed to emit %s event",
                type(self).__name__,
                event_type_name,
                exc_info=True,
            )

    def _emit_trace_event_safe(
        self,
        event_type: Any,
        name: str,
        *,
        is_async: bool = False,
    ) -> None:
        """Emit a TraceEvent with exception handling.

        Args:
            event_type: The EventType (e.g., EventType.AGENT_START).
            name: The event name.
            is_async: Whether this is for an async context (affects log message).
        """
        from agent_debugger_sdk.core.events import TraceEvent

        try:
            if self._transport is not None and self._session_id:
                event = TraceEvent(
                    session_id=self._session_id,
                    event_type=event_type,
                    name=name,
                )
                self._transport.send_event(event.to_dict())
        except Exception:
            logger.warning(
                "%s: failed to emit %s event%s",
                type(self).__name__,
                event_type.value,
                " (async)" if is_async else "",
                exc_info=True,
            )

    def _emit_error_event_safe(
        self,
        name: str,
        exc: Exception,
        *,
        is_async: bool = False,
    ) -> None:
        """Emit an ErrorEvent with exception handling.

        Args:
            name: The error event name.
            exc: The exception that occurred.
            is_async: Whether this is for an async context (affects log message).
        """
        from agent_debugger_sdk.core.events import ErrorEvent, EventType

        try:
            if self._transport is not None and self._session_id:
                event = ErrorEvent(
                    session_id=self._session_id,
                    event_type=EventType.ERROR,
                    name=name,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                self._transport.send_event(event.to_dict())
        except Exception:
            logger.warning(
                "%s: failed to emit ERROR event%s",
                type(self).__name__,
                " (async)" if is_async else "",
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Wrapper factories (shared implementation)
    # ------------------------------------------------------------------

    def _make_sync_wrapper(self, original):
        """Create a sync wrapper that delegates to _call_sync."""
        adapter = self

        def wrapper(self_client, *args, **kwargs):
            if kwargs.get("stream"):
                return original(self_client, *args, **kwargs)
            return adapter._call_sync(original, self_client, *args, **kwargs)

        return wrapper

    def _make_async_wrapper(self, original):
        """Create an async wrapper that delegates to _call_async."""
        adapter = self

        async def wrapper(self_client, *args, **kwargs):
            if kwargs.get("stream"):
                return await original(self_client, *args, **kwargs)
            return await adapter._call_async(original, self_client, *args, **kwargs)

        return wrapper

    # ------------------------------------------------------------------
    # Instrumented call paths (shared implementation)
    # ------------------------------------------------------------------

    def _call_sync(self, original, self_client, *args, **kwargs):
        """Wrap a sync call with request/response event emission."""
        from agent_debugger_sdk.auto_patch._transport import get_or_create_session

        if self._config is None or self._transport is None:
            return original(self_client, *args, **kwargs)

        try:
            session_id = get_or_create_session(self._transport, self._config.agent_name, self.name)
            request_id = self._emit_request(kwargs, session_id)
        except Exception:
            logger.warning("Failed to emit LLM request", exc_info=True)
            session_id, request_id = "", ""

        start = time.perf_counter()
        try:
            response = original(self_client, *args, **kwargs)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000

        try:
            self._emit_response(response, request_id, session_id, duration_ms)
        except Exception:
            logger.warning("Failed to emit LLM response", exc_info=True)

        return response

    async def _call_async(self, original, self_client, *args, **kwargs):
        """Wrap an async call with request/response event emission."""
        from agent_debugger_sdk.auto_patch._transport import get_or_create_session

        if self._config is None or self._transport is None:
            return await original(self_client, *args, **kwargs)

        try:
            session_id = get_or_create_session(self._transport, self._config.agent_name, self.name)
            request_id = self._emit_request(kwargs, session_id)
        except Exception:
            logger.warning("Failed to emit LLM request", exc_info=True)
            session_id, request_id = "", ""

        start = time.perf_counter()
        try:
            response = await original(self_client, *args, **kwargs)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000

        try:
            self._emit_response(response, request_id, session_id, duration_ms)
        except Exception:
            logger.warning("Failed to emit LLM response", exc_info=True)

        return response

    # ------------------------------------------------------------------
    # Framework-specific event emission (override in subclasses that need it)
    # ------------------------------------------------------------------

    def _emit_request(self, kwargs: dict, session_id: str) -> str:
        """Build and send an LLMRequestEvent; return its event id.

        Subclasses that use the shared _call_sync/_call_async methods must override this.
        Adapters using different patterns (e.g., callback handlers) can leave this as-is.
        """
        raise NotImplementedError("Subclass must implement _emit_request")

    def _emit_response(
        self,
        response,
        request_event_id: str,
        session_id: str,
        duration_ms: float,
    ) -> None:
        """Build and send LLMResponseEvent plus individual ToolCallEvents.

        Subclasses that use the shared _call_sync/_call_async methods must override this.
        Adapters using different patterns (e.g., callback handlers) can leave this as-is.
        """
        raise NotImplementedError("Subclass must implement _emit_response")


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

    def registered_names(self) -> list[str]:
        """Return names of all registered adapters.

        Returns:
            List of adapter name strings.
        """
        return [a.name for a in self._adapters]


_registry = PatchRegistry()


def get_registry() -> PatchRegistry:
    """Return the global singleton PatchRegistry.

    Returns:
        The module-level PatchRegistry instance shared across all adapters.
    """
    return _registry
