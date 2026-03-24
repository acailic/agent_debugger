"""Tests for SyncTransport and session management helpers."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import agent_debugger_sdk.auto_patch._transport as transport_module
from agent_debugger_sdk.auto_patch._transport import SyncTransport, get_or_create_session


@pytest.fixture(autouse=True)
def reset_session_id():
    """Reset module-level session state between tests."""
    original = transport_module._current_session_id
    yield
    transport_module._current_session_id = original


class TestSyncTransportSendEvent:
    def test_send_event_puts_item_on_queue(self) -> None:
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            # Suppress reachability check
            mock_client.get.side_effect = Exception("no server")

            t = SyncTransport(server_url="http://localhost:9999")
            event_dict = {"event_type": "llm_request", "id": "test-123"}
            t.send_event(event_dict)

            # The item should appear in the internal queue
            item = t._queue.get(timeout=1.0)
            assert item == event_dict

    def test_send_event_returns_immediately(self) -> None:
        """send_event must be non-blocking (fire and forget)."""
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.get.side_effect = Exception("no server")

            t = SyncTransport(server_url="http://localhost:9999")

            import time

            start = time.monotonic()
            t.send_event({"event_type": "test"})
            elapsed = time.monotonic() - start

            # Should complete in well under 100ms
            assert elapsed < 0.1


class TestSyncTransportSendSession:
    def test_send_session_returns_session_id(self) -> None:
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.get.side_effect = Exception("no server")

            # Mock the POST for session creation
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "session-abc-123"}
            mock_response.raise_for_status.return_value = None
            mock_client.post.return_value = mock_response

            t = SyncTransport(server_url="http://localhost:9999")
            session_dict = {"agent_name": "test-agent", "framework": "openai"}
            result = t.send_session(session_dict)

            assert result == "session-abc-123"

    def test_send_session_falls_back_gracefully_on_error(self) -> None:
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.get.side_effect = Exception("no server")
            mock_client.post.side_effect = Exception("connection refused")

            t = SyncTransport(server_url="http://localhost:9999")
            result = t.send_session({"agent_name": "test-agent", "framework": "openai"})

            # Falls back — returns a non-empty string (a generated UUID)
            assert isinstance(result, str)
            assert len(result) > 0


class TestGetOrCreateSession:
    def test_get_or_create_session_creates_session_when_none(self) -> None:
        transport_module._current_session_id = None

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.get.side_effect = Exception("no server")
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "new-session-999"}
            mock_response.raise_for_status.return_value = None
            mock_client.post.return_value = mock_response

            t = SyncTransport(server_url="http://localhost:9999")
            session_id = get_or_create_session(t, agent_name="my-agent", framework="openai")

        assert session_id == "new-session-999"
        assert transport_module._current_session_id == "new-session-999"

    def test_get_or_create_session_reuses_existing_session_id(self) -> None:
        transport_module._current_session_id = "existing-session-42"

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.get.side_effect = Exception("no server")

            t = SyncTransport(server_url="http://localhost:9999")
            session_id = get_or_create_session(t, agent_name="my-agent", framework="openai")

        # post should NOT have been called for session creation
        mock_client.post.assert_not_called()
        assert session_id == "existing-session-42"
        assert transport_module._current_session_id == "existing-session-42"

    def test_get_or_create_session_second_call_same_id(self) -> None:
        transport_module._current_session_id = None

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.get.side_effect = Exception("no server")
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "session-first"}
            mock_response.raise_for_status.return_value = None
            mock_client.post.return_value = mock_response

            t = SyncTransport(server_url="http://localhost:9999")
            id1 = get_or_create_session(t, agent_name="agent", framework="openai")
            id2 = get_or_create_session(t, agent_name="agent", framework="openai")

        assert id1 == id2 == "session-first"
        # post should only be called once for session creation
        assert mock_client.post.call_count == 1
