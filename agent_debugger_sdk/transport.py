"""HTTP transport for sending events to the collector."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

import httpx

from agent_debugger_sdk.core.events import Session, TraceEvent

logger = logging.getLogger("agent_debugger")


# =============================================================================
# Typed Exceptions
# =============================================================================


class TransportError(Exception):
    """Base exception for transport-related errors."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TransientError(TransportError):
    """Error that may be resolved by retrying (e.g., network timeout, 5xx)."""

    pass


class PermanentError(TransportError):
    """Error that will not be resolved by retrying (e.g., 4xx auth failure)."""

    pass


# =============================================================================
# Callback Type
# =============================================================================

DeliveryFailureCallback = Callable[[TransportError], None]


# =============================================================================
# Retry Configuration
# =============================================================================

MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 0.5
BACKOFF_MULTIPLIER = 2.0


class HttpTransport:
    """HTTP transport for sending trace events and sessions to the collector.

    This class provides async methods to send events and session data to a remote
    collector via HTTP. It includes API key authentication for multi-tenant isolation
    and graceful error handling to prevent transport failures from breaking agent execution.

    Attributes:
        _endpoint: The base URL of the collector endpoint
        _headers: HTTP headers to include in all requests (including auth)
        _client: The httpx async HTTP client
        _on_delivery_failure: Optional callback invoked when delivery fails after retries
    """

    def __init__(
        self,
        endpoint: str,
        api_key: str | None = None,
        *,
        on_delivery_failure: DeliveryFailureCallback | None = None,
    ) -> None:
        """Initialize the HTTP transport.

        Args:
            endpoint: The base URL of the collector (e.g., "http://localhost:8000")
            api_key: Optional API key for authentication. If provided, will be
                included in the Authorization header as a Bearer token.
            on_delivery_failure: Optional callback invoked when delivery fails after
                all retry attempts. Receives the final TransportError.
        """
        self._endpoint = endpoint.rstrip("/")
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=self._endpoint,
            headers=self._headers,
            timeout=5.0,
        )
        self._on_delivery_failure = on_delivery_failure

    async def send_event(
        self,
        event: TraceEvent,
        *,
        on_delivery_failure: DeliveryFailureCallback | None = None,
    ) -> None:
        """Send a trace event to the collector.

        Posts the event to the /api/traces endpoint. If the request fails for any
        reason (network error, server error, timeout), the error is logged and
        swallowed to prevent breaking agent execution. Transient errors (5xx, timeouts)
        will be retried with exponential backoff up to 3 times.

        Args:
            event: The TraceEvent to send
            on_delivery_failure: Optional callback invoked when delivery fails after
                all retry attempts. If provided, overrides the instance-level callback.
        """
        await self._send_with_retry(
            method="POST",
            path="/api/traces",
            payload=event.to_dict(),
            context=f"event_id={event.id}",
            on_delivery_failure=on_delivery_failure,
        )

    async def send_session_start(
        self,
        session: Session,
        *,
        on_delivery_failure: DeliveryFailureCallback | None = None,
    ) -> None:
        """Send a session start event to create a new session.

        Posts the session to the /api/sessions endpoint. If the request fails,
        the error is logged and swallowed. Transient errors (5xx, timeouts)
        will be retried with exponential backoff up to 3 times.

        Args:
            session: The Session object to create
            on_delivery_failure: Optional callback invoked when delivery fails after
                all retry attempts. If provided, overrides the instance-level callback.
        """
        await self._send_with_retry(
            method="POST",
            path="/api/sessions",
            payload=session.to_dict(),
            context=f"session_id={session.id}",
            on_delivery_failure=on_delivery_failure,
        )

    async def send_session_update(
        self,
        session: Session,
        *,
        on_delivery_failure: DeliveryFailureCallback | None = None,
    ) -> None:
        """Send a session update to the collector.

        Puts the updated session data to the /api/sessions/{id} endpoint.
        If the request fails, the error is logged and swallowed. Transient errors
        (5xx, timeouts) will be retried with exponential backoff up to 3 times.

        Args:
            session: The Session object with updated data
            on_delivery_failure: Optional callback invoked when delivery fails after
                all retry attempts. If provided, overrides the instance-level callback.
        """
        await self._send_with_retry(
            method="PUT",
            path=f"/api/sessions/{session.id}",
            payload=session.to_dict(),
            context=f"session_id={session.id}",
            on_delivery_failure=on_delivery_failure,
        )

    async def _execute_http_request(
        self,
        method: str,
        path: str,
        payload: dict,
    ) -> None:
        """Execute a single HTTP request and validate the response.

        Args:
            method: HTTP method (POST, PUT, etc.)
            path: API path
            payload: JSON payload

        Raises:
            ValueError: If HTTP method is not supported
            PermanentError: For 4xx status codes
            TransientError: For 5xx status codes
        """
        if method == "POST":
            response = await self._client.post(path, json=payload)
        elif method == "PUT":
            response = await self._client.put(path, json=payload)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        if response.status_code >= 500:
            raise TransientError(
                f"Server error (status={response.status_code})",
                status_code=response.status_code,
            )
        elif response.status_code >= 400:
            raise PermanentError(
                f"Client error (status={response.status_code})",
                status_code=response.status_code,
            )

    def _should_retry(self, error: Exception) -> bool:
        """Determine if an error is retryable.

        Args:
            error: The exception that occurred

        Returns:
            True if the error is transient and should be retried
        """
        return isinstance(error, TransientError)

    async def _handle_retry_backoff(self, attempt: int) -> None:
        """Handle exponential backoff between retries.

        Args:
            attempt: Current attempt number (0-indexed)
        """
        if attempt < MAX_RETRIES:
            backoff = INITIAL_BACKOFF_SECONDS * (BACKOFF_MULTIPLIER**attempt)
            await asyncio.sleep(backoff)

    def _invoke_failure_callback(
        self,
        error: TransportError,
        callback_override: DeliveryFailureCallback | None = None,
    ) -> None:
        """Invoke the failure callback safely.

        Args:
            error: The error that occurred
            callback_override: Optional callback that overrides instance-level callback
        """
        callback = callback_override or self._on_delivery_failure
        if callback is not None:
            try:
                callback(error)
            except Exception as exc:
                logger.error("Error in on_delivery_failure callback: %s", exc)

    async def _send_with_retry(
        self,
        *,
        method: str,
        path: str,
        payload: dict,
        context: str,
        on_delivery_failure: DeliveryFailureCallback | None = None,
    ) -> None:
        """Send a request with retry logic for transient errors.

        Args:
            method: HTTP method (POST, PUT, etc.)
            path: API path
            payload: JSON payload
            context: Context string for logging (e.g., "event_id=abc")
            on_delivery_failure: Optional callback for final failure notification
        """
        last_error: TransportError | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                await self._execute_http_request(method, path, payload)
                return
            except httpx.TimeoutException as exc:
                last_error = TransientError(f"Request timeout: {exc}", status_code=None)
                logger.warning(
                    "Transient error sending to collector (%s, attempt=%d/%d): %s",
                    context,
                    attempt + 1,
                    MAX_RETRIES + 1,
                    exc,
                )
            except httpx.NetworkError as exc:
                last_error = TransientError(f"Network error: {exc}", status_code=None)
                logger.warning(
                    "Transient error sending to collector (%s, attempt=%d/%d): %s",
                    context,
                    attempt + 1,
                    MAX_RETRIES + 1,
                    exc,
                )
            except (PermanentError, Exception) as exc:
                # PermanentError or unexpected - log and stop retrying
                if isinstance(exc, PermanentError):
                    last_error = exc
                else:
                    last_error = PermanentError(f"Unexpected error: {exc}", status_code=None)
                logger.warning("Permanent error sending to collector (%s): %s", context, exc)
                break

            # Retry logic for transient errors
            if self._should_retry(last_error) if last_error else False:
                await self._handle_retry_backoff(attempt)

        # All retries exhausted - invoke callback
        if last_error is not None:
            self._invoke_failure_callback(last_error, on_delivery_failure)

    async def close(self) -> None:
        """Close the HTTP client and release resources.

        Should be called when the transport is no longer needed to properly
        clean up network resources.
        """
        await self._client.aclose()
