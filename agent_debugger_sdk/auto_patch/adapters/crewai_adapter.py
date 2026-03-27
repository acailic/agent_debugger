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
from agent_debugger_sdk.auto_patch.registry import AgentAdapterMixin, BaseAdapter, PatchConfig

logger = logging.getLogger("agent_debugger.auto_patch")


class CrewAIAdapter(BaseAdapter, AgentAdapterMixin):
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
            return adapter._wrap_sync_call(
                lambda: adapter._original_kickoff(self_crew, *args, **kwargs),
                start_name="crew.kickoff",
                end_name="crew.kickoff.end",
                error_name="crew.kickoff.error",
            )

        traced_kickoff._peaky_peek_patched = True  # type: ignore[attr-defined]

        async def traced_kickoff_async(self_crew: Any, *args: Any, **kwargs: Any) -> Any:
            return await adapter._wrap_async_call(
                lambda: adapter._original_kickoff_async(self_crew, *args, **kwargs),
                start_name="crew.kickoff_async",
                end_name="crew.kickoff_async.end",
                error_name="crew.kickoff_async.error",
            )

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
