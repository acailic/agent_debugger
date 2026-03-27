"""HTTP transport service for cloud mode."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from .events import Session, TraceEvent


class TransportService:
    """Manage HTTP transport for cloud mode.

    Responsibilities:
    - Detect cloud mode configuration
    - Initialize HttpTransport when needed
    - Provide transport callbacks (event_persister, session hooks)
    - Clean up transport on context exit
    """

    def __init__(self) -> None:
        self._transport: Any | None = None
        self._event_persister: Callable[[TraceEvent], Awaitable[None]] | None = None
        self._session_start_hook: Callable[[Session], Awaitable[None]] | None = None
        self._session_update_hook: Callable[[Session], Awaitable[None]] | None = None

    @property
    def event_persister(self) -> Callable[[TraceEvent], Awaitable[None]] | None:
        return self._event_persister

    @property
    def session_start_hook(self) -> Callable[[Session], Awaitable[None]] | None:
        return self._session_start_hook

    @property
    def session_update_hook(self) -> Callable[[Session], Awaitable[None]] | None:
        return self._session_update_hook

    def configure_for_cloud_mode(self) -> bool:
        """Configure transport for cloud mode if enabled.

        Returns:
            True if cloud mode was configured, False otherwise
        """
        from agent_debugger_sdk.config import get_config

        config = get_config()
        if config.mode == "cloud" and config.api_key:
            from agent_debugger_sdk.transport import HttpTransport

            self._transport = HttpTransport(config.endpoint, config.api_key)
            self._event_persister = self._transport.send_event
            self._session_start_hook = self._transport.send_session_start
            self._session_update_hook = self._transport.send_session_update
            return True

        self._transport = None
        return False

    async def close(self) -> None:
        """Close the transport if it was created."""
        if self._transport is not None:
            await self._transport.close()
            self._transport = None
