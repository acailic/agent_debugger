"""Auto-patch adapter for LlamaIndex.

Tier 3 strategy: monkey-patches ``llama_index.core.query_engine.BaseQueryEngine.query``
(sync) and ``aquery`` (async) at the class level so that every query engine
invocation emits AGENT_START and AGENT_END trace events without any
user-code changes.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_debugger_sdk.auto_patch.registry import BaseAdapter, PatchConfig
from agent_debugger_sdk.core.events import EventType

logger = logging.getLogger("agent_debugger.auto_patch")


class LlamaIndexAdapter(BaseAdapter):
    """Auto-patch adapter for LlamaIndex.

    Monkey-patches ``llama_index.core.query_engine.BaseQueryEngine.query``
    (sync) and ``aquery`` (async) at the class level so that every query
    emits AGENT_START / AGENT_END trace events.

    The original methods are restored on :meth:`unpatch`.
    """

    name = "llamaindex"

    def __init__(self) -> None:
        super().__init__()
        self._original_query: Any = None
        self._original_aquery: Any = None

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
        if self._is_patched(BaseQueryEngine.query):
            logger.debug("LlamaIndexAdapter: BaseQueryEngine.query already patched — skipping")
            return

        self._setup_transport_and_session(config)

        self._original_query = BaseQueryEngine.query
        self._original_aquery = BaseQueryEngine.aquery

        adapter = self

        def traced_query(self_engine: Any, *args: Any, **kwargs: Any) -> Any:
            adapter._emit_trace_event_safe(EventType.AGENT_START, "llamaindex.query")

            try:
                result = adapter._original_query(self_engine, *args, **kwargs)
            except Exception as exc:
                adapter._emit_error_event_safe("llamaindex.query.error", exc)
                raise

            adapter._emit_trace_event_safe(EventType.AGENT_END, "llamaindex.query.end")
            return result

        traced_query._peaky_peek_patched = True  # type: ignore[attr-defined]

        async def traced_aquery(self_engine: Any, *args: Any, **kwargs: Any) -> Any:
            adapter._emit_trace_event_safe(EventType.AGENT_START, "llamaindex.aquery", is_async=True)

            try:
                result = await adapter._original_aquery(self_engine, *args, **kwargs)
            except Exception as exc:
                adapter._emit_error_event_safe("llamaindex.aquery.error", exc, is_async=True)
                raise

            adapter._emit_trace_event_safe(EventType.AGENT_END, "llamaindex.aquery.end", is_async=True)
            return result

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
            self._cleanup_transport()
