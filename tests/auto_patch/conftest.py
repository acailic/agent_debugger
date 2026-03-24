"""Shared fixtures and helpers for auto_patch tests."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

import agent_debugger_sdk.auto_patch._transport as transport_module

_FLUSH_TIMEOUT = 2.0


@pytest.fixture(autouse=True)
def setup_test_db():
    """No-op override: auto_patch tests do not need a database."""
    yield


def _flush(adapter: Any) -> None:
    """Drain the background transport thread queue for any adapter.

    Args:
        adapter: Any adapter instance with a ``_transport`` attribute
            pointing to a :class:`~agent_debugger_sdk.auto_patch._transport.SyncTransport`.
    """
    assert adapter._transport is not None
    transport = adapter._transport
    transport._queue.put(transport_module._SENTINEL)
    transport._thread.join(timeout=_FLUSH_TIMEOUT)


def _get_trace_events(mock_httpx: MagicMock) -> list[dict]:
    """Extract the JSON bodies of all /api/traces POST calls.

    Args:
        mock_httpx: The mock ``httpx.Client`` instance used in the test.

    Returns:
        List of event payload dicts sent to ``/api/traces``.
    """
    events = []
    for c in mock_httpx.post.call_args_list:
        url = c.args[0] if c.args else c.kwargs.get("url", "")
        if "/api/traces" in str(url):
            payload = c.kwargs.get("json") or (c.args[1] if len(c.args) > 1 else None)
            if isinstance(payload, dict):
                events.append(payload)
    return events
