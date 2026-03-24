"""Integration tests for the auto-patch activation lifecycle.

These tests exercise the full ``activate()`` / ``deactivate()`` flow without
relying on any real LLM libraries being installed.  All seven adapter libraries
are mocked via ``sys.modules`` so that ``is_available()`` returns True and
``patch()`` can access the required attributes.

Key design decisions
--------------------
* ``monkeypatch.setitem(sys.modules, ...)`` ensures sys.modules is restored
  after each test (no cross-test pollution).
* ``httpx.Client`` is mocked so no network calls are made.
* ``deactivate()`` is always called in a ``finally`` block to reset registry
  state and ``_current_session_id``.
* The global ``PatchRegistry`` singleton is reset before each test via the
  ``clean_registry`` fixture.
"""
from __future__ import annotations

import sys
import threading
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import agent_debugger_sdk.auto_patch._transport as transport_module
from agent_debugger_sdk.auto_patch import _build_config_from_env, activate, deactivate
from agent_debugger_sdk.auto_patch.registry import PatchConfig, get_registry

# ---------------------------------------------------------------------------
# Module-level fake library builders
# ---------------------------------------------------------------------------


def _make_mock_method() -> MagicMock:
    """Return a MagicMock whose ``_peaky_peek_patched`` attribute is False.

    Several adapters guard against double-patching via:
        getattr(some_method, "_peaky_peek_patched", False)

    Since ``MagicMock`` returns a truthy child mock for any attribute access,
    we must explicitly set the flag to ``False`` on the real method mock so
    that the guard does not prevent patching.
    """
    m = MagicMock()
    m._peaky_peek_patched = False
    return m


def _build_fake_openai() -> types.ModuleType:
    """Return a fake ``openai`` module with the minimal attribute tree."""
    mod = types.ModuleType("openai")

    sync_create = _make_mock_method()
    async_create = _make_mock_method()

    sync_completions = SimpleNamespace(create=sync_create)
    async_completions = SimpleNamespace(create=async_create)
    sync_chat = SimpleNamespace(completions=sync_completions)
    async_chat = SimpleNamespace(completions=async_completions)

    class FakeOpenAI:
        chat = sync_chat

    class FakeAsyncOpenAI:
        chat = async_chat

    mod.OpenAI = FakeOpenAI  # type: ignore[attr-defined]
    mod.AsyncOpenAI = FakeAsyncOpenAI  # type: ignore[attr-defined]
    return mod


def _build_fake_anthropic() -> types.ModuleType:
    """Return a fake ``anthropic`` module with the minimal attribute tree."""
    mod = types.ModuleType("anthropic")

    sync_create = _make_mock_method()
    async_create = _make_mock_method()

    sync_messages = SimpleNamespace(create=sync_create)
    async_messages = SimpleNamespace(create=async_create)

    class FakeAnthropic:
        messages = sync_messages

    class FakeAsyncAnthropic:
        messages = async_messages

    mod.Anthropic = FakeAnthropic  # type: ignore[attr-defined]
    mod.AsyncAnthropic = FakeAsyncAnthropic  # type: ignore[attr-defined]
    return mod


def _build_fake_langchain_core() -> types.ModuleType:
    """Return a fake ``langchain_core`` module with a mutable _handlers list."""
    mod = types.ModuleType("langchain_core")
    callbacks_mod = types.ModuleType("langchain_core.callbacks")
    manager_mod = types.ModuleType("langchain_core.callbacks.manager")
    manager_mod._handlers = []  # type: ignore[attr-defined]
    callbacks_mod.manager = manager_mod  # type: ignore[attr-defined]
    mod.callbacks = callbacks_mod  # type: ignore[attr-defined]
    return mod


def _build_fake_pydantic_ai() -> types.ModuleType:
    """Return a fake ``pydantic_ai`` module with a minimal Agent class."""
    mod = types.ModuleType("pydantic_ai")
    run_method = _make_mock_method()

    class FakeAgent:
        run = run_method

    mod.Agent = FakeAgent  # type: ignore[attr-defined]
    return mod


def _build_fake_crewai() -> types.ModuleType:
    """Return a fake ``crewai`` module with a minimal Crew class."""
    mod = types.ModuleType("crewai")
    kickoff = _make_mock_method()
    kickoff_async = _make_mock_method()

    class FakeCrew:
        pass

    FakeCrew.kickoff = kickoff  # type: ignore[attr-defined]
    FakeCrew.kickoff_async = kickoff_async  # type: ignore[attr-defined]
    mod.Crew = FakeCrew  # type: ignore[attr-defined]
    return mod


def _build_fake_autogen() -> types.ModuleType:
    """Return a fake ``autogen`` module with a minimal ConversableAgent class."""
    mod = types.ModuleType("autogen")
    initiate_chat = _make_mock_method()

    class FakeConversableAgent:
        pass

    FakeConversableAgent.initiate_chat = initiate_chat  # type: ignore[attr-defined]
    mod.ConversableAgent = FakeConversableAgent  # type: ignore[attr-defined]
    return mod


def _build_fake_llama_index_core() -> tuple[types.ModuleType, types.ModuleType]:
    """Return fake ``llama_index`` and ``llama_index.core`` modules.

    LlamaIndex accesses ``llama_index.core.query_engine.BaseQueryEngine``
    so we need a nested module hierarchy.
    """
    query_method = _make_mock_method()
    aquery_method = _make_mock_method()

    class FakeBaseQueryEngine:
        pass

    FakeBaseQueryEngine.query = query_method  # type: ignore[attr-defined]
    FakeBaseQueryEngine.aquery = aquery_method  # type: ignore[attr-defined]

    query_engine_mod = types.ModuleType("llama_index.core.query_engine")
    query_engine_mod.BaseQueryEngine = FakeBaseQueryEngine  # type: ignore[attr-defined]

    core_mod = types.ModuleType("llama_index.core")
    core_mod.query_engine = query_engine_mod  # type: ignore[attr-defined]

    llama_index_mod = types.ModuleType("llama_index")
    llama_index_mod.core = core_mod  # type: ignore[attr-defined]

    return llama_index_mod, core_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_registry():
    """Reset the global registry and transport session state between tests.

    The registry singleton holds adapter instances and tracks which are patched.
    Without resetting it, adapter registrations (and their patched state) leak
    between tests.  We clear both lists directly to guarantee a clean slate.
    """
    registry = get_registry()
    registry._adapters.clear()
    registry._patched.clear()
    # Also reset the transport session ID.
    transport_module._current_session_id = None
    yield
    # Ensure deactivate is called in case a test failed without cleanup.
    try:
        deactivate()
    except Exception:
        pass
    registry._adapters.clear()
    registry._patched.clear()
    transport_module._current_session_id = None


@pytest.fixture()
def mock_httpx():
    """Patch ``httpx.Client`` so SyncTransport never touches the network."""
    with patch("httpx.Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        # Simulate unreachable server on GET /health (triggers warning, not error).
        mock_client.get.side_effect = Exception("no server")
        # POST /api/sessions returns a fake session id.
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "session-integration-test"}
        mock_response.raise_for_status.return_value = None
        mock_client.post.return_value = mock_response
        yield mock_client


# ---------------------------------------------------------------------------
# Helper: inject all 7 fake libraries into sys.modules
# ---------------------------------------------------------------------------


def _inject_all_libs(monkeypatch) -> None:
    """Inject mocked versions of all 7 supported libraries into sys.modules."""
    llama_index_mod, llama_index_core_mod = _build_fake_llama_index_core()
    query_engine_mod = llama_index_core_mod.query_engine

    monkeypatch.setitem(sys.modules, "openai", _build_fake_openai())
    monkeypatch.setitem(sys.modules, "anthropic", _build_fake_anthropic())
    monkeypatch.setitem(sys.modules, "langchain_core", _build_fake_langchain_core())
    monkeypatch.setitem(sys.modules, "pydantic_ai", _build_fake_pydantic_ai())
    monkeypatch.setitem(sys.modules, "crewai", _build_fake_crewai())
    monkeypatch.setitem(sys.modules, "autogen", _build_fake_autogen())
    # LlamaIndex needs the full module hierarchy registered.
    monkeypatch.setitem(sys.modules, "llama_index", llama_index_mod)
    monkeypatch.setitem(sys.modules, "llama_index.core", llama_index_core_mod)
    monkeypatch.setitem(sys.modules, "llama_index.core.query_engine", query_engine_mod)


# ---------------------------------------------------------------------------
# Test 1: activate() with all libs available patches all 7 adapters
# ---------------------------------------------------------------------------


def test_activate_all_patches_all_available_adapters(monkeypatch, mock_httpx):
    """When all 7 libraries are available, activate() patches all 7 adapters."""
    _inject_all_libs(monkeypatch)
    # Remove PEAKY_PEEK_AUTO_PATCH so activate() treats names=None (all).
    monkeypatch.delenv("PEAKY_PEEK_AUTO_PATCH", raising=False)

    config = PatchConfig(server_url="http://localhost:9999")
    try:
        activate(config)
        names = get_registry().patched_names()
        assert "openai" in names, f"Expected 'openai' in {names}"
        assert "anthropic" in names, f"Expected 'anthropic' in {names}"
        assert "langchain" in names, f"Expected 'langchain' in {names}"
        assert "pydanticai" in names, f"Expected 'pydanticai' in {names}"
        assert "crewai" in names, f"Expected 'crewai' in {names}"
        assert "autogen" in names, f"Expected 'autogen' in {names}"
        assert "llamaindex" in names, f"Expected 'llamaindex' in {names}"
        assert len(names) == 7, f"Expected exactly 7 patched adapters, got {names}"
    finally:
        deactivate()


# ---------------------------------------------------------------------------
# Test 2: activate() with env var restricts to named adapters only
# ---------------------------------------------------------------------------


def test_activate_env_var_patches_only_named_adapters(monkeypatch, mock_httpx):
    """PEAKY_PEEK_AUTO_PATCH=openai,anthropic patches only those two."""
    _inject_all_libs(monkeypatch)
    monkeypatch.setenv("PEAKY_PEEK_AUTO_PATCH", "openai,anthropic")

    # When PEAKY_PEEK_AUTO_PATCH is set to a comma-separated list, only those
    # named adapters are patched — all others are skipped.
    config = PatchConfig(server_url="http://localhost:9999")
    try:
        activate(config)
        names = get_registry().patched_names()
        assert "openai" in names, f"Expected 'openai' in {names}"
        assert "anthropic" in names, f"Expected 'anthropic' in {names}"
        # All others must be absent.
        assert "langchain" not in names, f"'langchain' should not be in {names}"
        assert "pydanticai" not in names, f"'pydanticai' should not be in {names}"
        assert "crewai" not in names, f"'crewai' should not be in {names}"
        assert "autogen" not in names, f"'autogen' should not be in {names}"
        assert "llamaindex" not in names, f"'llamaindex' should not be in {names}"
        assert len(names) == 2, f"Expected exactly 2 patched adapters, got {names}"
    finally:
        deactivate()


# ---------------------------------------------------------------------------
# Test 3: Unavailable adapter is skipped silently
# ---------------------------------------------------------------------------


def test_unavailable_adapter_skipped_silently(monkeypatch, mock_httpx):
    """When anthropic is not mocked, it is absent and skipped without error."""
    # Only inject openai — anthropic is NOT mocked.
    monkeypatch.setitem(sys.modules, "openai", _build_fake_openai())
    # Ensure anthropic is absent (not importable).
    monkeypatch.setitem(sys.modules, "anthropic", None)  # type: ignore[arg-type]
    monkeypatch.delenv("PEAKY_PEEK_AUTO_PATCH", raising=False)

    config = PatchConfig(server_url="http://localhost:9999")
    try:
        activate(config)
        names = get_registry().patched_names()
        assert "openai" in names, f"Expected 'openai' in {names}"
        assert "anthropic" not in names, f"'anthropic' should not be in {names} (not available)"
    finally:
        deactivate()


# ---------------------------------------------------------------------------
# Test 4: deactivate() removes all patches and resets session
# ---------------------------------------------------------------------------


def test_deactivate_clears_patched_names_and_resets_session(monkeypatch, mock_httpx):
    """After deactivate(), patched_names() is empty and session ID is None."""
    monkeypatch.setitem(sys.modules, "openai", _build_fake_openai())
    monkeypatch.delenv("PEAKY_PEEK_AUTO_PATCH", raising=False)

    config = PatchConfig(server_url="http://localhost:9999")
    activate(config)
    try:
        assert "openai" in get_registry().patched_names()
        deactivate()
        assert get_registry().patched_names() == [], (
            f"Expected empty patched_names after deactivate, got {get_registry().patched_names()}"
        )
        assert transport_module._current_session_id is None, (
            "Expected _current_session_id to be None after deactivate()"
        )
    finally:
        deactivate()  # safe no-op if already called


# ---------------------------------------------------------------------------
# Test 5: activate() → deactivate() → activate() cycle works cleanly
# ---------------------------------------------------------------------------


def test_activate_deactivate_cycle_is_idempotent(monkeypatch, mock_httpx):
    """Two full activate/deactivate cycles work without leaking state."""
    monkeypatch.setitem(sys.modules, "openai", _build_fake_openai())
    monkeypatch.delenv("PEAKY_PEEK_AUTO_PATCH", raising=False)

    config = PatchConfig(server_url="http://localhost:9999")
    thread_count_before = threading.active_count()

    try:
        # --- First cycle ---
        activate(config)
        assert "openai" in get_registry().patched_names(), "Should be patched after first activate"

        deactivate()
        assert get_registry().patched_names() == [], "Should be empty after first deactivate"
        assert transport_module._current_session_id is None

        # --- Second cycle ---
        # Re-inject (monkeypatch keeps the mock in place).
        activate(config)
        assert "openai" in get_registry().patched_names(), "Should be patched after second activate"

        deactivate()
        assert get_registry().patched_names() == [], "Should be empty after second deactivate"
        assert transport_module._current_session_id is None

        # Thread count should not grow unboundedly (background transport threads are daemons).
        thread_count_after = threading.active_count()
        # Allow some tolerance — daemon threads from the transport may still be alive briefly.
        assert thread_count_after <= thread_count_before + 4, (
            f"Thread count grew from {thread_count_before} to {thread_count_after} — possible leak"
        )
    finally:
        deactivate()  # safe no-op if already called


# ---------------------------------------------------------------------------
# Test 6: PEAKY_PEEK_CAPTURE_CONTENT=true builds config with capture_content=True
# ---------------------------------------------------------------------------


def test_build_config_from_env_capture_content_true(monkeypatch):
    """PEAKY_PEEK_CAPTURE_CONTENT=true is wired into PatchConfig.capture_content."""
    monkeypatch.setenv("PEAKY_PEEK_CAPTURE_CONTENT", "true")
    monkeypatch.setenv("PEAKY_PEEK_SERVER_URL", "http://localhost:7777")
    monkeypatch.delenv("PEAKY_PEEK_AGENT_NAME", raising=False)

    config = _build_config_from_env()

    assert config.capture_content is True, (
        f"Expected capture_content=True, got {config.capture_content}"
    )
    assert config.server_url == "http://localhost:7777"


def test_build_config_from_env_capture_content_false_by_default(monkeypatch):
    """When PEAKY_PEEK_CAPTURE_CONTENT is not set, capture_content defaults to False."""
    monkeypatch.delenv("PEAKY_PEEK_CAPTURE_CONTENT", raising=False)
    monkeypatch.delenv("PEAKY_PEEK_SERVER_URL", raising=False)

    config = _build_config_from_env()

    assert config.capture_content is False, (
        f"Expected capture_content=False (default), got {config.capture_content}"
    )


# ---------------------------------------------------------------------------
# Test 7: PEAKY_PEEK_AGENT_NAME env var is respected
# ---------------------------------------------------------------------------


def test_build_config_from_env_agent_name(monkeypatch):
    """PEAKY_PEEK_AGENT_NAME is read by _build_config_from_env()."""
    monkeypatch.setenv("PEAKY_PEEK_AGENT_NAME", "my-agent")
    monkeypatch.delenv("PEAKY_PEEK_SERVER_URL", raising=False)
    monkeypatch.delenv("PEAKY_PEEK_CAPTURE_CONTENT", raising=False)

    config = _build_config_from_env()

    assert config.agent_name == "my-agent", (
        f"Expected agent_name='my-agent', got {config.agent_name!r}"
    )


def test_build_config_from_env_agent_name_default(monkeypatch):
    """When PEAKY_PEEK_AGENT_NAME is unset, agent_name defaults to 'auto-patched-agent'."""
    monkeypatch.delenv("PEAKY_PEEK_AGENT_NAME", raising=False)

    config = _build_config_from_env()

    assert config.agent_name == "auto-patched-agent", (
        f"Expected default agent_name='auto-patched-agent', got {config.agent_name!r}"
    )
