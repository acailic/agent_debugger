"""Tests for AlertDeriver.get_threshold and get_threshold_async."""

from __future__ import annotations

from typing import Any

from agent_debugger_sdk.core.events import TraceEvent
from collector.alerts.base import AlertDeriver


class _ConcreteDeriver(AlertDeriver):
    """Minimal concrete subclass for exercising AlertDeriver's threshold logic."""

    def derive(self, events: list[TraceEvent]) -> list[dict[str, Any]]:
        return []


def test_get_threshold_no_policy_getter():
    deriver = _ConcreteDeriver()
    assert deriver.get_threshold("tool_loop", default_threshold=5.0) == 5.0


def test_get_threshold_sync_policy_returns_threshold():
    def policy_getter(alert_type, agent_name):
        return {"enabled": True, "threshold_value": 3.0}

    deriver = _ConcreteDeriver(policy_getter=policy_getter)
    assert deriver.get_threshold("tool_loop", default_threshold=5.0) == 3.0


def test_get_threshold_sync_policy_disabled():
    def policy_getter(alert_type, agent_name):
        return {"enabled": False, "threshold_value": 3.0}

    deriver = _ConcreteDeriver(policy_getter=policy_getter)
    assert deriver.get_threshold("tool_loop", default_threshold=5.0) == 5.0


def test_get_threshold_sync_policy_none():
    def policy_getter(alert_type, agent_name):
        return None

    deriver = _ConcreteDeriver(policy_getter=policy_getter)
    assert deriver.get_threshold("tool_loop", default_threshold=5.0) == 5.0


def test_get_threshold_async_policy_getter_returns_default_immediately():
    created_coroutines = []

    async def policy_async(alert_type, agent_name):
        return {"enabled": True, "threshold_value": 3.0}

    def policy_getter(alert_type, agent_name):
        coro = policy_async(alert_type, agent_name)
        created_coroutines.append(coro)
        return coro

    deriver = _ConcreteDeriver(policy_getter=policy_getter)
    try:
        assert deriver.get_threshold("tool_loop", default_threshold=5.0) == 5.0
    finally:
        for coro in created_coroutines:
            coro.close()


async def test_get_threshold_async_no_policy_getter():
    deriver = _ConcreteDeriver()
    assert await deriver.get_threshold_async("tool_loop", default_threshold=5.0) == 5.0


async def test_get_threshold_async_sync_policy_getter():
    def policy_getter(alert_type, agent_name):
        return {"enabled": True, "threshold_value": 3.0}

    deriver = _ConcreteDeriver(policy_getter=policy_getter)
    assert await deriver.get_threshold_async("tool_loop", default_threshold=5.0) == 3.0


async def test_get_threshold_async_async_policy_getter_awaited():
    async def policy_getter(alert_type, agent_name):
        return {"enabled": True, "threshold_value": 3.0}

    deriver = _ConcreteDeriver(policy_getter=policy_getter)
    assert await deriver.get_threshold_async("tool_loop", default_threshold=5.0) == 3.0


async def test_get_threshold_async_disabled_policy():
    async def policy_getter(alert_type, agent_name):
        return {"enabled": False, "threshold_value": 3.0}

    deriver = _ConcreteDeriver(policy_getter=policy_getter)
    assert await deriver.get_threshold_async("tool_loop", default_threshold=5.0) == 5.0
