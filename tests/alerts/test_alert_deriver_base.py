"""Unit tests for AlertDeriver.get_threshold and get_threshold_async."""

from __future__ import annotations

from typing import Any

import pytest

from agent_debugger_sdk.core.events import TraceEvent
from collector.alerts.base import AlertDeriver


class _ConcreteAlertDeriver(AlertDeriver):
    """Minimal concrete subclass for testing the abstract base."""

    def derive(self, events: list[TraceEvent]) -> list[dict[str, Any]]:
        return []


def _sync_policy_getter(policy: dict[str, Any] | None):
    def getter(alert_type: str, agent_name: str | None = None):
        return policy

    return getter


def _async_policy_getter(policy: dict[str, Any] | None):
    async def getter(alert_type: str, agent_name: str | None = None):
        return policy

    return getter


class TestGetThreshold:
    def test_no_policy_getter_returns_default(self):
        deriver = _ConcreteAlertDeriver(policy_getter=None)

        result = deriver.get_threshold("tool_loop", "agent-1", default_threshold=5.0)

        assert result == 5.0

    def test_sync_policy_getter_returns_threshold_value(self):
        deriver = _ConcreteAlertDeriver(
            policy_getter=_sync_policy_getter({"enabled": True, "threshold_value": 3.0})
        )

        result = deriver.get_threshold("tool_loop", "agent-1", default_threshold=5.0)

        assert result == 3.0

    def test_sync_policy_disabled_returns_default(self):
        deriver = _ConcreteAlertDeriver(policy_getter=_sync_policy_getter({"enabled": False}))

        result = deriver.get_threshold("tool_loop", "agent-1", default_threshold=5.0)

        assert result == 5.0

    def test_sync_policy_getter_returns_none_uses_default(self):
        deriver = _ConcreteAlertDeriver(policy_getter=_sync_policy_getter(None))

        result = deriver.get_threshold("tool_loop", "agent-1", default_threshold=5.0)

        assert result == 5.0

    def test_async_policy_getter_returns_default_immediately(self):
        deriver = _ConcreteAlertDeriver(
            policy_getter=_async_policy_getter({"enabled": True, "threshold_value": 3.0})
        )

        result = deriver.get_threshold("tool_loop", "agent-1", default_threshold=5.0)

        # Documented sync-context limitation: coroutine is never awaited,
        # so the default is returned and the coroutine is left dangling.
        assert result == 5.0


class TestGetThresholdAsync:
    @pytest.mark.asyncio
    async def test_no_policy_getter_returns_default(self):
        deriver = _ConcreteAlertDeriver(policy_getter=None)

        result = await deriver.get_threshold_async("tool_loop", "agent-1", default_threshold=5.0)

        assert result == 5.0

    @pytest.mark.asyncio
    async def test_sync_policy_getter_returns_threshold_value(self):
        deriver = _ConcreteAlertDeriver(
            policy_getter=_sync_policy_getter({"enabled": True, "threshold_value": 3.0})
        )

        result = await deriver.get_threshold_async("tool_loop", "agent-1", default_threshold=5.0)

        assert result == 3.0

    @pytest.mark.asyncio
    async def test_async_policy_getter_awaits_and_returns_threshold_value(self):
        deriver = _ConcreteAlertDeriver(
            policy_getter=_async_policy_getter({"enabled": True, "threshold_value": 7.5})
        )

        result = await deriver.get_threshold_async("tool_loop", "agent-1", default_threshold=5.0)

        assert result == 7.5

    @pytest.mark.asyncio
    async def test_disabled_policy_returns_default(self):
        deriver = _ConcreteAlertDeriver(policy_getter=_sync_policy_getter({"enabled": False}))

        result = await deriver.get_threshold_async("tool_loop", "agent-1", default_threshold=5.0)

        assert result == 5.0
