"""Auto-patch adapter for LlamaIndex.

Tier 3 strategy: monkey-patches ``llama_index.core.query_engine.BaseQueryEngine.query``
(sync) and ``aquery`` (async) at the class level so that every query engine
invocation emits AGENT_START and AGENT_END trace events without any
user-code changes.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_debugger_sdk.auto_patch._transport import SyncTransport, get_or_create_session
from agent_debugger_sdk.auto_patch.registry import AgentAdapterMixin, BaseAdapter, PatchConfig

logger = logging.getLogger("agent_debugger.auto_patch")


class LlamaIndexAdapter(BaseAdapter, AgentAdapterMixin):
    """Auto-patch adapter for LlamaIndex.

    Monkey-patches ``llama_index.core.query_engine.BaseQueryEngine.query``
    (sync) and ``aquery`` (async) at the class level so that every query
    emits AGENT_START / AGENT_END trace events.

    The original methods are restored on :meth:`unpatch`.
    """

    name = "llamaindex"

    def __init__(self) -> None:
        self._original_query: Any = None
        self._original_aquery: Any = None
        self._transport: SyncTransport | None = None
        self._config: PatchConfig | None = None
        self._session_id: str | None = None

    def is_available(self) -> bool:
        """Return True if ``llama_index.core`` is importable."""
        try:
            import llama_index.core  # noqa: F401

            return True
        except ImportError:
            return False

    def patch(self, config: PatchConfig) -> None:
        """Monkey-patch ``BaseQueryEngine.query`` and ``aquery``.

        Args:
            config: Active patch configuration.
        """
        import llama_index.core.query_engine  # noqa: PLC0415

        BaseQueryEngine = llama_index.core.query_engine.BaseQueryEngine

        # Guard against double-patching
        if getattr(BaseQueryEngine.query, "_peaky_peek_patched", False):
            logger.debug("LlamaIndexAdapter: BaseQueryEngine.query already patched — skipping")
            return

        self._config = config
        self._transport = SyncTransport(config.server_url)
        self._session_id = get_or_create_session(self._transport, config.agent_name, self.name)

        self._original_query = BaseQueryEngine.query
        self._original_aquery = BaseQueryEngine.aquery

        adapter = self

        def traced_query(self_engine: Any, *args: Any, **kwargs: Any) -> Any:
            return adapter._wrap_sync_call(
                lambda: adapter._original_query(self_engine, *args, **kwargs),
                start_name="llamaindex.query",
                end_name="llamaindex.query.end",
                error_name="llamaindex.query.error",
            )

        traced_query._peaky_peek_patched = True  # type: ignore[attr-defined]

        async def traced_aquery(self_engine: Any, *args: Any, **kwargs: Any) -> Any:
            return await adapter._wrap_async_call(
                lambda: adapter._original_aquery(self_engine, *args, **kwargs),
                start_name="llamaindex.aquery",
                end_name="llamaindex.aquery.end",
                error_name="llamaindex.aquery.error",
            )

        traced_aquery._peaky_peek_patched = True  # type: ignore[attr-defined]

        BaseQueryEngine.query = traced_query  # type: ignore[method-assign]
        BaseQueryEngine.aquery = traced_aquery  # type: ignore[method-assign]
        logger.debug("LlamaIndexAdapter: patched BaseQueryEngine.query and aquery")

    def unpatch(self) -> None:
        """Restore the original ``BaseQueryEngine.query`` and ``aquery`` methods."""
        if self._original_query is None:
            return

        try:
            import llama_index.core.query_engine  # noqa: PLC0415

            BaseQueryEngine = llama_index.core.query_engine.BaseQueryEngine
            BaseQueryEngine.query = self._original_query  # type: ignore[method-assign]
            self._original_query = None
            if self._original_aquery is not None:
                BaseQueryEngine.aquery = self._original_aquery  # type: ignore[method-assign]
                self._original_aquery = None
            logger.debug("LlamaIndexAdapter: restored original BaseQueryEngine methods")
        except Exception:
            logger.warning("LlamaIndexAdapter: failed to restore BaseQueryEngine methods", exc_info=True)
        finally:
            if self._transport is not None:
                self._transport.shutdown()
                self._transport = None
            self._session_id = None
