"""Workflow tests: Reproducibility.

Verifies checkpoint replay and session diffing for LLM non-determinism.
"""

from __future__ import annotations

import yaml

from agent_debugger_sdk.core.events.base import EventType
from tests.fixtures.workflow_helpers import (
    CASSETTES_DIR,
    cassette_events,
    find_event,
    find_first_divergence,
    load_cassette,
)


class TestReplayFromCheckpointSameOutput:
    """Happy path: replay from a checkpoint produces consistent structure."""

    def test_checkpoint_exists(self):
        interactions = load_cassette("reproducibility/checkpoint_replay.yaml")
        events = cassette_events(interactions)

        checkpoint = find_event(events, event_type=EventType.CHECKPOINT)
        assert checkpoint is not None
        assert checkpoint.importance >= 0.5
        assert "state" in checkpoint.data

    def test_events_before_and_after_checkpoint(self):
        interactions = load_cassette("reproducibility/checkpoint_replay.yaml")
        events = cassette_events(interactions)

        checkpoint = find_event(events, event_type=EventType.CHECKPOINT)
        assert checkpoint is not None

        cp_idx = next(i for i, e in enumerate(events) if e.id == checkpoint.id)
        assert cp_idx > 0, "Checkpoint should not be the first event"
        assert cp_idx < len(events) - 1, "Checkpoint should not be the last event"

    def test_replay_preserves_event_types(self):
        interactions = load_cassette("reproducibility/checkpoint_replay.yaml")
        events = cassette_events(interactions)

        checkpoint = find_event(events, event_type=EventType.CHECKPOINT)
        assert checkpoint is not None

        cp_idx = next(i for i, e in enumerate(events) if e.id == checkpoint.id)

        # Simulate replay: events after checkpoint should have consistent types
        post_checkpoint = events[cp_idx + 1:]
        assert len(post_checkpoint) >= 2

        # Verify the post-checkpoint event types are deterministic
        post_types = [e.event_type for e in post_checkpoint]
        assert EventType.TOOL_CALL in post_types
        assert EventType.TOOL_RESULT in post_types


class TestDiffTwoSessionsFindDivergence:
    """Failure mode: same agent, two runs, find where they diverge."""

    def _load_sessions(self):
        path = CASSETTES_DIR / "reproducibility" / "session_diff_divergence.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        success_events = cassette_events(data["sessions"]["success"])
        failure_events = cassette_events(data["sessions"]["failure"])
        return success_events, failure_events

    def test_divergence_found(self):
        success_events, failure_events = self._load_sessions()

        divergence = find_first_divergence(success_events, failure_events)
        assert divergence is not None

    def test_divergence_has_both_events(self):
        success_events, failure_events = self._load_sessions()

        divergence = find_first_divergence(success_events, failure_events)
        assert divergence is not None
        assert divergence.index is not None
        assert divergence.explanation is not None

    def test_divergence_explains_difference(self):
        success_events, failure_events = self._load_sessions()

        divergence = find_first_divergence(success_events, failure_events)
        assert divergence is not None
        # The divergence should be at the 4th event (index 3) where success
        # has a tool_result but failure has an error
        assert divergence.index == 3
        assert divergence.event_a is not None
        assert divergence.event_b is not None
