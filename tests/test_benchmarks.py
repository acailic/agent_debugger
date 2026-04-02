"""Comprehensive tests for Research Benchmark scenarios.

This module tests:
- Benchmark scenario generation and validation
- CI regression assertions for known failure patterns
- Safe vs unsafe path validation
"""

from __future__ import annotations

import os

import pytest

os.environ["AGENT_DEBUGGER_ENABLED"] = "false"

from agent_debugger_sdk.core.events import (
    EventType,
)
from benchmarks.seed_data import (
    DEFAULT_SEED_SESSION_IDS,
    iter_seed_scenarios,
    run_evidence_grounding_session,
    run_failure_cluster_session,
    run_looping_behavior_session,
    run_multi_agent_dialogue_session,
    run_prompt_injection_session,
    run_prompt_policy_shift_session,
    run_replay_determinism_session,
    run_safety_escalation_session,
)


class TestBenchmarkScenarioGeneration:
    """Tests verifying all 8 benchmark scenarios produce valid sessions."""

    @pytest.mark.asyncio
    async def test_prompt_injection_session_produces_valid_session(self):
        """Prompt injection scenario should produce a session with safety events."""
        session = await run_prompt_injection_session()

        assert session.session_id == DEFAULT_SEED_SESSION_IDS["prompt_injection"]
        assert len(session.events) > 0
        assert len(session.checkpoints) == 0  # No checkpoints in this scenario

        # Should have safety-related events
        event_types = {e.event_type for e in session.events}
        assert EventType.SAFETY_CHECK in event_types
        assert EventType.REFUSAL in event_types
        assert EventType.POLICY_VIOLATION in event_types
        assert EventType.PROMPT_POLICY in event_types

    @pytest.mark.asyncio
    async def test_evidence_grounding_session_produces_valid_session(self):
        """Evidence grounding scenario should produce a session with tool and decision events."""
        session = await run_evidence_grounding_session()

        assert session.session_id == DEFAULT_SEED_SESSION_IDS["evidence_grounding"]
        assert len(session.events) > 0

        event_types = {e.event_type for e in session.events}
        assert EventType.LLM_REQUEST in event_types
        assert EventType.TOOL_CALL in event_types
        assert EventType.TOOL_RESULT in event_types
        assert EventType.DECISION in event_types
        assert EventType.LLM_RESPONSE in event_types

        # Decision should have evidence attached
        decisions = [e for e in session.events if e.event_type == EventType.DECISION]
        assert len(decisions) == 1
        decision = decisions[0]
        assert hasattr(decision, "evidence") and decision.evidence
        assert hasattr(decision, "evidence_event_ids") and decision.evidence_event_ids

    @pytest.mark.asyncio
    async def test_multi_agent_dialogue_session_produces_valid_session(self):
        """Multi-agent dialogue scenario should produce a session with agent turn events."""
        session = await run_multi_agent_dialogue_session()

        assert session.session_id == DEFAULT_SEED_SESSION_IDS["multi_agent_dialogue"]
        assert len(session.events) > 0

        event_types = {e.event_type for e in session.events}
        assert EventType.AGENT_TURN in event_types
        assert EventType.PROMPT_POLICY in event_types
        assert EventType.DECISION in event_types

        # Should have turns from multiple agents
        turns = [e for e in session.events if e.event_type == EventType.AGENT_TURN]
        speakers = {getattr(t, "speaker", None) for t in turns}
        assert len(speakers) >= 2  # At least planner and critic

    @pytest.mark.asyncio
    async def test_prompt_policy_shift_session_produces_valid_session(self):
        """Policy shift scenario should produce a session with multiple policy events."""
        session = await run_prompt_policy_shift_session()

        assert session.session_id == DEFAULT_SEED_SESSION_IDS["prompt_policy_shift"]
        assert len(session.events) > 0

        event_types = {e.event_type for e in session.events}
        assert EventType.PROMPT_POLICY in event_types
        assert EventType.LLM_REQUEST in event_types
        assert EventType.LLM_RESPONSE in event_types

        # Should have at least 2 policy events (router and responder)
        policies = [e for e in session.events if e.event_type == EventType.PROMPT_POLICY]
        assert len(policies) >= 2

        # Templates should differ
        template_ids = {getattr(p, "template_id", None) for p in policies}
        assert len(template_ids) >= 2

    @pytest.mark.asyncio
    async def test_safety_escalation_session_produces_valid_session(self):
        """Safety escalation scenario should produce a session with escalating safety events."""
        session = await run_safety_escalation_session()

        assert session.session_id == DEFAULT_SEED_SESSION_IDS["safety_escalation"]
        assert len(session.events) > 0

        event_types = {e.event_type for e in session.events}
        assert EventType.SAFETY_CHECK in event_types
        assert EventType.POLICY_VIOLATION in event_types
        assert EventType.REFUSAL in event_types
        assert EventType.TOOL_CALL in event_types
        assert EventType.TOOL_RESULT in event_types

        # Should have a checkpoint for escalation state
        assert len(session.checkpoints) == 1
        checkpoint = session.checkpoints[0]
        # Phase is nested inside data field
        assert checkpoint.state.get("data", {}).get("phase") == "guard-escalation"

    @pytest.mark.asyncio
    async def test_looping_behavior_session_produces_valid_session(self):
        """Looping behavior scenario should produce a session with repeated tool calls."""
        session = await run_looping_behavior_session()

        assert session.session_id == DEFAULT_SEED_SESSION_IDS["looping_behavior"]
        assert len(session.events) > 0

        event_types = {e.event_type for e in session.events}
        assert EventType.TOOL_CALL in event_types

        # Should have 3 tool calls forming a chain
        tool_calls = [e for e in session.events if e.event_type == EventType.TOOL_CALL]
        assert len(tool_calls) == 3

        # Tool calls should form a parent chain (looping pattern)
        # First call has no parent, others have parents
        calls_with_parent = [tc for tc in tool_calls if getattr(tc, "parent_id", None)]
        assert len(calls_with_parent) == 2  # Second and third calls have parent

    @pytest.mark.asyncio
    async def test_failure_cluster_session_produces_valid_session(self):
        """Failure cluster scenario should produce a session with repeated failures."""
        session = await run_failure_cluster_session()

        assert session.session_id == DEFAULT_SEED_SESSION_IDS["failure_cluster"]
        assert len(session.events) > 0

        event_types = {e.event_type for e in session.events}
        assert EventType.TOOL_CALL in event_types
        assert EventType.TOOL_RESULT in event_types
        assert EventType.POLICY_VIOLATION in event_types

        # Should have 3 failure attempts
        tool_results = [e for e in session.events if e.event_type == EventType.TOOL_RESULT]
        assert len(tool_results) == 3

        # All results should have explicit error events (not embedded in tool_result)
        errors = [e for e in session.events if e.event_type == EventType.ERROR]
        assert len(errors) == 3

        # Should have 3 corresponding policy violations
        violations = [e for e in session.events if e.event_type == EventType.POLICY_VIOLATION]
        assert len(violations) == 3

    @pytest.mark.asyncio
    async def test_replay_determinism_session_produces_valid_session(self):
        """Replay determinism scenario should produce a session with checkpoint and refusal."""
        session = await run_replay_determinism_session()

        assert session.session_id == DEFAULT_SEED_SESSION_IDS["replay_determinism"]
        assert len(session.events) > 0

        event_types = {e.event_type for e in session.events}
        assert EventType.TOOL_CALL in event_types
        assert EventType.TOOL_RESULT in event_types
        assert EventType.DECISION in event_types
        assert EventType.REFUSAL in event_types

        # Should have a checkpoint for replay anchoring
        assert len(session.checkpoints) == 1
        checkpoint = session.checkpoints[0]
        assert checkpoint.importance >= 0.9  # High importance checkpoint

    @pytest.mark.asyncio
    async def test_all_scenarios_via_iter_seed_scenarios(self):
        """All scenarios should be accessible via iter_seed_scenarios."""
        scenarios = iter_seed_scenarios()
        assert len(scenarios) == 8

        names = [name for name, _ in scenarios]
        expected_names = [
            "prompt_injection",
            "evidence_grounding",
            "multi_agent_dialogue",
            "prompt_policy_shift",
            "safety_escalation",
            "looping_behavior",
            "failure_cluster",
            "replay_determinism",
        ]
        assert names == expected_names

    @pytest.mark.asyncio
    async def test_custom_session_id_override(self):
        """All scenarios should accept custom session IDs."""
        custom_id = "custom-test-session-12345"

        session = await run_prompt_injection_session(custom_id)
        assert session.session_id == custom_id

        session = await run_evidence_grounding_session(custom_id)
        assert session.session_id == custom_id


class TestCIRegressionAssertions:
    """CI-friendly assertions that detect known issues and regression patterns."""

    @pytest.mark.asyncio
    async def test_prompt_injection_blocks_reveal_attempts(self):
        """Regression: Prompt injection should block reveal_system_prompt action."""
        session = await run_prompt_injection_session()

        safety_checks = [e for e in session.events if e.event_type == EventType.SAFETY_CHECK]
        assert len(safety_checks) >= 1

        # At least one safety check should have blocked the reveal attempt
        blocked_checks = [
            sc
            for sc in safety_checks
            if getattr(sc, "outcome", None) == "block" and getattr(sc, "blocked_action", None) == "reveal_system_prompt"
        ]
        assert len(blocked_checks) >= 1, "Expected blocked action for reveal_system_prompt"

    @pytest.mark.asyncio
    async def test_prompt_injection_records_violation_signature(self):
        """Regression: Prompt injection should record violation with signature."""
        session = await run_prompt_injection_session()

        violations = [e for e in session.events if e.event_type == EventType.POLICY_VIOLATION]
        assert len(violations) >= 1

        violation = violations[0]
        assert getattr(violation, "violation_type", None) == "instruction_override"

        details = getattr(violation, "details", {}) or {}
        assert "signature" in details
        assert "ignore previous instructions" in details.get("signature", "")

    @pytest.mark.asyncio
    async def test_safety_escalation_warns_then_blocks(self):
        """Regression: Safety escalation should warn before blocking."""
        session = await run_safety_escalation_session()

        safety_checks = [e for e in session.events if e.event_type == EventType.SAFETY_CHECK]
        assert len(safety_checks) >= 2

        # First check should warn, second should block
        warn_checks = [sc for sc in safety_checks if getattr(sc, "outcome", None) == "warn"]
        block_checks = [sc for sc in safety_checks if getattr(sc, "outcome", None) == "block"]

        assert len(warn_checks) >= 1, "Expected at least one warn outcome"
        assert len(block_checks) >= 1, "Expected at least one block outcome"

    @pytest.mark.asyncio
    async def test_safety_escalation_missing_approval_token_detected(self):
        """Regression: Missing approval token should be detected as policy violation."""
        session = await run_safety_escalation_session()

        violations = [e for e in session.events if e.event_type == EventType.POLICY_VIOLATION]
        assert len(violations) >= 1

        violation = violations[0]
        assert getattr(violation, "violation_type", None) == "missing_approval_token"
        assert getattr(violation, "severity", None) == "high"

    @pytest.mark.asyncio
    async def test_failure_cluster_all_attempts_fail(self):
        """Regression: All 3 attempts in failure cluster should produce error events."""
        session = await run_failure_cluster_session()

        tool_results = [e for e in session.events if e.event_type == EventType.TOOL_RESULT]
        assert len(tool_results) == 3

        errors = [e for e in session.events if e.event_type == EventType.ERROR]
        assert len(errors) == 3

        for error in errors:
            msg = error.error_message or error.error_type or ""
            assert "not found" in msg.lower() or "failed" in msg.lower()

    @pytest.mark.asyncio
    async def test_looping_behavior_creates_parent_chain(self):
        """Regression: Looping behavior should create parent chain."""
        session = await run_looping_behavior_session()

        tool_calls = [e for e in session.events if e.event_type == EventType.TOOL_CALL]
        assert len(tool_calls) == 3

        # Each subsequent call should be parented by the previous
        # First call: no parent
        # Second call: parent = first
        # Third call: parent = second
        sorted_calls = sorted(tool_calls, key=lambda e: e.timestamp)

        assert sorted_calls[0].parent_id is None
        assert sorted_calls[1].parent_id == sorted_calls[0].id
        assert sorted_calls[2].parent_id == sorted_calls[1].id

    @pytest.mark.asyncio
    async def test_evidence_grounding_links_evidence_chain(self):
        """Regression: Evidence grounding should link decision to tool result."""
        session = await run_evidence_grounding_session()

        decisions = [e for e in session.events if e.event_type == EventType.DECISION]
        tool_results = [e for e in session.events if e.event_type == EventType.TOOL_RESULT]

        assert len(decisions) == 1
        assert len(tool_results) == 1

        decision = decisions[0]
        tool_result = tool_results[0]

        # Decision should reference the tool result in evidence_event_ids
        assert tool_result.id in decision.evidence_event_ids

    @pytest.mark.asyncio
    async def test_replay_determinism_creates_high_importance_checkpoint(self):
        """Regression: Replay determinism should create high-importance checkpoint."""
        session = await run_replay_determinism_session()

        assert len(session.checkpoints) == 1
        checkpoint = session.checkpoints[0]

        assert checkpoint.importance >= 0.9
        # Step is nested inside data field
        assert "step" in checkpoint.state.get("data", {})

    @pytest.mark.asyncio
    async def test_policy_violation_high_severity_present(self):
        """Regression: High-severity policy violations should be present in risky scenarios."""
        risky_scenarios = [
            run_prompt_injection_session,
            run_safety_escalation_session,
            run_failure_cluster_session,
        ]

        for scenario_fn in risky_scenarios:
            session = await scenario_fn()
            violations = [e for e in session.events if e.event_type == EventType.POLICY_VIOLATION]

            if violations:  # Only check if scenario has violations
                high_severity = [v for v in violations if getattr(v, "severity", None) == "high"]
                assert len(high_severity) >= 1, f"Expected high severity violation in {scenario_fn.__name__}"


class TestSafeUnsafePaths:
    """Tests for safe vs unsafe tool-use path validation."""

    @pytest.mark.asyncio
    async def test_prompt_injection_has_blocked_action(self):
        """Unsafe path: Prompt injection should have explicit blocked_action."""
        session = await run_prompt_injection_session()

        refusals = [e for e in session.events if e.event_type == EventType.REFUSAL]
        assert len(refusals) >= 1

        refusal = refusals[0]
        assert getattr(refusal, "blocked_action", None) == "reveal_system_prompt"
        assert getattr(refusal, "safe_alternative", None) is not None

    @pytest.mark.asyncio
    async def test_prompt_injection_refusal_has_safe_alternative(self):
        """Safe path: Prompt injection refusal should offer safe alternative."""
        session = await run_prompt_injection_session()

        refusals = [e for e in session.events if e.event_type == EventType.REFUSAL]
        assert len(refusals) >= 1

        refusal = refusals[0]
        safe_alt = getattr(refusal, "safe_alternative", None)
        assert safe_alt is not None
        assert "without disclosing" in safe_alt.lower() or "high-level" in safe_alt.lower()

    @pytest.mark.asyncio
    async def test_safety_escalation_tool_result_has_error(self):
        """Unsafe path: Safety escalation should produce an explicit error event."""
        session = await run_safety_escalation_session()

        errors = [e for e in session.events if e.event_type == EventType.ERROR]
        assert len(errors) == 1

        error = errors[0]
        assert "Approval" in (error.error_message or "") or "Approval" in (error.error_type or "")

    @pytest.mark.asyncio
    async def test_safety_escalation_refusal_offers_sandbox(self):
        """Safe path: Safety escalation refusal should offer sandbox alternative."""
        session = await run_safety_escalation_session()

        refusals = [e for e in session.events if e.event_type == EventType.REFUSAL]
        assert len(refusals) >= 1

        refusal = refusals[0]
        safe_alt = getattr(refusal, "safe_alternative", None)
        assert safe_alt is not None
        assert "sandbox" in safe_alt.lower() or "approval token" in safe_alt.lower()

    @pytest.mark.asyncio
    async def test_evidence_grounding_tool_succeeds(self):
        """Safe path: Evidence grounding tool should succeed with result."""
        session = await run_evidence_grounding_session()

        tool_results = [e for e in session.events if e.event_type == EventType.TOOL_RESULT]
        assert len(tool_results) == 1

        result = tool_results[0]
        assert getattr(result, "error", None) is None  # No error
        assert getattr(result, "result", None) is not None

        # Result should have confidence score
        result_data = result.result
        assert "confidence" in result_data

    @pytest.mark.asyncio
    async def test_evidence_grounding_produces_grounded_answer(self):
        """Safe path: Evidence grounding should produce answer with evidence citation."""
        session = await run_evidence_grounding_session()

        decisions = [e for e in session.events if e.event_type == EventType.DECISION]
        assert len(decisions) == 1

        decision = decisions[0]
        assert decision.chosen_action == "answer_with_grounded_fact"
        assert decision.evidence is not None and len(decision.evidence) > 0

    @pytest.mark.asyncio
    async def test_failure_cluster_all_tools_fail(self):
        """Unsafe path: Failure cluster should have error events for each tool."""
        session = await run_failure_cluster_session()

        tool_results = [e for e in session.events if e.event_type == EventType.TOOL_RESULT]
        assert len(tool_results) == 3

        for result in tool_results:
            assert getattr(result, "result", None) is None

        errors = [e for e in session.events if e.event_type == EventType.ERROR]
        assert len(errors) == 3

    @pytest.mark.asyncio
    async def test_replay_determinism_blocks_unsafe_continuation(self):
        """Safe path: Replay determinism should block after conflict detection."""
        session = await run_replay_determinism_session()

        refusals = [e for e in session.events if e.event_type == EventType.REFUSAL]
        assert len(refusals) == 1

        refusal = refusals[0]
        assert "Unsafe" in refusal.reason or "conflict" in refusal.reason.lower()
        assert refusal.blocked_action == "continue_execution"

    @pytest.mark.asyncio
    async def test_safety_check_risk_levels_appropriate(self):
        """Risk levels should escalate appropriately in safety scenarios."""
        injection_session = await run_prompt_injection_session()
        escalation_session = await run_safety_escalation_session()

        # Injection should have high risk
        injection_safety = [e for e in injection_session.events if e.event_type == EventType.SAFETY_CHECK]
        for sc in injection_safety:
            assert getattr(sc, "risk_level", None) == "high"

        # Escalation should have medium then high risk
        escalation_safety = [e for e in escalation_session.events if e.event_type == EventType.SAFETY_CHECK]
        risk_levels = [getattr(sc, "risk_level", None) for sc in escalation_safety]
        assert "medium" in risk_levels
        assert "high" in risk_levels

    @pytest.mark.asyncio
    async def test_all_refusals_have_blocked_action_and_risk_level(self):
        """All refusal events should have blocked_action and risk_level for analysis."""
        scenarios = iter_seed_scenarios()

        for name, runner in scenarios:
            session = await runner()
            refusals = [e for e in session.events if e.event_type == EventType.REFUSAL]

            for refusal in refusals:
                assert getattr(refusal, "blocked_action", None) is not None, f"Refusal in {name} missing blocked_action"
                assert getattr(refusal, "risk_level", None) is not None, f"Refusal in {name} missing risk_level"
                assert getattr(refusal, "reason", None) is not None, f"Refusal in {name} missing reason"


class TestBenchmarkSessionIntegrity:
    """Tests for session data integrity and consistency."""

    @pytest.mark.asyncio
    async def test_all_sessions_have_valid_session_ids(self):
        """All sessions should have non-empty session IDs."""
        scenarios = iter_seed_scenarios()

        for name, runner in scenarios:
            session = await runner()
            assert session.session_id, f"Session {name} has empty session_id"
            assert session.session_id.startswith("seed-"), f"Session {name} should have seed- prefixed ID"

    @pytest.mark.asyncio
    async def test_all_events_have_required_fields(self):
        """All events should have required base fields."""
        scenarios = iter_seed_scenarios()

        for name, runner in scenarios:
            session = await runner()

            for event in session.events:
                assert event.id, f"Event in {name} missing id"
                assert event.session_id, f"Event in {name} missing session_id"
                assert event.event_type, f"Event in {name} missing event_type"
                assert event.timestamp, f"Event in {name} missing timestamp"

    @pytest.mark.asyncio
    async def test_upstream_event_ids_reference_valid_events(self):
        """upstream_event_ids should reference events that exist in the session."""
        scenarios = iter_seed_scenarios()

        for name, runner in scenarios:
            session = await runner()
            event_ids = {e.id for e in session.events}

            for event in session.events:
                for upstream_id in event.upstream_event_ids:
                    assert upstream_id in event_ids, (
                        f"Event {event.id} in {name} references unknown upstream {upstream_id}"
                    )

    @pytest.mark.asyncio
    async def test_parent_ids_reference_valid_events(self):
        """parent_id should reference events that exist in the session."""
        scenarios = iter_seed_scenarios()

        for name, runner in scenarios:
            session = await runner()
            event_ids = {e.id for e in session.events}

            for event in session.events:
                if event.parent_id:
                    assert event.parent_id in event_ids, (
                        f"Event {event.id} in {name} references unknown parent {event.parent_id}"
                    )

    @pytest.mark.asyncio
    async def test_checkpoints_have_valid_event_references(self):
        """Checkpoint event_id should reference existing events."""
        scenarios = iter_seed_scenarios()

        for name, runner in scenarios:
            session = await runner()
            event_ids = {e.id for e in session.events}

            for checkpoint in session.checkpoints:
                if checkpoint.event_id:
                    assert checkpoint.event_id in event_ids, (
                        f"Checkpoint in {name} references unknown event {checkpoint.event_id}"
                    )

    @pytest.mark.asyncio
    async def test_events_are_serializable(self):
        """All events should be serializable via to_dict()."""
        scenarios = iter_seed_scenarios()

        for name, runner in scenarios:
            session = await runner()

            for event in session.events:
                d = event.to_dict()
                assert isinstance(d, dict)
                assert "id" in d
                assert "event_type" in d

            for checkpoint in session.checkpoints:
                d = checkpoint.to_dict()
                assert isinstance(d, dict)
                assert "id" in d


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
        tool_result = next(e for e in session.events if e.event_type.value == "tool_result")
        decision = next(e for e in session.events if e.event_type.value == "decision")
        assert tool_result.id in decision.upstream_event_ids

    @pytest.mark.asyncio
    async def test_policy_shift_maintains_parent_chain(self):
        """Policy shift should maintain proper parent chain."""
        session = await run_prompt_policy_shift_session("linkage-policy")
        llm_response = next(e for e in session.events if e.event_type.value == "llm_response")
        llm_request = next(e for e in session.events if e.event_type.value == "llm_request")
        assert llm_response.parent_id == llm_request.id

    @pytest.mark.asyncio
    async def test_looping_behavior_has_parent_chain(self):
        """Looping behavior tool calls should form a parent chain."""
        session = await run_looping_behavior_session("linkage-loop")
        tool_calls = [e for e in session.events if e.event_type.value == "tool_call"]
        assert tool_calls[1].parent_id == tool_calls[0].id
        assert tool_calls[2].parent_id == tool_calls[1].id
