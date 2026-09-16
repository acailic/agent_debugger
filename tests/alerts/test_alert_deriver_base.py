"""Unit tests for AlertDeriver.get_threshold and get_threshold_async."""

from __future__ import annotations

import pytest

from agent_debugger_sdk.core.events import TraceEvent
from collector.alerts.base import AlertDeriver


class _ConcreteAlertDeriver(AlertDeriver):
    """Minimal concrete subclass to exercise the abstract AlertDeriver base."""

    def derive(self, events: list[TraceEvent]) -> list[dict]:
        return []


# =============================================================================
# get_threshold (sync)
# =============================================================================


class TestGetThreshold:
    def test_no_policy_getter_returns_default(self) -> None:
        deriver = _ConcreteAlertDeriver()

        result = deriver.get_threshold("tool_loop", default_threshold=1.5)

        assert result == 1.5

    def test_sync_policy_getter_returns_threshold_value(self) -> None:
        deriver = _ConcreteAlertDeriver(
            policy_getter=lambda alert_type, agent_name=None: {
                "enabled": True,
                "threshold_value": 3.0,
            }
        )

        result = deriver.get_threshold("tool_loop", default_threshold=1.0)

        assert result == 3.0

    def test_sync_policy_getter_disabled_returns_default(self) -> None:
        deriver = _ConcreteAlertDeriver(
            policy_getter=lambda alert_type, agent_name=None: {"enabled": False}
        )

        result = deriver.get_threshold("tool_loop", default_threshold=2.0)

        assert result == 2.0

    def test_sync_policy_getter_returns_none_returns_default(self) -> None:
        deriver = _ConcreteAlertDeriver(policy_getter=lambda alert_type, agent_name=None: None)

        result = deriver.get_threshold("tool_loop", default_threshold=2.5)

        assert result == 2.5

    @pytest.mark.filterwarnings("ignore:coroutine.*was never awaited:RuntimeWarning")
    def test_async_policy_getter_returns_default_immediately(self) -> None:
        """Sync get_threshold cannot await; documented limitation returns default.

        The base implementation deliberately drops the unawaited coroutine
        when the policy_getter is async, so this test expects (and silences)
        the resulting RuntimeWarning rather than treating it as a defect.
        """

        async def async_getter(alert_type: str, agent_name: str | None = None):
            return {"enabled": True, "threshold_value": 9.0}

        deriver = _ConcreteAlertDeriver(policy_getter=async_getter)

        result = deriver.get_threshold("tool_loop", default_threshold=4.0)

        assert result == 4.0


# =============================================================================
# get_threshold_async
# =============================================================================


class TestGetThresholdAsync:
    @pytest.mark.asyncio
    async def test_no_policy_getter_returns_default(self) -> None:
        deriver = _ConcreteAlertDeriver()

        result = await deriver.get_threshold_async("tool_loop", default_threshold=1.5)

        assert result == 1.5

    @pytest.mark.asyncio
    async def test_sync_policy_getter_returns_threshold_value(self) -> None:
        deriver = _ConcreteAlertDeriver(
            policy_getter=lambda alert_type, agent_name=None: {
                "enabled": True,
                "threshold_value": 3.0,
            }
        )

        result = await deriver.get_threshold_async("tool_loop", default_threshold=1.0)

        assert result == 3.0

    @pytest.mark.asyncio
    async def test_async_policy_getter_awaits_and_returns_threshold_value(self) -> None:
        async def async_getter(alert_type: str, agent_name: str | None = None):
            return {"enabled": True, "threshold_value": 7.5}

        deriver = _ConcreteAlertDeriver(policy_getter=async_getter)

        result = await deriver.get_threshold_async("tool_loop", default_threshold=1.0)

        assert result == 7.5

    @pytest.mark.asyncio
    async def test_disabled_policy_returns_default(self) -> None:
        deriver = _ConcreteAlertDeriver(
            policy_getter=lambda alert_type, agent_name=None: {"enabled": False}
        )

        result = await deriver.get_threshold_async("tool_loop", default_threshold=2.0)

        assert result == 2.0
