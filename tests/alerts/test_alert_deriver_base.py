"""Unit tests for AlertDeriver.get_threshold and get_threshold_async."""

from __future__ import annotations

from typing import Any

import pytest

from agent_debugger_sdk.core.events import TraceEvent
from collector.alerts.base import AlertDeriver


class _ConcreteDeriver(AlertDeriver):
    """Minimal concrete subclass for exercising AlertDeriver."""

    def derive(self, events: list[TraceEvent]) -> list[dict[str, Any]]:
        return []


def test_get_threshold_no_policy_getter_returns_default():
    deriver = _ConcreteDeriver()

    result = deriver.get_threshold("tool_loop", default_threshold=5.0)

    assert result == 5.0


def test_get_threshold_sync_policy_getter_returns_threshold_value():
    def policy_getter(alert_type: str, agent_name: str | None) -> dict[str, Any]:
        return {"enabled": True, "threshold_value": 3.0}

    deriver = _ConcreteDeriver(policy_getter=policy_getter)

    result = deriver.get_threshold("tool_loop", default_threshold=5.0)

    assert result == 3.0


def test_get_threshold_sync_policy_getter_disabled_returns_default():
    def policy_getter(alert_type: str, agent_name: str | None) -> dict[str, Any]:
        return {"enabled": False, "threshold_value": 3.0}

    deriver = _ConcreteDeriver(policy_getter=policy_getter)

    result = deriver.get_threshold("tool_loop", default_threshold=5.0)

    assert result == 5.0


def test_get_threshold_sync_policy_getter_returns_none_uses_default():
    def policy_getter(alert_type: str, agent_name: str | None) -> None:
        return None

    deriver = _ConcreteDeriver(policy_getter=policy_getter)

    result = deriver.get_threshold("tool_loop", default_threshold=5.0)

    assert result == 5.0


def test_get_threshold_async_policy_getter_returns_default_immediately():
    created: list[Any] = []

    async def _coro() -> dict[str, Any]:
        return {"enabled": True, "threshold_value": 3.0}

    def policy_getter(alert_type: str, agent_name: str | None) -> Any:
        coro = _coro()
        created.append(coro)
        return coro

    deriver = _ConcreteDeriver(policy_getter=policy_getter)

    result = deriver.get_threshold("tool_loop", default_threshold=5.0)

    assert result == 5.0
    for coro in created:
        coro.close()


@pytest.mark.asyncio
async def test_get_threshold_async_no_policy_getter_returns_default():
    deriver = _ConcreteDeriver()

    result = await deriver.get_threshold_async("tool_loop", default_threshold=5.0)

    assert result == 5.0


@pytest.mark.asyncio
async def test_get_threshold_async_sync_policy_getter_returns_threshold_value():
    def policy_getter(alert_type: str, agent_name: str | None) -> dict[str, Any]:
        return {"enabled": True, "threshold_value": 3.0}

    deriver = _ConcreteDeriver(policy_getter=policy_getter)

    result = await deriver.get_threshold_async("tool_loop", default_threshold=5.0)

    assert result == 3.0


@pytest.mark.asyncio
async def test_get_threshold_async_awaits_coroutine_policy_getter():
    async def policy_getter(alert_type: str, agent_name: str | None) -> dict[str, Any]:
        return {"enabled": True, "threshold_value": 3.0}

    deriver = _ConcreteDeriver(policy_getter=policy_getter)

    result = await deriver.get_threshold_async("tool_loop", default_threshold=5.0)

    assert result == 3.0


@pytest.mark.asyncio
async def test_get_threshold_async_disabled_policy_returns_default():
    async def policy_getter(alert_type: str, agent_name: str | None) -> dict[str, Any]:
        return {"enabled": False, "threshold_value": 3.0}

    deriver = _ConcreteDeriver(policy_getter=policy_getter)

    result = await deriver.get_threshold_async("tool_loop", default_threshold=5.0)

    assert result == 5.0
