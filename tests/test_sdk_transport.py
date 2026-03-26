"""Tests for SDK HTTP transport."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_debugger_sdk.core.events import EventType, Session, TraceEvent
from agent_debugger_sdk.transport import HttpTransport


def _make_event() -> TraceEvent:
    return TraceEvent(
        session_id="s1",
        parent_id=None,
        event_type=EventType.TOOL_CALL,
        name="test",
        data={},
        metadata={},
        importance=0.5,
        upstream_event_ids=[],
    )


@pytest.mark.asyncio
async def test_transport_sends_event():
    transport = HttpTransport(endpoint="http://localhost:8000", api_key="ad_live_test")
    with patch.object(transport, "_client") as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 202
        mock_client.post = AsyncMock(return_value=mock_response)
        await transport.send_event(_make_event())
        mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_transport_includes_auth_header():
    transport = HttpTransport(endpoint="http://localhost:8000", api_key="ad_live_test")
    assert transport._headers["Authorization"] == "Bearer ad_live_test"


@pytest.mark.asyncio
async def test_transport_no_auth_header_without_api_key():
    transport = HttpTransport(endpoint="http://localhost:8000", api_key=None)
    assert "Authorization" not in transport._headers
    assert transport._headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_transport_graceful_on_failure():
    transport = HttpTransport(endpoint="http://localhost:8000", api_key="ad_live_test")
    with patch.object(transport, "_client") as mock_client:
        mock_client.post = AsyncMock(side_effect=ConnectionError("down"))
        # Should not raise
        await transport.send_event(_make_event())


@pytest.mark.asyncio
async def test_transport_send_session_start():
    transport = HttpTransport(endpoint="http://localhost:8000", api_key="ad_live_test")
    with patch.object(transport, "_client") as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 201
        mock_client.post = AsyncMock(return_value=mock_response)

        session = Session(id="s1", agent_name="test_agent", framework="pydantic_ai")
        await transport.send_session_start(session)
        mock_client.post.assert_called_once_with("/api/sessions", json=session.to_dict())


@pytest.mark.asyncio
async def test_transport_send_session_update():
    transport = HttpTransport(endpoint="http://localhost:8000", api_key="ad_live_test")
    with patch.object(transport, "_client") as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_client.put = AsyncMock(return_value=mock_response)

        session = Session(id="s1", agent_name="test_agent", framework="pydantic_ai")
        await transport.send_session_update(session)
        mock_client.put.assert_called_once_with("/api/sessions/s1", json=session.to_dict())


@pytest.mark.asyncio
async def test_transport_send_session_update_logs_http_status_on_failure(caplog):
    transport = HttpTransport(endpoint="http://localhost:8000", api_key="ad_live_test")
    # Patch the put method directly on the client
    with patch.object(transport._client, "put") as mock_put:
        mock_response = MagicMock(status_code=404)
        mock_put.return_value = mock_response

        session = Session(id="s1", agent_name="test_agent", framework="pydantic_ai")
        with caplog.at_level(logging.WARNING, logger="agent_debugger"):
            await transport.send_session_update(session)

    # Ensure we got the warning log at the "agent_debugger" logger
    warning_records = [r for r in caplog.records if r.name == "agent_debugger" and r.levelno == logging.WARNING]
    # Updated to match new log format which uses "status=404" instead of "status_code=404"
    assert any("status=404" in r.message for r in warning_records), (
        f"No warning log found in agent_debugger: {caplog.records}"
    )


@pytest.mark.asyncio
async def test_transport_send_session_start_graceful_on_failure():
    transport = HttpTransport(endpoint="http://localhost:8000", api_key="ad_live_test")
    with patch.object(transport, "_client") as mock_client:
        mock_client.post = AsyncMock(side_effect=ConnectionError("down"))
        session = Session(id="s1", agent_name="test_agent", framework="pydantic_ai")

        await transport.send_session_start(session)


@pytest.mark.asyncio
async def test_transport_send_session_update_graceful_on_failure():
    transport = HttpTransport(endpoint="http://localhost:8000", api_key="ad_live_test")
    with patch.object(transport, "_client") as mock_client:
        mock_client.put = AsyncMock(side_effect=ConnectionError("down"))
        session = Session(id="s1", agent_name="test_agent", framework="pydantic_ai")

        await transport.send_session_update(session)


@pytest.mark.asyncio
async def test_transport_close():
    transport = HttpTransport(endpoint="http://localhost:8000", api_key="ad_live_test")
    with patch.object(transport, "_client") as mock_client:
        mock_client.aclose = AsyncMock()
        await transport.close()
        mock_client.aclose.assert_called_once()
