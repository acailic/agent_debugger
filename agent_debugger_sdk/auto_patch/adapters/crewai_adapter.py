"""Auto-patch adapter for CrewAI.

Tier 3 strategy: monkey-patches ``crewai.Crew.kickoff`` and
``crewai.Crew.kickoff_async`` at the class level so that every crew
run emits AGENT_START and AGENT_END trace events without any user-code
changes.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_debugger_sdk.auto_patch._transport import SyncTransport, get_or_create_session
from agent_debugger_sdk.auto_patch.registry import BaseAdapter, PatchConfig
from agent_debugger_sdk.core.events import ErrorEvent, EventType, TraceEvent

logger = logging.getLogger("agent_debugger.auto_patch")


class CrewAIAdapter(BaseAdapter):
    """Auto-patch adapter for CrewAI.

    Monkey-patches ``crewai.Crew.kickoff`` (sync) and
    ``crewai.Crew.kickoff_async`` (async) at the class level so that
    every crew invocation automatically emits AGENT_START / AGENT_END
    trace events.

    The original methods are restored on :meth:`unpatch`.
    """

    name = "crewai"

    def __init__(self) -> None:
        self._original_kickoff: Any = None
        self._original_kickoff_async: Any = None
        self._transport: SyncTransport | None = None
        self._config: PatchConfig | None = None
        self._session_id: str | None = None

    def is_available(self) -> bool:
        """Return True if ``crewai`` is importable."""
        try:
            import crewai  # noqa: F401

            return True
        except ImportError:
            return False

    def patch(self, config: PatchConfig) -> None:
        """Monkey-patch ``crewai.Crew.kickoff`` and ``kickoff_async``.

        Args:
            config: Active patch configuration.
        """
        import crewai  # noqa: PLC0415

        # Guard against double-patching
        if getattr(crewai.Crew.kickoff, "_peaky_peek_patched", False):
            logger.debug("CrewAIAdapter: Crew.kickoff already patched — skipping")
            return

        self._config = config
        self._transport = SyncTransport(config.server_url)
        self._session_id = get_or_create_session(self._transport, config.agent_name, self.name)

        self._original_kickoff = crewai.Crew.kickoff
        self._original_kickoff_async = crewai.Crew.kickoff_async

        adapter = self

        def traced_kickoff(self_crew: Any, *args: Any, **kwargs: Any) -> Any:
            transport = adapter._transport
            session_id = adapter._session_id or ""
            try:
                start_event = TraceEvent(
                    session_id=session_id,
                    event_type=EventType.AGENT_START,
                    name="crew.kickoff",
                )
                transport.send_event(start_event.to_dict())
            except Exception:
                logger.warning("CrewAIAdapter: failed to emit AGENT_START event", exc_info=True)

            try:
                result = adapter._original_kickoff(self_crew, *args, **kwargs)
            except Exception as exc:
                try:
                    error_event = ErrorEvent(
                        session_id=session_id,
                        event_type=EventType.ERROR,
                        name="crew.kickoff.error",
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                    if transport is not None:
                        transport.send_event(error_event.to_dict())
                except Exception:
                    logger.warning("CrewAIAdapter: failed to emit ERROR event", exc_info=True)
                raise

            try:
                end_event = TraceEvent(
                    session_id=session_id,
                    event_type=EventType.AGENT_END,
                    name="crew.kickoff.end",
                )
                transport.send_event(end_event.to_dict())
            except Exception:
                logger.warning("CrewAIAdapter: failed to emit AGENT_END event", exc_info=True)

            return result

        traced_kickoff._peaky_peek_patched = True  # type: ignore[attr-defined]

        async def traced_kickoff_async(self_crew: Any, *args: Any, **kwargs: Any) -> Any:
            transport = adapter._transport
            session_id = adapter._session_id or ""
            try:
                start_event = TraceEvent(
                    session_id=session_id,
                    event_type=EventType.AGENT_START,
                    name="crew.kickoff_async",
                )
                transport.send_event(start_event.to_dict())
            except Exception:
                logger.warning("CrewAIAdapter: failed to emit AGENT_START event (async)", exc_info=True)

            try:
                result = await adapter._original_kickoff_async(self_crew, *args, **kwargs)
            except Exception as exc:
                try:
                    error_event = ErrorEvent(
                        session_id=session_id,
                        event_type=EventType.ERROR,
                        name="crew.kickoff_async.error",
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                    if transport is not None:
                        transport.send_event(error_event.to_dict())
                except Exception:
                    logger.warning("CrewAIAdapter: failed to emit ERROR event (async)", exc_info=True)
                raise

            try:
                end_event = TraceEvent(
                    session_id=session_id,
                    event_type=EventType.AGENT_END,
                    name="crew.kickoff_async.end",
                )
                transport.send_event(end_event.to_dict())
            except Exception:
                logger.warning("CrewAIAdapter: failed to emit AGENT_END event (async)", exc_info=True)

            return result

        traced_kickoff_async._peaky_peek_patched = True  # type: ignore[attr-defined]

        crewai.Crew.kickoff = traced_kickoff  # type: ignore[method-assign]
        crewai.Crew.kickoff_async = traced_kickoff_async  # type: ignore[method-assign]
        logger.debug("CrewAIAdapter: patched Crew.kickoff and Crew.kickoff_async")

    def unpatch(self) -> None:
        """Restore the original ``crewai.Crew.kickoff`` and ``kickoff_async`` methods."""
        if self._original_kickoff is None:
            return

        try:
            import crewai  # noqa: PLC0415

            crewai.Crew.kickoff = self._original_kickoff  # type: ignore[method-assign]
            self._original_kickoff = None
            if self._original_kickoff_async is not None:
                crewai.Crew.kickoff_async = self._original_kickoff_async  # type: ignore[method-assign]
                self._original_kickoff_async = None
            logger.debug("CrewAIAdapter: restored original Crew.kickoff and kickoff_async")
        except Exception:
            logger.warning("CrewAIAdapter: failed to restore Crew methods", exc_info=True)
        finally:
            if self._transport is not None:
                self._transport.shutdown()
                self._transport = None
            self._session_id = None
