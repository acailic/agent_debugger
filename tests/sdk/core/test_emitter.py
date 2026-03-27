"""Comprehensive unit tests for EventEmitter and transport integration."""

from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_debugger_sdk.core.emitter import EventEmitter, EventBufferLike
from agent_debugger_sdk.core.events import (
    Checkpoint,
    EventType,
    LLMRequestEvent,
    LLMResponseEvent,
    Session,
    TraceEvent,
)
from agent_debugger_sdk.transport import (
    BACKOFF_MULTIPLIER,
    INITIAL_BACKOFF_SECONDS,
    MAX_RETRIES,
    DeliveryFailureCallback,
    HttpTransport,
    PermanentError,
    TransientError,
    TransportError,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def session_id() -> str:
    return "test-session-123"


@pytest.fixture
def session() -> Session:
    return Session(
        id="test-session-123",
        agent_name="test_agent",
        framework="test_framework",
    )


@pytest.fixture
def event_store() -> list[TraceEvent | Checkpoint]:
    return []


@pytest.fixture
def event_lock() -> asyncio.Lock:
    return asyncio.Lock()


@pytest.fixture
def event_sequence() -> ContextVar[int]:
    return ContextVar("event_sequence", default=0)


@pytest.fixture
def mock_event_buffer() -> MagicMock:
    """Mock event buffer that implements EventBufferLike protocol."""
    buffer = MagicMock(spec=EventBufferLike)
    buffer.publish = AsyncMock()
    return buffer


@pytest.fixture
def mock_persister() -> AsyncMock:
    """Mock event persister callable."""
    return AsyncMock()


@pytest.fixture
def mock_session_update_hook() -> AsyncMock:
    """Mock session update hook callable."""
    return AsyncMock()


@pytest.fixture
def emitter(
    session_id: str,
    session: Session,
    event_store: list[TraceEvent | Checkpoint],
    event_lock: asyncio.Lock,
    event_sequence: ContextVar[int],
    mock_event_buffer: MagicMock,
    mock_persister: AsyncMock,
    mock_session_update_hook: AsyncMock,
) -> EventEmitter:
    """Create a fully configured EventEmitter for testing."""
    return EventEmitter(
        session_id=session_id,
        session=session,
        event_store=event_store,
        event_lock=event_lock,
        event_sequence=event_sequence,
        event_buffer=mock_event_buffer,
        event_persister=mock_persister,
        session_update_hook=mock_session_update_hook,
    )


@pytest.fixture
def minimal_emitter(
    session_id: str,
    session: Session,
    event_store: list[TraceEvent | Checkpoint],
    event_lock: asyncio.Lock,
    event_sequence: ContextVar[int],
) -> EventEmitter:
    """Create a minimal EventEmitter without optional hooks."""
    return EventEmitter(
        session_id=session_id,
        session=session,
        event_store=event_store,
        event_lock=event_lock,
        event_sequence=event_sequence,
        event_buffer=None,
        event_persister=None,
        session_update_hook=None,
    )


def _make_event(
    event_type: EventType = EventType.TOOL_CALL,
    name: str = "test_event",
    session_id: str = "test-session-123",
    **kwargs,
) -> TraceEvent:
    """Helper to create a TraceEvent for testing."""
    return TraceEvent(
        session_id=session_id,
        event_type=event_type,
        name=name,
        data=kwargs.get("data", {}),
        metadata=kwargs.get("metadata", {}),
        **{k: v for k, v in kwargs.items() if k not in ("data", "metadata")},
    )


def _make_llm_response_event(
    session_id: str = "test-session-123",
    input_tokens: int = 100,
    output_tokens: int = 50,
    cost_usd: float = 0.01,
) -> LLMResponseEvent:
    """Helper to create an LLMResponseEvent for testing."""
    return LLMResponseEvent(
        session_id=session_id,
        event_type=EventType.LLM_RESPONSE,
        name="llm_response",
        model="gpt-4",
        content="Test response",
        usage={"input_tokens": input_tokens, "output_tokens": output_tokens},
        cost_usd=cost_usd,
    )


# =============================================================================
# EventEmitter Creation and Configuration Tests
# =============================================================================


class TestEventEmitterCreation:
    """Tests for EventEmitter instantiation and configuration."""

    def test_emitter_creation_with_all_dependencies(
        self,
        session_id: str,
        session: Session,
        event_store: list,
        event_lock: asyncio.Lock,
        event_sequence: ContextVar[int],
        mock_event_buffer: MagicMock,
        mock_persister: AsyncMock,
        mock_session_update_hook: AsyncMock,
    ):
        """Test EventEmitter creation with all dependencies."""
        emitter = EventEmitter(
            session_id=session_id,
            session=session,
            event_store=event_store,
            event_lock=event_lock,
            event_sequence=event_sequence,
            event_buffer=mock_event_buffer,
            event_persister=mock_persister,
            session_update_hook=mock_session_update_hook,
        )

        assert emitter._session_id == session_id
        assert emitter._session is session
        assert emitter._event_store is event_store
        assert emitter._event_lock is event_lock
        assert emitter._event_sequence is event_sequence
        assert emitter._event_buffer is mock_event_buffer
        assert emitter._event_persister is mock_persister
        assert emitter._session_update_hook is mock_session_update_hook

    def test_emitter_creation_with_minimal_dependencies(
        self,
        session_id: str,
        session: Session,
        event_store: list,
        event_lock: asyncio.Lock,
        event_sequence: ContextVar[int],
    ):
        """Test EventEmitter creation with only required dependencies."""
        emitter = EventEmitter(
            session_id=session_id,
            session=session,
            event_store=event_store,
            event_lock=event_lock,
            event_sequence=event_sequence,
            event_buffer=None,
            event_persister=None,
            session_update_hook=None,
        )

        assert emitter._session_id == session_id
        assert emitter._event_buffer is None
        assert emitter._event_persister is None
        assert emitter._session_update_hook is None

    def test_set_event_buffer(self, minimal_emitter: EventEmitter, mock_event_buffer: MagicMock):
        """Test updating the event buffer after creation."""
        assert minimal_emitter._event_buffer is None

        minimal_emitter.set_event_buffer(mock_event_buffer)
        assert minimal_emitter._event_buffer is mock_event_buffer

        minimal_emitter.set_event_buffer(None)
        assert minimal_emitter._event_buffer is None

    def test_set_event_persister(self, minimal_emitter: EventEmitter, mock_persister: AsyncMock):
        """Test updating the event persister after creation."""
        assert minimal_emitter._event_persister is None

        minimal_emitter.set_event_persister(mock_persister)
        assert minimal_emitter._event_persister is mock_persister

        minimal_emitter.set_event_persister(None)
        assert minimal_emitter._event_persister is None

    def test_set_session_update_hook(
        self, minimal_emitter: EventEmitter, mock_session_update_hook: AsyncMock
    ):
        """Test updating the session update hook after creation."""
        assert minimal_emitter._session_update_hook is None

        minimal_emitter.set_session_update_hook(mock_session_update_hook)
        assert minimal_emitter._session_update_hook is mock_session_update_hook

        minimal_emitter.set_session_update_hook(None)
        assert minimal_emitter._session_update_hook is None


# =============================================================================
# Event Emission Tests
# =============================================================================


class TestEventEmission:
    """Tests for basic event emission behavior."""

    @pytest.mark.asyncio
    async def test_emit_stores_event(
        self,
        emitter: EventEmitter,
        event_store: list,
        event_sequence: ContextVar[int],
    ):
        """Test that emit stores the event in the event store."""
        event = _make_event()

        await emitter.emit(event)

        assert len(event_store) == 1
        assert event_store[0] is event

    @pytest.mark.asyncio
    async def test_emit_increments_sequence(
        self,
        emitter: EventEmitter,
        event_sequence: ContextVar[int],
    ):
        """Test that emit increments the event sequence."""
        assert event_sequence.get() == 0

        await emitter.emit(_make_event())
        assert event_sequence.get() == 1

        await emitter.emit(_make_event())
        assert event_sequence.get() == 2

    @pytest.mark.asyncio
    async def test_emit_sets_sequence_in_metadata(
        self,
        emitter: EventEmitter,
        event_store: list,
    ):
        """Test that emit sets the sequence number in event metadata."""
        event1 = _make_event()
        event2 = _make_event()

        await emitter.emit(event1)
        await emitter.emit(event2)

        assert event_store[0].metadata["sequence"] == 1
        assert event_store[1].metadata["sequence"] == 2

    @pytest.mark.asyncio
    async def test_emit_sets_importance_score(
        self,
        emitter: EventEmitter,
        event_store: list,
    ):
        """Test that emit sets the importance score on the event."""
        event = _make_event()

        await emitter.emit(event)

        assert event_store[0].importance >= 0.0
        assert event_store[0].importance <= 1.0

    @pytest.mark.asyncio
    async def test_emit_calls_persister(
        self,
        emitter: EventEmitter,
        mock_persister: AsyncMock,
    ):
        """Test that emit calls the event persister."""
        event = _make_event()

        await emitter.emit(event)

        mock_persister.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_emit_calls_session_update_hook(
        self,
        emitter: EventEmitter,
        session: Session,
        mock_session_update_hook: AsyncMock,
    ):
        """Test that emit calls the session update hook."""
        event = _make_event()

        await emitter.emit(event)

        mock_session_update_hook.assert_awaited_once_with(session)

    @pytest.mark.asyncio
    async def test_emit_publishes_to_buffer(
        self,
        emitter: EventEmitter,
        session_id: str,
        mock_event_buffer: MagicMock,
    ):
        """Test that emit publishes the event to the buffer."""
        event = _make_event()

        await emitter.emit(event)

        mock_event_buffer.publish.assert_awaited_once_with(session_id, event)

    @pytest.mark.asyncio
    async def test_emit_without_optional_hooks(
        self,
        minimal_emitter: EventEmitter,
        event_store: list,
    ):
        """Test that emit works without optional hooks (buffer, persister, update hook)."""
        event = _make_event()

        # Should not raise
        await minimal_emitter.emit(event)

        assert len(event_store) == 1

    @pytest.mark.asyncio
    async def test_emit_skipped_when_disabled(
        self,
        emitter: EventEmitter,
        event_store: list,
        mock_persister: AsyncMock,
        mock_event_buffer: MagicMock,
    ):
        """Test that emit is skipped when SDK is disabled."""
        mock_config = SimpleNamespace(enabled=False)

        with patch("agent_debugger_sdk.config.get_config", return_value=mock_config):
            event = _make_event()
            await emitter.emit(event)

        assert len(event_store) == 0
        mock_persister.assert_not_awaited()
        mock_event_buffer.publish.assert_not_awaited()


# =============================================================================
# LLM Response Event Tests
# =============================================================================


class TestLLMResponseEventEmission:
    """Tests for LLM response event emission and session stats updates."""

    @pytest.mark.asyncio
    async def test_emit_llm_response_updates_token_counts(
        self,
        emitter: EventEmitter,
        session: Session,
        event_store: list,
    ):
        """Test that LLM response events update session token counts."""
        event = _make_llm_response_event(input_tokens=100, output_tokens=50)

        await emitter.emit(event)

        assert session.total_tokens == 150

    @pytest.mark.asyncio
    async def test_emit_llm_response_updates_cost(
        self,
        emitter: EventEmitter,
        session: Session,
        event_store: list,
    ):
        """Test that LLM response events update session cost."""
        event = _make_llm_response_event(cost_usd=0.05)

        await emitter.emit(event)

        assert session.total_cost_usd == 0.05

    @pytest.mark.asyncio
    async def test_emit_llm_response_increments_llm_calls(
        self,
        emitter: EventEmitter,
        session: Session,
        event_store: list,
    ):
        """Test that LLM response events increment the LLM call counter."""
        assert session.llm_calls == 0

        await emitter.emit(_make_llm_response_event())
        assert session.llm_calls == 1

        await emitter.emit(_make_llm_response_event())
        assert session.llm_calls == 2

    @pytest.mark.asyncio
    async def test_emit_non_llm_response_does_not_update_stats(
        self,
        emitter: EventEmitter,
        session: Session,
        event_store: list,
    ):
        """Test that non-LLM response events don't update session stats."""
        initial_tokens = session.total_tokens
        initial_cost = session.total_cost_usd
        initial_calls = session.llm_calls

        await emitter.emit(_make_event(event_type=EventType.TOOL_CALL))
        await emitter.emit(_make_event(event_type=EventType.DECISION))

        assert session.total_tokens == initial_tokens
        assert session.total_cost_usd == initial_cost
        assert session.llm_calls == initial_calls

    @pytest.mark.asyncio
    async def test_emit_llm_response_with_missing_token_fields(
        self,
        emitter: EventEmitter,
        session: Session,
        event_store: list,
    ):
        """Test LLM response with missing token fields handles gracefully."""
        event = LLMResponseEvent(
            session_id="test-session-123",
            name="llm_response",
            usage={},  # Missing token fields
            cost_usd=0.01,
        )

        await emitter.emit(event)

        assert session.total_tokens == 0  # Missing tokens treated as 0


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in event emission."""

    @pytest.mark.asyncio
    async def test_emit_handles_persister_failure(
        self,
        emitter: EventEmitter,
        event_store: list,
        mock_persister: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """Test that persister failures are caught and logged."""
        mock_persister.side_effect = RuntimeError("Persister failed")
        event = _make_event()

        with caplog.at_level(logging.WARNING, logger="agent_debugger"):
            await emitter.emit(event)

        assert len(event_store) == 1  # Event still stored
        assert any("Failed to persist event" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_emit_handles_session_update_failure(
        self,
        emitter: EventEmitter,
        event_store: list,
        mock_session_update_hook: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """Test that session update hook failures are caught and logged."""
        mock_session_update_hook.side_effect = RuntimeError("Update failed")
        event = _make_event()

        with caplog.at_level(logging.WARNING, logger="agent_debugger"):
            await emitter.emit(event)

        assert len(event_store) == 1
        assert any("Failed to update session" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_emit_handles_buffer_publish_failure(
        self,
        emitter: EventEmitter,
        event_store: list,
        mock_event_buffer: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """Test that buffer publish failures are caught and logged."""
        mock_event_buffer.publish.side_effect = RuntimeError("Buffer full")
        event = _make_event()

        with caplog.at_level(logging.WARNING, logger="agent_debugger"):
            await emitter.emit(event)

        assert len(event_store) == 1
        assert any("Failed to publish event" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_emit_continues_after_persister_failure(
        self,
        emitter: EventEmitter,
        mock_persister: AsyncMock,
        mock_session_update_hook: AsyncMock,
        mock_event_buffer: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """Test that emission continues through the pipeline even if persister fails."""
        mock_persister.side_effect = RuntimeError("Persist failed")

        with caplog.at_level(logging.WARNING, logger="agent_debugger"):
            event = _make_event()
            await emitter.emit(event)

        # Other hooks should still be called
        mock_session_update_hook.assert_awaited_once()
        mock_event_buffer.publish.assert_awaited_once()


# =============================================================================
# Concurrent Emission Tests
# =============================================================================


class TestConcurrentEmission:
    """Tests for concurrent event emission behavior."""

    @pytest.mark.asyncio
    async def test_concurrent_emissions_are_thread_safe(
        self,
        emitter: EventEmitter,
        event_store: list,
    ):
        """Test that concurrent emissions don't cause race conditions."""
        num_events = 100

        async def emit_event(i: int):
            event = _make_event(name=f"event_{i}")
            await emitter.emit(event)

        await asyncio.gather(*[emit_event(i) for i in range(num_events)])

        assert len(event_store) == num_events

    @pytest.mark.asyncio
    async def test_sequence_numbers_are_unique_under_concurrency(
        self,
        emitter: EventEmitter,
        event_store: list,
    ):
        """Test that sequence numbers are unique even with concurrent emissions."""
        num_events = 50

        async def emit_event(i: int):
            event = _make_event(name=f"event_{i}")
            await emitter.emit(event)

        await asyncio.gather(*[emit_event(i) for i in range(num_events)])

        sequences = [e.metadata["sequence"] for e in event_store]
        assert len(set(sequences)) == num_events  # All unique


# =============================================================================
# Transport Error Types Tests
# =============================================================================


class TestTransportErrorTypes:
    """Tests for transport error type hierarchy."""

    def test_transport_error_base(self):
        """Test TransportError base exception."""
        error = TransportError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.status_code is None

    def test_transport_error_with_status_code(self):
        """Test TransportError with status code."""
        error = TransportError("Not found", status_code=404)
        assert error.status_code == 404

    def test_transient_error_inherits_from_transport_error(self):
        """Test TransientError inheritance."""
        error = TransientError("Timeout", status_code=None)
        assert isinstance(error, TransportError)

    def test_permanent_error_inherits_from_transport_error(self):
        """Test PermanentError inheritance."""
        error = PermanentError("Auth failed", status_code=401)
        assert isinstance(error, TransportError)
        assert error.status_code == 401


# =============================================================================
# Transport Configuration Tests
# =============================================================================


class TestHttpTransportConfiguration:
    """Tests for HttpTransport configuration."""

    def test_transport_creation_with_endpoint(self):
        """Test transport creation with endpoint."""
        transport = HttpTransport(endpoint="http://localhost:8000")
        assert transport._endpoint == "http://localhost:8000"

    def test_transport_strips_trailing_slash(self):
        """Test that trailing slash is stripped from endpoint."""
        transport = HttpTransport(endpoint="http://localhost:8000/")
        assert transport._endpoint == "http://localhost:8000"

    def test_transport_includes_auth_header_with_api_key(self):
        """Test that Authorization header is set when API key is provided."""
        transport = HttpTransport(endpoint="http://localhost:8000", api_key="test_key")
        assert transport._headers["Authorization"] == "Bearer test_key"

    def test_transport_no_auth_header_without_api_key(self):
        """Test that Authorization header is not set without API key."""
        transport = HttpTransport(endpoint="http://localhost:8000", api_key=None)
        assert "Authorization" not in transport._headers

    def test_transport_sets_content_type_header(self):
        """Test that Content-Type header is always set."""
        transport = HttpTransport(endpoint="http://localhost:8000")
        assert transport._headers["Content-Type"] == "application/json"

    def test_transport_stores_delivery_failure_callback(self):
        """Test that delivery failure callback is stored."""
        callback = MagicMock(spec=DeliveryFailureCallback)
        transport = HttpTransport(endpoint="http://localhost:8000", on_delivery_failure=callback)
        assert transport._on_delivery_failure is callback

    def test_transport_default_timeout(self):
        """Test that default timeout is configured."""
        transport = HttpTransport(endpoint="http://localhost:8000")
        assert transport._client.timeout.read == 5.0


# =============================================================================
# Transport Send Event Tests
# =============================================================================


class TestHttpTransportSendEvent:
    """Tests for HttpTransport send_event method."""

    @pytest.mark.asyncio
    async def test_send_event_success(self):
        """Test successful event sending."""
        transport = HttpTransport(endpoint="http://localhost:8000")
        event = _make_event()

        with patch.object(transport._client, "post") as mock_post:
            mock_response = MagicMock(status_code=200)
            mock_post.return_value = mock_response

            await transport.send_event(event)

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[0][0] == "/api/traces"

    @pytest.mark.asyncio
    async def test_send_event_retries_on_5xx(self):
        """Test that 5xx errors are retried."""
        transport = HttpTransport(endpoint="http://localhost:8000")
        event = _make_event()

        with patch.object(transport._client, "post") as mock_post:
            # First two calls return 500, third returns 200
            mock_post.side_effect = [
                MagicMock(status_code=500),
                MagicMock(status_code=500),
                MagicMock(status_code=200),
            ]

            await transport.send_event(event)

            assert mock_post.call_count == 3

    @pytest.mark.asyncio
    async def test_send_event_no_retry_on_4xx(self):
        """Test that 4xx errors are not retried."""
        transport = HttpTransport(endpoint="http://localhost:8000")
        event = _make_event()
        callback = MagicMock(spec=DeliveryFailureCallback)
        transport._on_delivery_failure = callback

        with patch.object(transport._client, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=401)

            await transport.send_event(event)

            assert mock_post.call_count == 1
            callback.assert_called_once()
            assert isinstance(callback.call_args[0][0], PermanentError)

    @pytest.mark.asyncio
    async def test_send_event_retries_on_timeout(self):
        """Test that timeouts are retried."""
        transport = HttpTransport(endpoint="http://localhost:8000")
        event = _make_event()

        with patch.object(transport._client, "post") as mock_post:
            import httpx

            # First call times out, second succeeds
            mock_post.side_effect = [
                httpx.TimeoutException("Timeout"),
                MagicMock(status_code=200),
            ]

            await transport.send_event(event)

            assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_send_event_retries_on_network_error(self):
        """Test that network errors are retried."""
        transport = HttpTransport(endpoint="http://localhost:8000")
        event = _make_event()

        with patch.object(transport._client, "post") as mock_post:
            import httpx

            # First call fails with network error, second succeeds
            mock_post.side_effect = [
                httpx.NetworkError("Connection refused"),
                MagicMock(status_code=200),
            ]

            await transport.send_event(event)

            assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_send_event_calls_callback_after_max_retries(self):
        """Test that callback is called after max retries exhausted."""
        transport = HttpTransport(endpoint="http://localhost:8000")
        event = _make_event()
        callback = MagicMock(spec=DeliveryFailureCallback)
        transport._on_delivery_failure = callback

        with patch.object(transport._client, "post") as mock_post:
            import httpx

            # All calls fail
            mock_post.side_effect = httpx.TimeoutException("Timeout")

            await transport.send_event(event)

            assert mock_post.call_count == MAX_RETRIES + 1
            callback.assert_called_once()
            assert isinstance(callback.call_args[0][0], TransientError)

    @pytest.mark.asyncio
    async def test_send_event_per_call_callback_overrides_instance_callback(self):
        """Test that per-call callback overrides instance-level callback."""
        transport = HttpTransport(endpoint="http://localhost:8000", on_delivery_failure=MagicMock())
        event = _make_event()
        per_call_callback = MagicMock(spec=DeliveryFailureCallback)

        with patch.object(transport._client, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=401)

            await transport.send_event(event, on_delivery_failure=per_call_callback)

            per_call_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_event_callback_exception_is_caught(self):
        """Test that callback exceptions are caught and logged."""
        transport = HttpTransport(endpoint="http://localhost:8000")
        event = _make_event()
        callback = MagicMock(spec=DeliveryFailureCallback, side_effect=RuntimeError("Callback error"))

        with patch.object(transport._client, "post") as mock_post, patch(
            "agent_debugger_sdk.transport.logger"
        ) as mock_logger:
            mock_post.return_value = MagicMock(status_code=401)

            # Should not raise
            await transport.send_event(event, on_delivery_failure=callback)

            mock_logger.error.assert_called_once()


# =============================================================================
# Transport Session Methods Tests
# =============================================================================


class TestHttpTransportSessionMethods:
    """Tests for HttpTransport session-related methods."""

    @pytest.mark.asyncio
    async def test_send_session_start_success(self):
        """Test successful session start sending."""
        transport = HttpTransport(endpoint="http://localhost:8000")
        session = Session(id="s1", agent_name="test", framework="test")

        with patch.object(transport._client, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=201)

            await transport.send_session_start(session)

            mock_post.assert_called_once_with("/api/sessions", json=session.to_dict())

    @pytest.mark.asyncio
    async def test_send_session_update_success(self):
        """Test successful session update sending."""
        transport = HttpTransport(endpoint="http://localhost:8000")
        session = Session(id="s1", agent_name="test", framework="test")

        with patch.object(transport._client, "put") as mock_put:
            mock_put.return_value = MagicMock(status_code=200)

            await transport.send_session_update(session)

            mock_put.assert_called_once_with("/api/sessions/s1", json=session.to_dict())

    @pytest.mark.asyncio
    async def test_send_session_start_graceful_on_failure(self):
        """Test that session start failures are handled gracefully."""
        transport = HttpTransport(endpoint="http://localhost:8000")
        session = Session(id="s1", agent_name="test", framework="test")

        with patch.object(transport._client, "post") as mock_post:
            mock_post.side_effect = ConnectionError("Network down")

            # Should not raise
            await transport.send_session_start(session)

    @pytest.mark.asyncio
    async def test_send_session_update_graceful_on_failure(self):
        """Test that session update failures are handled gracefully."""
        transport = HttpTransport(endpoint="http://localhost:8000")
        session = Session(id="s1", agent_name="test", framework="test")

        with patch.object(transport._client, "put") as mock_put:
            mock_put.side_effect = ConnectionError("Network down")

            # Should not raise
            await transport.send_session_update(session)


# =============================================================================
# Transport Close Tests
# =============================================================================


class TestHttpTransportClose:
    """Tests for HttpTransport close method."""

    @pytest.mark.asyncio
    async def test_close_releases_resources(self):
        """Test that close releases HTTP client resources."""
        transport = HttpTransport(endpoint="http://localhost:8000")

        with patch.object(transport._client, "aclose") as mock_aclose:
            mock_aclose.return_value = None

            await transport.close()

            mock_aclose.assert_called_once()


# =============================================================================
# Transport Retry Configuration Tests
# =============================================================================


class TestTransportRetryConfiguration:
    """Tests for transport retry configuration constants."""

    def test_max_retries_value(self):
        """Test MAX_RETRIES has expected value."""
        assert MAX_RETRIES == 3

    def test_initial_backoff_value(self):
        """Test INITIAL_BACKOFF_SECONDS has expected value."""
        assert INITIAL_BACKOFF_SECONDS == 0.5

    def test_backoff_multiplier_value(self):
        """Test BACKOFF_MULTIPLIER has expected value."""
        assert BACKOFF_MULTIPLIER == 2.0


# =============================================================================
# Transport Unsupported Method Tests
# =============================================================================


class TestTransportUnsupportedMethods:
    """Tests for handling unsupported HTTP methods."""

    @pytest.mark.asyncio
    async def test_unsupported_method_raises_error(self):
        """Test that unsupported HTTP methods raise ValueError."""
        transport = HttpTransport(endpoint="http://localhost:8000")

        with pytest.raises(ValueError, match="Unsupported HTTP method"):
            await transport._send_with_retry(
                method="DELETE",
                path="/api/test",
                payload={},
                context="test",
            )


# =============================================================================
# Integration: Emitter with Transport Tests
# =============================================================================


class TestEmitterWithTransportIntegration:
    """Integration tests for EventEmitter with HttpTransport."""

    @pytest.mark.asyncio
    async def test_emitter_uses_transport_as_persister(
        self,
        session_id: str,
        session: Session,
        event_store: list,
        event_lock: asyncio.Lock,
        event_sequence: ContextVar[int],
    ):
        """Test that EventEmitter can use HttpTransport as persister."""
        transport = HttpTransport(endpoint="http://localhost:8000")

        async def persist_via_transport(event: TraceEvent) -> None:
            await transport.send_event(event)

        emitter = EventEmitter(
            session_id=session_id,
            session=session,
            event_store=event_store,
            event_lock=event_lock,
            event_sequence=event_sequence,
            event_buffer=None,
            event_persister=persist_via_transport,
            session_update_hook=None,
        )

        event = _make_event()

        with patch.object(transport._client, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)

            await emitter.emit(event)

            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_emitter_handles_transport_failure_gracefully(
        self,
        session_id: str,
        session: Session,
        event_store: list,
        event_lock: asyncio.Lock,
        event_sequence: ContextVar[int],
        caplog: pytest.LogCaptureFixture,
    ):
        """Test that transport failures in persister are handled gracefully."""
        transport = HttpTransport(endpoint="http://localhost:8000")

        async def persist_via_transport(event: TraceEvent) -> None:
            await transport.send_event(event)

        emitter = EventEmitter(
            session_id=session_id,
            session=session,
            event_store=event_store,
            event_lock=event_lock,
            event_sequence=event_sequence,
            event_buffer=None,
            event_persister=persist_via_transport,
            session_update_hook=None,
        )

        event = _make_event()

        with patch.object(transport._client, "post") as mock_post, caplog.at_level(
            logging.WARNING, logger="agent_debugger"
        ):
            import httpx

            mock_post.side_effect = httpx.NetworkError("Connection refused")

            await emitter.emit(event)

        # Event should still be stored locally
        assert len(event_store) == 1
