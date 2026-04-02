"""Synchronous fire-and-forget transport for auto-patch adapters.

Unlike the async HttpTransport used by the main SDK, this transport is
designed to be called from synchronous code paths (e.g. monkey-patched
library hooks).  Events are queued and dispatched by a background daemon
thread so that the calling code is never blocked.
"""

from __future__ import annotations

import logging
import queue
import threading
import uuid
from typing import Any

import httpx

logger = logging.getLogger("agent_debugger.auto_patch")

_SENTINEL = None  # value that signals the background thread to exit


class _SessionState:
    """Encapsulates the shared session state for all adapters in one process.

    Using a class instead of bare module globals makes the state lifecycle
    explicit and simplifies testing (replace the singleton instance).
    """

    def __init__(self) -> None:
        self._id: str | None = None
        self._lock = threading.Lock()

    def get_or_create(
        self,
        transport: SyncTransport,
        agent_name: str,
        framework: str,
    ) -> str:
        if self._id is not None:
            return self._id
        with self._lock:
            if self._id is not None:
                return self._id
            session_dict = {
                "agent_name": agent_name,
                "framework": framework,
                "status": "running",
                "config": {},
                "tags": [],
            }
            self._id = transport.send_session(session_dict)
        return self._id

    def reset(self) -> None:
        with self._lock:
            self._id = None


# Singleton shared by all adapters in one process
_session_state = _SessionState()


class SyncTransport:
    """Synchronous, fire-and-forget HTTP transport.

    Events are placed on an internal :class:`queue.Queue` and dispatched to
    the Peaky Peek collector by a background daemon thread, so callers never
    block on network I/O.

    Session creation is done synchronously (brief blocking call) because the
    session ID must be known before events can be sent.

    Args:
        server_url: Base URL of the Peaky Peek collector
            (e.g. ``"http://localhost:8000"``).
    """

    def __init__(self, server_url: str) -> None:
        self._server_url = server_url.rstrip("/")
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        self._client = httpx.Client(base_url=self._server_url, timeout=5.0, limits=limits)

        # Warn once if the server is not reachable, then proceed silently.
        try:
            self._client.get("/health")
        except Exception:
            logger.warning(
                "Peaky Peek server not reachable at %s — events will be queued "
                "but may not be delivered until the server starts.",
                self._server_url,
            )

        self._thread = threading.Thread(target=self._worker, daemon=True, name="peaky-peek-transport")
        self._thread.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_event(self, event_dict: dict[str, Any]) -> None:
        """Enqueue an event for background delivery.

        This method returns immediately; the event is dispatched by the
        background worker thread.

        Args:
            event_dict: Serialised event payload (plain dict, JSON-safe).
        """
        self._queue.put(event_dict)

    def send_session(self, session_dict: dict[str, Any]) -> str:
        """Create a new session on the collector (synchronous, brief block).

        Args:
            session_dict: Serialised session payload.

        Returns:
            The session ID returned by the server, or a locally generated
            UUID if the server is unreachable.
        """
        try:
            response = self._client.post("/api/sessions", json=session_dict)
            response.raise_for_status()
            data = response.json()
            session_id: str = data["id"]
            return session_id
        except Exception:
            fallback_id = str(uuid.uuid4())
            logger.warning(
                "Failed to create session on Peaky Peek server — using local ID %s",
                fallback_id,
            )
            return fallback_id

    def shutdown(self) -> None:
        """Signal the background thread to drain the queue and exit."""
        self._queue.put(_SENTINEL)
        self._thread.join(timeout=5.0)

    # ------------------------------------------------------------------
    # Internal worker
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        """Background thread: drains the queue and POSTs events."""
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                break
            try:
                self._client.post("/api/traces", json=item)
            except Exception:
                logger.warning("Failed to deliver event — event dropped", exc_info=True)


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


def get_or_create_session(transport: SyncTransport, agent_name: str, framework: str) -> str:
    """Return the current session ID, creating one if necessary.

    The session ID is stored in shared state so that all adapters
    within the same process share a single session.

    Args:
        transport: The :class:`SyncTransport` instance to use for creation.
        agent_name: Human-readable name for the agent being traced.
        framework: Framework identifier (e.g. ``"openai"``, ``"anthropic"``).

    Returns:
        The current (or newly created) session ID string.
    """
    return _session_state.get_or_create(transport, agent_name, framework)


def reset_session() -> None:
    """Reset the shared session ID (call on deactivate)."""
    _session_state.reset()
