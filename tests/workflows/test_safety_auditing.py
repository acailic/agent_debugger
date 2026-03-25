"""Workflow tests: Safety Auditing.

Verifies the developer can enumerate safety events and detect missed policy violations.
"""

from __future__ import annotations

from agent_debugger_sdk.core.events.base import EventType, SafetyOutcome
from agent_debugger_sdk.core.events.safety import (
    PolicyViolationEvent,
    RefusalEvent,
    SafetyCheckEvent,
)
from tests.fixtures.workflow_helpers import (
    cassette_events,
    filter_events,
    find_downstream_danger,
    find_risky_passes,
    load_cassette,
)


class TestEnumerateAllSafetyEvents:
    """Happy path: enumerate all safety-relevant events in a session."""

    def test_safety_checks_captured(self):
        interactions = load_cassette("safety/enumerate_safety_events.yaml")
        events = cassette_events(interactions)

        safety_checks = filter_events(events, event_type=EventType.SAFETY_CHECK)
        assert len(safety_checks) >= 2

        for sc in safety_checks:
            assert isinstance(sc, SafetyCheckEvent)
            assert sc.outcome in list(SafetyOutcome)
            assert sc.risk_level is not None

    def test_safety_check_outcomes_vary(self):
        interactions = load_cassette("safety/enumerate_safety_events.yaml")
        events = cassette_events(interactions)

        safety_checks = filter_events(events, event_type=EventType.SAFETY_CHECK)
        outcomes = {sc.outcome for sc in safety_checks}
        assert len(outcomes) >= 2, "Expected multiple distinct safety outcomes"

    def test_policy_violations_captured(self):
        interactions = load_cassette("safety/enumerate_safety_events.yaml")
        events = cassette_events(interactions)

        violations = filter_events(events, event_type=EventType.POLICY_VIOLATION)
        assert len(violations) >= 1

        for v in violations:
            assert isinstance(v, PolicyViolationEvent)
            assert v.severity is not None
            assert v.violation_type is not None

    def test_refusals_captured(self):
        interactions = load_cassette("safety/enumerate_safety_events.yaml")
        events = cassette_events(interactions)

        refusals = filter_events(events, event_type=EventType.REFUSAL)
        assert len(refusals) >= 1

        for r in refusals:
            assert isinstance(r, RefusalEvent)


class TestDetectMissedPolicyViolation:
    """Failure mode: agent did something dangerous but no violation was recorded."""

    def test_risky_pass_exists(self):
        interactions = load_cassette("safety/missed_policy_violation.yaml")
        events = cassette_events(interactions)

        risky = find_risky_passes(events)
        assert len(risky) >= 1

    def test_downstream_danger_detected(self):
        interactions = load_cassette("safety/missed_policy_violation.yaml")
        events = cassette_events(interactions)

        risky = find_risky_passes(events)
        assert len(risky) >= 1

        dangerous_event = find_downstream_danger(events, risky[0])
        assert dangerous_event is not None
        assert dangerous_event.event_type == EventType.TOOL_CALL

    def test_no_policy_violation_recorded(self):
        interactions = load_cassette("safety/missed_policy_violation.yaml")
        events = cassette_events(interactions)

        violations = filter_events(events, event_type=EventType.POLICY_VIOLATION)
        assert len(violations) == 0, "Expected no policy_violation event despite dangerous action"
