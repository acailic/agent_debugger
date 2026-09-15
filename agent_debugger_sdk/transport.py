"""HTTP transport for sending events to the collector."""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from agent_debugger_sdk.core.events import Checkpoint, Session, TraceEvent

logger = logging.getLogger("agent_debugger")

# HTTP timeout constants (seconds)
DEFAULT_HTTP_TIMEOUT = 5.0
DEFAULT_CONNECT_TIMEOUT = 3.0


class TransportError(Exception):
    """Base exception for transport-related errors."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TransientError(TransportError):
    """Error that may be resolved by retrying (e.g., network timeout, 5xx)."""

    def __init__(
        self, message: str, *, status_code: int | None = None, retry_after_seconds: float | None = None
    ) -> None:
        super().__init__(message, status_code=status_code)
        self.retry_after_seconds = retry_after_seconds


class PermanentError(TransportError):
    """Error that will not be resolved by retrying (e.g., 4xx auth failure)."""


DeliveryFailureCallback = Callable[[TransportError], None]


def _get_error_message(status_code: int) -> str:
    """Get a specific, actionable error message for a given HTTP status code."""
    messages = {
        401: "Authentication failed. Check your API key configuration.",
        403: "Access denied. Your API key may not have permission for this operation.",
        404: "API endpoint not found. Check that the server URL is correct.",
        408: "Server timed out receiving the request.",
        429: "Rate limited. Please retry after a brief pause.",
    }
    return messages.get(status_code, f"Client error (status={status_code})")


DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_BACKOFF_SECONDS = 0.5
DEFAULT_BACKOFF_MULTIPLIER = 2.0
DEFAULT_MAX_BACKOFF_SECONDS = 30.0


def _retry_after_seconds(value: str | None) -> float | None:
    """Parse Retry-After delay or HTTP date; ignore malformed headers."""
    if not isinstance(value, str):
        return None
    try:
        delay = float(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            delay = (retry_at - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0.0, delay) if math.isfinite(delay) else None


class RetryConfig:
    """Configuration for HTTP request retry behavior."""

    def __init__(
        self,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_backoff_seconds: float = DEFAULT_INITIAL_BACKOFF_SECONDS,
        backoff_multiplier: float = DEFAULT_BACKOFF_MULTIPLIER,
        max_backoff_seconds: float = DEFAULT_MAX_BACKOFF_SECONDS,
    ) -> None:
        """Initialize retry configuration.

        Args:
            max_retries: Maximum number of retry attempts for transient errors
            initial_backoff_seconds: Initial backoff delay before first retry
            backoff_multiplier: Multiplier for exponential backoff
            max_backoff_seconds: Maximum local backoff delay. A longer server
                Retry-After ends delivery with a failure callback instead of
                blocking the agent or retrying before the server allows it.

        Raises:
            ValueError: If configuration values are invalid
        """
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError(f"max_retries must be non-negative, got: {max_retries}")
        if not math.isfinite(initial_backoff_seconds) or initial_backoff_seconds < 0:
            raise ValueError(f"initial_backoff_seconds must be non-negative, got: {initial_backoff_seconds}")
        if not math.isfinite(backoff_multiplier) or backoff_multiplier < 1.0:
            raise ValueError(f"backoff_multiplier must be >= 1.0, got: {backoff_multiplier}")
        if not math.isfinite(max_backoff_seconds) or max_backoff_seconds < 0:
            raise ValueError(f"max_backoff_seconds must be finite and non-negative, got: {max_backoff_seconds}")

        self.max_retries = max_retries
        self.initial_backoff_seconds = initial_backoff_seconds
        self.backoff_multiplier = backoff_multiplier
        self.max_backoff_seconds = max_backoff_seconds


class HttpTransport:
    """Async HTTP transport for sending trace events and sessions to the collector."""

    def __init__(
        self,
        endpoint: str,
        api_key: str | None = None,
        *,
        retry_config: RetryConfig | None = None,
        on_delivery_failure: DeliveryFailureCallback | None = None,
    ) -> None:
        """Initialize the HTTP transport.

        Args:
            endpoint: Base URL of the collector server
            api_key: Optional API key for authentication
            retry_config: Optional retry configuration (uses defaults if None)
            on_delivery_failure: Optional callback for delivery failures
        """
        self._endpoint = endpoint.rstrip("/")
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=self._endpoint,
            headers=self._headers,
            timeout=httpx.Timeout(DEFAULT_HTTP_TIMEOUT, connect=DEFAULT_CONNECT_TIMEOUT),
        )
        self._retry_config = retry_config or RetryConfig()
        self._on_delivery_failure = on_delivery_failure

    async def send_event(
        self,
        event: TraceEvent,
        *,
        on_delivery_failure: DeliveryFailureCallback | None = None,
    ) -> None:
        """Send a trace event to the collector."""
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
        """Create a new session on the collector."""
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
        """Update a session on the collector."""
        await self._send_with_retry(
            method="PUT",
            path=f"/api/sessions/{session.id}",
            payload=session.to_dict(),
            context=f"session_id={session.id}",
            on_delivery_failure=on_delivery_failure,
        )

    async def send_checkpoint(
        self,
        checkpoint: Checkpoint,
        *,
        on_delivery_failure: DeliveryFailureCallback | None = None,
    ) -> None:
        """Deliver a checkpoint to the collector (time-travel state snapshot)."""
        await self._send_with_retry(
            method="POST",
            path="/api/checkpoints",
            payload=checkpoint.to_dict(),
            context=f"checkpoint_id={checkpoint.id}",
            on_delivery_failure=on_delivery_failure,
        )

    async def _execute_request(
        self,
        *,
        method: str,
        path: str,
        payload: dict,
    ) -> None:
        """Execute a single HTTP request."""
        if method == "POST":
            response = await self._client.post(path, json=payload)
        elif method == "PUT":
            response = await self._client.put(path, json=payload)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        # Check for HTTP error status codes
        if response.status_code >= 500 or response.status_code in (408, 429):
            raise TransientError(
                _get_error_message(response.status_code)
                if response.status_code < 500
                else f"Server error (status={response.status_code})",
                status_code=response.status_code,
                retry_after_seconds=_retry_after_seconds(response.headers.get("Retry-After")),
            )
        elif response.status_code >= 400:
            # Provide specific, actionable error messages for common status codes
            message = _get_error_message(response.status_code)
            raise PermanentError(
                message,
                status_code=response.status_code,
            )
        elif not 200 <= response.status_code < 300:
            raise PermanentError(
                f"Unexpected HTTP status={response.status_code}. Check that the server URL points directly "
                "to the collector API (redirects are not followed).",
                status_code=response.status_code,
            )

    def _classify_error(self, exc: Exception) -> tuple[TransportError, bool]:
        """Classify an exception as transient or permanent."""
        if isinstance(exc, httpx.TimeoutException):
            return TransientError(f"Request timeout: {exc}"), True
        if isinstance(exc, httpx.NetworkError):
            return TransientError(f"Network error: {exc}"), True
        if isinstance(exc, httpx.RemoteProtocolError):
            return TransientError(f"Server disconnected or sent an invalid response: {exc}"), True
        if isinstance(exc, TransientError):
            return exc, True
        if isinstance(exc, PermanentError):
            return exc, False
        # Unknown error - treat as permanent for safety
        return PermanentError(f"Unexpected error: {exc}"), False

    async def _send_with_retry(
        self,
        *,
        method: str,
        path: str,
        payload: dict,
        context: str,
        on_delivery_failure: DeliveryFailureCallback | None = None,
    ) -> None:
        """Send a request with retry logic for transient errors."""
        last_error: TransportError | None = None
        backoff = min(self._retry_config.initial_backoff_seconds, self._retry_config.max_backoff_seconds)

        for attempt in range(self._retry_config.max_retries + 1):
            try:
                await self._execute_request(method=method, path=path, payload=payload)
                return
            except Exception as exc:
                last_error, should_retry = self._classify_error(exc)

                if not should_retry:
                    logger.warning(
                        "Permanent error sending to collector (%s): %s",
                        context,
                        last_error,
                    )
                    break

                logger.warning(
                    "Transient error sending to collector (%s, attempt=%d/%d): %s",
                    context,
                    attempt + 1,
                    self._retry_config.max_retries + 1,
                    last_error,
                )

                # Wait and retry if not the last attempt
                if attempt < self._retry_config.max_retries:
                    retry_after = last_error.retry_after_seconds if isinstance(last_error, TransientError) else None
                    if retry_after is not None and retry_after > self._retry_config.max_backoff_seconds:
                        logger.warning(
                            "Collector requested Retry-After=%ss, exceeding max_backoff_seconds=%s (%s); "
                            "delivery failed without retrying early",
                            retry_after,
                            self._retry_config.max_backoff_seconds,
                            context,
                        )
                        break
                    await asyncio.sleep(max(backoff, retry_after or 0.0))
                    backoff = min(
                        backoff * self._retry_config.backoff_multiplier,
                        self._retry_config.max_backoff_seconds,
                    )

        # All retries exhausted or permanent error - invoke callback if provided
        if last_error is not None:
            callback = on_delivery_failure or self._on_delivery_failure
            if callback is not None:
                try:
                    callback(last_error)
                except Exception as callback_exc:
                    logger.error(
                        "Error in on_delivery_failure callback: %s",
                        callback_exc,
                    )

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        await self._client.aclose()

    async def __aenter__(self) -> HttpTransport:
        """Support async context manager protocol for resource cleanup."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Support async context manager protocol for resource cleanup."""
        await self.close()


__all__ = [
    "TransportError",
    "TransientError",
    "PermanentError",
    "DeliveryFailureCallback",
    "RetryConfig",
    "HttpTransport",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_INITIAL_BACKOFF_SECONDS",
    "DEFAULT_BACKOFF_MULTIPLIER",
    "DEFAULT_MAX_BACKOFF_SECONDS",
    "DEFAULT_HTTP_TIMEOUT",
    "DEFAULT_CONNECT_TIMEOUT",
]
