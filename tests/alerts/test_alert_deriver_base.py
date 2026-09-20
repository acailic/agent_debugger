"""Tests for AlertDeriver threshold resolution (get_threshold / get_threshold_async)."""

from __future__ import annotations

from typing import Any

import pytest

from agent_debugger_sdk.core.events import TraceEvent
from collector.alerts.base import AlertDeriver

DEFAULT = 5.0


class _Deriver(AlertDeriver):
    """Minimal concrete AlertDeriver."""

    def derive(self, events: list[TraceEvent]) -> list[dict[str, Any]]:
        return []


def _sync_getter(policy: dict | None):
    calls: list[tuple[str, str | None]] = []

    def getter(alert_type: str, agent_name: str | None):
        calls.append((alert_type, agent_name))
        return policy

    getter.calls = calls  # type: ignore[attr-defined]
    return getter


def _async_getter(policy: dict | None):
    async def getter(alert_type: str, agent_name: str | None):
        return policy

    return getter


class TestGetThreshold:
    def test_no_policy_getter_returns_default(self):
        assert _Deriver().get_threshold("tool_loop", default_threshold=DEFAULT) == DEFAULT

    def test_sync_policy_returns_threshold_value(self):
        getter = _sync_getter({"enabled": True, "threshold_value": 9.0})
        deriver = _Deriver(policy_getter=getter)

        assert deriver.get_threshold("tool_loop", "agent-a", DEFAULT) == 9.0
        assert getter.calls == [("tool_loop", "agent-a")]  # type: ignore[attr-defined]

    def test_sync_policy_enabled_defaults_true(self):
        deriver = _Deriver(policy_getter=_sync_getter({"threshold_value": 7.0}))

        assert deriver.get_threshold("tool_loop", default_threshold=DEFAULT) == 7.0

    def test_sync_policy_missing_threshold_value_returns_default(self):
        deriver = _Deriver(policy_getter=_sync_getter({"enabled": True}))

        assert deriver.get_threshold("tool_loop", default_threshold=DEFAULT) == DEFAULT

    def test_disabled_policy_returns_default(self):
        deriver = _Deriver(policy_getter=_sync_getter({"enabled": False, "threshold_value": 9.0}))

        assert deriver.get_threshold("tool_loop", default_threshold=DEFAULT) == DEFAULT

    def test_none_policy_returns_default(self):
        deriver = _Deriver(policy_getter=_sync_getter(None))

        assert deriver.get_threshold("tool_loop", default_threshold=DEFAULT) == DEFAULT

    def test_async_policy_getter_returns_default_immediately(self):
        coroutines: list[Any] = []
        async_getter = _async_getter({"enabled": True, "threshold_value": 9.0})

        def getter(alert_type: str, agent_name: str | None):
            coro = async_getter(alert_type, agent_name)
            coroutines.append(coro)
            return coro

        deriver = _Deriver(policy_getter=getter)

        assert deriver.get_threshold("tool_loop", default_threshold=DEFAULT) == DEFAULT
        for coro in coroutines:
            coro.close()  # never awaited by design; avoid RuntimeWarning


class TestGetThresholdAsync:
    @pytest.mark.asyncio
    async def test_no_policy_getter_returns_default(self):
        assert await _Deriver().get_threshold_async("tool_loop", default_threshold=DEFAULT) == DEFAULT

    @pytest.mark.asyncio
    async def test_sync_policy_returns_threshold_value(self):
        deriver = _Deriver(policy_getter=_sync_getter({"enabled": True, "threshold_value": 9.0}))

        assert await deriver.get_threshold_async("tool_loop", "agent-a", DEFAULT) == 9.0

    @pytest.mark.asyncio
    async def test_async_policy_is_awaited(self):
        deriver = _Deriver(policy_getter=_async_getter({"enabled": True, "threshold_value": 9.0}))

        assert await deriver.get_threshold_async("tool_loop", default_threshold=DEFAULT) == 9.0

    @pytest.mark.asyncio
    async def test_disabled_policy_returns_default(self):
        deriver = _Deriver(policy_getter=_async_getter({"enabled": False, "threshold_value": 9.0}))

        assert await deriver.get_threshold_async("tool_loop", default_threshold=DEFAULT) == DEFAULT

    @pytest.mark.asyncio
    async def test_none_policy_returns_default(self):
        deriver = _Deriver(policy_getter=_async_getter(None))

        assert await deriver.get_threshold_async("tool_loop", default_threshold=DEFAULT) == DEFAULT
