"""Tests for LlamaIndexAdapter.

``llama_index`` is not installed in this environment, so all tests mock the
module via ``sys.modules`` before calling any adapter method that does
``import llama_index.core``.

The tests verify:
1. ``is_available()`` returns False when llama_index.core is not installed.
2. ``is_available()`` returns True when llama_index.core is present.
3. ``patch()`` wraps ``BaseQueryEngine.query`` and ``aquery``.
4. Calling the wrapped query emits ``agent_start`` and ``agent_end`` events.
5. ``unpatch()`` restores original methods.
6. Double-patch guard works.
7. Server unreachability does not raise.
8. Errors during query emit an error event and re-raise.
"""
from __future__ import annotations

import asyncio
import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import agent_debugger_sdk.auto_patch._transport as transport_module
from agent_debugger_sdk.auto_patch.adapters.llamaindex_adapter import LlamaIndexAdapter
from agent_debugger_sdk.auto_patch.registry import PatchConfig

_FLUSH_TIMEOUT = 2.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_fake_llama_index() -> tuple[types.ModuleType, types.ModuleType, types.ModuleType]:
    """Return fake llama_index module hierarchy with a BaseQueryEngine class."""
    fake_llama_index = types.ModuleType("llama_index")
    fake_core = types.ModuleType("llama_index.core")
    fake_query_engine = types.ModuleType("llama_index.core.query_engine")

    class FakeBaseQueryEngine:
        def query(self, *args: Any, **kwargs: Any) -> str:
            return "query_result"

        async def aquery(self, *args: Any, **kwargs: Any) -> str:
            return "aquery_result"

    fake_query_engine.BaseQueryEngine = FakeBaseQueryEngine  # type: ignore[attr-defined]
    fake_core.query_engine = fake_query_engine  # type: ignore[attr-defined]
    fake_llama_index.core = fake_core  # type: ignore[attr-defined]
    return fake_llama_index, fake_core, fake_query_engine


def _flush(adapter: LlamaIndexAdapter) -> None:
    """Drain the background transport thread queue."""
    assert adapter._transport is not None
    transport = adapter._transport
    transport._queue.put(transport_module._SENTINEL)
    transport._thread.join(timeout=_FLUSH_TIMEOUT)


def _get_trace_events(mock_httpx: MagicMock) -> list[dict]:
    """Extract the JSON bodies of all /api/traces POST calls."""
    events = []
    for c in mock_httpx.post.call_args_list:
        url = c.args[0] if c.args else c.kwargs.get("url", "")
        if "/api/traces" in str(url):
            payload = c.kwargs.get("json") or (c.args[1] if len(c.args) > 1 else None)
            if isinstance(payload, dict):
                events.append(payload)
    return events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_session():
    """Reset shared session state between tests."""
    original = transport_module._current_session_id
    yield
    transport_module._current_session_id = original


@pytest.fixture()
def mock_httpx():
    """Patch httpx.Client so SyncTransport never touches the network."""
    with patch("httpx.Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.get.side_effect = Exception("no server")
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "session-llamaindex-test"}
        mock_response.raise_for_status.return_value = None
        mock_client.post.return_value = mock_response
        yield mock_client


@pytest.fixture()
def fake_llama_index(mock_httpx):
    """Inject fake llama_index modules into sys.modules."""
    llama_index, core, query_engine = _build_fake_llama_index()
    module_patches = {
        "llama_index": llama_index,
        "llama_index.core": core,
        "llama_index.core.query_engine": query_engine,
    }
    with patch.dict(sys.modules, module_patches):
        yield llama_index, core, query_engine


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


class TestLlamaIndexAdapterIsAvailable:
    def test_returns_false_when_llama_index_absent(self) -> None:
        with patch.dict(sys.modules, {"llama_index.core": None}):
            adapter = LlamaIndexAdapter()
            assert adapter.is_available() is False

    def test_returns_true_when_llama_index_present(self) -> None:
        fake_root = types.ModuleType("llama_index")
        fake_mod = types.ModuleType("llama_index.core")
        with patch.dict(sys.modules, {"llama_index": fake_root, "llama_index.core": fake_mod}):
            adapter = LlamaIndexAdapter()
            assert adapter.is_available() is True


# ---------------------------------------------------------------------------
# patch / unpatch
# ---------------------------------------------------------------------------


class TestLlamaIndexAdapterPatchUnpatch:
    def test_patch_replaces_query(self, fake_llama_index, mock_httpx) -> None:
        """patch() should replace BaseQueryEngine.query with a traced wrapper."""
        _, _, query_engine = fake_llama_index
        original_query = query_engine.BaseQueryEngine.query

        adapter = LlamaIndexAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        assert query_engine.BaseQueryEngine.query is not original_query
        assert getattr(query_engine.BaseQueryEngine.query, "_peaky_peek_patched", False) is True

        adapter.unpatch()

    def test_patch_replaces_aquery(self, fake_llama_index, mock_httpx) -> None:
        """patch() should replace BaseQueryEngine.aquery with a traced wrapper."""
        _, _, query_engine = fake_llama_index
        original_aquery = query_engine.BaseQueryEngine.aquery

        adapter = LlamaIndexAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        assert query_engine.BaseQueryEngine.aquery is not original_aquery
        assert getattr(query_engine.BaseQueryEngine.aquery, "_peaky_peek_patched", False) is True

        adapter.unpatch()

    def test_unpatch_restores_query(self, fake_llama_index, mock_httpx) -> None:
        """unpatch() should restore the original BaseQueryEngine.query."""
        _, _, query_engine = fake_llama_index
        original_query = query_engine.BaseQueryEngine.query

        adapter = LlamaIndexAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)
        adapter.unpatch()

        assert query_engine.BaseQueryEngine.query is original_query

    def test_unpatch_restores_aquery(self, fake_llama_index, mock_httpx) -> None:
        """unpatch() should restore the original BaseQueryEngine.aquery."""
        _, _, query_engine = fake_llama_index
        original_aquery = query_engine.BaseQueryEngine.aquery

        adapter = LlamaIndexAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)
        adapter.unpatch()

        assert query_engine.BaseQueryEngine.aquery is original_aquery

    def test_unpatch_without_patch_does_not_raise(self) -> None:
        """Calling unpatch() before patch() should be a no-op."""
        adapter = LlamaIndexAdapter()
        adapter.unpatch()

    def test_double_patch_is_guarded(self, fake_llama_index, mock_httpx) -> None:
        """Calling patch() twice should not double-wrap BaseQueryEngine.query."""
        _, _, query_engine = fake_llama_index

        adapter = LlamaIndexAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)
        first_query = query_engine.BaseQueryEngine.query

        adapter.patch(config)  # second patch — should be a no-op
        assert query_engine.BaseQueryEngine.query is first_query

        adapter.unpatch()

    def test_patch_creates_transport(self, fake_llama_index, mock_httpx) -> None:
        adapter = LlamaIndexAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)
        assert adapter._transport is not None
        adapter.unpatch()


# ---------------------------------------------------------------------------
# Event emission via patched query (sync)
# ---------------------------------------------------------------------------


class TestLlamaIndexAdapterSyncEventEmission:
    def test_query_emits_agent_start_and_end(self, fake_llama_index, mock_httpx) -> None:
        """The traced query wrapper should emit agent_start and agent_end events."""
        _, _, query_engine = fake_llama_index

        adapter = LlamaIndexAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        engine_instance = query_engine.BaseQueryEngine()
        result = query_engine.BaseQueryEngine.query(engine_instance, "What is AI?")
        assert result == "query_result"

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "agent_start" in types_
        assert "agent_end" in types_

        adapter.unpatch()

    def test_query_start_event_name(self, fake_llama_index, mock_httpx) -> None:
        """The agent_start event should carry the expected name."""
        _, _, query_engine = fake_llama_index

        adapter = LlamaIndexAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        engine_instance = query_engine.BaseQueryEngine()
        query_engine.BaseQueryEngine.query(engine_instance, "test query")

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        start = next(e for e in sent if e["event_type"] == "agent_start")
        assert start["name"] == "llamaindex.query"

        adapter.unpatch()

    def test_query_error_emits_error_event_and_reraises(
        self, fake_llama_index, mock_httpx
    ) -> None:
        """When query raises, an error event should be sent and the exception re-raised."""
        _, _, query_engine = fake_llama_index
        original_query = query_engine.BaseQueryEngine.query

        def boom(self_engine, *args, **kwargs):  # noqa: ANN001
            raise RuntimeError("query failed")

        query_engine.BaseQueryEngine.query = boom

        adapter = LlamaIndexAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        engine_instance = query_engine.BaseQueryEngine()
        with pytest.raises(RuntimeError, match="query failed"):
            query_engine.BaseQueryEngine.query(engine_instance, "test")

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "error" in types_

        query_engine.BaseQueryEngine.query = original_query
        adapter.unpatch()

    def test_server_unreachable_does_not_raise(self, fake_llama_index, mock_httpx) -> None:
        """Even if the server is unreachable, the query should complete."""
        _, _, query_engine = fake_llama_index
        mock_httpx.post.side_effect = Exception("connection refused")

        adapter = LlamaIndexAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        engine_instance = query_engine.BaseQueryEngine()
        result = query_engine.BaseQueryEngine.query(engine_instance, "safe query")
        assert result == "query_result"

        adapter.unpatch()


# ---------------------------------------------------------------------------
# Event emission via patched aquery (async)
# ---------------------------------------------------------------------------


class TestLlamaIndexAdapterAsyncEventEmission:
    def test_aquery_emits_agent_start_and_end(self, fake_llama_index, mock_httpx) -> None:
        """The traced aquery wrapper should emit agent_start and agent_end events."""
        _, _, query_engine = fake_llama_index

        adapter = LlamaIndexAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        engine_instance = query_engine.BaseQueryEngine()
        result = asyncio.run(query_engine.BaseQueryEngine.aquery(engine_instance, "async query"))
        assert result == "aquery_result"

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "agent_start" in types_
        assert "agent_end" in types_

        adapter.unpatch()

    def test_aquery_start_event_name(self, fake_llama_index, mock_httpx) -> None:
        """The async agent_start event should carry the expected name."""
        _, _, query_engine = fake_llama_index

        adapter = LlamaIndexAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        engine_instance = query_engine.BaseQueryEngine()
        asyncio.run(query_engine.BaseQueryEngine.aquery(engine_instance, "test"))

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        start = next(e for e in sent if e["event_type"] == "agent_start")
        assert start["name"] == "llamaindex.aquery"

        adapter.unpatch()
