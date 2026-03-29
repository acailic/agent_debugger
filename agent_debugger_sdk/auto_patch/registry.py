"""Auto-patch registry: PatchConfig, BaseAdapter, and PatchRegistry."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

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


class AgentAdapterMixin:
    """Mixin providing common agent-style (AGENT_START/AGENT_END) wrapping logic.

    This mixin is designed for adapters that wrap agent framework orchestration
    methods (e.g., CrewAI.kickoff, LlamaIndex.query, AutoGen.run) and need to
    emit AGENT_START, AGENT_END, and ERROR trace events.

    Adapters using this mixin must:
    - Set self._transport before calling wrap methods
    - Set self._session_id before calling wrap methods

    The wrap methods handle all event emission with proper error handling -
    any exception during event emission is logged but does not propagate.
    """

    def _wrap_sync_call(
        self,
        fn,
        *,
        start_name: str,
        end_name: str,
        error_name: str,
    ):
        """Wrap a synchronous call with AGENT_START/AGENT_END event emission.

        Args:
            fn: A callable that performs the actual work.
            start_name: Event name for AGENT_START.
            end_name: Event name for AGENT_END.
            error_name: Event name for ERROR.

        Returns:
            The result of calling fn().
        """
        from agent_debugger_sdk.core.events import ErrorEvent, EventType, TraceEvent

        transport = self._transport
        session_id = self._session_id or ""
        try:
            start_event = TraceEvent(
                session_id=session_id,
                event_type=EventType.AGENT_START,
                name=start_name,
            )
            if transport is not None:
                transport.send_event(start_event.to_dict())
        except (OSError, ConnectionError, TimeoutError) as e:
            logger.warning("Failed to emit AGENT_START event: %s: %s", type(e).__name__, e)

        try:
            result = fn()
        except Exception as exc:
            try:
                error_event = ErrorEvent(
                    session_id=session_id,
                    event_type=EventType.ERROR,
                    name=error_name,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                if transport is not None:
                    transport.send_event(error_event.to_dict())
            except (OSError, ConnectionError, TimeoutError) as e:
                logger.warning("Failed to emit ERROR event: %s: %s", type(e).__name__, e)
            raise

        try:
            end_event = TraceEvent(
                session_id=session_id,
                event_type=EventType.AGENT_END,
                name=end_name,
            )
            if transport is not None:
                transport.send_event(end_event.to_dict())
        except (OSError, ConnectionError, TimeoutError) as e:
            logger.warning("Failed to emit AGENT_END event: %s: %s", type(e).__name__, e)

        return result

    async def _wrap_async_call(
        self,
        fn,
        *,
        start_name: str,
        end_name: str,
        error_name: str,
    ):
        """Wrap an asynchronous call with AGENT_START/AGENT_END event emission.

        Args:
            fn: An async callable that performs the actual work.
            start_name: Event name for AGENT_START.
            end_name: Event name for AGENT_END.
            error_name: Event name for ERROR.

        Returns:
            The result of awaiting fn().
        """
        from agent_debugger_sdk.core.events import ErrorEvent, EventType, TraceEvent

        transport = self._transport
        session_id = self._session_id or ""
        try:
            start_event = TraceEvent(
                session_id=session_id,
                event_type=EventType.AGENT_START,
                name=start_name,
            )
            if transport is not None:
                transport.send_event(start_event.to_dict())
        except (OSError, ConnectionError, TimeoutError) as e:
            logger.warning("Failed to emit AGENT_START event (async): %s: %s", type(e).__name__, e)

        try:
            result = await fn()
        except Exception as exc:
            try:
                error_event = ErrorEvent(
                    session_id=session_id,
                    event_type=EventType.ERROR,
                    name=error_name,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                if transport is not None:
                    transport.send_event(error_event.to_dict())
            except (OSError, ConnectionError, TimeoutError) as e:
                logger.warning("Failed to emit ERROR event (async): %s: %s", type(e).__name__, e)
            raise

        try:
            end_event = TraceEvent(
                session_id=session_id,
                event_type=EventType.AGENT_END,
                name=end_name,
            )
            if transport is not None:
                transport.send_event(end_event.to_dict())
        except (OSError, ConnectionError, TimeoutError) as e:
            logger.warning("Failed to emit AGENT_END event (async): %s: %s", type(e).__name__, e)

        return result


class BaseAdapter(ABC):
    """Abstract base class for framework auto-patch adapters.

    Each adapter wraps a specific LLM library (e.g. openai, anthropic) and
    knows how to monkey-patch it to emit trace events with zero user code changes.

    Class Attributes:
        name: Short identifier for this adapter (e.g. "openai", "anthropic").
    """

    name: str  # class-level attribute, must be set by subclasses
    _config: PatchConfig
    _transport: "SyncTransport"
    _originals: dict

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

        try:
            session_id = get_or_create_session(self._transport, self._config.agent_name, self.name)
            request_id = self._emit_request(kwargs, session_id)
        except (OSError, ConnectionError, TimeoutError, TypeError, ValueError) as e:
            logger.warning("Failed to emit LLM request: %s: %s", type(e).__name__, e)
            session_id, request_id = "", ""

        start = time.perf_counter()
        try:
            response = original(self_client, *args, **kwargs)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000

        try:
            self._emit_response(response, request_id, session_id, duration_ms)
        except (OSError, ConnectionError, TimeoutError, TypeError, ValueError) as e:
            logger.warning("Failed to emit LLM response: %s: %s", type(e).__name__, e)

        return response

    async def _call_async(self, original, self_client, *args, **kwargs):
        """Wrap an async call with request/response event emission."""
        from agent_debugger_sdk.auto_patch._transport import get_or_create_session

        try:
            session_id = get_or_create_session(self._transport, self._config.agent_name, self.name)
            request_id = self._emit_request(kwargs, session_id)
        except (OSError, ConnectionError, TimeoutError, TypeError, ValueError) as e:
            logger.warning("Failed to emit LLM request: %s: %s", type(e).__name__, e)
            session_id, request_id = "", ""

        start = time.perf_counter()
        try:
            response = await original(self_client, *args, **kwargs)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000

        try:
            self._emit_response(response, request_id, session_id, duration_ms)
        except (OSError, ConnectionError, TimeoutError, TypeError, ValueError) as e:
            logger.warning("Failed to emit LLM response: %s: %s", type(e).__name__, e)

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
            except (AttributeError, ImportError, TypeError, RuntimeError, OSError) as e:
                logger.warning("Failed to patch adapter %r: %s: %s", adapter.name, type(e).__name__, e)

    def unapply(self) -> None:
        """Undo patching for all currently patched adapters."""
        for adapter in list(self._patched):
            try:
                adapter.unpatch()
                logger.info("Unpatched adapter: %s", adapter.name)
            except (AttributeError, RuntimeError, OSError) as e:
                logger.warning("Failed to unpatch adapter %r: %s: %s", adapter.name, type(e).__name__, e)
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
