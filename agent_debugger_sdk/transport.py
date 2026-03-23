"""HTTP transport for sending events to the collector."""
from __future__ import annotations

import logging

import httpx

from agent_debugger_sdk.core.events import Session, TraceEvent

logger = logging.getLogger("agent_debugger")


class HttpTransport:
    """HTTP transport for sending trace events and sessions to the collector.

    This class provides async methods to send events and session data to a remote
    collector via HTTP. It includes API key authentication for multi-tenant isolation
    and graceful error handling to prevent transport failures from breaking agent execution.

    Attributes:
        _endpoint: The base URL of the collector endpoint
        _headers: HTTP headers to include in all requests (including auth)
        _client: The httpx async HTTP client
    """

    def __init__(self, endpoint: str, api_key: str | None = None) -> None:
        """Initialize the HTTP transport.

        Args:
            endpoint: The base URL of the collector (e.g., "http://localhost:8000")
            api_key: Optional API key for authentication. If provided, will be
                included in the Authorization header as a Bearer token.
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

    async def send_event(self, event: TraceEvent) -> None:
        """Send a trace event to the collector.

        Posts the event to the /api/traces endpoint. If the request fails for any
        reason (network error, server error, timeout), the error is logged and
        swallowed to prevent breaking agent execution.

        Args:
            event: The TraceEvent to send
        """
        try:
            await self._client.post("/api/traces", json=event.to_dict())
        except Exception:
            logger.warning("Failed to send event %s to collector", event.id)

    async def send_session_start(self, session: Session) -> None:
        """Send a session start event to create a new session.

        Posts the session to the /api/sessions endpoint. If the request fails,
        the error is logged and swallowed.

        Args:
            session: The Session object to create
        """
        try:
            await self._client.post("/api/sessions", json=session.to_dict())
        except Exception:
            logger.warning("Failed to send session start to collector")

    async def send_session_update(self, session: Session) -> None:
        """Send a session update to the collector.

        Puts the updated session data to the /api/sessions/{id} endpoint.
        If the request fails, the error is logged and swallowed.

        Args:
            session: The Session object with updated data
        """
        try:
            response = await self._client.put(
                f"/api/sessions/{session.id}", json=session.to_dict()
            )
            if response.status_code >= 400:
                logger.warning(
                    "Failed to send session update to collector (session_id=%s, status_code=%s)",
                    session.id,
                    response.status_code,
                )
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", "unknown")
            logger.warning(
                "Failed to send session update to collector (session_id=%s, status_code=%s)",
                session.id,
                status_code,
            )

    async def close(self) -> None:
        """Close the HTTP client and release resources.

        Should be called when the transport is no longer needed to properly
        clean up network resources.
        """
        await self._client.aclose()
