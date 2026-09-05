"""Unit tests for AlertDeriver.get_threshold / get_threshold_async."""

from __future__ import annotations

import pytest

from collector.alerts.base import AlertDeriver


class _ConcreteDeriver(AlertDeriver):
    """Minimal concrete subclass to exercise the abstract base."""

    def derive(self, events):
        return []


def test_get_threshold_no_policy_getter_returns_default():
    deriver = _ConcreteDeriver()

    result = deriver.get_threshold("tool_loop", default_threshold=3.0)

    assert result == 3.0


def test_get_threshold_sync_policy_returns_threshold_value():
    def policy_getter(alert_type, agent_name):
        return {"enabled": True, "threshold_value": 7.5}

    deriver = _ConcreteDeriver(policy_getter=policy_getter)

    result = deriver.get_threshold("tool_loop", agent_name="agent-1", default_threshold=1.0)

    assert result == 7.5


def test_get_threshold_disabled_policy_returns_default():
    def policy_getter(alert_type, agent_name):
        return {"enabled": False, "threshold_value": 7.5}

    deriver = _ConcreteDeriver(policy_getter=policy_getter)

    result = deriver.get_threshold("tool_loop", default_threshold=2.0)

    assert result == 2.0


def test_get_threshold_policy_getter_returns_none():
    def policy_getter(alert_type, agent_name):
        return None

    deriver = _ConcreteDeriver(policy_getter=policy_getter)

    result = deriver.get_threshold("tool_loop", default_threshold=4.0)

    assert result == 4.0


@pytest.mark.filterwarnings("ignore:coroutine.*was never awaited:RuntimeWarning")
def test_get_threshold_async_policy_getter_returns_default_immediately():
    async def policy_getter(alert_type, agent_name):
        return {"enabled": True, "threshold_value": 9.0}

    deriver = _ConcreteDeriver(policy_getter=policy_getter)

    # get_threshold (sync) cannot await; an async getter must fall back to default.
    result = deriver.get_threshold("tool_loop", default_threshold=5.0)

    assert result == 5.0


@pytest.mark.asyncio
async def test_get_threshold_async_no_policy_getter_returns_default():
    deriver = _ConcreteDeriver()

    result = await deriver.get_threshold_async("tool_loop", default_threshold=3.0)

    assert result == 3.0


@pytest.mark.asyncio
async def test_get_threshold_async_sync_policy_returns_threshold_value():
    def policy_getter(alert_type, agent_name):
        return {"enabled": True, "threshold_value": 6.0}

    deriver = _ConcreteDeriver(policy_getter=policy_getter)

    result = await deriver.get_threshold_async("tool_loop", default_threshold=1.0)

    assert result == 6.0


@pytest.mark.asyncio
async def test_get_threshold_async_awaits_coroutine_policy_getter():
    async def policy_getter(alert_type, agent_name):
        return {"enabled": True, "threshold_value": 8.0}

    deriver = _ConcreteDeriver(policy_getter=policy_getter)

    result = await deriver.get_threshold_async(
        "tool_loop", agent_name="agent-1", default_threshold=1.0
    )

    assert result == 8.0


@pytest.mark.asyncio
async def test_get_threshold_async_disabled_policy_returns_default():
    async def policy_getter(alert_type, agent_name):
        return {"enabled": False, "threshold_value": 8.0}

    deriver = _ConcreteDeriver(policy_getter=policy_getter)

    result = await deriver.get_threshold_async("tool_loop", default_threshold=2.0)

    assert result == 2.0
