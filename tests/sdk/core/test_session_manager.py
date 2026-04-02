"""Tests for SessionManager."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_debugger_sdk.checkpoints import CustomCheckpointState
from agent_debugger_sdk.core.context.session_manager import (
    SessionManager,
    _CheckpointRestoreError,
)
from agent_debugger_sdk.core.events import Session, SessionStatus


@pytest.fixture(autouse=True)
def reset_shared_client():
    """Reset shared async client before each test."""
    import agent_debugger_sdk.core.context.session_manager as sm_mod

    original = getattr(sm_mod, "_shared_async_client", None)
    sm_mod._shared_async_client = None
    yield
    sm_mod._shared_async_client = original


class TestSessionManagerCreation:
    """Tests for SessionManager instantiation and basic properties."""

    def test_creates_with_session(self):
        session = Session(id="s1", agent_name="test_agent", framework="custom")
        manager = SessionManager(session)
        assert manager.session is session
        assert manager.session.id == "s1"

    def test_stores_session_start_hook(self):
        hook = AsyncMock()
        session = Session(id="s1", agent_name="test", framework="custom")
        manager = SessionManager(session, session_start_hook=hook)
        assert manager._session_start_hook is hook

    def test_stores_session_update_hook(self):
        hook = AsyncMock()
        session = Session(id="s1", agent_name="test", framework="custom")
        manager = SessionManager(session, session_update_hook=hook)
        assert manager._session_update_hook is hook


class TestSessionManagerStart:
    """Tests for session start hook execution."""

    @pytest.mark.asyncio
    async def test_start_executes_hook_when_configured(self):
        hook = AsyncMock()
        session = Session(id="s1", agent_name="test", framework="custom")
        manager = SessionManager(session, session_start_hook=hook)
        await manager.start()
        hook.assert_called_once_with(session)

    @pytest.mark.asyncio
    async def test_start_no_error_without_hook(self):
        session = Session(id="s1", agent_name="test", framework="custom")
        manager = SessionManager(session)
        await manager.start()


class TestSessionManagerUpdate:
    """Tests for session status updates."""

    @pytest.mark.asyncio
    async def test_update_changes_status(self):
        session = Session(id="s1", agent_name="test", framework="custom", status=SessionStatus.RUNNING)
        manager = SessionManager(session)
        await manager.update(SessionStatus.COMPLETED)
        assert session.status == SessionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_update_sets_ended_at(self):
        session = Session(id="s1", agent_name="test", framework="custom", status=SessionStatus.RUNNING)
        manager = SessionManager(session)
        before = datetime.now(timezone.utc)
        await manager.update(SessionStatus.ERROR)
        after = datetime.now(timezone.utc)
        assert session.ended_at is not None
        assert before <= session.ended_at <= after

    @pytest.mark.asyncio
    async def test_update_executes_hook_when_configured(self):
        hook = AsyncMock()
        session = Session(id="s1", agent_name="test", framework="custom", status=SessionStatus.RUNNING)
        manager = SessionManager(session, session_update_hook=hook)
        await manager.update(SessionStatus.COMPLETED)
        hook.assert_called_once_with(session)

    @pytest.mark.asyncio
    async def test_update_no_error_without_hook(self):
        session = Session(id="s1", agent_name="test", framework="custom", status=SessionStatus.RUNNING)
        manager = SessionManager(session)
        await manager.update(SessionStatus.COMPLETED)


def _make_mock_http_client(checkpoint_data: dict) -> AsyncMock:
    """Helper to create a mock httpx AsyncClient that returns checkpoint data."""
    mock_response = MagicMock()
    mock_response.json.return_value = checkpoint_data
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()
    return mock_client


class TestRestoreFromCheckpoint:
    """Tests for checkpoint restoration flow."""

    @pytest.mark.asyncio
    async def test_restore_creates_session_with_default_id(self):
        checkpoint_data = {
            "id": "cp-123",
            "session_id": "original-session",
            "state": {"framework": "langchain"},
        }

        with patch("agent_debugger_sdk.core.context.session_manager._shared_async_client", None):
            with patch("httpx.AsyncClient", return_value=_make_mock_http_client(checkpoint_data)):
                session, state = await SessionManager.restore_from_checkpoint("cp-123", server_url="http://test:8000")

                assert session.id is not None
                assert len(session.id) == 36
                assert session.framework == "langchain"
                assert state is not None

    @pytest.mark.asyncio
    async def test_restore_creates_session_with_custom_id(self):
        checkpoint_data = {
            "id": "cp-123",
            "session_id": "original-session",
            "state": {"framework": "custom"},
        }

        with patch("agent_debugger_sdk.core.context.session_manager._shared_async_client", None):
            with patch("httpx.AsyncClient", return_value=_make_mock_http_client(checkpoint_data)):
                session, state = await SessionManager.restore_from_checkpoint(
                    "cp-123", session_id="my-custom-id", server_url="http://test:8000"
                )

                assert session.id == "my-custom-id"

    @pytest.mark.asyncio
    async def test_restore_uses_label_for_agent_name(self):
        checkpoint_data = {
            "id": "cp-123",
            "session_id": "original-session",
            "state": {"framework": "test"},
        }

        with patch("agent_debugger_sdk.core.context.session_manager._shared_async_client", None):
            with patch("httpx.AsyncClient", return_value=_make_mock_http_client(checkpoint_data)):
                session, state = await SessionManager.restore_from_checkpoint(
                    "cp-123", label="restored_agent", server_url="http://test:8000"
                )

                assert session.agent_name == "restored_agent"

    @pytest.mark.asyncio
    async def test_restore_includes_checkpoint_metadata_in_config(self):
        checkpoint_data = {
            "id": "cp-123",
            "session_id": "original-session",
            "state": {"framework": "test"},
        }

        with patch("agent_debugger_sdk.core.context.session_manager._shared_async_client", None):
            with patch("httpx.AsyncClient", return_value=_make_mock_http_client(checkpoint_data)):
                session, state = await SessionManager.restore_from_checkpoint("cp-123", server_url="http://test:8000")

                assert session.config["restored_from_checkpoint"] == "cp-123"
                assert session.config["original_session_id"] == "original-session"

    @pytest.mark.asyncio
    async def test_restore_handles_custom_checkpoint_state(self):
        checkpoint_data = {
            "id": "cp-123",
            "session_id": "original-session",
            "state": {"framework": "custom", "custom_key": "custom_value"},
        }

        with patch("agent_debugger_sdk.core.context.session_manager._shared_async_client", None):
            with patch("httpx.AsyncClient", return_value=_make_mock_http_client(checkpoint_data)):
                session, state = await SessionManager.restore_from_checkpoint("cp-123", server_url="http://test:8000")

                assert isinstance(state, CustomCheckpointState)
                assert state.data.get("custom_key") == "custom_value"


class TestRestoreErrorHandling:
    """Tests for error handling during checkpoint restoration."""

    @pytest.mark.asyncio
    async def test_restore_raises_on_checkpoint_not_found(self):
        """Test that HTTPStatusError is wrapped in _CheckpointRestoreError."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.reason_phrase = "Not Found"
        http_error = httpx.HTTPStatusError("404", request=MagicMock(), response=mock_response)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=http_error)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        # Patch httpx where it's imported in the session_manager module
        # Don't use return_value - let __aenter__ return the configured mock_client
        with patch("agent_debugger_sdk.core.context.session_manager.httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = mock_client
            mock_async_client.return_value.__aexit__.return_value = None

            with pytest.raises(_CheckpointRestoreError, match="Failed to restore checkpoint"):
                await SessionManager.restore_from_checkpoint("nonexistent", server_url="http://test:8000")

    @pytest.mark.asyncio
    async def test_restore_raises_on_connection_error(self):
        """Test that RequestError is wrapped in _CheckpointRestoreError."""
        import httpx

        mock_client = AsyncMock()
        request_error = httpx.RequestError("Connection refused", request=MagicMock())
        mock_client.get = AsyncMock(side_effect=request_error)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        # Patch httpx where it's imported in the session_manager module
        # Don't use return_value - let __aenter__ return the configured mock_client
        with patch("agent_debugger_sdk.core.context.session_manager.httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__.return_value = mock_client
            mock_async_client.return_value.__aexit__.return_value = None

            with pytest.raises(_CheckpointRestoreError, match="Network error"):
                await SessionManager.restore_from_checkpoint("cp-123", server_url="http://unreachable:8000")


class TestClientLifecycle:
    """Tests for AsyncClient lifecycle management."""

    @pytest.mark.asyncio
    async def test_async_client_context_manager_used(self):
        """Verify that AsyncClient is used as context manager (no connection leaks)."""
        checkpoint_data = {
            "id": "cp-123",
            "session_id": "original-session",
            "state": {"framework": "test"},
        }

        mock_client = _make_mock_http_client(checkpoint_data)

        with patch("httpx.AsyncClient", return_value=mock_client) as mock_client_class:
            await SessionManager.restore_from_checkpoint("cp-123", server_url="http://test:8000")

            # Verify AsyncClient was instantiated (entering context manager)
            mock_client_class.assert_called_once()

            # Verify __aenter__ was called (context manager protocol)
            mock_client.__aenter__.assert_called_once()

            # Verify __aexit__ was called (proper cleanup)
            mock_client.__aexit__.assert_called_once()
