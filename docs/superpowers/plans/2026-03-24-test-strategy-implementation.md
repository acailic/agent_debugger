# Test Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Comprehensive test suite overhaul to make the codebase robust and professional

**Architecture:** Fix syntax errors in existing test files, add comprehensive SDK events package tests, complete adaptive intelligence and benchmark coverage, and add CI regression tests

**Tech Stack:** Python 3.10+, pytest, pytest-asyncio, unittest.mock

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_events_package.py` | Create | SDK events package comprehensive tests |
| `tests/test_replay_depth_l3.py` | Fix | Syntax error fixes (line 175) |
| `tests/test_adaptive_intelligence.py` | Expand | Add edge cases |
| `tests/test_benchmarks.py` | Expand | Add property-based tests |
| `tests/test_regressions.py` | Create | CI regression tests |

---

## Task 1: Fix test_replay_depth_l3.py Syntax Error

**Files:**
- Modify: `tests/test_replay_depth_l3.py:175`

**Issue:** Line 175 has `pytest.skip(...)` followed immediately by `def test_...` without newline

- [ ] **Step 1: Fix the syntax error**

Find line 175 which looks like:
```python
        except ImportError as e:
            pytest.skip(f"Hook integration not yet implemented: {e}")    def test_langchain_restore_hook_exists(self):
```

Change to:
```python
        except ImportError as e:
            pytest.skip(f"Hook integration not yet implemented: {e}")


class TestStateDriftDetection:
    """Tests for detecting when restored execution diverges from original."""

    def test_langchain_restore_hook_exists(self):
```

Note: Looking at the file, there's a duplicate section starting at line 175. The `TestStateDriftDetection` class header is missing, and the tests from 175-313 are duplicates of earlier tests. This needs cleanup.

- [ ] **Step 2: Verify syntax fix**

Run: `python3 -c "import ast; ast.parse(open('tests/test_replay_depth_l3.py').read())"`
Expected: No output (success)

- [ ] **Step 3: Run the test file**

Run: `python3 -m pytest tests/test_replay_depth_l3.py -v --tb=short`
Expected: Tests run (some may skip due to unimplemented features)

- [ ] **Step 4: Commit**

```bash
git add tests/test_replay_depth_l3.py
git commit -m "fix: resolve syntax error in test_replay_depth_l3.py"
```

---

## Task 2: Create SDK Events Package Tests

**Files:**
- Create: `tests/test_events_package.py`
- Reference: `agent_debugger_sdk/core/events/__init__.py`
- Reference: `agent_debugger_sdk/core/events/base.py`
- Reference: `agent_debugger_sdk/core/events/registry.py`

- [ ] **Step 1: Write test file header and imports**

```python
"""Comprehensive tests for agent_debugger_sdk.core.events package.

Covers:
- All 13 event types with specific field validation
- EventType registry lazy loading
- Event serialization/deserialization
- Event hierarchy and inheritance
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from agent_debugger_sdk.core.events import (
    AgentTurnEvent,
    BehaviorAlertEvent,
    Checkpoint,
    DecisionEvent,
    ErrorEvent,
    EVENT_TYPE_REGISTRY,
    EventType,
    LLMRequestEvent,
    LLMResponseEvent,
    PolicyViolationEvent,
    PromptPolicyEvent,
    RefusalEvent,
    RiskLevel,
    SafetyCheckEvent,
    SafetyOutcome,
    Session,
    SessionStatus,
    ToolCallEvent,
    ToolResultEvent,
    TraceEvent,
)
```

- [ ] **Step 2: Write TestEventTypeRegistry class**

```python
class TestEventTypeRegistry:
    """Tests for EVENT_TYPE_REGISTRY behavior."""

    def test_registry_has_all_event_types(self):
        """Registry should contain all defined EventType values."""
        expected_types = {
            EventType.TOOL_CALL,
            EventType.TOOL_RESULT,
            EventType.LLM_REQUEST,
            EventType.LLM_RESPONSE,
            EventType.DECISION,
            EventType.SAFETY_CHECK,
            EventType.REFUSAL,
            EventType.POLICY_VIOLATION,
            EventType.PROMPT_POLICY,
            EventType.AGENT_TURN,
            EventType.BEHAVIOR_ALERT,
            EventType.ERROR,
        }

        for event_type in expected_types:
            assert event_type in EVENT_TYPE_REGISTRY, f"{event_type} missing from registry"

    def test_registry_returns_correct_class_for_tool_call(self):
        """Registry should return ToolCallEvent for TOOL_CALL type."""
        event_cls = EVENT_TYPE_REGISTRY[EventType.TOOL_CALL]
        assert event_cls is ToolCallEvent

    def test_registry_returns_correct_class_for_decision(self):
        """Registry should return DecisionEvent for DECISION type."""
        event_cls = EVENT_TYPE_REGISTRY[EventType.DECISION]
        assert event_cls is DecisionEvent

    def test_registry_returns_correct_class_for_safety_check(self):
        """Registry should return SafetyCheckEvent for SAFETY_CHECK type."""
        event_cls = EVENT_TYPE_REGISTRY[EventType.SAFETY_CHECK]
        assert event_cls is SafetyCheckEvent

    def test_registry_lazy_loading_works(self):
        """Registry should lazy-load event classes on first access."""
        # This test verifies the _EventTypeRegistry.__missing__ behavior
        # by accessing a type that hasn't been accessed yet
        event_cls = EVENT_TYPE_REGISTRY[EventType.REFUSAL]
        assert event_cls is RefusalEvent
```

- [ ] **Step 3: Write TestEventTypes class for all 13 event types**

```python
class TestEventTypes:
    """Tests for all event type classes."""

    def test_tool_call_event_fields(self):
        """ToolCallEvent should have required fields."""
        event = ToolCallEvent(
            id="test-1",
            session_id="session-1",
            tool_name="search",
            arguments={"query": "test"},
        )
        assert event.tool_name == "search"
        assert event.arguments == {"query": "test"}
        assert event.event_type == EventType.TOOL_CALL

    def test_tool_result_event_fields(self):
        """ToolResultEvent should have result or error fields."""
        event = ToolResultEvent(
            id="test-2",
            session_id="session-1",
            tool_name="search",
            result="found",
        )
        assert event.result == "found"
        assert event.error is None

    def test_tool_result_event_with_error(self):
        """ToolResultEvent should accept error field."""
        event = ToolResultEvent(
            id="test-3",
            session_id="session-1",
            tool_name="search",
            error="timeout",
        )
        assert event.error == "timeout"
        assert event.result is None

    def test_llm_request_event_fields(self):
        """LLMRequestEvent should have model and messages."""
        event = LLMRequestEvent(
            id="test-4",
            session_id="session-1",
            model="gpt-4",
            messages=[{"role": "user", "content": "hello"}],
        )
        assert event.model == "gpt-4"
        assert len(event.messages) == 1

    def test_llm_response_event_fields(self):
        """LLMResponseEvent should have content and optional cost."""
        event = LLMResponseEvent(
            id="test-5",
            session_id="session-1",
            model="gpt-4",
            content="response text",
            cost_usd=0.01,
        )
        assert event.content == "response text"
        assert event.cost_usd == 0.01

    def test_decision_event_fields(self):
        """DecisionEvent should have reasoning and confidence."""
        event = DecisionEvent(
            id="test-6",
            session_id="session-1",
            chosen_action="proceed",
            confidence=0.85,
            evidence=[{"source": "tool", "content": "data"}],
        )
        assert event.chosen_action == "proceed"
        assert event.confidence == 0.85

    def test_safety_check_event_fields(self):
        """SafetyCheckEvent should have outcome and risk_level."""
        event = SafetyCheckEvent(
            id="test-7",
            session_id="session-1",
            policy_name="content-policy",
            outcome="pass",
            risk_level="low",
            rationale="No issues detected",
        )
        assert event.outcome == "pass"
        assert event.risk_level == "low"

    def test_refusal_event_fields(self):
        """RefusalEvent should have reason and optional blocked_action."""
        event = RefusalEvent(
            id="test-8",
            session_id="session-1",
            reason="Unsafe action",
            policy_name="safety-policy",
            risk_level="high",
            blocked_action="execute_command",
        )
        assert event.reason == "Unsafe action"
        assert event.blocked_action == "execute_command"

    def test_policy_violation_event_fields(self):
        """PolicyViolationEvent should have violation_type and severity."""
        event = PolicyViolationEvent(
            id="test-9",
            session_id="session-1",
            policy_name="content-policy",
            violation_type="pii_detected",
            severity="critical",
            details={"field": "email"},
        )
        assert event.violation_type == "pii_detected"
        assert event.severity == "critical"

    def test_prompt_policy_event_fields(self):
        """PromptPolicyEvent should have template_id and parameters."""
        event = PromptPolicyEvent(
            id="test-10",
            session_id="session-1",
            template_id="router-v3",
            policy_parameters={"strictness": "high"},
            speaker="system",
            state_summary="Routing mode",
            goal="Select best response",
        )
        assert event.template_id == "router-v3"
        assert event.speaker == "system"

    def test_agent_turn_event_fields(self):
        """AgentTurnEvent should have agent_id and turn_index."""
        event = AgentTurnEvent(
            id="test-11",
            session_id="session-1",
            agent_id="planner",
            speaker="planner",
            turn_index=1,
            turn_goal="Analyze request",
        )
        assert event.agent_id == "planner"
        assert event.turn_index == 1

    def test_behavior_alert_event_fields(self):
        """BehaviorAlertEvent should have alert_type and severity."""
        event = BehaviorAlertEvent(
            id="test-12",
            session_id="session-1",
            alert_type="tool_loop",
            severity="high",
            signal="Tool 'search' called 3 times with same arguments",
        )
        assert event.alert_type == "tool_loop"
        assert event.severity == "high"

    def test_error_event_fields(self):
        """ErrorEvent should have error_type and error_message."""
        event = ErrorEvent(
            id="test-13",
            session_id="session-1",
            error_type="ValueError",
            error_message="Invalid input",
        )
        assert event.error_type == "ValueError"
        assert event.error_message == "Invalid input"
```

- [ ] **Step 4: Write TestEventSerialization class**

```python
class TestEventSerialization:
    """Tests for event serialization and deserialization."""

    def test_to_dict_includes_all_fields(self):
        """to_dict should include all event fields."""
        event = ToolCallEvent(
            id="serial-1",
            session_id="session-1",
            tool_name="search",
            arguments={"q": "test"},
        )
        data = event.to_dict()

        assert data["id"] == "serial-1"
        assert data["session_id"] == "session-1"
        assert data["tool_name"] == "search"
        assert data["arguments"] == {"q": "test"}
        assert data["event_type"] == EventType.TOOL_CALL

    def test_from_dict_reconstructs_event(self):
        """from_dict should reconstruct an event from dict."""
        original = DecisionEvent(
            id="serial-2",
            session_id="session-1",
            chosen_action="proceed",
            confidence=0.9,
            evidence=[],
        )
        data = original.to_dict()
        reconstructed = TraceEvent.from_dict(data)

        assert reconstructed.id == original.id
        assert reconstructed.session_id == original.session_id

    def test_timestamp_serialization_preserves_isoformat(self):
        """Timestamp should serialize to ISO format string."""
        ts = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        event = TraceEvent(id="ts-1", timestamp=ts)
        data = event.to_dict()

        assert "2026-03-24T12:00:00" in data["timestamp"]

    def test_timestamp_deserialization_from_isoformat(self):
        """from_dict should parse ISO format timestamp."""
        data = {
            "id": "ts-2",
            "timestamp": "2026-03-24T12:00:00+00:00",
            "event_type": "agent_start",
        }
        event = TraceEvent.from_dict(data)

        assert event.timestamp.year == 2026
        assert event.timestamp.month == 3
        assert event.timestamp.day == 24

    def test_event_type_serialization(self):
        """EventType enum should serialize to string."""
        event = TraceEvent(id="et-1", event_type=EventType.DECISION)
        data = event.to_dict()

        assert data["event_type"] == "decision"

    def test_event_type_deserialization(self):
        """from_dict should parse event_type string to enum."""
        data = {"id": "et-2", "event_type": "tool_call"}
        event = TraceEvent.from_dict(data)

        assert event.event_type == EventType.TOOL_CALL

    def test_nested_data_serialization(self):
        """Nested dicts and lists in data should serialize correctly."""
        event = TraceEvent(
            id="nested-1",
            data={
                "items": [1, 2, 3],
                "nested": {"key": "value"},
            },
        )
        data = event.to_dict()

        assert data["data"]["items"] == [1, 2, 3]
        assert data["data"]["nested"]["key"] == "value"
```

- [ ] **Step 5: Write TestEventHierarchy class**

```python
class TestEventHierarchy:
    """Tests for event inheritance patterns."""

    def test_all_events_inherit_from_trace_event(self):
        """All event classes should inherit from TraceEvent."""
        event_classes = [
            ToolCallEvent,
            ToolResultEvent,
            LLMRequestEvent,
            LLMResponseEvent,
            DecisionEvent,
            SafetyCheckEvent,
            RefusalEvent,
            PolicyViolationEvent,
            PromptPolicyEvent,
            AgentTurnEvent,
            BehaviorAlertEvent,
            ErrorEvent,
        ]

        for cls in event_classes:
            assert issubclass(cls, TraceEvent), f"{cls.__name__} should inherit from TraceEvent"

    def test_trace_event_has_base_fields(self):
        """TraceEvent should have all base fields."""
        event = TraceEvent(id="base-1")
        assert hasattr(event, "id")
        assert hasattr(event, "session_id")
        assert hasattr(event, "parent_id")
        assert hasattr(event, "event_type")
        assert hasattr(event, "timestamp")
        assert hasattr(event, "name")
        assert hasattr(event, "data")
        assert hasattr(event, "metadata")
        assert hasattr(event, "importance")

    def test_event_parent_chain(self):
        """Events should support parent_id for hierarchy."""
        parent = TraceEvent(id="parent-1")
        child = TraceEvent(id="child-1", parent_id=parent.id)

        assert child.parent_id == parent.id

    def test_upstream_event_ids(self):
        """Events should track upstream dependencies."""
        event = TraceEvent(
            id="upstream-1",
            upstream_event_ids=["evt-1", "evt-2"],
        )

        assert event.upstream_event_ids == ["evt-1", "evt-2"]

    def test_typed_field_names_excludes_base(self):
        """_typed_field_names should only return event-specific fields."""
        typed_fields = ToolCallEvent._typed_field_names()

        assert "tool_name" in typed_fields
        assert "arguments" in typed_fields
        assert "id" not in typed_fields  # base field
        assert "session_id" not in typed_fields  # base field
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_events_package.py -v`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add tests/test_events_package.py
git commit -m "test: add comprehensive SDK events package tests"
```

---

## Task 3: Expand Adaptive Intelligence Tests

**Files:**
- Modify: `tests/test_adaptive_intelligence.py`

- [ ] **Step 1: Add edge case tests for clustering**

Add to the file after the existing `TestRetentionTierAssignment` class:

```python
class TestClusteringEdgeCases:
    """Edge case tests for failure clustering."""

    @pytest.fixture
    def intelligence(self) -> TraceIntelligence:
        return TraceIntelligence()

    def test_single_failure_creates_cluster(self, intelligence: TraceIntelligence, make_trace_event):
        """Single failure should create a cluster of size 1."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            make_trace_event(
                id="start-1",
                session_id="session-1",
                event_type=EventType.AGENT_START,
                timestamp=timestamp,
            ),
            ErrorEvent(
                id="error-1",
                session_id="session-1",
                error_type="ValueError",
                error_message="Single error",
                timestamp=timestamp,
            ),
        ]
        analysis = intelligence.analyze_session(events, [])

        assert len(analysis["failure_clusters"]) == 1
        assert analysis["failure_clusters"][0]["count"] == 1

    def test_identical_errors_same_fingerprint(self, intelligence: TraceIntelligence, make_trace_event):
        """Identical errors should have the same fingerprint."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        error1 = ErrorEvent(
            id="error-1",
            session_id="session-1",
            error_type="ConnectionError",
            error_message="Failed to connect",
            timestamp=timestamp,
        )
        error2 = ErrorEvent(
            id="error-2",
            session_id="session-1",
            error_type="ConnectionError",
            error_message="Failed to connect",
            timestamp=timestamp,
        )

        fp1 = intelligence.fingerprint(error1)
        fp2 = intelligence.fingerprint(error2)

        assert fp1 == fp2

    def test_different_errors_different_fingerprint(self, intelligence: TraceIntelligence, make_trace_event):
        """Different error types should have different fingerprints."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=timezone.utc)
        error1 = ErrorEvent(
            id="error-1",
            session_id="session-1",
            error_type="ValueError",
            error_message="Error",
            timestamp=timestamp,
        )
        error2 = ErrorEvent(
            id="error-2",
            session_id="session-1",
            error_type="TypeError",
            error_message="Error",
            timestamp=timestamp,
        )

        fp1 = intelligence.fingerprint(error1)
        fp2 = intelligence.fingerprint(error2)

        assert fp1 != fp2
```

- [ ] **Step 2: Add tests for retention tier edge cases**

```python
class TestRetentionTierEdgeCases:
    """Edge case tests for retention tier assignment."""

    @pytest.fixture
    def intelligence(self) -> TraceIntelligence:
        return TraceIntelligence()

    def test_replay_value_exactly_at_threshold(self, intelligence: TraceIntelligence):
        """Retention tier should handle exact threshold values."""
        # Full retention threshold is 0.72
        tier = intelligence.retention_tier(
            replay_value=0.72,
            high_severity_count=0,
            failure_cluster_count=0,
            behavior_alert_count=0,
        )
        assert tier == "full"

        # Just below full threshold
        tier = intelligence.retention_tier(
            replay_value=0.71,
            high_severity_count=0,
            failure_cluster_count=0,
            behavior_alert_count=0,
        )
        assert tier == "summarized"

    def test_multiple_conditions_trigger_full_retention(self, intelligence: TraceIntelligence):
        """Multiple conditions should all trigger full retention."""
        # High severity
        tier = intelligence.retention_tier(
            replay_value=0.1,
            high_severity_count=1,
            failure_cluster_count=0,
            behavior_alert_count=0,
        )
        assert tier == "full"

        # Multiple failure clusters
        tier = intelligence.retention_tier(
            replay_value=0.1,
            high_severity_count=0,
            failure_cluster_count=2,
            behavior_alert_count=0,
        )
        assert tier == "full"

    def test_zero_replay_value_gets_downsampled(self, intelligence: TraceIntelligence):
        """Zero replay value should result in downsampled tier."""
        tier = intelligence.retention_tier(
            replay_value=0.0,
            high_severity_count=0,
            failure_cluster_count=0,
            behavior_alert_count=0,
        )
        assert tier == "downsampled"
```

- [ ] **Step 3: Run tests to verify**

Run: `python3 -m pytest tests/test_adaptive_intelligence.py -v -k "EdgeCase"`
Expected: All edge case tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_adaptive_intelligence.py
git commit -m "test: add edge cases for adaptive intelligence tests"
```

---

## Task 4: Expand Benchmark Tests

**Files:**
- Modify: `tests/test_benchmarks.py`

- [ ] **Step 1: Add property-based tests for event generation**

Add after the existing test classes:

```python
class TestBenchmarkConsistency:
    """Tests for benchmark consistency and determinism."""

    @pytest.mark.asyncio
    async def test_same_scenario_produces_consistent_event_count(self):
        """Running same scenario twice should produce same number of events."""
        session1 = await run_prompt_injection_session("consistency-a")
        session2 = await run_prompt_injection_session("consistency-b")

        assert len(session1.events) == len(session2.events)

    @pytest.mark.asyncio
    async def test_same_scenario_produces_consistent_event_types(self):
        """Running same scenario twice should produce same event types in order."""
        session1 = await run_prompt_injection_session("types-a")
        session2 = await run_prompt_injection_session("types-b")

        types1 = [e.event_type.value for e in session1.events]
        types2 = [e.event_type.value for e in session2.events]

        assert types1 == types2

    @pytest.mark.asyncio
    async def test_all_scenarios_have_valid_session_ids(self):
        """All scenarios should have non-empty session IDs."""
        scenarios = iter_seed_scenarios()

        for name, runner in scenarios:
            session = await runner(f"valid-{name}")
            assert session.session_id is not None
            assert len(session.session_id) > 0

    @pytest.mark.asyncio
    async def test_all_scenarios_have_events(self):
        """All scenarios should produce at least one event."""
        scenarios = iter_seed_scenarios()

        for name, runner in scenarios:
            session = await runner(f"events-{name}")
            assert len(session.events) > 0, f"{name} produced no events"


class TestBenchmarkEventLinkage:
    """Tests for event linkage in benchmark scenarios."""

    @pytest.mark.asyncio
    async def test_evidence_grounding_links_tool_result_to_decision(self):
        """Decision should reference tool result as evidence."""
        session = await run_evidence_grounding_session("linkage-evidence")

        tool_result = next(
            e for e in session.events if e.event_type.value == "tool_result"
        )
        decision = next(
            e for e in session.events if e.event_type.value == "decision"
        )

        assert tool_result.id in decision.upstream_event_ids

    @pytest.mark.asyncio
    async def test_policy_shift_maintains_parent_chain(self):
        """Policy shift should maintain proper parent chain."""
        session = await run_prompt_policy_shift_session("linkage-policy")

        llm_response = next(
            e for e in session.events if e.event_type.value == "llm_response"
        )
        llm_request = next(
            e for e in session.events if e.event_type.value == "llm_request"
        )

        # Response should be child of request
        assert llm_response.parent_id == llm_request.id

    @pytest.mark.asyncio
    async def test_looping_behavior_has_parent_chain(self):
        """Looping behavior tool calls should form a parent chain."""
        session = await run_looping_behavior_session("linkage-loop")

        tool_calls = [
            e for e in session.events if e.event_type.value == "tool_call"
        ]

        # Second call should have first as parent
        assert tool_calls[1].parent_id == tool_calls[0].id
        # Third call should have second as parent
        assert tool_calls[2].parent_id == tool_calls[1].id
```

- [ ] **Step 2: Run tests to verify**

Run: `python3 -m pytest tests/test_benchmarks.py -v -k "Consistency or Linkage"`
Expected: All new tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_benchmarks.py
git commit -m "test: add consistency and linkage tests for benchmarks"
```

---

## Task 5: Create CI Regression Tests

**Files:**
- Create: `tests/test_regressions.py`

- [ ] **Step 1: Create regression test file**

```python
"""Regression tests to catch known issues early in CI.

These tests validate critical flows and known issue patterns.
They should be fast (< 30 seconds total) and run on every PR.
"""

from __future__ import annotations

import pytest


class TestSDKImports:
    """Tests that SDK imports work correctly."""

    def test_import_main_sdk_module(self):
        """Main SDK module should import without error."""
        import agent_debugger_sdk
        assert agent_debugger_sdk is not None

    def test_import_events_package(self):
        """Events package should import all event types."""
        from agent_debugger_sdk.core.events import (
            AgentTurnEvent,
            BehaviorAlertEvent,
            Checkpoint,
            DecisionEvent,
            ErrorEvent,
            EVENT_TYPE_REGISTRY,
            EventType,
            LLMRequestEvent,
            LLMResponseEvent,
            PolicyViolationEvent,
            PromptPolicyEvent,
            RefusalEvent,
            SafetyCheckEvent,
            Session,
            ToolCallEvent,
            ToolResultEvent,
            TraceEvent,
        )
        assert TraceEvent is not None

    def test_import_checkpoint_module(self):
        """Checkpoint module should import correctly."""
        from agent_debugger_sdk.checkpoints import (
            BaseCheckpointState,
            CustomCheckpointState,
            LangChainCheckpointState,
        )
        assert BaseCheckpointState is not None

    def test_import_config_module(self):
        """Config module should import correctly."""
        from agent_debugger_sdk.config import get_config
        assert callable(get_config)

    def test_no_import_cycles(self):
        """There should be no import cycles in SDK."""
        # This test passes if import succeeds without RecursionError
        import agent_debugger_sdk
        from agent_debugger_sdk.core import events
        from agent_debugger_sdk.checkpoints import states
        from agent_debugger_sdk.auto_patch import registry

        assert all([
            agent_debugger_sdk is not None,
            events is not None,
            states is not None,
            registry is not None,
        ])


class TestEventSerialization:
    """Tests for event serialization regressions."""

    def test_event_to_dict_json_serializable(self):
        """Event to_dict output should be JSON serializable."""
        import json
        from agent_debugger_sdk.core.events import ToolCallEvent

        event = ToolCallEvent(
            id="test-1",
            session_id="session-1",
            tool_name="search",
            arguments={"query": "test"},
        )
        data = event.to_dict()

        # Should not raise
        json_str = json.dumps(data)
        assert json_str is not None

    def test_event_from_dict_round_trip(self):
        """Event should survive from_dict(to_dict()) round trip."""
        from agent_debugger_sdk.core.events import TraceEvent, EventType

        original = TraceEvent(
            id="round-trip-1",
            session_id="session-1",
            event_type=EventType.DECISION,
            name="test",
        )
        data = original.to_dict()
        restored = TraceEvent.from_dict(data)

        assert restored.id == original.id
        assert restored.session_id == original.session_id
        assert restored.event_type == original.event_type


class TestEventTypeRegistry:
    """Tests for event type registry regressions."""

    def test_registry_complete(self):
        """Registry should contain all event types."""
        from agent_debugger_sdk.core.events import EVENT_TYPE_REGISTRY, EventType

        expected = {
            EventType.TOOL_CALL,
            EventType.TOOL_RESULT,
            EventType.LLM_REQUEST,
            EventType.LLM_RESPONSE,
            EventType.DECISION,
            EventType.SAFETY_CHECK,
            EventType.REFUSAL,
            EventType.POLICY_VIOLATION,
            EventType.PROMPT_POLICY,
            EventType.AGENT_TURN,
            EventType.BEHAVIOR_ALERT,
            EventType.ERROR,
        }

        for et in expected:
            assert et in EVENT_TYPE_REGISTRY, f"{et} missing from registry"

    def test_registry_returns_correct_classes(self):
        """Registry should return correct class for each type."""
        from agent_debugger_sdk.core.events import (
            EVENT_TYPE_REGISTRY,
            EventType,
            ToolCallEvent,
            DecisionEvent,
            ErrorEvent,
        )

        assert EVENT_TYPE_REGISTRY[EventType.TOOL_CALL] is ToolCallEvent
        assert EVENT_TYPE_REGISTRY[EventType.DECISION] is DecisionEvent
        assert EVENT_TYPE_REGISTRY[EventType.ERROR] is ErrorEvent


class TestAPIContractBasics:
    """Basic API contract tests to catch contract regressions."""

    def test_session_schema_has_required_fields(self):
        """Session schema should have required fields."""
        from agent_debugger_sdk.core.events import Session

        # Check class has expected fields
        assert hasattr(Session, "__dataclass_fields__")
        fields = Session.__dataclass_fields__
        assert "id" in fields
        assert "agent_name" in fields
        assert "framework" in fields

    def test_checkpoint_schema_has_required_fields(self):
        """Checkpoint schema should have required fields."""
        from agent_debugger_sdk.core.events import Checkpoint

        assert hasattr(Checkpoint, "__dataclass_fields__")
        fields = Checkpoint.__dataclass_fields__
        assert "id" in fields
        assert "session_id" in fields
        assert "event_id" in fields


class TestKnownIssuePatterns:
    """Tests for known issue patterns to prevent regressions."""

    def test_no_duplicate_event_ids_in_benchmark(self):
        """Benchmark scenarios should not produce duplicate event IDs."""
        import asyncio
        from benchmarks import run_prompt_injection_session

        async def check():
            session = await run_prompt_injection_session("no-dup")
            ids = [e.id for e in session.events]
            assert len(ids) == len(set(ids)), "Duplicate event IDs found"

        asyncio.run(check())

    def test_event_type_enum_values_are_strings(self):
        """EventType enum values should be strings for JSON serialization."""
        from agent_debugger_sdk.core.events import EventType

        for et in EventType:
            assert isinstance(et.value, str), f"{et} value is not a string"
```

- [ ] **Step 2: Run tests to verify**

Run: `python3 -m pytest tests/test_regressions.py -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_regressions.py
git commit -m "test: add CI regression tests for critical flows"
```

---

## Task 6: Final Validation

- [ ] **Step 1: Run full test suite**

Run: `python3 -m pytest -q`
Expected: All tests pass (or known skips)

- [ ] **Step 2: Check syntax of all test files**

Run: `python3 -m py_compile tests/test_events_package.py tests/test_replay_depth_l3.py tests/test_regressions.py`
Expected: No output (success)

- [ ] **Step 3: Run linter**

Run: `ruff check tests/`
Expected: No errors

- [ ] **Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "chore: final validation fixes for test suite"
```

---

## Summary

| Task | File | Action | Estimated Time |
|------|------|--------|----------------|
| 1 | `test_replay_depth_l3.py` | Fix syntax | 10 min |
| 2 | `test_events_package.py` | Create | 45 min |
| 3 | `test_adaptive_intelligence.py` | Expand | 20 min |
| 4 | `test_benchmarks.py` | Expand | 15 min |
| 5 | `test_regressions.py` | Create | 20 min |
| 6 | All | Validate | 10 min |

**Total Estimated Time:** ~2 hours

**Dependencies:** None (uses existing pytest infrastructure)
