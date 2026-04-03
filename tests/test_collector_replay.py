"""Tests for collector/replay.py replay building logic."""

from __future__ import annotations

from datetime import datetime, timezone

from agent_debugger_sdk.core.events import (
    Checkpoint,
    DecisionEvent,
    EventType,
    SafetyCheckEvent,
    ToolCallEvent,
    TraceEvent,
)
from collector.replay import (
    _build_children_by_parent,
    _collect_focus_scope_ids,
    _collect_scoped_ancestor_ids,
    _collect_scoped_descendant_ids,
    build_replay,
    build_tree,
    event_is_failure,
    matches_breakpoint,
)


class TestBuildTree:
    """Tests for build_tree function."""

    def test_empty_events_returns_none(self) -> None:
        """Empty event list should return None."""
        assert build_tree([]) is None

    def test_single_event_returns_single_node(self) -> None:
        """Single event without parent should return a single node tree."""
        event = TraceEvent(
            session_id="s1",
            event_type=EventType.TOOL_CALL,
            name="test_tool",
        )
        result = build_tree([event])

        assert result is not None
        assert result["event"]["id"] == event.id
        assert result["children"] == []

    def test_parent_child_relationship(self) -> None:
        """Parent-child relationships should be reflected in tree structure."""
        parent = TraceEvent(
            session_id="s1",
            event_type=EventType.TOOL_CALL,
            name="parent",
        )
        child = TraceEvent(
            session_id="s1",
            parent_id=parent.id,
            event_type=EventType.TOOL_RESULT,
            name="child",
        )

        result = build_tree([parent, child])

        assert result is not None
        assert result["event"]["id"] == parent.id
        assert len(result["children"]) == 1
        assert result["children"][0]["event"]["id"] == child.id

    def test_multiple_roots_create_virtual_root(self) -> None:
        """Multiple root events should create a virtual trace_root node."""
        root1 = TraceEvent(
            session_id="s1",
            event_type=EventType.TOOL_CALL,
            name="root1",
        )
        root2 = TraceEvent(
            session_id="s1",
            event_type=EventType.TOOL_CALL,
            name="root2",
        )

        result = build_tree([root1, root2])

        assert result is not None
        assert result["event"]["event_type"] == "trace_root"
        assert result["event"]["data"]["root_count"] == 2
        assert len(result["children"]) == 2

    def test_virtual_root_timestamp_is_earliest(self) -> None:
        """Virtual root timestamp should be the earliest event timestamp."""
        earlier = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        later = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)

        event1 = TraceEvent(
            session_id="s1",
            event_type=EventType.TOOL_CALL,
            name="event1",
            timestamp=later,
        )
        event2 = TraceEvent(
            session_id="s1",
            event_type=EventType.TOOL_CALL,
            name="event2",
            timestamp=earlier,
        )

        result = build_tree([event1, event2])
        assert result is not None
        assert "2026-01-01T10:00:00+00:00" in result["event"]["timestamp"]


class TestEventIsFailure:
    """Tests for event_is_failure function."""

    def test_error_event_is_failure(self) -> None:
        """ERROR event type should be considered a failure."""
        event = TraceEvent(
            session_id="s1",
            event_type=EventType.ERROR,
            name="error",
        )
        assert event_is_failure(event) is True

    def test_refusal_event_is_failure(self) -> None:
        """REFUSAL event type should be considered a failure."""
        event = TraceEvent(
            session_id="s1",
            event_type=EventType.REFUSAL,
            name="refusal",
        )
        assert event_is_failure(event) is True

    def test_policy_violation_event_is_failure(self) -> None:
        """POLICY_VIOLATION event type should be considered a failure."""
        event = TraceEvent(
            session_id="s1",
            event_type=EventType.POLICY_VIOLATION,
            name="violation",
        )
        assert event_is_failure(event) is True

    def test_safety_check_with_fail_outcome_is_failure(self) -> None:
        """SAFETY_CHECK with non-pass outcome should be considered a failure."""
        event = TraceEvent(
            session_id="s1",
            event_type=EventType.SAFETY_CHECK,
            name="safety",
            data={"outcome": "fail"},
        )
        assert event_is_failure(event) is True

    def test_safety_check_with_pass_outcome_is_not_failure(self) -> None:
        """SAFETY_CHECK with pass outcome should not be considered a failure."""
        event = TraceEvent(
            session_id="s1",
            event_type=EventType.SAFETY_CHECK,
            name="safety",
            data={"outcome": "pass"},
        )
        assert event_is_failure(event) is False

    def test_behavior_alert_is_failure(self) -> None:
        """BEHAVIOR_ALERT event type should be considered a failure."""
        event = TraceEvent(
            session_id="s1",
            event_type=EventType.BEHAVIOR_ALERT,
            name="alert",
        )
        assert event_is_failure(event) is True

    def test_tool_result_with_error_is_failure(self) -> None:
        """TOOL_RESULT with error field should be considered a failure."""
        event = TraceEvent(
            session_id="s1",
            event_type=EventType.TOOL_RESULT,
            name="result",
            data={"error": "Something went wrong"},
        )
        assert event_is_failure(event) is True

    def test_tool_result_without_error_is_not_failure(self) -> None:
        """TOOL_RESULT without error should not be considered a failure."""
        event = TraceEvent(
            session_id="s1",
            event_type=EventType.TOOL_RESULT,
            name="result",
            data={"result": "Success"},
        )
        assert event_is_failure(event) is False

    def test_normal_event_is_not_failure(self) -> None:
        """Normal event types should not be considered failures."""
        event = TraceEvent(
            session_id="s1",
            event_type=EventType.TOOL_CALL,
            name="tool",
        )
        assert event_is_failure(event) is False


class TestMatchesBreakpoint:
    """Tests for matches_breakpoint function."""

    def test_matches_event_type(self) -> None:
        """Should match when event type is in breakpoint set."""
        event = TraceEvent(
            session_id="s1",
            event_type=EventType.ERROR,
            name="error",
        )
        assert (
            matches_breakpoint(
                event, event_types={"error"}, tool_names=set(), confidence_below=None, safety_outcomes=set()
            )
            is True
        )

    def test_does_not_match_event_type(self) -> None:
        """Should not match when event type is not in breakpoint set."""
        event = TraceEvent(
            session_id="s1",
            event_type=EventType.TOOL_CALL,
            name="tool",
        )
        assert (
            matches_breakpoint(
                event, event_types={"error"}, tool_names=set(), confidence_below=None, safety_outcomes=set()
            )
            is False
        )

    def test_matches_tool_name(self) -> None:
        """Should match when tool name is in breakpoint set."""
        event = ToolCallEvent(
            session_id="s1",
            tool_name="search",
            arguments={"q": "test"},
        )
        assert (
            matches_breakpoint(
                event, event_types=set(), tool_names={"search"}, confidence_below=None, safety_outcomes=set()
            )
            is True
        )

    def test_matches_confidence_below_threshold(self) -> None:
        """Should match when confidence is below threshold."""
        event = DecisionEvent(
            session_id="s1",
            reasoning="test reasoning",
            confidence=0.3,
            chosen_action="test_action",
        )
        assert (
            matches_breakpoint(event, event_types=set(), tool_names=set(), confidence_below=0.5, safety_outcomes=set())
            is True
        )

    def test_does_not_match_confidence_above_threshold(self) -> None:
        """Should not match when confidence is above threshold."""
        event = DecisionEvent(
            session_id="s1",
            reasoning="test reasoning",
            confidence=0.8,
            chosen_action="test_action",
        )
        assert (
            matches_breakpoint(event, event_types=set(), tool_names=set(), confidence_below=0.5, safety_outcomes=set())
            is False
        )

    def test_matches_safety_outcome(self) -> None:
        """Should match when safety outcome is in breakpoint set."""
        event = SafetyCheckEvent(
            session_id="s1",
            policy_name="test_policy",
            outcome="fail",
            rationale="test rationale",
        )
        assert (
            matches_breakpoint(
                event, event_types=set(), tool_names=set(), confidence_below=None, safety_outcomes={"fail"}
            )
            is True
        )

    def test_matches_no_criteria_returns_false(self) -> None:
        """Should return False when no criteria match."""
        event = TraceEvent(
            session_id="s1",
            event_type=EventType.TOOL_CALL,
            name="tool",
        )
        assert (
            matches_breakpoint(event, event_types=set(), tool_names=set(), confidence_below=None, safety_outcomes=set())
            is False
        )


class TestBuildChildrenByParent:
    """Tests for _build_children_by_parent helper."""

    def test_builds_parent_to_children_mapping(self) -> None:
        """Should map parent IDs to their children."""
        parent = TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="parent")
        child1 = TraceEvent(session_id="s1", parent_id=parent.id, event_type=EventType.TOOL_RESULT, name="child1")
        child2 = TraceEvent(session_id="s1", parent_id=parent.id, event_type=EventType.TOOL_RESULT, name="child2")

        result = _build_children_by_parent([parent, child1, child2])

        assert parent.id in result
        assert set(result[parent.id]) == {child1.id, child2.id}

    def test_events_without_parent_not_in_mapping(self) -> None:
        """Events without parent_id should not appear as keys."""
        event = TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="root")

        result = _build_children_by_parent([event])

        assert event.id not in result


class TestCollectScopedAncestorIds:
    """Tests for _collect_scoped_ancestor_ids helper."""

    def test_includes_focus_event(self) -> None:
        """Should include the focus event ID."""
        event = TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="focus")
        events = [event]
        event_index = {e.id: i for i, e in enumerate(events)}
        event_by_id = {e.id: e for e in events}

        result = _collect_scoped_ancestor_ids(event.id, event_index=event_index, event_by_id=event_by_id, start_index=0)

        assert event.id in result

    def test_includes_parent_chain(self) -> None:
        """Should include all ancestors via parent_id."""
        grandparent = TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="grandparent")
        parent = TraceEvent(session_id="s1", parent_id=grandparent.id, event_type=EventType.TOOL_CALL, name="parent")
        child = TraceEvent(session_id="s1", parent_id=parent.id, event_type=EventType.TOOL_CALL, name="child")

        events = [grandparent, parent, child]
        event_index = {e.id: i for i, e in enumerate(events)}
        event_by_id = {e.id: e for e in events}

        result = _collect_scoped_ancestor_ids(child.id, event_index=event_index, event_by_id=event_by_id, start_index=0)

        assert child.id in result
        assert parent.id in result
        assert grandparent.id in result

    def test_includes_upstream_events(self) -> None:
        """Should include upstream_event_ids in scope."""
        upstream = TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="upstream")
        focus = TraceEvent(
            session_id="s1",
            event_type=EventType.TOOL_CALL,
            name="focus",
            upstream_event_ids=[upstream.id],
        )

        events = [upstream, focus]
        event_index = {e.id: i for i, e in enumerate(events)}
        event_by_id = {e.id: e for e in events}

        result = _collect_scoped_ancestor_ids(focus.id, event_index=event_index, event_by_id=event_by_id, start_index=0)

        assert focus.id in result
        assert upstream.id in result

    def test_respects_start_index(self) -> None:
        """Should not include events before start_index."""
        early_event = TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="early")
        late_event = TraceEvent(
            session_id="s1",
            parent_id=early_event.id,
            event_type=EventType.TOOL_CALL,
            name="late",
        )

        events = [early_event, late_event]
        event_index = {e.id: i for i, e in enumerate(events)}
        event_by_id = {e.id: e for e in events}

        result = _collect_scoped_ancestor_ids(
            late_event.id, event_index=event_index, event_by_id=event_by_id, start_index=1
        )

        # late_event should be included, but early_event is before start_index
        assert late_event.id in result
        assert early_event.id not in result


class TestCollectScopedDescendantIds:
    """Tests for _collect_scoped_descendant_ids helper."""

    def test_includes_focus_event(self) -> None:
        """Should include the focus event ID."""
        event = TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="focus")
        events = [event]
        event_index = {e.id: i for i, e in enumerate(events)}
        children_by_parent = {}

        result = _collect_scoped_descendant_ids(
            event.id, event_index=event_index, children_by_parent=children_by_parent, start_index=0
        )

        assert event.id in result

    def test_includes_all_descendants(self) -> None:
        """Should include all descendants via parent relationships."""
        root = TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="root")
        child1 = TraceEvent(session_id="s1", parent_id=root.id, event_type=EventType.TOOL_CALL, name="child1")
        child2 = TraceEvent(session_id="s1", parent_id=root.id, event_type=EventType.TOOL_CALL, name="child2")
        grandchild = TraceEvent(session_id="s1", parent_id=child1.id, event_type=EventType.TOOL_CALL, name="grandchild")

        events = [root, child1, child2, grandchild]
        event_index = {e.id: i for i, e in enumerate(events)}
        children_by_parent = _build_children_by_parent(events)

        result = _collect_scoped_descendant_ids(
            root.id, event_index=event_index, children_by_parent=children_by_parent, start_index=0
        )

        # Should include root and all descendants
        assert root.id in result
        assert child1.id in result
        assert child2.id in result
        assert grandchild.id in result

    def test_respects_start_index(self) -> None:
        """Should not include events before start_index."""
        early = TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="early")
        middle = TraceEvent(session_id="s1", parent_id=early.id, event_type=EventType.TOOL_CALL, name="middle")
        late = TraceEvent(session_id="s1", parent_id=middle.id, event_type=EventType.TOOL_CALL, name="late")

        events = [early, middle, late]
        event_index = {e.id: i for i, e in enumerate(events)}
        children_by_parent = _build_children_by_parent(events)

        # Start from middle (index 1) - only events at index 1+ should be included
        result = _collect_scoped_descendant_ids(
            middle.id, event_index=event_index, children_by_parent=children_by_parent, start_index=1
        )

        # middle and late should be included (both at index >= 1)
        assert middle.id in result
        assert late.id in result
        # early is at index 0, so it's excluded
        assert early.id not in result


class TestCollectFocusScopeIds:
    """Tests for _collect_focus_scope_ids integration."""

    def test_includes_focus_and_ancestors_and_descendants(self) -> None:
        """Should include focus event, its ancestors, and descendants."""
        grandparent = TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="grandparent")
        parent = TraceEvent(session_id="s1", parent_id=grandparent.id, event_type=EventType.TOOL_CALL, name="parent")
        focus = TraceEvent(session_id="s1", parent_id=parent.id, event_type=EventType.TOOL_CALL, name="focus")
        child = TraceEvent(session_id="s1", parent_id=focus.id, event_type=EventType.TOOL_CALL, name="child")

        events = [grandparent, parent, focus, child]

        result = _collect_focus_scope_ids(events, focus_event_id=focus.id, start_index=0)

        # Should include the entire branch
        assert grandparent.id in result
        assert parent.id in result
        assert focus.id in result
        assert child.id in result

    def test_invalid_focus_id_returns_all_from_start(self) -> None:
        """Should return all events from start_index when focus_id is invalid."""
        events = [TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name=f"event{i}") for i in range(5)]

        result = _collect_focus_scope_ids(events, focus_event_id="invalid", start_index=2)

        # Should include all events from index 2 onwards
        assert len(result) == 3
        assert events[2].id in result
        assert events[3].id in result
        assert events[4].id in result


class TestBuildReplay:
    """Tests for build_replay function."""

    def test_empty_events_returns_empty_replay(self) -> None:
        """Empty event list should return replay structure with empty lists."""
        result = build_replay([], [], mode="full", focus_event_id=None)

        assert result["mode"] == "full"
        assert result["focus_event_id"] is None
        assert result["start_index"] == 0
        assert result["events"] == []
        assert result["checkpoints"] == []
        assert result["nearest_checkpoint"] is None
        assert result["breakpoints"] == []
        assert result["failure_event_ids"] == []

    def test_full_mode_includes_all_events(self) -> None:
        """Full mode should include all events and checkpoints."""
        events = [TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name=f"tool{i}") for i in range(3)]
        checkpoints = [Checkpoint(session_id="s1", event_id=events[1].id, sequence=1)]

        result = build_replay(events, checkpoints, mode="full", focus_event_id=None)

        assert len(result["events"]) == 3
        assert len(result["checkpoints"]) == 1
        assert result["start_index"] == 0

    def test_identifies_failure_events(self) -> None:
        """Should identify and list failure event IDs."""
        events = [
            TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="tool"),
            TraceEvent(session_id="s1", event_type=EventType.ERROR, name="error"),
            TraceEvent(session_id="s1", event_type=EventType.REFUSAL, name="refusal"),
        ]

        result = build_replay(events, [], mode="full", focus_event_id=None)

        assert len(result["failure_event_ids"]) == 2
        assert events[1].id in result["failure_event_ids"]
        assert events[2].id in result["failure_event_ids"]

    def test_failure_mode_uses_last_failure_as_focus(self) -> None:
        """Failure mode should use the last failure event as focus."""
        events = [
            TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="tool"),
            TraceEvent(session_id="s1", event_type=EventType.ERROR, name="error1"),
            TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="tool2"),
            TraceEvent(session_id="s1", event_type=EventType.ERROR, name="error2"),
        ]

        result = build_replay(events, [], mode="failure", focus_event_id=None)

        # Should focus on the last failure (error2)
        assert result["focus_event_id"] == events[3].id

    def test_finds_nearest_checkpoint_before_focus(self) -> None:
        """Should find the nearest checkpoint at or before the focus index."""
        events = [TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name=f"event{i}") for i in range(5)]
        checkpoints = [
            Checkpoint(session_id="s1", event_id=events[1].id, sequence=1),
            Checkpoint(session_id="s1", event_id=events[3].id, sequence=2),
        ]

        result = build_replay(events, checkpoints, mode="focus", focus_event_id=events[4].id)

        # Nearest checkpoint before index 4 is at index 3
        assert result["nearest_checkpoint"]["event_id"] == events[3].id

    def test_focus_mode_filters_to_focus_branch(self) -> None:
        """Focus mode should filter events to the focus branch."""
        # Create a tree: root -> branch1 -> leaf1, root -> branch2 -> leaf2
        root = TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="root")
        branch1 = TraceEvent(session_id="s1", parent_id=root.id, event_type=EventType.TOOL_CALL, name="branch1")
        leaf1 = TraceEvent(session_id="s1", parent_id=branch1.id, event_type=EventType.TOOL_CALL, name="leaf1")
        branch2 = TraceEvent(session_id="s1", parent_id=root.id, event_type=EventType.TOOL_CALL, name="branch2")
        leaf2 = TraceEvent(session_id="s1", parent_id=branch2.id, event_type=EventType.TOOL_CALL, name="leaf2")

        events = [root, branch1, leaf1, branch2, leaf2]

        result = build_replay(events, [], mode="focus", focus_event_id=leaf2.id)

        # Should only include root, branch2, and leaf2 (not branch1 or leaf1)
        event_ids = {e["id"] for e in result["events"]}
        assert root.id in event_ids
        assert branch2.id in event_ids
        assert leaf2.id in event_ids
        assert branch1.id not in event_ids
        assert leaf1.id not in event_ids

    def test_focus_mode_includes_nearest_checkpoint(self) -> None:
        """Focus mode should include the nearest checkpoint even if not in scope."""
        root = TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="root")
        branch1 = TraceEvent(session_id="s1", parent_id=root.id, event_type=EventType.TOOL_CALL, name="branch1")
        branch2 = TraceEvent(session_id="s1", parent_id=root.id, event_type=EventType.TOOL_CALL, name="branch2")

        events = [root, branch1, branch2]
        # Checkpoint on branch1 (not in focus branch for branch2)
        checkpoint = Checkpoint(session_id="s1", event_id=branch1.id, sequence=1)

        result = build_replay(events, [checkpoint], mode="focus", focus_event_id=branch2.id)

        # Should include the checkpoint from branch1 as nearest
        checkpoint_ids = [cp["id"] for cp in result["checkpoints"]]
        assert checkpoint.id in checkpoint_ids

    def test_respects_checkpoint_start_index(self) -> None:
        """Focus/failure modes should start from checkpoint index."""
        events = [TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name=f"event{i}") for i in range(5)]
        checkpoint = Checkpoint(session_id="s1", event_id=events[2].id, sequence=1)

        result = build_replay(events, [checkpoint], mode="focus", focus_event_id=events[4].id)

        # Start index should be at the checkpoint
        assert result["start_index"] == 2

    def test_identifies_breakpoints_by_event_type(self) -> None:
        """Should identify breakpoints matching event types."""
        events = [
            TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="tool"),
            TraceEvent(session_id="s1", event_type=EventType.ERROR, name="error"),
            TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="tool2"),
        ]

        result = build_replay(
            events,
            [],
            mode="full",
            focus_event_id=None,
            breakpoint_event_types={"error"},
        )

        # Should find one breakpoint (the error)
        assert len(result["breakpoints"]) == 1
        assert result["breakpoints"][0]["id"] == events[1].id

    def test_identifies_breakpoints_by_tool_name(self) -> None:
        """Should identify breakpoints matching tool names."""
        events = [
            ToolCallEvent(
                session_id="s1",
                tool_name="search",
                arguments={"q": "test"},
            ),
            ToolCallEvent(
                session_id="s1",
                tool_name="write",
                arguments={"content": "test"},
            ),
        ]

        result = build_replay(
            events,
            [],
            mode="full",
            focus_event_id=None,
            breakpoint_tool_names={"search"},
        )

        # Should find one breakpoint (the search tool)
        assert len(result["breakpoints"]) == 1
        assert result["breakpoints"][0]["tool_name"] == "search"

    def test_identifies_breakpoints_by_confidence(self) -> None:
        """Should identify breakpoints with confidence below threshold."""
        events = [
            DecisionEvent(
                session_id="s1",
                reasoning="high confidence",
                confidence=0.9,
                chosen_action="action1",
            ),
            DecisionEvent(
                session_id="s1",
                reasoning="low confidence",
                confidence=0.3,
                chosen_action="action2",
            ),
        ]

        result = build_replay(
            events,
            [],
            mode="full",
            focus_event_id=None,
            breakpoint_confidence_below=0.5,
        )

        # Should find one breakpoint (the low confidence decision)
        assert len(result["breakpoints"]) == 1
        assert result["breakpoints"][0]["reasoning"] == "low confidence"

    def test_identifies_breakpoints_by_safety_outcome(self) -> None:
        """Should identify breakpoints matching safety outcomes."""
        events = [
            SafetyCheckEvent(
                session_id="s1",
                policy_name="policy1",
                outcome="pass",
                rationale="safe",
            ),
            SafetyCheckEvent(
                session_id="s1",
                policy_name="policy2",
                outcome="fail",
                rationale="unsafe",
            ),
        ]

        result = build_replay(
            events,
            [],
            mode="full",
            focus_event_id=None,
            breakpoint_safety_outcomes={"fail"},
        )

        # Should find one breakpoint (the failed safety check)
        assert len(result["breakpoints"]) == 1
        assert result["breakpoints"][0]["policy_name"] == "policy2"

    def test_breakpoints_in_replay_window_only(self) -> None:
        """Breakpoints should only be identified in the replay window."""
        events = [
            TraceEvent(session_id="s1", event_type=EventType.ERROR, name="error1"),
            TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="tool"),
            TraceEvent(session_id="s1", event_type=EventType.ERROR, name="error2"),
        ]
        checkpoint = Checkpoint(session_id="s1", event_id=events[1].id, sequence=1)

        result = build_replay(
            events,
            [checkpoint],
            mode="focus",
            focus_event_id=events[2].id,
            breakpoint_event_types={"error"},
        )

        # Only error2 should be a breakpoint (error1 is before the checkpoint)
        assert len(result["breakpoints"]) == 1
        assert result["breakpoints"][0]["name"] == "error2"

    def test_breakpoints_follow_filtered_focus_scope(self) -> None:
        """Focus replays should only return breakpoint hits inside the visible branch."""
        root = TraceEvent(session_id="s1", event_type=EventType.TOOL_CALL, name="root")
        branch1 = TraceEvent(session_id="s1", parent_id=root.id, event_type=EventType.TOOL_CALL, name="branch1")
        branch1_error = TraceEvent(session_id="s1", parent_id=branch1.id, event_type=EventType.ERROR, name="error1")
        branch2 = TraceEvent(session_id="s1", parent_id=root.id, event_type=EventType.TOOL_CALL, name="branch2")
        branch2_error = TraceEvent(session_id="s1", parent_id=branch2.id, event_type=EventType.ERROR, name="error2")

        result = build_replay(
            [root, branch1, branch1_error, branch2, branch2_error],
            [],
            mode="focus",
            focus_event_id=branch2_error.id,
            breakpoint_event_types={"error"},
        )

        assert [event["id"] for event in result["events"]] == [root.id, branch2.id, branch2_error.id]
        assert [event["id"] for event in result["breakpoints"]] == [branch2_error.id]
