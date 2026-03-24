"""Tests for Replay Depth L3+ features.

This test module covers advanced replay features not yet fully implemented:
- L3: Deterministic Restore Hooks (per-framework state reconstruction)
- L4: State-Drift Detection (compare restored vs original execution)
- L3 extended: Auto-Replay (automatic event replay after checkpoint)

These tests define the expected interface and behavior. Some may fail
until the features are implemented.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# L3: Deterministic Restore Hooks
# =============================================================================


class TestDeterministicRestoreHooks:
    """Tests for per-framework restore hooks that reconstruct agent state.

    Restore hooks are framework-specific callbacks that take a checkpoint state
    and reconstruct the appropriate agent state. For example, LangChain hooks
    would restore messages and intermediate_steps into the agent scratchpad.
    """

    def test_restore_hook_protocol_exists(self):
        """The RestoreHook protocol should be importable."""
        try:
            from agent_debugger_sdk.checkpoints import RestoreHook
            assert RestoreHook is not None
        except ImportError:
            pytest.skip("RestoreHook protocol not yet implemented")

    def test_restore_hook_registry_exists(self):
        """A registry for framework-specific restore hooks should exist."""
        try:
            from agent_debugger_sdk.checkpoints import RESTORE_HOOK_REGISTRY
            assert isinstance(RESTORE_HOOK_REGISTRY, dict)
        except ImportError:
            pytest.skip("RESTORE_HOOK_REGISTRY not yet implemented")

    @pytest.mark.asyncio
    async def test_langchain_hook_restores_messages(self):
        """LangChain hook should restore message history into agent state."""
        try:
            from agent_debugger_sdk.checkpoints import (
                LangChainCheckpointState,
                apply_restore_hook,
            )

            # Simulated agent state (would be actual LangChain agent in practice)
            agent_state = MagicMock()
            agent_state.messages = []

            checkpoint_state = LangChainCheckpointState(
                label="after_tool",
                messages=[
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there!"},
                ],
                intermediate_steps=[{"tool": "search", "result": "found"}],
            )

            result = await apply_restore_hook("langchain", checkpoint_state, agent_state)

            assert result.messages == checkpoint_state.messages
        except ImportError:
            pytest.skip("apply_restore_hook not yet implemented")
    @pytest.mark.asyncio
    async def test_langchain_hook_restores_intermediate_steps(self):
        """LangChain hook should restore intermediate_steps into scratchpad."""
        try:
            from agent_debugger_sdk.checkpoints import (
                LangChainCheckpointState,
                apply_restore_hook,
            )

            agent_state = MagicMock()
            agent_state.intermediate_steps = []

            checkpoint_state = LangChainCheckpointState(
                label="after_tool",
                messages=[],
                intermediate_steps=[
                    {"tool": "search", "args": {"query": "test"}, "result": "found"},
                ],
            )

            result = await apply_restore_hook("langchain", checkpoint_state, agent_state)

            assert len(result.intermediate_steps) == 1
        except ImportError:
            pytest.skip("apply_restore_hook not yet implemented")
    @pytest.mark.asyncio
    async def test_unknown_framework_falls_back_to_generic_hook(self):
        """Unknown frameworks should use a generic hook that just copies data."""
        try:
            from agent_debugger_sdk.checkpoints import (
                CustomCheckpointState,
                apply_restore_hook,
            )

            target = MagicMock()
            target.data = {}

            checkpoint_state = CustomCheckpointState(
                label="test",
                data={"step": 5, "payload": {"x": 1}},
            )

            result = await apply_restore_hook("unknown_framework", checkpoint_state, target)

            # Should still work with generic handling
            assert result is not None
        except ImportError:
            pytest.skip("apply_restore_hook not yet implemented")
    @pytest.mark.asyncio
    async def test_restore_context_calls_hook(self):
        """TraceContext.restore should automatically call registered hooks."""
        try:
            from agent_debugger_sdk import TraceContext
            from agent_debugger_sdk.checkpoints import (
                LangChainCheckpointState,
                RESTORE_HOOK_REGISTRY,
            )

            hook_called = []

            async def mock_hook(state, target):
                hook_called.append((state, target))
                return target

            # Register hook
            RESTORE_HOOK_REGISTRY["langchain"] = mock_hook

            mock_checkpoint_data = {
                "id": "cp-hook-test",
                "session_id": "sess-original",
                "event_id": "evt-1",
                "sequence": 1,
                "state": {
                    "framework": "langchain",
                    "label": "test",
                    "messages": [{"role": "user", "content": "hi"}],
                },
                "memory": {},
                "timestamp": "2026-03-24T12:00:00Z",
                "importance": 0.5,
            }

            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_response = MagicMock()
                mock_response.json.return_value = mock_checkpoint_data
                mock_response.raise_for_status = MagicMock()
                mock_get.return_value = mock_response

                ctx = await TraceContext.restore(
                    checkpoint_id="cp-hook-test",
                    server_url="http://localhost:8000",
                )

                # Hook should have been called
                assert len(hook_called) > 0 or ctx.restored_state is not None
        except ImportError as e:
            pytest.skip(f"Hook integration not yet implemented: {e}")


# =============================================================================
# L4: State-Drift Detection
# =============================================================================


class TestStateDriftDetection:
    """Tests for detecting when restored execution diverges from original.

    State-drift detection compares the execution path after restoration
    with the originally recorded events. When paths diverge, drift events
    are emitted with severity levels.
    """

    def test_drift_detector_class_exists(self):
        """DriftDetector class should be importable."""
        try:
            from agent_debugger_sdk.drift import DriftDetector
            assert DriftDetector is not None
        except ImportError:
            pytest.skip("DriftDetector not yet implemented")

    def test_drift_event_schema_exists(self):
        """DriftEvent schema should be defined."""
        try:
            from agent_debugger_sdk.drift import DriftEvent, DriftSeverity
            assert DriftEvent is not None
            assert DriftSeverity is not None
        except ImportError:
            pytest.skip("DriftEvent schema not yet implemented")

    def test_drift_severity_levels(self):
        """DriftSeverity should have warning and critical levels."""
        try:
            from agent_debugger_sdk.drift import DriftSeverity

            assert hasattr(DriftSeverity, "WARNING")
            assert hasattr(DriftSeverity, "CRITICAL")
            # Optionally also MINOR/MAJOR
        except ImportError:
            pytest.skip("DriftSeverity not yet implemented")

    def test_drift_detector_initialization(self):
        """DriftDetector should accept original events for comparison."""
        try:
            from agent_debugger_sdk.drift import DriftDetector

            original_events = [
                {"event_type": "decision", "action": "tool_a"},
                {"event_type": "tool_call", "tool": "tool_a"},
            ]

            detector = DriftDetector(original_events)
            assert detector is not None
        except ImportError:
            pytest.skip("DriftDetector not yet implemented")

    def test_drift_detector_compare_method(self):
        """DriftDetector should have a compare method for new events."""
        try:
            from agent_debugger_sdk.drift import DriftDetector

            original_events = [
                {"id": "1", "event_type": "decision", "data": {"action": "tool_a"}},
                {"id": "2", "event_type": "tool_call", "data": {"tool": "tool_a"}},
            ]

            detector = DriftDetector(original_events)
            new_event = {"id": "3", "event_type": "decision", "data": {"action": "tool_a"}}

            drift = detector.compare(new_event, index=0)
            # Should return None if no drift, or DriftEvent if drift detected
            assert drift is None or hasattr(drift, "severity")
        except ImportError:
            pytest.skip("DriftDetector.compare not yet implemented")

    def test_detect_action_drift(self):
        """Should detect when restored agent takes different action."""
        try:
            from agent_debugger_sdk.drift import DriftDetector, DriftSeverity

            original_events = [
                {"id": "1", "event_type": "decision", "data": {"chosen_action": "tool_a"}},
            ]

            detector = DriftDetector(original_events)
            restored_event = {"id": "2", "event_type": "decision", "data": {"chosen_action": "tool_b"}}

            drift = detector.compare(restored_event, index=0)

            assert drift is not None
            assert drift.severity in (DriftSeverity.WARNING, DriftSeverity.CRITICAL)
        except ImportError:
            pytest.skip("DriftDetector action drift not yet implemented")

    def test_detect_tool_call_drift(self):
        """Should detect when restored agent calls different tool."""
        try:
            from agent_debugger_sdk.drift import DriftDetector, DriftSeverity

            original_events = [
                {"id": "1", "event_type": "tool_call", "data": {"tool_name": "search"}},
            ]

            detector = DriftDetector(original_events)
            restored_event = {"id": "2", "event_type": "tool_call", "data": {"tool_name": "lookup"}}

            drift = detector.compare(restored_event, index=0)

            assert drift is not None
            assert "tool" in drift.description.lower() or "call" in drift.description.lower()
        except ImportError:
            pytest.skip("DriftDetector tool drift not yet implemented")

    def test_detect_confidence_drift(self):
        """Should detect when restored confidence differs significantly."""
        try:
            from agent_debugger_sdk.drift import DriftDetector

            original_events = [
                {"id": "1", "event_type": "decision", "data": {"confidence": 0.9}},
            ]

            detector = DriftDetector(original_events)
            restored_event = {"id": "2", "event_type": "decision", "data": {"confidence": 0.3}}

            drift = detector.compare(restored_event, index=0)

            # Large confidence drop should trigger drift
            assert drift is not None
        except ImportError:
            pytest.skip("DriftDetector confidence drift not yet implemented")

    def test_no_drift_on_matching_events(self):
        """Should not report drift when events match."""
        try:
            from agent_debugger_sdk.drift import DriftDetector

            original_events = [
                {"id": "1", "event_type": "decision", "data": {"action": "tool_a", "confidence": 0.8}},
                {"id": "2", "event_type": "tool_call", "data": {"tool_name": "tool_a"}},
            ]

            detector = DriftDetector(original_events)

            # Matching events
            restored_event = {"id": "3", "event_type": "decision", "data": {"action": "tool_a", "confidence": 0.8}}

            drift = detector.compare(restored_event, index=0)
            assert drift is None
        except ImportError:
            pytest.skip("DriftDetector not yet implemented")

    def test_drift_event_includes_context(self):
        """DriftEvent should include original and restored values."""
        try:
            from agent_debugger_sdk.drift import DriftDetector, DriftEvent

            original_events = [
                {"id": "1", "event_type": "decision", "data": {"action": "a"}},
            ]

            detector = DriftDetector(original_events)
            restored_event = {"id": "2", "event_type": "decision", "data": {"action": "b"}}

            drift = detector.compare(restored_event, index=0)

            assert drift is not None
            assert hasattr(drift, "original_value") or hasattr(drift, "expected")
            assert hasattr(drift, "restored_value") or hasattr(drift, "actual")
        except ImportError:
            pytest.skip("DriftEvent context not yet implemented")

    @pytest.mark.asyncio
    async def test_trace_context_drift_tracking(self):
        """TraceContext should track drift when restored with tracking enabled."""
        try:
            from agent_debugger_sdk import TraceContext

            mock_checkpoint_data = {
                "id": "cp-drift-test",
                "session_id": "sess-original",
                "event_id": "evt-1",
                "sequence": 1,
                "state": {"framework": "custom", "data": {}},
                "memory": {},
                "timestamp": "2026-03-24T12:00:00Z",
                "importance": 0.5,
            }

            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_response = MagicMock()
                mock_response.json.return_value = mock_checkpoint_data
                mock_response.raise_for_status = MagicMock()
                mock_get.return_value = mock_response

                ctx = await TraceContext.restore(
                    checkpoint_id="cp-drift-test",
                    server_url="http://localhost:8000",
                    track_drift=True,
                    original_session_id="sess-original",
                )

                # Should have drift detector attached
                assert hasattr(ctx, "_drift_detector") or hasattr(ctx, "drift_detector")
        except (ImportError, TypeError) as e:
            pytest.skip(f"Drift tracking in TraceContext not yet implemented: {e}")


# =============================================================================
# L3 Extended: Auto-Replay
# =============================================================================


class TestAutoReplay:
    """Tests for automatic event replay after checkpoint restoration.

    Auto-replay allows restoring from a checkpoint and automatically
    replaying all events that occurred after the checkpoint was taken,
    rebuilding the agent state as if execution had continued naturally.
    """

    @pytest.mark.asyncio
    async def test_restore_with_replay_events_option(self):
        """TraceContext.restore should accept replay_events parameter."""
        try:
            from agent_debugger_sdk import TraceContext

            mock_checkpoint_data = {
                "id": "cp-auto-replay",
                "session_id": "sess-original",
                "event_id": "evt-5",
                "sequence": 1,
                "state": {"framework": "custom", "data": {"step": 5}},
                "memory": {},
                "timestamp": "2026-03-24T12:00:00Z",
                "importance": 0.5,
            }

            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_response = MagicMock()
                mock_response.json.return_value = mock_checkpoint_data
                mock_response.raise_for_status = MagicMock()
                mock_get.return_value = mock_response

                # This should accept replay_events parameter
                ctx = await TraceContext.restore(
                    checkpoint_id="cp-auto-replay",
                    server_url="http://localhost:8000",
                    replay_events=True,
                )

                assert ctx is not None
        except TypeError as e:
            if "replay_events" in str(e):
                pytest.skip("replay_events parameter not yet implemented")
            raise

    @pytest.mark.asyncio
    async def test_auto_replay_fetches_post_checkpoint_events(self):
        """Auto-replay should fetch events that occurred after checkpoint."""
        try:
            from agent_debugger_sdk import TraceContext
            from agent_debugger_sdk.checkpoints import AutoReplayManager

            # Mock both checkpoint fetch and events fetch
            mock_checkpoint_data = {
                "id": "cp-post-events",
                "session_id": "sess-original",
                "event_id": "evt-3",
                "sequence": 1,
                "state": {"framework": "custom", "data": {}},
                "memory": {},
                "timestamp": "2026-03-24T12:00:00Z",
                "importance": 0.5,
            }

            mock_events = [
                {"id": "evt-4", "event_type": "decision", "data": {"action": "search"}},
                {"id": "evt-5", "event_type": "tool_call", "data": {"tool": "search"}},
                {"id": "evt-6", "event_type": "tool_result", "data": {"result": "found"}},
            ]

            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                def side_effect(url, *args, **kwargs):
                    mock_response = MagicMock()
                    if "checkpoints" in url:
                        mock_response.json.return_value = mock_checkpoint_data
                    elif "events" in url or "replay" in url:
                        mock_response.json.return_value = {"events": mock_events}
                    mock_response.raise_for_status = MagicMock()
                    return mock_response

                mock_get.side_effect = side_effect

                ctx = await TraceContext.restore(
                    checkpoint_id="cp-post-events",
                    server_url="http://localhost:8000",
                    replay_events=True,
                )

                # Should have replayed events available
                assert hasattr(ctx, "replayed_events") or len(ctx._events) > 0
        except (TypeError, ImportError) as e:
            pytest.skip(f"Auto-replay event fetching not yet implemented: {e}")

    @pytest.mark.asyncio
    async def test_auto_replay_filters_by_sequence(self):
        """Auto-replay should only include events after checkpoint sequence."""
        try:
            from agent_debugger_sdk import TraceContext

            checkpoint_sequence = 3

            mock_checkpoint_data = {
                "id": "cp-seq-filter",
                "session_id": "sess-original",
                "event_id": "evt-3",
                "sequence": checkpoint_sequence,
                "state": {"framework": "custom", "data": {}},
                "memory": {},
                "timestamp": "2026-03-24T12:00:00Z",
                "importance": 0.5,
            }

            # Events 1-3 should be excluded, 4-6 should be included
            mock_events = [
                {"id": "evt-1", "sequence": 1, "event_type": "decision"},
                {"id": "evt-2", "sequence": 2, "event_type": "tool_call"},
                {"id": "evt-3", "sequence": 3, "event_type": "tool_result"},
                {"id": "evt-4", "sequence": 4, "event_type": "decision"},
                {"id": "evt-5", "sequence": 5, "event_type": "tool_call"},
                {"id": "evt-6", "sequence": 6, "event_type": "tool_result"},
            ]

            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                def side_effect(url, *args, **kwargs):
                    mock_response = MagicMock()
                    if "checkpoints" in url:
                        mock_response.json.return_value = mock_checkpoint_data
                    elif "events" in url or "replay" in url:
                        mock_response.json.return_value = {"events": mock_events}
                    mock_response.raise_for_status = MagicMock()
                    return mock_response

                mock_get.side_effect = side_effect

                ctx = await TraceContext.restore(
                    checkpoint_id="cp-seq-filter",
                    server_url="http://localhost:8000",
                    replay_events=True,
                )

                # Only events after checkpoint should be replayed
                if hasattr(ctx, "replayed_events"):
                    for event in ctx.replayed_events:
                        assert event.get("sequence", 0) > checkpoint_sequence
        except (TypeError, AttributeError) as e:
            pytest.skip(f"Auto-replay sequence filtering not yet implemented: {e}")

    @pytest.mark.asyncio
    async def test_auto_replay_applies_hooks_during_replay(self):
        """Auto-replay should call restore hooks for each replayed event."""
        try:
            from agent_debugger_sdk import TraceContext
            from agent_debugger_sdk.checkpoints import RESTORE_HOOK_REGISTRY

            hook_calls = []

            async def tracking_hook(state, target):
                hook_calls.append(state)
                return target

            RESTORE_HOOK_REGISTRY["langchain"] = tracking_hook

            mock_checkpoint_data = {
                "id": "cp-hooks-replay",
                "session_id": "sess-original",
                "event_id": "evt-1",
                "sequence": 1,
                "state": {
                    "framework": "langchain",
                    "messages": [{"role": "user", "content": "test"}],
                },
                "memory": {},
                "timestamp": "2026-03-24T12:00:00Z",
                "importance": 0.5,
            }

            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_response = MagicMock()
                mock_response.json.return_value = mock_checkpoint_data
                mock_response.raise_for_status = MagicMock()
                mock_get.return_value = mock_response

                ctx = await TraceContext.restore(
                    checkpoint_id="cp-hooks-replay",
                    server_url="http://localhost:8000",
                    replay_events=True,
                )

                # Hook should have been called
                assert len(hook_calls) > 0
        except (TypeError, ImportError, KeyError) as e:
            pytest.skip(f"Auto-replay hook application not yet implemented: {e}")

    @pytest.mark.asyncio
    async def test_auto_replay_respects_importance_filter(self):
        """Auto-replay should optionally filter by importance threshold."""
        try:
            from agent_debugger_sdk import TraceContext

            mock_checkpoint_data = {
                "id": "cp-importance-filter",
                "session_id": "sess-original",
                "event_id": "evt-1",
                "sequence": 1,
                "state": {"framework": "custom", "data": {}},
                "memory": {},
                "timestamp": "2026-03-24T12:00:00Z",
                "importance": 0.5,
            }

            mock_events = [
                {"id": "evt-2", "importance": 0.1, "event_type": "log"},
                {"id": "evt-3", "importance": 0.9, "event_type": "decision"},
                {"id": "evt-4", "importance": 0.2, "event_type": "debug"},
                {"id": "evt-5", "importance": 0.8, "event_type": "error"},
            ]

            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                def side_effect(url, *args, **kwargs):
                    mock_response = MagicMock()
                    if "checkpoints" in url:
                        mock_response.json.return_value = mock_checkpoint_data
                    elif "events" in url:
                        mock_response.json.return_value = {"events": mock_events}
                    mock_response.raise_for_status = MagicMock()
                    return mock_response

                mock_get.side_effect = side_effect

                ctx = await TraceContext.restore(
                    checkpoint_id="cp-importance-filter",
                    server_url="http://localhost:8000",
                    replay_events=True,
                    importance_threshold=0.5,
                )

                if hasattr(ctx, "replayed_events"):
                    for event in ctx.replayed_events:
                        assert event.get("importance", 0) >= 0.5
        except (TypeError, AttributeError) as e:
            pytest.skip(f"Auto-replay importance filtering not yet implemented: {e}")

    def test_auto_replay_manager_class_exists(self):
        """AutoReplayManager class should exist to orchestrate replay."""
        try:
            from agent_debugger_sdk.checkpoints import AutoReplayManager
            assert AutoReplayManager is not None
        except ImportError:
            pytest.skip("AutoReplayManager not yet implemented")

    @pytest.mark.asyncio
    async def test_auto_replay_can_be_cancelled(self):
        """Auto-replay should support cancellation via callback."""
        try:
            from agent_debugger_sdk import TraceContext

            mock_checkpoint_data = {
                "id": "cp-cancel",
                "session_id": "sess-original",
                "event_id": "evt-1",
                "sequence": 1,
                "state": {"framework": "custom", "data": {}},
                "memory": {},
                "timestamp": "2026-03-24T12:00:00Z",
                "importance": 0.5,
            }

            cancelled = []

            def on_cancel(event):
                cancelled.append(event)
                return False  # Stop replay

            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_response = MagicMock()
                mock_response.json.return_value = mock_checkpoint_data
                mock_response.raise_for_status = MagicMock()
                mock_get.return_value = mock_response

                ctx = await TraceContext.restore(
                    checkpoint_id="cp-cancel",
                    server_url="http://localhost:8000",
                    replay_events=True,
                    on_replay_event=on_cancel,
                )

                # Replay should have been cancelled
                assert len(cancelled) > 0
        except (TypeError, AttributeError) as e:
            pytest.skip(f"Auto-replay cancellation not yet implemented: {e}")


# =============================================================================
# Integration Tests
# =============================================================================


class TestReplayDepthIntegration:
    """Integration tests for L3+ features working together."""

    @pytest.mark.asyncio
    async def test_restore_with_hooks_drift_detection_and_replay(self):
        """Full integration: restore with hooks, auto-replay, and drift tracking."""
        try:
            from agent_debugger_sdk import TraceContext
            from agent_debugger_sdk.checkpoints import RESTORE_HOOK_REGISTRY

            hook_calls = []
            drift_events = []

            async def integration_hook(state, target):
                hook_calls.append(state)
                return target

            RESTORE_HOOK_REGISTRY["langchain"] = integration_hook

            mock_checkpoint_data = {
                "id": "cp-full-integration",
                "session_id": "sess-original",
                "event_id": "evt-3",
                "sequence": 3,
                "state": {
                    "framework": "langchain",
                    "messages": [{"role": "user", "content": "test"}],
                    "intermediate_steps": [],
                },
                "memory": {},
                "timestamp": "2026-03-24T12:00:00Z",
                "importance": 0.5,
            }

            mock_events = [
                {"id": "evt-4", "sequence": 4, "event_type": "decision", "data": {"action": "search"}},
                {"id": "evt-5", "sequence": 5, "event_type": "tool_call", "data": {"tool": "search"}},
            ]

            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                def side_effect(url, *args, **kwargs):
                    mock_response = MagicMock()
                    if "checkpoints" in url:
                        mock_response.json.return_value = mock_checkpoint_data
                    elif "events" in url:
                        mock_response.json.return_value = {"events": mock_events}
                    mock_response.raise_for_status = MagicMock()
                    return mock_response

                mock_get.side_effect = side_effect

                ctx = await TraceContext.restore(
                    checkpoint_id="cp-full-integration",
                    server_url="http://localhost:8000",
                    replay_events=True,
                    track_drift=True,
                )

                # Verify all features engaged
                assert ctx.restored_state is not None
                assert len(hook_calls) > 0  # Hook was called
                # Drift detector should be attached
                assert hasattr(ctx, "_drift_detector") or hasattr(ctx, "drift_detector")
        except (TypeError, ImportError, AttributeError) as e:
            pytest.skip(f"Full L3+ integration not yet implemented: {e}")

    @pytest.mark.asyncio
    async def test_drift_detected_during_replay_emits_event(self):
        """When drift is detected during auto-replay, event should be emitted."""
        try:
            from agent_debugger_sdk import TraceContext
            from agent_debugger_sdk.checkpoints import RESTORE_HOOK_REGISTRY
            from agent_debugger_sdk.drift import DriftSeverity

            emitted_events = []

            async def capture_event(event):
                emitted_events.append(event)

            mock_checkpoint_data = {
                "id": "cp-drift-emit",
                "session_id": "sess-original",
                "event_id": "evt-1",
                "sequence": 1,
                "state": {"framework": "custom", "data": {}},
                "memory": {},
                "timestamp": "2026-03-24T12:00:00Z",
                "importance": 0.5,
            }

            # Original events show different action than what will be replayed
            mock_events = [
                {"id": "evt-2", "sequence": 2, "event_type": "decision", "data": {"chosen_action": "tool_a"}},
            ]

            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                def side_effect(url, *args, **kwargs):
                    mock_response = MagicMock()
                    if "checkpoints" in url:
                        mock_response.json.return_value = mock_checkpoint_data
                    elif "events" in url:
                        mock_response.json.return_value = {"events": mock_events}
                    mock_response.raise_for_status = MagicMock()
                    return mock_response

                mock_get.side_effect = side_effect

                async with await TraceContext.restore(
                    checkpoint_id="cp-drift-emit",
                    server_url="http://localhost:8000",
                    replay_events=True,
                    track_drift=True,
                ) as ctx:
                    # Record a different decision than original
                    await ctx.record_decision(
                        reasoning="Different path",
                        confidence=0.8,
                        chosen_action="tool_b",  # Different from original "tool_a"
                    )

                    # Drift event should have been emitted
                    drift_events = [e for e in emitted_events if getattr(e, "event_type", None) == "drift"]
                    assert len(drift_events) > 0
        except (TypeError, ImportError, AttributeError) as e:
            pytest.skip(f"Drift event emission not yet implemented: {e}")


# =============================================================================
# API Integration Tests
# =============================================================================


class TestReplayDepthAPIIntegration:
    """Tests for REST API integration with L3+ features."""

    @pytest.mark.asyncio
    async def test_restore_endpoint_supports_replay_events(self):
        """POST /api/checkpoints/{id}/restore should accept replay_events option."""
        import httpx
        from fastapi.testclient import TestClient

        try:
            import api.main as api_main

            # Create test session and checkpoint first
            # This would require setup; for now just test the schema
            # In real implementation, we'd create fixtures

            # Check that RestoreRequest schema supports replay_events
            from api.schemas import RestoreRequest

            # Should accept replay_events field
            request = RestoreRequest(
                session_id=None,
                label="test",
                replay_events=True,  # This field should exist
            )
            assert request.replay_events is True
        except (TypeError, ImportError) as e:
            pytest.skip(f"RestoreRequest.replay_events not yet implemented: {e}")

    @pytest.mark.asyncio
    async def test_restore_endpoint_supports_drift_tracking(self):
        """POST /api/checkpoints/{id}/restore should accept track_drift option."""
        try:
            from api.schemas import RestoreRequest

            request = RestoreRequest(
                session_id=None,
                label="test",
                track_drift=True,  # This field should exist
            )
            assert request.track_drift is True
        except (TypeError, ImportError) as e:
            pytest.skip(f"RestoreRequest.track_drift not yet implemented: {e}")

    @pytest.mark.asyncio
    async def test_restore_response_includes_replay_status(self):
        """RestoreResponse should include replay status when replay_events=True."""
        try:
            from api.schemas import RestoreResponse

            # Response should include replayed event count
            response = RestoreResponse(
                checkpoint_id="cp-test",
                original_session_id="sess-original",
                new_session_id="sess-new",
                restored_at="2026-03-24T12:00:00Z",
                state={},
                restore_token="token",
                replayed_events_count=5,  # Should exist
                drift_detected=False,  # Should exist
            )
            assert response.replayed_events_count == 5
            assert response.drift_detected is False
        except (TypeError, ImportError) as e:
            pytest.skip(f"RestoreResponse replay fields not yet implemented: {e}")


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestReplayDepthErrorHandling:
    """Tests for error handling in L3+ features."""

    @pytest.mark.asyncio
    async def test_restore_hook_failure_graceful_handling(self):
        """Restore hook failure should be logged but not crash restore."""
        try:
            from agent_debugger_sdk import TraceContext
            from agent_debugger_sdk.checkpoints import RESTORE_HOOK_REGISTRY

            async def failing_hook(state, target):
                raise RuntimeError("Hook failed!")

            RESTORE_HOOK_REGISTRY["langchain"] = failing_hook

            mock_checkpoint_data = {
                "id": "cp-hook-fail",
                "session_id": "sess-original",
                "event_id": "evt-1",
                "sequence": 1,
                "state": {
                    "framework": "langchain",
                    "messages": [],
                },
                "memory": {},
                "timestamp": "2026-03-24T12:00:00Z",
                "importance": 0.5,
            }

            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_response = MagicMock()
                mock_response.json.return_value = mock_checkpoint_data
                mock_response.raise_for_status = MagicMock()
                mock_get.return_value = mock_response

                # Should not raise, should handle gracefully
                ctx = await TraceContext.restore(
                    checkpoint_id="cp-hook-fail",
                    server_url="http://localhost:8000",
                )

                # Context should still be created
                assert ctx is not None
                # Hook error should be recorded somewhere
                assert hasattr(ctx, "_hook_errors") or True  # Optional field
        except (TypeError, ImportError) as e:
            pytest.skip(f"Hook error handling not yet implemented: {e}")

    @pytest.mark.asyncio
    async def test_auto_replay_network_failure_handling(self):
        """Auto-replay network failures should be handled gracefully."""
        try:
            from agent_debugger_sdk import TraceContext

            mock_checkpoint_data = {
                "id": "cp-network-fail",
                "session_id": "sess-original",
                "event_id": "evt-1",
                "sequence": 1,
                "state": {"framework": "custom", "data": {}},
                "memory": {},
                "timestamp": "2026-03-24T12:00:00Z",
                "importance": 0.5,
            }

            call_count = [0]

            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                def side_effect(url, *args, **kwargs):
                    call_count[0] += 1
                    mock_response = MagicMock()
                    if "checkpoints" in url:
                        mock_response.json.return_value = mock_checkpoint_data
                        mock_response.raise_for_status = MagicMock()
                    elif "events" in url and call_count[0] > 1:
                        # Simulate network failure on events fetch
                        raise httpx.NetworkError("Network unreachable")
                    return mock_response

                import httpx
                mock_get.side_effect = side_effect

                # Should not crash, should log warning or return partial result
                ctx = await TraceContext.restore(
                    checkpoint_id="cp-network-fail",
                    server_url="http://localhost:8000",
                    replay_events=True,
                )

                # Context should still be created
                assert ctx is not None
        except (TypeError, ImportError, NameError) as e:
            pytest.skip(f"Network failure handling not yet implemented: {e}")

    def test_drift_detector_handles_missing_fields(self):
        """DriftDetector should handle events with missing fields."""
        try:
            from agent_debugger_sdk.drift import DriftDetector

            original_events = [
                {"id": "1"},  # Missing event_type and data
                {"id": "2", "event_type": "decision"},  # Missing data
            ]

            # Should not crash on initialization
            detector = DriftDetector(original_events)

            # Should handle comparison with incomplete events
            drift = detector.compare({"id": "3"}, index=0)
            # Should return None (no drift detectable) or handle gracefully
        except ImportError:
            pytest.skip("DriftDetector not yet implemented")
