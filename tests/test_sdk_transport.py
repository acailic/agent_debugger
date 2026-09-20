"""Tests for SDK HTTP transport."""

import logging
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agent_debugger_sdk.core.events import EventType, Session, TraceEvent
from agent_debugger_sdk.transport import HttpTransport, PermanentError, RetryConfig, TransientError


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
    # Updated to match new enhanced error message format
    assert any("API endpoint not found" in r.message for r in warning_records), (
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


@pytest.mark.parametrize("status_code", [408, 429, 503])
async def test_transport_recovers_from_temporary_http_failure(status_code):
    failure = MagicMock()
    async with HttpTransport("http://localhost:8000", on_delivery_failure=failure) as transport:
        with (
            patch.object(transport._client, "post", new_callable=AsyncMock) as post,
            patch("agent_debugger_sdk.transport.asyncio.sleep", new_callable=AsyncMock) as sleep,
        ):
            post.side_effect = [httpx.Response(status_code), httpx.Response(202)]
            await transport.send_event(_make_event())

        assert post.call_count == 2
        assert post.call_args_list[0] == post.call_args_list[1]
        sleep.assert_awaited_once_with(0.5)
        failure.assert_not_called()


@pytest.mark.parametrize("status_code", [301, 302, 307, 308])
async def test_transport_reports_redirect_as_delivery_failure(status_code):
    failure = MagicMock()
    async with HttpTransport("http://localhost:8000", on_delivery_failure=failure) as transport:
        with patch.object(transport._client, "post", new_callable=AsyncMock) as post:
            post.return_value = httpx.Response(status_code, headers={"Location": "https://other.example"})
            await transport.send_event(_make_event())

        post.assert_awaited_once()
        failure.assert_called_once()
        error = failure.call_args.args[0]
        assert isinstance(error, PermanentError)
        assert error.status_code == status_code
        assert "server URL" in str(error)


async def test_transport_retries_remote_disconnect():
    failure = MagicMock()
    async with HttpTransport("http://localhost:8000", on_delivery_failure=failure) as transport:
        with (
            patch.object(transport._client, "post", new_callable=AsyncMock) as post,
            patch("agent_debugger_sdk.transport.asyncio.sleep", new_callable=AsyncMock),
        ):
            post.side_effect = [httpx.RemoteProtocolError("Server disconnected"), httpx.Response(202)]
            await transport.send_event(_make_event())

        assert post.call_count == 2
        failure.assert_not_called()


@pytest.mark.parametrize("status_code", [429, 503])
@pytest.mark.parametrize("header,expected_delay", [("3", 3), ("invalid", 0.5), ("NaN", 0.5), ("-1", 0.5)])
async def test_transport_observes_retry_after(status_code, header, expected_delay):
    async with HttpTransport("http://localhost:8000") as transport:
        with (
            patch.object(transport._client, "post", new_callable=AsyncMock) as post,
            patch("agent_debugger_sdk.transport.asyncio.sleep", new_callable=AsyncMock) as sleep,
        ):
            post.side_effect = [httpx.Response(status_code, headers={"Retry-After": header}), httpx.Response(202)]
            await transport.send_event(_make_event())
        assert post.call_count == 2
        sleep.assert_awaited_once_with(expected_delay)


async def test_transport_observes_retry_after_http_date():
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    async with HttpTransport("http://localhost:8000") as transport:
        with (
            patch.object(transport._client, "post", new_callable=AsyncMock) as post,
            patch("agent_debugger_sdk.transport.asyncio.sleep", new_callable=AsyncMock) as sleep,
            patch("agent_debugger_sdk.transport.datetime") as clock,
        ):
            clock.now.return_value = now
            post.side_effect = [
                httpx.Response(429, headers={"Retry-After": format_datetime(now + timedelta(seconds=10))}),
                httpx.Response(202),
            ]
            await transport.send_event(_make_event())
        sleep.assert_awaited_once_with(10)


async def test_transport_reports_long_retry_after_without_waiting_or_retrying_early():
    failure = MagicMock()
    async with HttpTransport("http://localhost:8000", on_delivery_failure=failure) as transport:
        with (
            patch.object(transport._client, "post", new_callable=AsyncMock) as post,
            patch("agent_debugger_sdk.transport.asyncio.sleep", new_callable=AsyncMock) as sleep,
        ):
            post.return_value = httpx.Response(429, headers={"Retry-After": "3600"})
            await transport.send_event(_make_event())
        post.assert_awaited_once()
        sleep.assert_not_awaited()
        failure.assert_called_once()
        assert isinstance(failure.call_args.args[0], TransientError)
        assert failure.call_args.args[0].retry_after_seconds == 3600


async def test_transport_bounds_backoff_and_reports_exhausted_retries_once():
    failure = MagicMock()
    retry = RetryConfig(max_retries=3, initial_backoff_seconds=2, max_backoff_seconds=3)
    async with HttpTransport("http://localhost:8000", retry_config=retry, on_delivery_failure=failure) as transport:
        with (
            patch.object(transport._client, "post", new_callable=AsyncMock) as post,
            patch("agent_debugger_sdk.transport.asyncio.sleep", new_callable=AsyncMock) as sleep,
        ):
            post.return_value = httpx.Response(429)
            await transport.send_event(_make_event())
        assert post.call_count == 4
        assert [call.args[0] for call in sleep.await_args_list] == [2, 3, 3]
        failure.assert_called_once()
        assert failure.call_args.args[0].status_code == 429


@pytest.mark.parametrize("field", ["initial_backoff_seconds", "backoff_multiplier", "max_backoff_seconds"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_retry_configuration_rejects_unbounded_delays(field, value):
    with pytest.raises(ValueError):
        RetryConfig(**{field: value})


@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_retry_configuration_requires_nonnegative_integer_attempts(value):
    with pytest.raises(ValueError):
        RetryConfig(max_retries=value)
