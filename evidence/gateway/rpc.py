"""JSON-RPC 2.0 over stdio client for the single upstream MCP server.

The transport is the pilot's one pinned transport: newline-delimited
UTF-8 JSON, one message per line.  A daemon reader thread pushes parsed
response lines onto a queue; ``request`` matches responses by id.

Failure semantics are deliberately narrow: any timeout or stream EOF
*after a request was sent* raises :class:`UpstreamLost`.  The caller
must record the outcome as unknown and must never retry the forwarded
mutation — this module never retries on its own.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from queue import Empty, Queue
from typing import Any

from evidence.schema import MCP_PROTOCOL_VERSION

__all__ = ["UpstreamLost", "StdioUpstream"]

#: Sentinel the reader thread enqueues when stdout reaches EOF.
_EOF = object()


class UpstreamLost(RuntimeError):
    """The upstream timed out or died after a request was sent.

    The request may or may not have been applied — the outcome is
    unknown, which is exactly what the gateway records.
    """


class StdioUpstream:
    """Client for one MCP server spawned as a subprocess over stdio."""

    def __init__(self, command: list[str], timeout_s: float = 5.0) -> None:
        self.timeout_s = timeout_s
        self._next_id = 0
        self._write_lock = threading.Lock()
        self._closed = False
        self._proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
        self._responses: Queue[Any] = Queue()
        self._reader = threading.Thread(
            target=self._read_loop, name="stdio-upstream-reader", daemon=True
        )
        self._reader.start()

    # -- plumbing ---------------------------------------------------------

    def _read_loop(self) -> None:
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                # Tolerate stray non-JSON output on stdout; only responses
                # (messages carrying an id) are interesting here.
                continue
            if isinstance(message, dict) and "id" in message:
                self._responses.put(message)
        self._responses.put(_EOF)

    def _send(self, message: dict[str, Any]) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.write(json.dumps(message) + "\n")
        self._proc.stdin.flush()

    def _send_message(self, message: dict[str, Any], what: str) -> None:
        if self._closed:
            raise UpstreamLost(f"cannot send {what}: upstream client already closed")
        with self._write_lock:
            try:
                self._send(message)
            except OSError as exc:
                raise UpstreamLost(f"failed to send {what}: {exc}") from exc

    # -- public API ---------------------------------------------------------

    def request(
        self, method: str, params: dict[str, Any], timeout_s: float | None = None
    ) -> dict[str, Any]:
        """Send a JSON-RPC request and return the full response object.

        Raises :class:`UpstreamLost` on timeout or EOF after the send —
        never retries.
        """
        with self._write_lock:
            if self._closed:
                raise UpstreamLost(f"cannot call {method!r}: upstream client already closed")
            self._next_id += 1
            request_id = self._next_id
            message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            try:
                self._send(message)
            except OSError as exc:
                raise UpstreamLost(f"failed to send {method!r}: {exc}") from exc

        timeout = self.timeout_s if timeout_s is None else timeout_s
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise UpstreamLost(f"timeout waiting for response to {method!r}")
            try:
                item = self._responses.get(timeout=remaining)
            except Empty as exc:
                raise UpstreamLost(f"timeout waiting for response to {method!r}") from exc
            if item is _EOF:
                raise UpstreamLost(f"upstream closed the stream before answering {method!r}")
            if item.get("id") == request_id:
                return item
            # A response to an older (already-failed) request: drop it.

    def notify(self, method: str, params: dict[str, Any]) -> None:
        """Send a notification; no response is expected."""
        self._send_message(
            {"jsonrpc": "2.0", "method": method, "params": params}, f"notification {method!r}"
        )

    def initialize(
        self, client_info: dict[str, Any], timeout_s: float | None = None
    ) -> dict[str, Any]:
        """MCP handshake: ``initialize`` with the pinned protocol version,
        then ``notifications/initialized``.  Returns the server's result."""
        response = self.request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": client_info,
            },
            timeout_s=timeout_s,
        )
        if response.get("error") is not None:
            raise UpstreamLost(f"upstream initialize failed: {response['error']!r}")
        self.notify("notifications/initialized", {})
        return response.get("result") or {}

    def close(self) -> None:
        """Terminate the server: SIGTERM, wait, kill on hang.  Idempotent."""
        if self._closed:
            return
        self._closed = True
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=3.0)
        for stream in (self._proc.stdin, self._proc.stdout):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        self._reader.join(timeout=1.0)

    def __enter__(self) -> StdioUpstream:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
