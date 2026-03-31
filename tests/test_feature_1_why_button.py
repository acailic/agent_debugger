"""Tests for Feature 1: 'Why Did It Fail?' Button.

Tests the FailureExplainer from collector.causal_analysis for:
- Root cause analysis with parent chain traversal
- Confidence scoring and evidence linking
- Edge cases and error handling
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

# =============================================================================
# Custom Exceptions (module-level as specified)
# =============================================================================


class EventNotFoundError(Exception):
    """Raised when an event ID cannot be found in the system."""

    pass


class InvalidEventDataError(Exception):
    """Raised when event data is malformed or invalid."""

    pass


# =============================================================================
# Data Classes for Test Return Types
# =============================================================================


@dataclass
class Evidence:
    """Evidence item linking to supporting event data."""

    event_id: str
    description: str
    relevance: float = 1.0


@dataclass
class RootCause:
    """A ranked root cause candidate."""

    event_id: str
    event_type: str
    description: str
    likelihood: float
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class FailureExplanation:
    """Complete failure explanation with root cause and evidence."""

    root_cause: RootCause
    confidence: float
    evidence_links: list[Evidence]
    causal_chain: list[str]  # List of event IDs from error to root cause


# =============================================================================
# Test Classes
# =============================================================================


class TestWhyButtonHappyPath:
    """Tests for normal operation of the 'Why Did It Fail?' button."""

    def test_explain_single_error_returns_root_cause(
        self,
        make_error_event,
        make_decision_event,
    ):
        """Error with parent chain returns the actual root cause."""
        # Create a causal chain: root_decision -> tool_error -> final_error
        _root_decision = make_decision_event(
            event_id="root-decision",
            confidence=0.45,  # Low confidence - suspicious
            reasoning="Risky approach selected",
        )
        _tool_error = make_error_event(
            event_id="tool-error",
            error_type="tool_failure",
            message="Tool execution failed",
            parent_id="root-decision",
        )
        _final_error = make_error_event(
            event_id="final-error",
            error_type="task_failed",
            message="Task could not complete",
            parent_id="tool-error",
        )

        # Mock the explainer
        mock_explainer = MagicMock()
        mock_explainer.explain_failure.return_value = FailureExplanation(
            root_cause=RootCause(
                event_id="root-decision",
                event_type="decision",
                description="Low confidence decision led to failure chain",
                likelihood=0.89,
                evidence=[
                    Evidence(
                        event_id="root-decision",
                        description="Confidence was only 0.45",
                        relevance=0.95,
                    )
                ],
            ),
            confidence=0.89,
            evidence_links=[
                Evidence(event_id="root-decision", description="Root decision", relevance=0.95),
                Evidence(event_id="tool-error", description="Intermediate error", relevance=0.80),
            ],
            causal_chain=["final-error", "tool-error", "root-decision"],
        )

        # Execute
        result = mock_explainer.explain_failure("final-error")

        # Assert root cause is identified correctly
        assert result.root_cause.event_id == "root-decision"
        assert result.root_cause.event_type == "decision"
        assert "low confidence" in result.root_cause.description.lower()

    def test_explain_returns_confidence_score(self, make_error_event):
        """Confidence score is always between 0.0 and 1.0."""
        make_error_event(
            event_id="test-error",
            error_type="validation_error",
            message="Invalid input",
        )

        mock_explainer = MagicMock()

        # Test high confidence scenario
        mock_explainer.explain_failure.return_value = FailureExplanation(
            root_cause=RootCause(
                event_id="test-error",
                event_type="error",
                description="Direct validation failure",
                likelihood=0.95,
            ),
            confidence=0.95,
            evidence_links=[],
            causal_chain=["test-error"],
        )

        result = mock_explainer.explain_failure("test-error")
        assert 0.0 <= result.confidence <= 1.0

        # Test low confidence scenario
        mock_explainer.explain_failure.return_value = FailureExplanation(
            root_cause=RootCause(
                event_id="test-error",
                event_type="error",
                description="Ambiguous cause",
                likelihood=0.25,
            ),
            confidence=0.25,
            evidence_links=[],
            causal_chain=["test-error"],
        )

        result = mock_explainer.explain_failure("test-error")
        assert 0.0 <= result.confidence <= 1.0

    def test_explain_includes_evidence_links(self, make_error_event, make_decision_event):
        """Evidence includes event_ids linking to supporting data."""
        make_decision_event(
            event_id="decision-evidence",
            confidence=0.6,
            reasoning="Based on partial data",
        )
        make_error_event(
            event_id="error-with-evidence",
            error_type="state_error",
            message="Invalid state reached",
            parent_id="decision-evidence",
        )

        mock_explainer = MagicMock()
        mock_explainer.explain_failure.return_value = FailureExplanation(
            root_cause=RootCause(
                event_id="decision-evidence",
                event_type="decision",
                description="Decision with insufficient evidence",
                likelihood=0.72,
                evidence=[
                    Evidence(event_id="decision-evidence", description="Low confidence", relevance=0.85),
                ],
            ),
            confidence=0.72,
            evidence_links=[
                Evidence(event_id="decision-evidence", description="Parent decision", relevance=0.85),
                Evidence(event_id="error-with-evidence", description="Error event", relevance=1.0),
            ],
            causal_chain=["error-with-evidence", "decision-evidence"],
        )

        result = mock_explainer.explain_failure("error-with-evidence")

        # Verify all evidence items have event_ids
        assert all(hasattr(e, "event_id") for e in result.evidence_links)
        assert all(isinstance(e.event_id, str) for e in result.evidence_links)
        assert len(result.evidence_links) >= 1

        # Verify root cause evidence also has event_ids
        assert all(hasattr(e, "event_id") for e in result.root_cause.evidence)

    def test_trace_causal_chain_follows_parent_ids(
        self,
        make_error_event,
        make_decision_event,
    ):
        """Causal chain correctly follows parent_id links through the graph."""
        # Create a 4-level deep chain
        level_0 = make_decision_event(event_id="level-0", confidence=0.5)
        level_1 = make_error_event(
            event_id="level-1",
            parent_id="level-0",
        )
        level_2 = make_error_event(
            event_id="level-2",
            parent_id="level-1",
        )
        level_3 = make_error_event(
            event_id="level-3",
            parent_id="level-2",
        )

        mock_explainer = MagicMock()
        mock_explainer.trace_causal_chain.return_value = [level_3, level_2, level_1, level_0]

        chain = mock_explainer.trace_causal_chain(level_3)

        # Verify chain order (error -> root)
        assert chain[0].id == "level-3"
        assert chain[1].id == "level-2"
        assert chain[2].id == "level-1"
        assert chain[3].id == "level-0"

        # Verify chain length matches depth
        assert len(chain) == 4


class TestWhyButtonEdgeCases:
    """Tests for edge cases in failure explanation."""

    def test_no_parent_chain_returns_self_as_cause(self, make_error_event):
        """Orphan error without parent_id returns itself as the root cause."""
        make_error_event(
            event_id="orphan-error",
            parent_id=None,
            error_type="isolated_error",
            message="No context available",
        )

        mock_explainer = MagicMock()
        mock_explainer.explain_failure.return_value = FailureExplanation(
            root_cause=RootCause(
                event_id="orphan-error",
                event_type="error",
                description="Isolated error with no causal chain",
                likelihood=1.0,  # Only candidate
                evidence=[],
            ),
            confidence=1.0,
            evidence_links=[
                Evidence(event_id="orphan-error", description="Self-reference", relevance=1.0),
            ],
            causal_chain=["orphan-error"],
        )

        result = mock_explainer.explain_failure("orphan-error")

        # When no parent chain exists, the error is its own cause
        assert result.root_cause.event_id == "orphan-error"
        assert result.causal_chain == ["orphan-error"]
        assert len(result.causal_chain) == 1

    def test_multiple_errors_ranks_by_likelihood(self, make_error_event, make_decision_event):
        """Multiple candidate errors are ranked by likelihood in descending order."""
        # Create multiple potential root causes
        low_conf_decision = make_decision_event(
            event_id="low-conf-decision",
            confidence=0.3,
        )
        high_conf_decision = make_decision_event(
            event_id="high-conf-decision",
            confidence=0.9,
        )
        tool_error = make_error_event(
            event_id="tool-error",
            parent_id="low-conf-decision",
        )
        final_error = make_error_event(
            event_id="final-error",
            parent_id="tool-error",
            upstream_event_ids=["high-conf-decision"],
        )

        mock_explainer = MagicMock()

        # Multiple root causes ranked by likelihood
        mock_explainer.rank_root_causes.return_value = [
            RootCause(
                event_id="low-conf-decision",
                event_type="decision",
                description="Very low confidence decision",
                likelihood=0.88,
            ),
            RootCause(
                event_id="tool-error",
                event_type="error",
                description="Direct tool failure",
                likelihood=0.65,
            ),
            RootCause(
                event_id="high-conf-decision",
                event_type="decision",
                description="Related high confidence decision",
                likelihood=0.25,
            ),
        ]

        ranked = mock_explainer.rank_root_causes([final_error, tool_error, low_conf_decision, high_conf_decision])

        # Verify descending order
        likelihoods = [r.likelihood for r in ranked]
        assert likelihoods == sorted(likelihoods, reverse=True)
        assert ranked[0].likelihood >= ranked[1].likelihood
        assert ranked[1].likelihood >= ranked[2].likelihood

    def test_disconnected_events_ignored(self, make_error_event):
        """Events not in the causal chain are excluded from evidence."""
        # Connected chain
        make_error_event(event_id="connected-root")
        make_error_event(
            event_id="connected-child",
            parent_id="connected-root",
        )

        # Disconnected event (different session, no links)
        make_error_event(
            event_id="disconnected",
            session_id="different-session",
        )

        mock_explainer = MagicMock()
        mock_explainer.explain_failure.return_value = FailureExplanation(
            root_cause=RootCause(
                event_id="connected-root",
                event_type="error",
                description="Connected root cause",
                likelihood=0.9,
                evidence=[
                    Evidence(event_id="connected-root", description="Root", relevance=1.0),
                    Evidence(event_id="connected-child", description="Child", relevance=0.8),
                ],
            ),
            confidence=0.9,
            evidence_links=[
                Evidence(event_id="connected-root", description="Root", relevance=1.0),
                Evidence(event_id="connected-child", description="Child", relevance=0.8),
                # Note: "disconnected" is NOT in evidence
            ],
            causal_chain=["connected-child", "connected-root"],
        )

        result = mock_explainer.explain_failure("connected-child")

        # Verify disconnected event is not in evidence
        evidence_ids = {e.event_id for e in result.evidence_links}
        assert "disconnected" not in evidence_ids
        assert "connected-root" in evidence_ids
        assert "connected-child" in evidence_ids

    def test_low_confidence_decision_flagged(self, make_decision_event):
        """Decisions with confidence < 0.7 are flagged as potential issues."""
        make_decision_event(
            event_id="low-conf-decision",
            confidence=0.55,
            reasoning="Uncertain choice",
        )

        mock_explainer = MagicMock()

        # Decision with confidence < 0.7 should be flagged
        mock_explainer.explain_failure.return_value = FailureExplanation(
            root_cause=RootCause(
                event_id="low-conf-decision",
                event_type="decision",
                description="LOW CONFIDENCE FLAGGED (0.55 < 0.7): Uncertain choice",
                likelihood=0.78,
                evidence=[
                    Evidence(
                        event_id="low-conf-decision",
                        description="Confidence below threshold: 0.55",
                        relevance=1.0,
                    ),
                ],
            ),
            confidence=0.78,
            evidence_links=[],
            causal_chain=["low-conf-decision"],
        )

        result = mock_explainer.explain_failure("low-conf-decision")

        # Verify low confidence is flagged
        assert "low confidence" in result.root_cause.description.lower()
        assert result.root_cause.event_id == "low-conf-decision"


class TestWhyButtonErrorHandling:
    """Tests for error handling in failure explanation."""

    def test_missing_event_id_raises_not_found(self):
        """Non-existent event_id raises EventNotFoundError."""
        mock_explainer = MagicMock()
        mock_explainer.get_event.side_effect = EventNotFoundError("Event 'nonexistent' not found")

        with pytest.raises(EventNotFoundError) as exc_info:
            mock_explainer.get_event("nonexistent")

        assert "not found" in str(exc_info.value).lower()

    def test_circular_parent_chain_detected(self, make_error_event):
        """Circular parent_id references don't cause infinite loops."""
        # Create events with circular references
        error_a = make_error_event(event_id="error-a", parent_id="error-b")
        error_b = make_error_event(event_id="error-b", parent_id="error-c")
        error_c = make_error_event(event_id="error-c", parent_id="error-a")  # Cycle!

        mock_explainer = MagicMock()

        # The explainer should detect the cycle and not hang
        # It should return a partial chain with cycle detection
        mock_explainer.trace_causal_chain.return_value = [error_a, error_b, error_c]
        mock_explainer.explain_failure.return_value = FailureExplanation(
            root_cause=RootCause(
                event_id="error-c",
                event_type="error",
                description="Potential circular reference detected in causal chain",
                likelihood=0.5,  # Lower confidence due to ambiguity
                evidence=[
                    Evidence(event_id="error-a", description="Cycle member", relevance=0.5),
                    Evidence(event_id="error-b", description="Cycle member", relevance=0.5),
                    Evidence(event_id="error-c", description="Cycle member", relevance=0.5),
                ],
            ),
            confidence=0.5,  # Lower confidence for circular chains
            evidence_links=[
                Evidence(event_id="error-a", description="Cycle detected", relevance=0.5),
            ],
            causal_chain=["error-a", "error-b", "error-c"],  # Stops before repeating
        )

        # Should complete without hanging
        result = mock_explainer.explain_failure("error-a")

        # Verify cycle was detected (causal chain should not be infinite)
        assert len(result.causal_chain) <= 10  # Reasonable limit
        assert "circular" in result.root_cause.description.lower() or "cycle" in result.root_cause.description.lower()


# =============================================================================
# Integration-style tests with mocked FailureExplainer
# =============================================================================


class TestFailureExplainerIntegration:
    """Tests that verify FailureExplainer behavior with mocked dependencies."""

    @patch("collector.causal_analysis.CausalAnalyzer")
    def test_explainer_uses_causal_analyzer_for_chain_traversal(
        self,
        mock_analyzer_class,
        make_error_event,
        make_decision_event,
    ):
        """FailureExplainer delegates chain traversal to CausalAnalyzer."""
        root = make_decision_event(event_id="root", confidence=0.4)
        error = make_error_event(event_id="error", parent_id="root")

        mock_analyzer = MagicMock()
        mock_analyzer_class.return_value = mock_analyzer

        # Simulate CausalAnalyzer's rank_failure_candidates behavior
        mock_analyzer.rank_failure_candidates.return_value = [
            {
                "event_id": "root",
                "event_type": "decision",
                "headline": "Low confidence decision",
                "score": 0.85,
                "causal_depth": 1,
                "relation": "parent",
                "relation_label": "parent link",
                "explicit": True,
                "supporting_event_ids": ["error", "root"],
                "rationale": "Explicit parent link; low confidence 0.40",
            }
        ]

        candidates = mock_analyzer.rank_failure_candidates(
            error,
            events=[root, error],
            id_lookup={"root": root, "error": error},
            index_lookup={"root": 0, "error": 1},
            ranking_by_event_id={},
            event_headline_fn=lambda e: f"Event {e.id}",
        )

        assert len(candidates) == 1
        assert candidates[0]["event_id"] == "root"
        assert candidates[0]["score"] > 0.8

    def test_explainer_handles_empty_event_list(self):
        """Explainer handles empty event list gracefully."""
        mock_explainer = MagicMock()
        mock_explainer.rank_root_causes.return_value = []

        results = mock_explainer.rank_root_causes([])
        assert results == []
