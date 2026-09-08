"""Tests for AlertDeriver.get_threshold and get_threshold_async."""

from __future__ import annotations

from typing import Any

import pytest

from agent_debugger_sdk.core.events import TraceEvent
from collector.alerts.base import AlertDeriver


class _ConcreteAlertDeriver(AlertDeriver):
    """Minimal concrete subclass for exercising AlertDeriver."""

    def derive(self, events: list[TraceEvent]) -> list[dict[str, Any]]:
        return []


def test_get_threshold_no_policy_getter_returns_default():
    deriver = _ConcreteAlertDeriver(policy_getter=None)

    result = deriver.get_threshold("tool_loop", "agent-1", default_threshold=5.0)

    assert result == 5.0


def test_get_threshold_sync_policy_returns_threshold_value():
    def policy_getter(alert_type: str, agent_name: str | None) -> dict[str, Any]:
        return {"enabled": True, "threshold_value": 3.0}

    deriver = _ConcreteAlertDeriver(policy_getter=policy_getter)

    result = deriver.get_threshold("tool_loop", "agent-1", default_threshold=5.0)

    assert result == 3.0


def test_get_threshold_sync_policy_disabled_returns_default():
    def policy_getter(alert_type: str, agent_name: str | None) -> dict[str, Any]:
        return {"enabled": False, "threshold_value": 3.0}

    deriver = _ConcreteAlertDeriver(policy_getter=policy_getter)

    result = deriver.get_threshold("tool_loop", "agent-1", default_threshold=5.0)

    assert result == 5.0


def test_get_threshold_sync_policy_none_returns_default():
    def policy_getter(alert_type: str, agent_name: str | None) -> None:
        return None

    deriver = _ConcreteAlertDeriver(policy_getter=policy_getter)

    result = deriver.get_threshold("tool_loop", "agent-1", default_threshold=5.0)

    assert result == 5.0


@pytest.mark.filterwarnings("ignore:coroutine .* was never awaited:RuntimeWarning")
def test_get_threshold_async_policy_getter_returns_default_immediately():
    async def policy_getter(alert_type: str, agent_name: str | None) -> dict[str, Any]:
        return {"enabled": True, "threshold_value": 3.0}

    deriver = _ConcreteAlertDeriver(policy_getter=policy_getter)

    # get_threshold is sync; when the policy_getter returns a coroutine it
    # cannot be awaited here, so it falls back to the default threshold.
    # The unawaited coroutine warning is expected and suppressed above.
    result = deriver.get_threshold("tool_loop", "agent-1", default_threshold=5.0)

    assert result == 5.0


@pytest.mark.asyncio
async def test_get_threshold_async_no_policy_getter_returns_default():
    deriver = _ConcreteAlertDeriver(policy_getter=None)

    result = await deriver.get_threshold_async("tool_loop", "agent-1", default_threshold=5.0)

    assert result == 5.0


@pytest.mark.asyncio
async def test_get_threshold_async_sync_policy_getter_returns_threshold_value():
    def policy_getter(alert_type: str, agent_name: str | None) -> dict[str, Any]:
        return {"enabled": True, "threshold_value": 3.0}

    deriver = _ConcreteAlertDeriver(policy_getter=policy_getter)

    result = await deriver.get_threshold_async("tool_loop", "agent-1", default_threshold=5.0)

    assert result == 3.0


@pytest.mark.asyncio
async def test_get_threshold_async_async_policy_getter_awaits_and_returns_threshold_value():
    async def policy_getter(alert_type: str, agent_name: str | None) -> dict[str, Any]:
        return {"enabled": True, "threshold_value": 3.0}

    deriver = _ConcreteAlertDeriver(policy_getter=policy_getter)

    result = await deriver.get_threshold_async("tool_loop", "agent-1", default_threshold=5.0)

    assert result == 3.0


@pytest.mark.asyncio
async def test_get_threshold_async_disabled_policy_returns_default():
    async def policy_getter(alert_type: str, agent_name: str | None) -> dict[str, Any]:
        return {"enabled": False, "threshold_value": 3.0}

    deriver = _ConcreteAlertDeriver(policy_getter=policy_getter)

    result = await deriver.get_threshold_async("tool_loop", "agent-1", default_threshold=5.0)

    assert result == 5.0
