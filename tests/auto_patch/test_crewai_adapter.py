"""Tests for CrewAIAdapter.

``crewai`` is not installed in this environment, so all tests mock the
module via ``sys.modules`` before calling any adapter method that does
``import crewai``.

The tests verify:
1. ``is_available()`` returns False when crewai is not installed.
2. ``is_available()`` returns True when crewai is present.
3. ``patch()`` wraps ``Crew.kickoff`` and ``Crew.kickoff_async``.
4. Calling the wrapped method emits ``agent_start`` and ``agent_end`` events.
5. ``unpatch()`` restores original methods.
6. Double-patch guard works.
7. Server unreachability does not raise.
8. Errors during kickoff emit an error event and re-raise.
"""
from __future__ import annotations

import asyncio
import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import agent_debugger_sdk.auto_patch._transport as transport_module
from agent_debugger_sdk.auto_patch.adapters.crewai_adapter import CrewAIAdapter
from agent_debugger_sdk.auto_patch.registry import PatchConfig

_FLUSH_TIMEOUT = 2.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_fake_crewai() -> types.ModuleType:
    """Return a fake ``crewai`` module with a minimal Crew class."""
    fake_crewai = types.ModuleType("crewai")

    class FakeCrew:
        def kickoff(self, *args: Any, **kwargs: Any) -> str:
            return "crew_result"

        async def kickoff_async(self, *args: Any, **kwargs: Any) -> str:
            return "crew_result_async"

    fake_crewai.Crew = FakeCrew  # type: ignore[attr-defined]
    return fake_crewai


def _flush(adapter: CrewAIAdapter) -> None:
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
        mock_response.json.return_value = {"id": "session-crewai-test"}
        mock_response.raise_for_status.return_value = None
        mock_client.post.return_value = mock_response
        yield mock_client


@pytest.fixture()
def fake_crewai(mock_httpx):
    """Inject a fake ``crewai`` module into sys.modules."""
    mod = _build_fake_crewai()
    with patch.dict(sys.modules, {"crewai": mod}):
        yield mod


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


class TestCrewAIAdapterIsAvailable:
    def test_returns_false_when_crewai_absent(self) -> None:
        with patch.dict(sys.modules, {"crewai": None}):
            adapter = CrewAIAdapter()
            assert adapter.is_available() is False

    def test_returns_true_when_crewai_present(self) -> None:
        fake_mod = types.ModuleType("crewai")
        fake_mod.Crew = object  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"crewai": fake_mod}):
            adapter = CrewAIAdapter()
            assert adapter.is_available() is True


# ---------------------------------------------------------------------------
# patch / unpatch
# ---------------------------------------------------------------------------


class TestCrewAIAdapterPatchUnpatch:
    def test_patch_replaces_crew_kickoff(self, fake_crewai, mock_httpx) -> None:
        """patch() should replace Crew.kickoff with a traced wrapper."""
        original_kickoff = fake_crewai.Crew.kickoff

        adapter = CrewAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        assert fake_crewai.Crew.kickoff is not original_kickoff
        assert getattr(fake_crewai.Crew.kickoff, "_peaky_peek_patched", False) is True

        adapter.unpatch()

    def test_patch_replaces_crew_kickoff_async(self, fake_crewai, mock_httpx) -> None:
        """patch() should replace Crew.kickoff_async with a traced wrapper."""
        original_kickoff_async = fake_crewai.Crew.kickoff_async

        adapter = CrewAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        assert fake_crewai.Crew.kickoff_async is not original_kickoff_async
        assert getattr(fake_crewai.Crew.kickoff_async, "_peaky_peek_patched", False) is True

        adapter.unpatch()

    def test_unpatch_restores_kickoff(self, fake_crewai, mock_httpx) -> None:
        """unpatch() should restore the original Crew.kickoff."""
        original_kickoff = fake_crewai.Crew.kickoff

        adapter = CrewAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)
        adapter.unpatch()

        assert fake_crewai.Crew.kickoff is original_kickoff

    def test_unpatch_restores_kickoff_async(self, fake_crewai, mock_httpx) -> None:
        """unpatch() should restore the original Crew.kickoff_async."""
        original_kickoff_async = fake_crewai.Crew.kickoff_async

        adapter = CrewAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)
        adapter.unpatch()

        assert fake_crewai.Crew.kickoff_async is original_kickoff_async

    def test_unpatch_without_patch_does_not_raise(self) -> None:
        """Calling unpatch() before patch() should be a no-op."""
        adapter = CrewAIAdapter()
        adapter.unpatch()  # should not raise

    def test_double_patch_is_guarded(self, fake_crewai, mock_httpx) -> None:
        """Calling patch() twice should not double-wrap Crew.kickoff."""
        adapter = CrewAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)
        first_kickoff = fake_crewai.Crew.kickoff

        adapter.patch(config)  # second patch — should be a no-op
        assert fake_crewai.Crew.kickoff is first_kickoff

        adapter.unpatch()

    def test_patch_creates_transport(self, fake_crewai, mock_httpx) -> None:
        adapter = CrewAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)
        assert adapter._transport is not None
        adapter.unpatch()


# ---------------------------------------------------------------------------
# Event emission via patched kickoff (sync)
# ---------------------------------------------------------------------------


class TestCrewAIAdapterSyncEventEmission:
    def test_kickoff_emits_agent_start_and_end(self, fake_crewai, mock_httpx) -> None:
        """The traced kickoff wrapper should emit agent_start and agent_end events."""
        adapter = CrewAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        crew_instance = fake_crewai.Crew()
        result = fake_crewai.Crew.kickoff(crew_instance)
        assert result == "crew_result"

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "agent_start" in types_
        assert "agent_end" in types_

        adapter.unpatch()

    def test_kickoff_start_event_name(self, fake_crewai, mock_httpx) -> None:
        """The agent_start event should carry the expected name."""
        adapter = CrewAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        crew_instance = fake_crewai.Crew()
        fake_crewai.Crew.kickoff(crew_instance)

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        start = next(e for e in sent if e["event_type"] == "agent_start")
        assert start["name"] == "crew.kickoff"

        adapter.unpatch()

    def test_kickoff_error_emits_error_event_and_reraises(self, fake_crewai, mock_httpx) -> None:
        """When kickoff raises, an error event should be sent and the exception re-raised."""
        adapter = CrewAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        # Inject failure via the saved original — after patching, not before
        saved_original = adapter._original_kickoff
        adapter._original_kickoff = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("crew failed"))
        try:
            crew_instance = fake_crewai.Crew()
            with pytest.raises(RuntimeError, match="crew failed"):
                fake_crewai.Crew.kickoff(crew_instance)

            _flush(adapter)
            sent = _get_trace_events(mock_httpx)
            types_ = [e["event_type"] for e in sent]
            assert "error" in types_
        finally:
            adapter._original_kickoff = saved_original
            adapter.unpatch()

    def test_server_unreachable_does_not_raise(self, fake_crewai, mock_httpx) -> None:
        """Even if the server is unreachable, kickoff should complete."""
        mock_httpx.post.side_effect = Exception("connection refused")

        adapter = CrewAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        crew_instance = fake_crewai.Crew()
        result = fake_crewai.Crew.kickoff(crew_instance)
        assert result == "crew_result"

        adapter.unpatch()


# ---------------------------------------------------------------------------
# Event emission via patched kickoff_async
# ---------------------------------------------------------------------------


class TestCrewAIAdapterAsyncEventEmission:
    def test_kickoff_async_emits_agent_start_and_end(self, fake_crewai, mock_httpx) -> None:
        """The traced kickoff_async wrapper should emit agent_start and agent_end events."""
        adapter = CrewAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        crew_instance = fake_crewai.Crew()
        result = asyncio.run(fake_crewai.Crew.kickoff_async(crew_instance))
        assert result == "crew_result_async"

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "agent_start" in types_
        assert "agent_end" in types_

        adapter.unpatch()

    def test_kickoff_async_start_event_name(self, fake_crewai, mock_httpx) -> None:
        """The async agent_start event should carry the expected name."""
        adapter = CrewAIAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        crew_instance = fake_crewai.Crew()
        asyncio.run(fake_crewai.Crew.kickoff_async(crew_instance))

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        start = next(e for e in sent if e["event_type"] == "agent_start")
        assert start["name"] == "crew.kickoff_async"

        adapter.unpatch()
