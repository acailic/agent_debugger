"""Real redis-server integration tests for RedisEventBuffer.

These tests exercise the buffer against an actual redis-server process:
pub/sub fan-out, XADD stream durability, bounded-queue drop-oldest
overflow, and listener reconnect after a dropped connection.

They are skipped unless BOTH of the following hold:

- the optional 'redis' python package is installed, and
- a runnable 'redis-server' binary is available on PATH.

Each test spawns its own ephemeral redis-server on a free TCP port with
persistence disabled (``--save '' --appendonly no``) and terminates it
afterwards, so nothing leaks into a developer- or CI-owned instance.
"""

from __future__ import annotations

import asyncio
import shutil
import socket
import subprocess
import time
from collections.abc import AsyncIterator
from typing import Any

import pytest

# Skip entirely if the redis client package is not installed.
pytest.importorskip("redis")

_REDIS_SERVER = shutil.which("redis-server")
if _REDIS_SERVER is None:
    pytest.skip("redis-server binary not available on PATH", allow_module_level=True)

from agent_debugger_sdk.core.events import TraceEvent  # noqa: E402
from collector.buffer_redis import RedisEventBuffer  # noqa: E402


def _free_port() -> int:
    """Reserve an ephemeral TCP port for the spawned redis-server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_server(port: int) -> subprocess.Popen:
    """Start a disposable redis-server with no persistence on ``port``."""
    return subprocess.Popen(
        [
            _REDIS_SERVER,
            "--port",
            str(port),
            "--bind",
            "127.0.0.1",
            "--save",
            "",
            "--appendonly",
            "no",
            "--daemonize",
            "no",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop_server(proc: subprocess.Popen) -> None:
    """Terminate the disposable redis-server (escalate to kill if needed)."""
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


async def _aclose_client(client: Any) -> None:
    """Close a redis client; best-effort, never raises."""
    close = getattr(client, "aclose", None) or getattr(client, "close", None)
    if close is not None:
        try:
            await close()
        except Exception:
            pass


async def _make_client(url: str):
    from redis.asyncio import Redis

    return Redis.from_url(url)


async def _wait_for_server(url: str, timeout: float = 10.0) -> None:
    """Block until the spawned redis-server answers PING (or raise)."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        client = await _make_client(url)
        try:
            if await client.ping():
                return
        except Exception as exc:  # server not up yet
            last_error = exc
        finally:
            await _aclose_client(client)
        await asyncio.sleep(0.05)
    raise RuntimeError(f"redis-server at {url} did not become ready: {last_error!r}")


async def _wait_for_numsub(
    url: str,
    channel: str,
    minimum: int | None = None,
    maximum: int | None = None,
    timeout: float = 10.0,
) -> None:
    """Wait until the server reports a satisfying subscriber count on ``channel``.

    redis-py returns channel names as bytes unless decode_responses is set,
    so both the str and bytes forms of the channel are checked.
    """
    assert (minimum is None) != (maximum is None), "pass exactly one of minimum/maximum"
    client = await _make_client(url)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            counts = await client.pubsub_numsub(channel)
            # redis-py >= 5.2 returns a list of (name, count) tuples; older
            # versions (and the sync API) return a dict.
            pairs = counts.items() if isinstance(counts, dict) else counts
            total = sum(
                count
                for name, count in pairs
                if name in (channel, channel.encode())
            )
            if minimum is not None and total >= minimum:
                return
            if maximum is not None and total <= maximum:
                return
            await asyncio.sleep(0.05)
        raise AssertionError(f"unexpected subscriber count on {channel}: never satisfied")
    finally:
        await _aclose_client(client)


@pytest.fixture()
async def redis_url() -> AsyncIterator[str]:
    """Yield a URL for a fresh, private redis-server; terminate it afterwards."""
    port = _free_port()
    proc = _start_server(port)
    url = f"redis://127.0.0.1:{port}"
    try:
        await _wait_for_server(url)
        yield url
    finally:
        _stop_server(proc)


@pytest.mark.asyncio
async def test_publish_fans_out_to_subscriber_and_xadds(redis_url: str, make_event) -> None:
    """publish() both appends to the session stream and reaches subscribers."""
    async with RedisEventBuffer(redis_url=redis_url) as buf:
        queue = await buf.subscribe("s1")
        # Wait until the listener has actually SUBSCRIBEd on the server.
        await _wait_for_numsub(redis_url, "ad:live:s1", minimum=1)

        event = make_event(session_id="s1", name="real-1")
        await buf.publish("s1", event)

        received = await asyncio.wait_for(queue.get(), timeout=5.0)
        assert isinstance(received, TraceEvent)
        assert received.session_id == "s1"
        assert received.name == "real-1"
        assert received.event_type == event.event_type
        assert received.data == event.data

        # Durable path: the event was appended to the session's Redis stream.
        stream_len = await buf._redis.xlen("ad:stream:s1")
        assert stream_len == 1


@pytest.mark.asyncio
async def test_listener_reconnects_after_connection_drop(redis_url: str, make_event) -> None:
    """Killing the pooled connections does not starve the subscriber permanently."""
    async with RedisEventBuffer(redis_url=redis_url, reconnect_delay=0.1) as buf:
        queue = await buf.subscribe("s1")
        await _wait_for_numsub(redis_url, "ad:live:s1", minimum=1)

        first = make_event(session_id="s1", name="before-drop")
        await buf.publish("s1", first)
        received = await asyncio.wait_for(queue.get(), timeout=5.0)
        assert received.name == "before-drop"

        # Drop every pooled connection, including the listener's socket.
        await buf._redis.connection_pool.disconnect()
        # The old subscription disappears server-side...
        await _wait_for_numsub(redis_url, "ad:live:s1", maximum=0)
        # ...then the listener re-subscribes. Pub/sub has no replay, so wait
        # for the fresh subscription before publishing again.
        await _wait_for_numsub(redis_url, "ad:live:s1", minimum=1)

        second = make_event(session_id="s1", name="after-drop")
        await buf.publish("s1", second)
        received_again = await asyncio.wait_for(queue.get(), timeout=10.0)
        assert received_again.name == "after-drop"


@pytest.mark.asyncio
async def test_slow_subscriber_queue_is_bounded_drop_oldest(redis_url: str, make_event) -> None:
    """A subscriber that never reads keeps only the newest bounded backlog."""
    async with RedisEventBuffer(redis_url=redis_url, subscriber_maxsize=10) as buf:
        queue = await buf.subscribe("s1")
        await _wait_for_numsub(redis_url, "ad:live:s1", minimum=1)

        for i in range(25):
            await buf.publish("s1", make_event(session_id="s1", name=f"e{i:02d}"))

        # Consume until the final published event arrives: delivery is
        # ordered, so seeing e24 means the backlog state is final.
        received: list[str] = []
        while True:
            event = await asyncio.wait_for(queue.get(), timeout=5.0)
            received.append(event.name)
            if event.name == "e24":
                break

        assert received == [f"e{i:02d}" for i in range(15, 25)]
