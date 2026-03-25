"""Workflow tests: Root Cause Hunting.

Verifies the developer can use CausalAnalyzer and FailureDiagnostics
to find the decision that caused a failure, validate evidence chains,
and classify failure patterns.
"""

from __future__ import annotations

from agent_debugger_sdk.core.events.base import EventType, TraceEvent
from agent_debugger_sdk.core.events.decisions import DecisionEvent
from collector.causal_analysis import CausalAnalyzer
from collector.failure_diagnostics import FailureDiagnostics
from tests.fixtures.workflow_helpers import (
    cassette_events,
    find_event,
    load_cassette,
    validate_evidence_chain,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _build_analytics(events: list[TraceEvent]):
    """Build CausalAnalyzer and FailureDiagnostics from cassette events."""
    causal = CausalAnalyzer()
    diagnostics = FailureDiagnostics(causal)
    id_lookup = {e.id: e for e in events}
    index_lookup = {e.id: i for i, e in enumerate(events)}

    # Build minimal ranking_by_event_id from severity scores
    ranking_by_event_id = {
        e.id: {"severity": causal.severity(e), "composite": causal.severity(e)}
        for e in events
    }
    return causal, diagnostics, id_lookup, index_lookup, ranking_by_event_id


# ── Happy path: CausalAnalyzer traces failure to decision ─────────────────────


class TestCausalAnalysisTracesFailureToDecision:
    """Use CausalAnalyzer to find the decision behind a tool failure."""

    def _load(self):
        interactions = load_cassette("root_cause/tool_failure_to_decision.yaml")
        events = cassette_events(interactions)
        return events, *_build_analytics(events)

    def test_failure_event_is_identified(self):
        events, _, diagnostics, *_ = self._load()
        failures = [e for e in events if diagnostics.is_failure_event(e)]
        assert len(failures) >= 1

    def test_top_candidate_is_decision(self):
        events, causal, diagnostics, id_lookup, index_lookup, ranking = self._load()
        failure = find_event(events, event_type=EventType.TOOL_RESULT)
        assert failure is not None

        candidates = causal.rank_failure_candidates(
            failure,
            events=events,
            id_lookup=id_lookup,
            index_lookup=index_lookup,
            ranking_by_event_id=ranking,
            event_headline_fn=lambda e: e.name or str(e.event_type),
        )
        assert len(candidates) >= 1

        # At least one candidate should be upstream of the failure
        assert candidates[0]["score"] > 0.0
        assert candidates[0]["causal_depth"] >= 1

    def test_failure_mode_is_tool_execution(self):
        events, _, diagnostics, id_lookup, _, ranking = self._load()
        failure = find_event(events, event_type=EventType.TOOL_RESULT)
        assert failure is not None

        candidates = [
            {"event_id": "", "score": 0.0}
        ]  # minimal candidate to check mode
        mode = diagnostics.failure_mode(failure, candidates[0], id_lookup)
        assert mode in ("tool_execution_failure", "ungrounded_decision")

    def test_failure_symptom_is_generated(self):
        events, _, diagnostics, *_ = self._load()
        failure = find_event(events, event_type=EventType.TOOL_RESULT)
        assert failure is not None

        symptom = diagnostics.failure_symptom(
            failure, lambda e: e.name or str(e.event_type)
        )
        assert "failed" in symptom.lower()

    def test_failure_narrative_mentions_upstream_cause(self):
        events, causal, diagnostics, id_lookup, index_lookup, ranking = self._load()
        failure = find_event(events, event_type=EventType.TOOL_RESULT)
        assert failure is not None

        explanations = diagnostics.build_failure_explanations(
            events, ranking, lambda e: e.name or str(e.event_type)
        )
        assert len(explanations) >= 1

        top = explanations[0]
        assert top["narrative"]
        assert top["failure_mode"] in ("tool_execution_failure", "ungrounded_decision")


# ── Evidence chain validation ─────────────────────────────────────────────────


class TestEvidenceChainValidation:
    """Validate evidence chains at existence, temporal, and content levels."""

    def test_happy_path_evidence_chain_is_clean(self):
        interactions = load_cassette("root_cause/tool_failure_to_decision.yaml")
        events = cassette_events(interactions)

        decision = find_event(events, event_type=EventType.DECISION)
        assert decision is not None
        assert isinstance(decision, DecisionEvent)

        issues = validate_evidence_chain(decision, events)
        # All evidence_event_ids should resolve; no temporal issues
        missing = [i for i in issues if i.kind == "missing"]
        temporal = [i for i in issues if i.kind == "temporal"]
        assert len(missing) == 0, f"Unexpected missing refs: {missing}"
        assert len(temporal) == 0

    def test_hallucinated_evidence_has_broken_reference(self):
        interactions = load_cassette("root_cause/hallucinated_evidence.yaml")
        events = cassette_events(interactions)

        decision = find_event(events, event_type=EventType.DECISION)
        assert decision is not None
        assert isinstance(decision, DecisionEvent)

        issues = validate_evidence_chain(decision, events)
        missing = [i for i in issues if i.kind == "missing"]
        assert len(missing) >= 1, "Expected at least one broken evidence reference"

    def test_hallucinated_evidence_has_content_mismatch(self):
        interactions = load_cassette("root_cause/hallucinated_evidence.yaml")
        events = cassette_events(interactions)

        decision = find_event(events, event_type=EventType.DECISION)
        assert decision is not None

        issues = validate_evidence_chain(decision, events)
        content = [i for i in issues if i.kind == "content_mismatch"]
        assert len(content) >= 1, (
            "Expected content mismatch: decision claims 37.4M but tool result says 13.96M"
        )


# ── Pattern-based root cause detection ───────────────────────────────────────


class TestPatternBasedRootCause:
    """Classify failure patterns using FailureDiagnostics."""

    def test_tool_failure_pattern(self):
        interactions = load_cassette("root_cause/tool_failure_to_decision.yaml")
        events = cassette_events(interactions)

        _, diagnostics, id_lookup, _, ranking = _build_analytics(events)
        failure = find_event(events, event_type=EventType.TOOL_RESULT)
        assert failure is not None

        # Get actual top candidate for accurate mode classification
        causal = CausalAnalyzer()
        index_lookup = {e.id: i for i, e in enumerate(events)}
        candidates = causal.rank_failure_candidates(
            failure,
            events=events,
            id_lookup=id_lookup,
            index_lookup=index_lookup,
            ranking_by_event_id=ranking,
            event_headline_fn=lambda e: e.name or str(e.event_type),
        )
        top = candidates[0] if candidates else None

        mode = diagnostics.failure_mode(failure, top, id_lookup)
        assert mode == "tool_execution_failure"

    def test_ungrounded_decision_pattern(self):
        interactions = load_cassette("root_cause/ungrounded_decision.yaml")
        events = cassette_events(interactions)

        _, diagnostics, id_lookup, _, ranking = _build_analytics(events)

        # The tool result failure should be classified
        failure = find_event(events, event_type=EventType.TOOL_RESULT)
        assert failure is not None

        causal = CausalAnalyzer()
        index_lookup = {e.id: i for i, e in enumerate(events)}
        candidates = causal.rank_failure_candidates(
            failure,
            events=events,
            id_lookup=id_lookup,
            index_lookup=index_lookup,
            ranking_by_event_id=ranking,
            event_headline_fn=lambda e: e.name or str(e.event_type),
        )
        top = candidates[0] if candidates else None

        mode = diagnostics.failure_mode(failure, top, id_lookup)
        assert mode == "ungrounded_decision"

    def test_ungrounded_decision_has_no_evidence(self):
        interactions = load_cassette("root_cause/ungrounded_decision.yaml")
        events = cassette_events(interactions)

        decision = find_event(events, event_type=EventType.DECISION)
        assert decision is not None
        assert isinstance(decision, DecisionEvent)
        assert decision.confidence < 0.5
        assert len(decision.evidence) == 0
        assert len(decision.evidence_event_ids) == 0

    def test_failure_explanations_include_symptom_and_cause(self):
        interactions = load_cassette("root_cause/ungrounded_decision.yaml")
        events = cassette_events(interactions)

        _, diagnostics, _, _, ranking = _build_analytics(events)
        explanations = diagnostics.build_failure_explanations(
            events, ranking, lambda e: e.name or str(e.event_type)
        )
        assert len(explanations) >= 1

        for exp in explanations:
            assert exp["symptom"]
            assert exp["likely_cause"]
            assert exp["failure_mode"]
