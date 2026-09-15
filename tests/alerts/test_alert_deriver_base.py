"""Tests for AlertDeriver.get_threshold and get_threshold_async."""

from __future__ import annotations

from typing import Any

import pytest

from agent_debugger_sdk.core.events import TraceEvent
from collector.alerts.base import AlertDeriver


class _NoopDeriver(AlertDeriver):
    """Minimal concrete AlertDeriver for exercising the base class."""

    def derive(self, events: list[TraceEvent]) -> list[dict[str, Any]]:
        return []


def test_get_threshold_no_policy_getter_returns_default():
    deriver = _NoopDeriver()

    result = deriver.get_threshold("tool_loop", default_threshold=1.5)

    assert result == 1.5


def test_get_threshold_sync_policy_getter_returns_threshold_value():
    def policy_getter(alert_type: str, agent_name: str | None) -> dict:
        return {"enabled": True, "threshold_value": 4.0}

    deriver = _NoopDeriver(policy_getter=policy_getter)

    result = deriver.get_threshold("tool_loop", default_threshold=1.0)

    assert result == 4.0


def test_get_threshold_sync_policy_disabled_returns_default():
    def policy_getter(alert_type: str, agent_name: str | None) -> dict:
        return {"enabled": False, "threshold_value": 4.0}

    deriver = _NoopDeriver(policy_getter=policy_getter)

    result = deriver.get_threshold("tool_loop", default_threshold=1.0)

    assert result == 1.0


def test_get_threshold_sync_policy_none_returns_default():
    def policy_getter(alert_type: str, agent_name: str | None) -> None:
        return None

    deriver = _NoopDeriver(policy_getter=policy_getter)

    result = deriver.get_threshold("tool_loop", default_threshold=2.0)

    assert result == 2.0


def test_get_threshold_async_policy_getter_returns_default_immediately():
    async def policy_getter(alert_type: str, agent_name: str | None) -> dict:
        return {"enabled": True, "threshold_value": 9.0}

    deriver = _NoopDeriver(policy_getter=policy_getter)

    # Documented sync-context limitation: an async policy_getter yields a
    # coroutine object, which get_threshold cannot await, so it falls back
    # to the default and leaves the coroutine unawaited.
    result = deriver.get_threshold("tool_loop", default_threshold=3.0)

    assert result == 3.0


@pytest.mark.asyncio
async def test_get_threshold_async_no_policy_getter_returns_default():
    deriver = _NoopDeriver()

    result = await deriver.get_threshold_async("tool_loop", default_threshold=1.5)

    assert result == 1.5


@pytest.mark.asyncio
async def test_get_threshold_async_sync_policy_getter_returns_threshold_value():
    def policy_getter(alert_type: str, agent_name: str | None) -> dict:
        return {"enabled": True, "threshold_value": 5.0}

    deriver = _NoopDeriver(policy_getter=policy_getter)

    result = await deriver.get_threshold_async("tool_loop", default_threshold=1.0)

    assert result == 5.0


@pytest.mark.asyncio
async def test_get_threshold_async_async_policy_getter_awaits_and_returns_threshold_value():
    async def policy_getter(alert_type: str, agent_name: str | None) -> dict:
        return {"enabled": True, "threshold_value": 7.0}

    deriver = _NoopDeriver(policy_getter=policy_getter)

    result = await deriver.get_threshold_async("tool_loop", default_threshold=1.0)

    assert result == 7.0


@pytest.mark.asyncio
async def test_get_threshold_async_disabled_policy_returns_default():
    async def policy_getter(alert_type: str, agent_name: str | None) -> dict:
        return {"enabled": False, "threshold_value": 7.0}

    deriver = _NoopDeriver(policy_getter=policy_getter)

    result = await deriver.get_threshold_async("tool_loop", default_threshold=2.5)

    assert result == 2.5
