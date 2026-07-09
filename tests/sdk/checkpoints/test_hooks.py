"""Tests for restore hooks and automatic replay orchestration.

Covers ``agent_debugger_sdk/checkpoints/hooks.py``:

- The ``RestoreHook`` runtime-checkable protocol.
- ``_langchain_hook`` and ``_generic_hook`` for both matching and non-matching
  state types (covering the ``isinstance`` False branches).
- ``apply_restore_hook`` dispatch, fallback, and exception handling.
- ``AutoReplayManager`` construction and replay semantics, including early
  termination when the per-event callback returns ``False``.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest

from agent_debugger_sdk.checkpoints.hooks import (
    RESTORE_HOOK_REGISTRY,
    AutoReplayManager,
    RestoreHook,
    _generic_hook,
    _langchain_hook,
    apply_restore_hook,
)
from agent_debugger_sdk.checkpoints.schemas import (
    BaseCheckpointState,
    CustomCheckpointState,
    LangChainCheckpointState,
)


class TestRestoreHookProtocol:
    """Tests for the runtime-checkable RestoreHook protocol."""

    def test_async_callable_satisfies_protocol(self) -> None:
        """An object with an async ``__call__`` should be recognized as a RestoreHook."""

        async def my_hook(state: BaseCheckpointState, target: Any) -> Any:  # noqa: ARG001
            return target

        # runtime_checkable protocols only check attribute presence, but an async
        # function exposes __call__, so it satisfies the protocol structurally.
        assert isinstance(my_hook, RestoreHook)

    def test_plain_object_does_not_satisfy_protocol(self) -> None:
        """An object without ``__call__`` should not satisfy the RestoreHook protocol."""

        class NotAHook:
            pass

        assert not isinstance(NotAHook(), RestoreHook)

    def test_builtin_functions_satisfy_protocol_via_call(self) -> None:
        """Builtins expose ``__call__`` so they pass the runtime structural check.

        This documents that runtime_checkable only inspects for ``__call__``;
        the registry still expects an awaitable result.
        """

        async def fake(state: BaseCheckpointState, target: Any) -> Any:  # noqa: ARG001
            return target

        assert isinstance(fake, RestoreHook)


class TestLangChainHook:
    """Tests for the default ``_langchain_hook``."""

    @pytest.mark.asyncio
    async def test_restores_messages_and_intermediate_steps(self) -> None:
        """LangChain state should populate messages + intermediate_steps on target."""
        state = LangChainCheckpointState(
            messages=[{"role": "user", "content": "hi"}],
            intermediate_steps=[{"tool": "search", "result": "ok"}],
            run_name="run-1",
            run_id="abc",
        )
        target = SimpleNamespace()

        result = await _langchain_hook(state, target)

        assert result is target
        assert result.messages == [{"role": "user", "content": "hi"}]
        assert result.intermediate_steps == [{"tool": "search", "result": "ok"}]

    @pytest.mark.asyncio
    async def test_returns_target_unchanged_for_custom_state(self) -> None:
        """A non-LangChain state should pass through without mutation (47->50 branch)."""
        state = CustomCheckpointState(data={"k": "v"})
        target = SimpleNamespace()

        result = await _langchain_hook(state, target)

        assert result is target
        # The langchain hook must not add langchain-specific attributes for
        # mismatched state types.
        assert not hasattr(result, "messages")
        assert not hasattr(result, "intermediate_steps")

    @pytest.mark.asyncio
    async def test_returns_target_unchanged_for_base_state(self) -> None:
        """A bare BaseCheckpointState should also pass through unchanged."""
        state = BaseCheckpointState(framework="langchain", label="base")
        target = SimpleNamespace(existing=True)

        result = await _langchain_hook(state, target)

        assert result is target
        assert result.existing is True
        assert not hasattr(result, "messages")


class TestGenericHook:
    """Tests for the ``_generic_hook`` fallback."""

    @pytest.mark.asyncio
    async def test_copies_data_for_custom_state(self) -> None:
        """CustomCheckpointState.data should be copied onto the target."""
        state = CustomCheckpointState(data={"answer": 42})
        target = SimpleNamespace()

        result = await _generic_hook(state, target)

        assert result is target
        assert result.data == {"answer": 42}

    @pytest.mark.asyncio
    async def test_returns_target_unchanged_for_langchain_state(self) -> None:
        """A LangChain state should not be mutated by the generic hook (58->60 branch)."""
        state = LangChainCheckpointState(messages=[{"r": 1}])
        target = SimpleNamespace()

        result = await _generic_hook(state, target)

        assert result is target
        assert not hasattr(result, "data")

    @pytest.mark.asyncio
    async def test_returns_target_unchanged_for_base_state(self) -> None:
        """A bare BaseCheckpointState should pass through without a data attribute."""
        state = BaseCheckpointState(framework="custom")
        target = SimpleNamespace(marker="x")

        result = await _generic_hook(state, target)

        assert result is target
        assert result.marker == "x"
        assert not hasattr(result, "data")


class TestApplyRestoreHookDispatch:
    """Tests for ``apply_restore_hook`` registry lookup and dispatch."""

    @pytest.mark.asyncio
    async def test_dispatches_to_langchain_hook(self) -> None:
        """The ``langchain`` framework should resolve to the registered langchain hook."""
        state = LangChainCheckpointState(messages=[{"m": 1}], intermediate_steps=[{"s": 2}])
        target = SimpleNamespace()

        result = await apply_restore_hook("langchain", state, target)

        assert result is target
        assert result.messages == [{"m": 1}]
        assert result.intermediate_steps == [{"s": 2}]

    @pytest.mark.asyncio
    async def test_falls_back_to_generic_hook_for_unknown_framework(self) -> None:
        """Unknown frameworks should fall back to the generic hook."""
        state = CustomCheckpointState(data={"payload": "yes"})
        target = SimpleNamespace()

        result = await apply_restore_hook("some-unknown-framework", state, target)

        assert result is target
        assert result.data == {"payload": "yes"}

    @pytest.mark.asyncio
    async def test_generic_fallback_handles_non_custom_state(self) -> None:
        """The generic fallback should not mutate non-Custom state (58->60 via dispatch)."""
        state = LangChainCheckpointState(messages=[{"a": 1}])
        target = SimpleNamespace()

        result = await apply_restore_hook("not-a-framework", state, target)

        assert result is target
        # generic hook only sets ``data`` for CustomCheckpointState
        assert not hasattr(result, "data")

    @pytest.mark.asyncio
    async def test_langchain_hook_handles_non_langchain_state_via_dispatch(self) -> None:
        """Dispatching langchain with a non-langchain state covers the 47->50 branch."""
        state = CustomCheckpointState(data={"x": 1})
        target = SimpleNamespace()

        result = await apply_restore_hook("langchain", state, target)

        assert result is target
        # langchain hook ignores CustomCheckpointState
        assert not hasattr(result, "messages")
        assert not hasattr(result, "intermediate_steps")


class TestApplyRestoreHookErrorHandling:
    """Tests for ``apply_restore_hook`` exception isolation."""

    @pytest.mark.asyncio
    async def test_returns_target_unchanged_when_hook_raises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A failing hook should log and return the target unchanged (lines 90-92)."""

        async def boom(state: BaseCheckpointState, target: Any) -> Any:  # noqa: ARG001
            raise RuntimeError("hook exploded")

        RESTORE_HOOK_REGISTRY["failing"] = boom
        try:
            target = SimpleNamespace()
            state = BaseCheckpointState(framework="failing")

            with caplog.at_level(
                logging.ERROR, logger="agent_debugger_sdk.checkpoints.hooks"
            ):
                result = await apply_restore_hook("failing", state, target)

            assert result is target
            assert any("failing" in record.message for record in caplog.records)
            assert any(
                record.levelno == logging.ERROR
                and record.name == "agent_debugger_sdk.checkpoints.hooks"
                for record in caplog.records
            )
            # logger.exception records the traceback text
            assert any("hook exploded" in record.exc_text or "RuntimeError" in (
                record.exc_text or ""
            ) for record in caplog.records)
        finally:
            RESTORE_HOOK_REGISTRY.pop("failing", None)

    @pytest.mark.asyncio
    async def test_hook_raising_value_error_also_isolated(self) -> None:
        """Any Exception subclass (not just RuntimeError) should be isolated."""

        async def bad(state: BaseCheckpointState, target: Any) -> Any:  # noqa: ARG001
            raise ValueError("bad value")

        RESTORE_HOOK_REGISTRY["bad"] = bad
        try:
            target = SimpleNamespace(original=True)
            state = BaseCheckpointState(framework="bad")

            result = await apply_restore_hook("bad", state, target)

            assert result is target
            assert result.original is True
        finally:
            RESTORE_HOOK_REGISTRY.pop("bad", None)


class TestRestoreHookRegistryCustomization:
    """Tests for custom hook registration in RESTORE_HOOK_REGISTRY."""

    @pytest.mark.asyncio
    async def test_custom_registered_hook_is_invoked(self) -> None:
        """A user-registered hook should be used in place of the fallback."""

        async def my_hook(state: BaseCheckpointState, target: Any) -> Any:
            target.framework_seen = state.framework
            target.touched = True
            return target

        RESTORE_HOOK_REGISTRY["my-framework"] = my_hook
        try:
            target = SimpleNamespace()
            state = BaseCheckpointState(framework="my-framework", label="lbl")

            result = await apply_restore_hook("my-framework", state, target)

            assert result is target
            assert result.framework_seen == "my-framework"
            assert result.touched is True
        finally:
            RESTORE_HOOK_REGISTRY.pop("my-framework", None)

    def test_langchain_registered_by_default(self) -> None:
        """The default registry should expose the langchain hook."""
        assert "langchain" in RESTORE_HOOK_REGISTRY
        assert RESTORE_HOOK_REGISTRY["langchain"] is _langchain_hook

    def test_registry_does_not_include_generic_by_default(self) -> None:
        """The generic hook is the implicit fallback, not a registry entry."""
        # The generic hook is only reached when a framework is absent.
        assert "custom" not in RESTORE_HOOK_REGISTRY


class TestAutoReplayManagerInit:
    """Tests for ``AutoReplayManager.__init__`` (lines 113-116)."""

    def test_defaults_for_framework_and_callback(self) -> None:
        """Omitted framework/on_event should default to ``custom`` and ``None``."""
        events: list[dict[str, Any]] = [{"id": 1}]

        manager = AutoReplayManager(events)

        assert manager.events is events
        assert manager.framework == "custom"
        assert manager.on_event is None
        assert manager.replayed == []

    def test_stores_custom_arguments(self) -> None:
        """Custom framework and on_event should be stored verbatim."""
        events = [{"id": "a"}, {"id": "b"}]

        def on_event(event: dict[str, Any]) -> bool:
            return True

        manager = AutoReplayManager(events, framework="langchain", on_event=on_event)

        assert manager.events == [{"id": "a"}, {"id": "b"}]
        assert manager.framework == "langchain"
        assert manager.on_event is on_event
        assert manager.replayed == []

    def test_replayed_starts_empty_independent_per_instance(self) -> None:
        """Each instance gets its own ``replayed`` list (no shared mutable default)."""
        m1 = AutoReplayManager([])
        m2 = AutoReplayManager([])

        m1.replayed.append({"x": 1})
        assert m2.replayed == []


class TestAutoReplayManagerRun:
    """Tests for ``AutoReplayManager.run`` (lines 124-130)."""

    @pytest.mark.asyncio
    async def test_empty_events_returns_empty_list(self) -> None:
        """With no events, run() should return an empty list without invoking callback."""
        called: list[dict[str, Any]] = []

        def on_event(event: dict[str, Any]) -> bool:
            called.append(event)
            return True

        manager = AutoReplayManager([], framework="custom", on_event=on_event)

        result = await manager.run()

        assert result == []
        assert manager.replayed == []
        assert called == []

    @pytest.mark.asyncio
    async def test_no_callback_replays_all_events(self) -> None:
        """Without an on_event callback, every event should be replayed."""
        events = [{"seq": 1}, {"seq": 2}, {"seq": 3}]
        manager = AutoReplayManager(events)

        result = await manager.run()

        assert result == events
        assert manager.replayed == events

    @pytest.mark.asyncio
    async def test_callback_returning_true_replays_all(self) -> None:
        """A truthy callback return value should let replay continue to the end."""
        events = [{"seq": 1}, {"seq": 2}]
        seen: list[dict[str, Any]] = []

        def on_event(event: dict[str, Any]) -> bool:
            seen.append(event)
            return True

        manager = AutoReplayManager(events, on_event=on_event)

        result = await manager.run()

        assert result == events
        assert seen == events

    @pytest.mark.asyncio
    async def test_callback_returning_false_stops_early(self) -> None:
        """Returning exactly ``False`` should break the replay loop immediately."""
        events = [{"seq": 1}, {"seq": 2}, {"seq": 3}]
        seen: list[dict[str, Any]] = []

        def on_event(event: dict[str, Any]) -> bool:
            seen.append(event)
            # Stop right before the second event is replayed.
            return event["seq"] != 1

        manager = AutoReplayManager(events, on_event=on_event)

        result = await manager.run()

        # The callback saw the first event (returning False), so the loop broke
        # before appending anything. The returned list reflects what was
        # actually replayed.
        assert seen == [{"seq": 1}]
        assert result == []
        assert manager.replayed == []

    @pytest.mark.asyncio
    async def test_callback_returning_none_continues_replay(self) -> None:
        """A ``None`` return is falsy but is not ``False``, so replay must continue.

        This locks in the ``result is False`` identity check (line 127).
        """
        events = [{"seq": 1}, {"seq": 2}]

        def on_event(event: dict[str, Any]) -> None:
            return None

        manager = AutoReplayManager(events, on_event=on_event)

        result = await manager.run()

        assert result == events
        assert manager.replayed == events

    @pytest.mark.asyncio
    async def test_callback_returning_zero_continues_replay(self) -> None:
        """``0`` is falsy but not identical to ``False``; replay should continue."""
        events = [{"seq": 1}, {"seq": 2}, {"seq": 3}]

        def on_event(event: dict[str, Any]) -> int:
            return 0

        manager = AutoReplayManager(events, on_event=on_event)

        result = await manager.run()

        assert result == events
        assert manager.replayed == events

    @pytest.mark.asyncio
    async def test_callback_receives_each_event_in_order(self) -> None:
        """The per-event callback should observe events in their list order."""
        events = [{"seq": i} for i in range(5)]
        seen: list[int] = []

        def on_event(event: dict[str, Any]) -> bool:
            seen.append(event["seq"])
            return True

        manager = AutoReplayManager(events, on_event=on_event)

        await manager.run()

        assert seen == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_run_does_not_reset_replayed_between_calls(self) -> None:
        """Calling run() twice appends to the same accumulating ``replayed`` list.

        The manager does not reset ``replayed`` between runs, and run() returns
        the live ``self.replayed`` list (not a copy), so prior results observe
        later mutations. Document this current-implementation behavior.
        """
        events = [{"seq": 1}]
        manager = AutoReplayManager(events)

        first = await manager.run()
        # first is the live self.replayed list reference.
        assert first is manager.replayed
        assert first == [{"seq": 1}]

        second = await manager.run()
        # second is the same list object, now holding two appends.
        assert second is first
        assert second == [{"seq": 1}, {"seq": 1}]
        assert manager.replayed == [{"seq": 1}, {"seq": 1}]

    @pytest.mark.asyncio
    async def test_false_on_first_event_yields_empty_replay(self) -> None:
        """Returning False on the very first event yields an empty replayed list."""
        events = [{"seq": 1}, {"seq": 2}]

        def on_event(event: dict[str, Any]) -> bool:
            return False

        manager = AutoReplayManager(events, on_event=on_event)

        result = await manager.run()

        assert result == []
        assert manager.replayed == []
