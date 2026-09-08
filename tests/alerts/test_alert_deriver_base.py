"""Tests for AlertDeriver.get_threshold and get_threshold_async."""

from __future__ import annotations

from typing import Any

from agent_debugger_sdk.core.events import TraceEvent
from collector.alerts.base import AlertDeriver


class _ConcreteDeriver(AlertDeriver):
    """Minimal concrete subclass for exercising the base class."""

    def derive(self, events: list[TraceEvent]) -> list[dict[str, Any]]:
        return []


def _sync_policy(policy: dict | None):
    def getter(alert_type: str, agent_name: str | None = None):
        return policy

    return getter


async def _async_policy_value(policy: dict | None):
    return policy


def _async_policy(policy: dict | None):
    def getter(alert_type: str, agent_name: str | None = None):
        return _async_policy_value(policy)

    return getter


def test_get_threshold_no_policy_getter_returns_default():
    deriver = _ConcreteDeriver()

    result = deriver.get_threshold("tool_loop", default_threshold=1.5)

    assert result == 1.5


def test_get_threshold_sync_policy_returns_threshold_value():
    deriver = _ConcreteDeriver(
        policy_getter=_sync_policy({"enabled": True, "threshold_value": 3.0})
    )

    result = deriver.get_threshold("tool_loop", default_threshold=1.0)

    assert result == 3.0


def test_get_threshold_sync_policy_disabled_returns_default():
    deriver = _ConcreteDeriver(policy_getter=_sync_policy({"enabled": False}))

    result = deriver.get_threshold("tool_loop", default_threshold=1.0)

    assert result == 1.0


def test_get_threshold_sync_policy_none_returns_default():
    deriver = _ConcreteDeriver(policy_getter=_sync_policy(None))

    result = deriver.get_threshold("tool_loop", default_threshold=2.0)

    assert result == 2.0


def test_get_threshold_async_policy_getter_returns_default_immediately():
    created: list[Any] = []

    def getter(alert_type: str, agent_name: str | None = None):
        coro = _async_policy_value({"enabled": True, "threshold_value": 9.0})
        created.append(coro)
        return coro

    deriver = _ConcreteDeriver(policy_getter=getter)

    result = deriver.get_threshold("tool_loop", default_threshold=1.0)

    assert result == 1.0
    for coro in created:
        coro.close()


async def test_get_threshold_async_no_policy_getter_returns_default():
    deriver = _ConcreteDeriver()

    result = await deriver.get_threshold_async("tool_loop", default_threshold=1.5)

    assert result == 1.5


async def test_get_threshold_async_sync_policy_getter_returns_threshold_value():
    deriver = _ConcreteDeriver(
        policy_getter=_sync_policy({"enabled": True, "threshold_value": 4.0})
    )

    result = await deriver.get_threshold_async("tool_loop", default_threshold=1.0)

    assert result == 4.0


async def test_get_threshold_async_async_policy_getter_awaits_and_returns_threshold_value():
    deriver = _ConcreteDeriver(
        policy_getter=_async_policy({"enabled": True, "threshold_value": 7.0})
    )

    result = await deriver.get_threshold_async("tool_loop", default_threshold=1.0)

    assert result == 7.0


async def test_get_threshold_async_disabled_policy_returns_default():
    deriver = _ConcreteDeriver(policy_getter=_sync_policy({"enabled": False}))

    result = await deriver.get_threshold_async("tool_loop", default_threshold=2.5)

    assert result == 2.5
