"""Tests for AlertDeriver.get_threshold and get_threshold_async."""

from __future__ import annotations

from typing import Any

import pytest

from agent_debugger_sdk.core.events import TraceEvent
from collector.alerts.base import AlertDeriver


class _ConcreteAlertDeriver(AlertDeriver):
    """Minimal concrete subclass for exercising the base class."""

    def derive(self, events: list[TraceEvent]) -> list[dict[str, Any]]:
        return []


async def _async_policy_getter(policy: dict | None):
    return policy


def test_get_threshold_no_policy_getter():
    deriver = _ConcreteAlertDeriver()

    result = deriver.get_threshold("tool_loop", default_threshold=1.5)

    assert result == 1.5


def test_get_threshold_sync_policy_getter_returns_threshold():
    deriver = _ConcreteAlertDeriver(
        policy_getter=lambda alert_type, agent_name: {"enabled": True, "threshold_value": 3.0}
    )

    result = deriver.get_threshold("tool_loop", default_threshold=1.0)

    assert result == 3.0


def test_get_threshold_sync_policy_getter_disabled():
    deriver = _ConcreteAlertDeriver(
        policy_getter=lambda alert_type, agent_name: {"enabled": False, "threshold_value": 3.0}
    )

    result = deriver.get_threshold("tool_loop", default_threshold=1.0)

    assert result == 1.0


def test_get_threshold_sync_policy_getter_returns_none():
    deriver = _ConcreteAlertDeriver(policy_getter=lambda alert_type, agent_name: None)

    result = deriver.get_threshold("tool_loop", default_threshold=2.0)

    assert result == 2.0


def test_get_threshold_async_policy_getter_returns_default_immediately():
    pending: list[Any] = []

    def policy_getter(alert_type: str, agent_name: str | None):
        coro = _async_policy_getter({"enabled": True, "threshold_value": 9.0})
        pending.append(coro)
        return coro

    deriver = _ConcreteAlertDeriver(policy_getter=policy_getter)

    result = deriver.get_threshold("tool_loop", default_threshold=4.0)

    assert result == 4.0
    for coro in pending:
        coro.close()


@pytest.mark.asyncio
async def test_get_threshold_async_no_policy_getter():
    deriver = _ConcreteAlertDeriver()

    result = await deriver.get_threshold_async("tool_loop", default_threshold=1.5)

    assert result == 1.5


@pytest.mark.asyncio
async def test_get_threshold_async_sync_policy_getter():
    deriver = _ConcreteAlertDeriver(
        policy_getter=lambda alert_type, agent_name: {"enabled": True, "threshold_value": 5.0}
    )

    result = await deriver.get_threshold_async("tool_loop", default_threshold=1.0)

    assert result == 5.0


@pytest.mark.asyncio
async def test_get_threshold_async_awaits_coroutine_policy_getter():
    deriver = _ConcreteAlertDeriver(
        policy_getter=lambda alert_type, agent_name: _async_policy_getter(
            {"enabled": True, "threshold_value": 7.0}
        )
    )

    result = await deriver.get_threshold_async("tool_loop", default_threshold=1.0)

    assert result == 7.0


@pytest.mark.asyncio
async def test_get_threshold_async_disabled_policy():
    deriver = _ConcreteAlertDeriver(
        policy_getter=lambda alert_type, agent_name: {"enabled": False, "threshold_value": 7.0}
    )

    result = await deriver.get_threshold_async("tool_loop", default_threshold=1.0)

    assert result == 1.0
