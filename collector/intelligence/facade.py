"""Main facade for session-level trace analysis and adaptive ranking."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from agent_debugger_sdk.core.events import Checkpoint, EventType, TraceEvent

from ..causal_analysis import CausalAnalyzer
from ..clustering import FailureClusterAnalyzer
from ..failure_diagnostics import FailureDiagnostics
from ..highlights import generate_highlights
from ..live_monitor import LiveMonitor
from ..ranking import CheckpointRankingService, EventRankingService
from .compute import compute_checkpoint_rankings, compute_event_ranking, detect_tool_loop
from .event_utils import event_headline, fingerprint as fingerprint_fn, retention_tier
from .helpers import event_value, mean


@dataclass
class TraceIntelligence:
    """Compute replay-centric analysis from session events.

    This class is a **facade** that composes focused components:
    - :class:`~collector.causal_analysis.CausalAnalyzer`
    - :class:`~collector.clustering.failure_clusters.FailureClusterAnalyzer`
    - :class:`~collector.failure_diagnostics.FailureDiagnostics`
    - :class:`~collector.live_monitor.LiveMonitor`
    - :class:`~collector.ranking.event_ranker.EventRankingService`
    - :class:`~collector.ranking.checkpoint_ranker.CheckpointRankingService`

    The public API is unchanged so all callers continue to work without
    modification.
    """

    severity_weights: dict[EventType, float] | None = None

    def __post_init__(self) -> None:
        if self.severity_weights is None:
            self.severity_weights = {
                EventType.ERROR: 1.0,
                EventType.POLICY_VIOLATION: 0.96,
                EventType.REFUSAL: 0.92,
                EventType.BEHAVIOR_ALERT: 0.88,
                EventType.SAFETY_CHECK: 0.8,
                EventType.DECISION: 0.72,
                EventType.CHECKPOINT: 0.65,
                EventType.TOOL_RESULT: 0.58,
                EventType.LLM_RESPONSE: 0.52,
                EventType.PROMPT_POLICY: 0.48,
                EventType.AGENT_TURN: 0.44,
                EventType.TOOL_CALL: 0.4,
                EventType.LLM_REQUEST: 0.35,
                EventType.AGENT_START: 0.2,
                EventType.AGENT_END: 0.2,
            }
        self._causal = CausalAnalyzer(self.severity_weights)
        self._clusterer = FailureClusterAnalyzer()
        self._diagnostics = FailureDiagnostics(self._causal)
        self._monitor = LiveMonitor()
        self._event_ranker = EventRankingService(
            causal_analyzer=self._causal,
            fingerprint_fn=self.fingerprint,
            severity_fn=self.severity,
        )
        self._checkpoint_ranker = CheckpointRankingService()

    # ------------------------------------------------------------------
    # Public API methods (delegate to submodules or provide utilities)
    # ------------------------------------------------------------------

    def event_headline(self, event: TraceEvent) -> str:
        """Return a compact human-readable label for an event."""
        return event_headline(event)

    def is_failure_event(self, event: TraceEvent) -> bool:
        """Return whether an event should receive post-hoc diagnosis."""
        return self._diagnostics.is_failure_event(event)

    def fingerprint(self, event: TraceEvent) -> str:
        """Return a coarse fingerprint used for recurrence clustering."""
        return fingerprint_fn(event)

    def severity(self, event: TraceEvent) -> float:
        """Compute an event severity score."""
        return self._causal.severity(event)

    def retention_tier(
        self,
        *,
        replay_value: float,
        high_severity_count: int,
        failure_cluster_count: int,
        behavior_alert_count: int,
    ) -> str:
        """Assign a coarse retention tier for a session or checkpoint."""
        return retention_tier(
            replay_value=replay_value,
            high_severity_count=high_severity_count,
            failure_cluster_count=failure_cluster_count,
            behavior_alert_count=behavior_alert_count,
        )

    # ------------------------------------------------------------------
    # Delegating entry-points
    # ------------------------------------------------------------------

    def build_live_summary(self, events: list[TraceEvent], checkpoints: list[Checkpoint]) -> dict[str, Any]:
        """Build a live monitoring summary from the current persisted session state."""
        return self._monitor.build_live_summary(events, checkpoints)

    def analyze_session(self, events: list[TraceEvent], checkpoints: list[Checkpoint]) -> dict[str, Any]:
        """Analyze session events for replay, clustering, and anomaly signals."""
        if not events:
            return {
                "event_rankings": [],
                "failure_clusters": [],
                "representative_failure_ids": [],
                "high_replay_value_ids": [],
                "behavior_alerts": [],
                "checkpoint_rankings": [],
                "session_replay_value": 0.0,
                "retention_tier": "downsampled",
                "session_summary": {
                    "failure_count": 0,
                    "behavior_alert_count": 0,
                    "high_severity_count": 0,
                    "checkpoint_count": 0,
                },
                "failure_explanations": [],
                "live_summary": self.build_live_summary(events, checkpoints),
                "highlights": [],
            }

        fingerprints = [self.fingerprint(event) for event in events]
        counts = Counter(fingerprints)
        checkpoint_event_ids = {checkpoint.event_id for checkpoint in checkpoints}
        event_rankings: list[dict[str, Any]] = []
        behavior_alerts: list[dict[str, Any]] = []

        # Pre-aggregate metrics during single pass (avoids separate loops)
        total_cost = 0.0
        high_severity_count = 0
        consecutive_tool_loop = 0
        previous_tool_name = None

        for index, event in enumerate(events):
            ranking = compute_event_ranking(
                event=event,
                fingerprint=fingerprints[index],
                counts=counts,
                total_events=len(events),
                checkpoint_event_ids=checkpoint_event_ids,
                severity_fn=self.severity,
            )
            event_rankings.append(ranking)

            # Pre-aggregate: count high severity during ranking
            if ranking["severity"] >= 0.9:
                high_severity_count += 1

            # Pre-aggregate: accumulate cost from LLM responses
            if event.event_type == EventType.LLM_RESPONSE:
                cost = event_value(event, "cost_usd", 0.0)
                if cost:
                    total_cost += float(cost)

            # Detect and track tool loops
            consecutive_tool_loop, previous_tool_name, new_alerts = detect_tool_loop(
                event=event,
                consecutive_tool_loop=consecutive_tool_loop,
                previous_tool_name=previous_tool_name,
            )
            behavior_alerts.extend(new_alerts)

        # Use FailureClusterAnalyzer for clustering logic
        failure_clusters = self._clusterer.cluster_failures(event_rankings)
        representative_failure_ids = [cluster["representative_event_id"] for cluster in failure_clusters]
        high_replay_value_ids = [
            ranking["event_id"]
            for ranking in sorted(event_rankings, key=lambda item: item["composite"], reverse=True)[:12]
        ]
        ranking_by_event_id = {ranking["event_id"]: ranking for ranking in event_rankings}
        failure_explanations = self._diagnostics.build_failure_explanations(
            events, ranking_by_event_id, self.event_headline
        )

        # Compute checkpoint rankings
        checkpoint_rankings, checkpoint_values = compute_checkpoint_rankings(
            checkpoints=checkpoints,
            ranking_by_event_id=ranking_by_event_id,
            representative_failure_ids=representative_failure_ids,
        )

        # Compute session-level metrics
        top_composites = [
            ranking["composite"]
            for ranking in sorted(event_rankings, key=lambda item: item["composite"], reverse=True)[:5]
        ]
        session_replay_value = min(
            1.0,
            mean(top_composites) * 0.55
            + min(len(representative_failure_ids) / 4, 1.0) * 0.2
            + min(len(behavior_alerts) / 3, 1.0) * 0.1
            + mean(checkpoint_values) * 0.1
            + min(total_cost / 0.25, 1.0) * 0.05,
        )
        retention_tier_result = self.retention_tier(
            replay_value=session_replay_value,
            high_severity_count=high_severity_count,
            failure_cluster_count=len(failure_clusters),
            behavior_alert_count=len(behavior_alerts),
        )

        # Generate highlights
        highlights = generate_highlights(events, event_rankings, self.event_headline)

        return {
            "event_rankings": event_rankings,
            "failure_clusters": failure_clusters,
            "representative_failure_ids": representative_failure_ids,
            "high_replay_value_ids": high_replay_value_ids,
            "behavior_alerts": behavior_alerts,
            "checkpoint_rankings": checkpoint_rankings,
            "session_replay_value": round(session_replay_value, 4),
            "retention_tier": retention_tier_result,
            "session_summary": {
                "failure_count": len(representative_failure_ids),
                "behavior_alert_count": len(behavior_alerts),
                "high_severity_count": high_severity_count,
                "checkpoint_count": len(checkpoints),
            },
            "failure_explanations": failure_explanations,
            "live_summary": self.build_live_summary(events, checkpoints),
            "highlights": highlights,
        }
