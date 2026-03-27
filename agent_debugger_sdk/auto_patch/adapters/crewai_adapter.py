"""Auto-patch adapter for CrewAI.

Tier 3 strategy: monkey-patches ``crewai.Crew.kickoff`` and
``crewai.Crew.kickoff_async`` at the class level so that every crew
run emits AGENT_START and AGENT_END trace events without any user-code
changes.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_debugger_sdk.auto_patch.registry import BaseAdapter, PatchConfig
from agent_debugger_sdk.core.events import EventType

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
        super().__init__()
        self._original_kickoff: Any = None
        self._original_kickoff_async: Any = None

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
        if self._is_patched(crewai.Crew.kickoff):
            logger.debug("CrewAIAdapter: Crew.kickoff already patched — skipping")
            return

        self._setup_transport_and_session(config)

        self._original_kickoff = crewai.Crew.kickoff
        self._original_kickoff_async = crewai.Crew.kickoff_async

        adapter = self

        def traced_kickoff(self_crew: Any, *args: Any, **kwargs: Any) -> Any:
            adapter._emit_trace_event_safe(EventType.AGENT_START, "crew.kickoff")

            try:
                result = adapter._original_kickoff(self_crew, *args, **kwargs)
            except Exception as exc:
                adapter._emit_error_event_safe("crew.kickoff.error", exc)
                raise

            adapter._emit_trace_event_safe(EventType.AGENT_END, "crew.kickoff.end")
            return result

        traced_kickoff._peaky_peek_patched = True  # type: ignore[attr-defined]

        async def traced_kickoff_async(self_crew: Any, *args: Any, **kwargs: Any) -> Any:
            adapter._emit_trace_event_safe(EventType.AGENT_START, "crew.kickoff_async", is_async=True)

            try:
                result = await adapter._original_kickoff_async(self_crew, *args, **kwargs)
            except Exception as exc:
                adapter._emit_error_event_safe("crew.kickoff_async.error", exc, is_async=True)
                raise

            adapter._emit_trace_event_safe(EventType.AGENT_END, "crew.kickoff_async.end", is_async=True)
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
            self._cleanup_transport()
