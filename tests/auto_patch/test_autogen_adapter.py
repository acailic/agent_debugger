"""Tests for AutoGenAdapter.

Neither ``autogen`` nor ``autogen_agentchat`` is installed in this environment,
so all tests mock the modules via ``sys.modules``.

The tests verify:
1. ``is_available()`` returns False when neither package is installed.
2. ``is_available()`` returns True for autogen v0.2 (``autogen``).
3. ``is_available()`` returns True for autogen v0.4 (``autogen_agentchat``).
4. ``patch()`` wraps ``ConversableAgent.initiate_chat`` (v0.2).
5. Calling the wrapped method emits ``agent_start`` and ``agent_end`` events (v0.2).
6. ``patch()`` wraps ``AssistantAgent.run`` (v0.4) when v0.2 unavailable.
7. Calling the v0.4 wrapped method emits ``agent_start`` and ``agent_end`` events.
8. ``unpatch()`` restores original method.
9. Double-patch guard works.
10. Server unreachability does not raise.
"""
from __future__ import annotations

import asyncio
import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import agent_debugger_sdk.auto_patch._transport as transport_module
from agent_debugger_sdk.auto_patch.adapters.autogen_adapter import AutoGenAdapter
from agent_debugger_sdk.auto_patch.registry import PatchConfig

_FLUSH_TIMEOUT = 2.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_fake_autogen_v02() -> types.ModuleType:
    """Return a fake ``autogen`` (v0.2) module with a ConversableAgent class."""
    fake_autogen = types.ModuleType("autogen")

    class FakeConversableAgent:
        def initiate_chat(self, *args: Any, **kwargs: Any) -> str:
            return "v02_chat_result"

    fake_autogen.ConversableAgent = FakeConversableAgent  # type: ignore[attr-defined]
    return fake_autogen


def _build_fake_autogen_v04() -> tuple[types.ModuleType, types.ModuleType]:
    """Return fake ``autogen_agentchat`` and ``autogen_agentchat.agents`` modules."""
    fake_agentchat = types.ModuleType("autogen_agentchat")
    fake_agents = types.ModuleType("autogen_agentchat.agents")

    class FakeAssistantAgent:
        async def run(self, *args: Any, **kwargs: Any) -> str:
            return "v04_run_result"

    fake_agents.AssistantAgent = FakeAssistantAgent  # type: ignore[attr-defined]
    fake_agentchat.agents = fake_agents  # type: ignore[attr-defined]
    return fake_agentchat, fake_agents


def _flush(adapter: AutoGenAdapter) -> None:
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
        mock_response.json.return_value = {"id": "session-autogen-test"}
        mock_response.raise_for_status.return_value = None
        mock_client.post.return_value = mock_response
        yield mock_client


@pytest.fixture()
def fake_autogen_v02(mock_httpx):
    """Inject fake ``autogen`` (v0.2) module into sys.modules."""
    mod = _build_fake_autogen_v02()
    with patch.dict(sys.modules, {"autogen": mod, "autogen_agentchat": None}):
        yield mod


@pytest.fixture()
def fake_autogen_v04(mock_httpx):
    """Inject fake ``autogen_agentchat`` (v0.4) module into sys.modules."""
    agentchat, agents = _build_fake_autogen_v04()
    with patch.dict(
        sys.modules,
        {
            "autogen": None,
            "autogen_agentchat": agentchat,
            "autogen_agentchat.agents": agents,
        },
    ):
        yield agentchat, agents


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


class TestAutoGenAdapterIsAvailable:
    def test_returns_false_when_neither_package_present(self) -> None:
        with patch.dict(sys.modules, {"autogen": None, "autogen_agentchat": None}):
            adapter = AutoGenAdapter()
            assert adapter.is_available() is False

    def test_returns_true_when_autogen_v02_present(self) -> None:
        fake_mod = types.ModuleType("autogen")
        fake_mod.ConversableAgent = object  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"autogen": fake_mod}):
            adapter = AutoGenAdapter()
            assert adapter.is_available() is True

    def test_returns_true_when_autogen_v04_present(self) -> None:
        fake_mod = types.ModuleType("autogen_agentchat")
        with patch.dict(sys.modules, {"autogen": None, "autogen_agentchat": fake_mod}):
            adapter = AutoGenAdapter()
            assert adapter.is_available() is True


# ---------------------------------------------------------------------------
# patch / unpatch  — v0.2
# ---------------------------------------------------------------------------


class TestAutoGenAdapterV02PatchUnpatch:
    def test_patch_replaces_initiate_chat(self, fake_autogen_v02, mock_httpx) -> None:
        """patch() should replace ConversableAgent.initiate_chat with a traced wrapper."""
        original = fake_autogen_v02.ConversableAgent.initiate_chat

        adapter = AutoGenAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        assert fake_autogen_v02.ConversableAgent.initiate_chat is not original
        assert getattr(
            fake_autogen_v02.ConversableAgent.initiate_chat, "_peaky_peek_patched", False
        ) is True

        adapter.unpatch()

    def test_unpatch_restores_initiate_chat(self, fake_autogen_v02, mock_httpx) -> None:
        """unpatch() should restore the original ConversableAgent.initiate_chat."""
        original = fake_autogen_v02.ConversableAgent.initiate_chat

        adapter = AutoGenAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)
        adapter.unpatch()

        assert fake_autogen_v02.ConversableAgent.initiate_chat is original

    def test_unpatch_without_patch_does_not_raise(self) -> None:
        """Calling unpatch() before patch() should be a no-op."""
        adapter = AutoGenAdapter()
        adapter.unpatch()

    def test_double_patch_is_guarded(self, fake_autogen_v02, mock_httpx) -> None:
        """Calling patch() twice should not double-wrap initiate_chat."""
        adapter = AutoGenAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)
        first_method = fake_autogen_v02.ConversableAgent.initiate_chat

        adapter.patch(config)  # second patch — should be a no-op
        assert fake_autogen_v02.ConversableAgent.initiate_chat is first_method

        adapter.unpatch()


# ---------------------------------------------------------------------------
# Event emission — v0.2
# ---------------------------------------------------------------------------


class TestAutoGenAdapterV02EventEmission:
    def test_initiate_chat_emits_agent_start_and_end(
        self, fake_autogen_v02, mock_httpx
    ) -> None:
        """The traced initiate_chat should emit agent_start and agent_end events."""
        adapter = AutoGenAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        agent_instance = fake_autogen_v02.ConversableAgent()
        result = fake_autogen_v02.ConversableAgent.initiate_chat(agent_instance)
        assert result == "v02_chat_result"

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "agent_start" in types_
        assert "agent_end" in types_

        adapter.unpatch()

    def test_initiate_chat_error_emits_error_event_and_reraises(
        self, fake_autogen_v02, mock_httpx
    ) -> None:
        """When initiate_chat raises, an error event should be sent and re-raised."""
        adapter = AutoGenAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        # Inject failure via the saved original — after patching, not before
        saved_original = adapter._original_method
        adapter._original_method = lambda *a, **kw: (_ for _ in ()).throw(ValueError("initiate_chat failed"))
        try:
            agent_instance = fake_autogen_v02.ConversableAgent()
            with pytest.raises(ValueError, match="initiate_chat failed"):
                fake_autogen_v02.ConversableAgent.initiate_chat(agent_instance)

            _flush(adapter)
            sent = _get_trace_events(mock_httpx)
            types_ = [e["event_type"] for e in sent]
            assert "error" in types_
        finally:
            adapter._original_method = saved_original
            adapter.unpatch()

    def test_server_unreachable_does_not_raise(self, fake_autogen_v02, mock_httpx) -> None:
        """Even if the server is unreachable, initiate_chat should complete."""
        mock_httpx.post.side_effect = Exception("connection refused")

        adapter = AutoGenAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        agent_instance = fake_autogen_v02.ConversableAgent()
        result = fake_autogen_v02.ConversableAgent.initiate_chat(agent_instance)
        assert result == "v02_chat_result"

        adapter.unpatch()


# ---------------------------------------------------------------------------
# patch / unpatch  — v0.4
# ---------------------------------------------------------------------------


class TestAutoGenAdapterV04PatchUnpatch:
    def test_patch_replaces_assistant_agent_run(self, fake_autogen_v04, mock_httpx) -> None:
        """patch() should replace AssistantAgent.run with a traced wrapper (v0.4)."""
        _, agents = fake_autogen_v04
        original = agents.AssistantAgent.run

        adapter = AutoGenAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        assert agents.AssistantAgent.run is not original
        assert getattr(agents.AssistantAgent.run, "_peaky_peek_patched", False) is True

        adapter.unpatch()

    def test_unpatch_restores_assistant_agent_run(self, fake_autogen_v04, mock_httpx) -> None:
        """unpatch() should restore the original AssistantAgent.run (v0.4)."""
        _, agents = fake_autogen_v04
        original = agents.AssistantAgent.run

        adapter = AutoGenAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)
        adapter.unpatch()

        assert agents.AssistantAgent.run is original


# ---------------------------------------------------------------------------
# Event emission — v0.4
# ---------------------------------------------------------------------------


class TestAutoGenAdapterV04EventEmission:
    def test_run_emits_agent_start_and_end(self, fake_autogen_v04, mock_httpx) -> None:
        """The traced AssistantAgent.run should emit agent_start and agent_end events."""
        _, agents = fake_autogen_v04

        adapter = AutoGenAdapter()
        config = PatchConfig(server_url="http://localhost:9999")
        adapter.patch(config)

        agent_instance = agents.AssistantAgent()
        result = asyncio.run(agents.AssistantAgent.run(agent_instance))
        assert result == "v04_run_result"

        _flush(adapter)
        sent = _get_trace_events(mock_httpx)
        types_ = [e["event_type"] for e in sent]
        assert "agent_start" in types_
        assert "agent_end" in types_

        adapter.unpatch()
