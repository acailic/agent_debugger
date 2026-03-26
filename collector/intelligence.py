"""Session-level trace analysis and adaptive ranking."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from agent_debugger_sdk.core.events import Checkpoint, EventType, TraceEvent

from .causal_analysis import CausalAnalyzer
from .failure_diagnostics import FailureDiagnostics
from .live_monitor import LiveMonitor


@dataclass
class Highlight:
    """Represents a highlight-worthy moment in a session trace."""

    event_id: str
    event_type: str
    highlight_type: str  # "decision", "error", "refusal", "anomaly", "state_change"
    importance: float
    reason: str  # Human-readable reason why this is highlighted
    timestamp: str


def generate_highlights(
    events: list[TraceEvent],
    rankings: list[dict[str, Any]],
    event_headline_fn: Any,
) -> list[dict[str, Any]]:
    """Generate a curated list of highlight-worthy moments."""
    highlights: list[dict[str, Any]] = []

    # Build ranking lookup
    ranking_by_id = {r["event_id"]: r for r in rankings}

    for event in events:
        ranking = ranking_by_id.get(event.id, {})
        composite = ranking.get("composite", 0)
        severity = ranking.get("severity", 0)

        highlight_type: str | None = None
        reason: str | None = None

        # Determine highlight type and reason
        if event.event_type == EventType.ERROR:
            highlight_type = "error"
            reason = "Error event"
        elif event.event_type == EventType.REFUSAL:
            highlight_type = "refusal"
            reason = "Refusal triggered"
        elif event.event_type == EventType.POLICY_VIOLATION:
            highlight_type = "refusal"
            reason = "Policy violation"
        elif event.event_type == EventType.BEHAVIOR_ALERT:
            highlight_type = "anomaly"
            reason = str(event.data.get("signal", "Behavior anomaly"))
        elif event.event_type == EventType.SAFETY_CHECK:
            outcome = event.data.get("outcome", "pass")
            if outcome != "pass":
                highlight_type = "anomaly"
                reason = f"Safety check {outcome}"
        elif event.event_type == EventType.DECISION:
            confidence = event.data.get("confidence", 0.5)
            if confidence < 0.5:
                highlight_type = "decision"
                reason = f"Low confidence decision ({confidence:.2f})"
            elif composite > 0.6:
                highlight_type = "decision"
                reason = "High-impact decision"
        elif event.event_type == EventType.TOOL_RESULT:
            if event.data.get("error"):
                highlight_type = "error"
                reason = "Tool execution failed"
            elif severity > 0.7:
                highlight_type = "anomaly"
                reason = "Unusual tool result"

        # Only add if we have a highlight type and sufficient importance
        if highlight_type and (severity > 0.5 or composite > 0.5):
            importance = min(severity, composite) if composite > 0 else severity
            timestamp = event.timestamp.isoformat() if hasattr(event.timestamp, "isoformat") else str(event.timestamp)
            highlights.append(
                {
                    "event_id": event.id,
                    "event_type": str(event.event_type),
                    "highlight_type": highlight_type,
                    "importance": round(importance, 4),
                    "reason": reason,
                    "timestamp": timestamp,
                    "headline": event_headline_fn(event),
                }
            )

    # Sort by importance, limit to top 20
    highlights.sort(key=lambda h: -h["importance"])
    return highlights[:20]


# ---------------------------------------------------------------------------
# Module-level helpers kept here for backward-compat (tests import them)
# ---------------------------------------------------------------------------


def _event_value(event: TraceEvent | None, key: str, default: Any = None) -> Any:
    if event is None:
        return default
    if hasattr(event, key):
        return getattr(event, key)
    return event.data.get(key, default)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


@dataclass
class TraceIntelligence:
    """Compute replay-centric analysis from session events.

    This class is a **facade** that composes three focused components:
    - :class:`~collector.causal_analysis.CausalAnalyzer`
    - :class:`~collector.failure_diagnostics.FailureDiagnostics`
    - :class:`~collector.live_monitor.LiveMonitor`

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
        self._diagnostics = FailureDiagnostics(self._causal)
        self._monitor = LiveMonitor()

    # ------------------------------------------------------------------
    # Utility methods (kept on the facade for backward-compat)
    # ------------------------------------------------------------------

    def event_headline(self, event: TraceEvent) -> str:
        """Return a compact human-readable label for an event."""
        match event.event_type:
            case EventType.DECISION:
                return _event_value(event, "chosen_action", event.name or "decision")
            case EventType.TOOL_CALL | EventType.TOOL_RESULT:
                return _event_value(event, "tool_name", event.name or "tool")
            case EventType.REFUSAL:
                return _event_value(event, "reason", event.name or "refusal")
            case EventType.SAFETY_CHECK:
                policy_name = _event_value(event, "policy_name", "safety")
                outcome = _event_value(event, "outcome", "pass")
                return f"{policy_name} -> {outcome}"
            case EventType.POLICY_VIOLATION:
                return _event_value(event, "violation_type", event.name or "policy violation")
            case EventType.BEHAVIOR_ALERT:
                return _event_value(event, "alert_type", event.name or "behavior alert")
            case EventType.ERROR:
                return _event_value(event, "error_type", event.name or "error")
            case EventType.AGENT_TURN:
                return _event_value(event, "speaker", _event_value(event, "agent_id", event.name or "turn"))
            case _:
                return event.name or str(event.event_type)

    def is_failure_event(self, event: TraceEvent) -> bool:
        """Return whether an event should receive post-hoc diagnosis."""
        return self._diagnostics.is_failure_event(event)

    def fingerprint(self, event: TraceEvent) -> str:
        """Return a coarse fingerprint used for recurrence clustering."""
        match event.event_type:
            case EventType.ERROR:
                return (
                    f"error:{_event_value(event, 'error_type', 'unknown')}:{_event_value(event, 'error_message', '')}"
                )
            case EventType.TOOL_RESULT:
                return f"tool:{_event_value(event, 'tool_name', 'unknown')}:{bool(_event_value(event, 'error'))}"
            case EventType.REFUSAL:
                return f"refusal:{_event_value(event, 'policy_name', 'unknown')}:{_event_value(event, 'risk_level', 'medium')}"
            case EventType.POLICY_VIOLATION:
                return f"policy:{_event_value(event, 'policy_name', 'unknown')}:{_event_value(event, 'violation_type', 'unknown')}"
            case EventType.BEHAVIOR_ALERT:
                return f"alert:{_event_value(event, 'alert_type', 'unknown')}"
            case EventType.SAFETY_CHECK:
                return (
                    f"safety:{_event_value(event, 'policy_name', 'unknown')}:{_event_value(event, 'outcome', 'pass')}"
                )
            case EventType.DECISION:
                return f"decision:{_event_value(event, 'chosen_action', 'unknown')}"
            case _:
                return f"{event.event_type}:{event.name}"

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
        if replay_value >= 0.72 or high_severity_count > 0 or failure_cluster_count >= 2:
            return "full"
        if replay_value >= 0.42 or behavior_alert_count > 0 or failure_cluster_count > 0:
            return "summarized"
        return "downsampled"

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

        consecutive_tool_loop = 0
        previous_tool_name = None
        behavior_alerts: list[dict[str, Any]] = []

        for index, event in enumerate(events):
            fingerprint = fingerprints[index]
            severity = self.severity(event)
            recurrence_count = counts[fingerprint]
            recurrence = min((recurrence_count - 1) / max(len(events), 1), 1.0)
            novelty = 1.0 / recurrence_count
            replay_value = severity * 0.55
            replay_value += 0.15 if event.id in checkpoint_event_ids else 0.0
            replay_value += (
                0.1 if event.event_type in {EventType.DECISION, EventType.REFUSAL, EventType.POLICY_VIOLATION} else 0.0
            )
            replay_value += (
                0.1
                if bool(_event_value(event, "upstream_event_ids", getattr(event, "upstream_event_ids", [])))
                else 0.0
            )
            replay_value += 0.1 if bool(_event_value(event, "evidence_event_ids", [])) else 0.0
            composite = min(1.0, severity * 0.45 + novelty * 0.2 + recurrence * 0.15 + replay_value * 0.2)

            event_rankings.append(
                {
                    "event_id": event.id,
                    "event_type": str(event.event_type),
                    "fingerprint": fingerprint,
                    "severity": round(severity, 4),
                    "novelty": round(novelty, 4),
                    "recurrence": round(recurrence, 4),
                    "replay_value": round(min(replay_value, 1.0), 4),
                    "composite": round(composite, 4),
                }
            )

            if event.event_type == EventType.TOOL_CALL:
                tool_name = _event_value(event, "tool_name", "")
                if tool_name and tool_name == previous_tool_name:
                    consecutive_tool_loop += 1
                else:
                    consecutive_tool_loop = 1
                previous_tool_name = tool_name
                if consecutive_tool_loop >= 3:
                    behavior_alerts.append(
                        {
                            "alert_type": "tool_loop",
                            "severity": "high",
                            "signal": f"Repeated tool loop for {tool_name}",
                            "event_id": event.id,
                        }
                    )
            else:
                previous_tool_name = None
                consecutive_tool_loop = 0

        clusters: dict[str, dict[str, Any]] = {}
        for ranking in event_rankings:
            if ranking["severity"] < 0.78:
                continue
            cluster = clusters.setdefault(
                ranking["fingerprint"],
                {
                    "fingerprint": ranking["fingerprint"],
                    "count": 0,
                    "event_ids": [],
                    "representative_event_id": ranking["event_id"],
                    "max_composite": ranking["composite"],
                },
            )
            cluster["count"] += 1
            cluster["event_ids"].append(ranking["event_id"])
            if ranking["composite"] > cluster["max_composite"]:
                cluster["max_composite"] = ranking["composite"]
                cluster["representative_event_id"] = ranking["event_id"]

        failure_clusters = sorted(clusters.values(), key=lambda item: (-item["count"], -item["max_composite"]))
        representative_failure_ids = [cluster["representative_event_id"] for cluster in failure_clusters]
        high_replay_value_ids = [
            ranking["event_id"]
            for ranking in sorted(event_rankings, key=lambda item: item["composite"], reverse=True)[:12]
        ]
        ranking_by_event_id = {ranking["event_id"]: ranking for ranking in event_rankings}
        failure_explanations = self._diagnostics.build_failure_explanations(
            events, ranking_by_event_id, self.event_headline
        )
        checkpoint_rankings: list[dict[str, Any]] = []
        total_cost = sum(
            float(_event_value(event, "cost_usd", 0.0) or 0.0)
            for event in events
            if event.event_type == EventType.LLM_RESPONSE
        )
        high_severity_count = sum(1 for ranking in event_rankings if ranking["severity"] >= 0.9)
        top_composites = [
            ranking["composite"]
            for ranking in sorted(event_rankings, key=lambda item: item["composite"], reverse=True)[:5]
        ]
        checkpoint_values: list[float] = []

        max_sequence = max((checkpoint.sequence for checkpoint in checkpoints), default=0)
        for checkpoint in checkpoints:
            event_ranking = ranking_by_event_id.get(checkpoint.event_id)
            event_replay = float(event_ranking["replay_value"]) if event_ranking else 0.0
            event_composite = float(event_ranking["composite"]) if event_ranking else 0.0
            sequence_weight = checkpoint.sequence / max(max_sequence, 1)
            restore_value = min(
                1.0, event_replay * 0.45 + event_composite * 0.2 + checkpoint.importance * 0.2 + sequence_weight * 0.15
            )
            checkpoint_values.append(restore_value)
            checkpoint_rankings.append(
                {
                    "checkpoint_id": checkpoint.id,
                    "event_id": checkpoint.event_id,
                    "sequence": checkpoint.sequence,
                    "importance": round(checkpoint.importance, 4),
                    "replay_value": round(event_replay, 4),
                    "restore_value": round(restore_value, 4),
                    "retention_tier": self.retention_tier(
                        replay_value=restore_value,
                        high_severity_count=1 if event_ranking and event_ranking["severity"] >= 0.92 else 0,
                        failure_cluster_count=1 if checkpoint.event_id in representative_failure_ids else 0,
                        behavior_alert_count=0,
                    ),
                }
            )

        checkpoint_rankings.sort(key=lambda item: (-item["restore_value"], -item["importance"], -item["sequence"]))
        session_replay_value = min(
            1.0,
            _mean(top_composites) * 0.55
            + min(len(representative_failure_ids) / 4, 1.0) * 0.2
            + min(len(behavior_alerts) / 3, 1.0) * 0.1
            + _mean(checkpoint_values) * 0.1
            + min(total_cost / 0.25, 1.0) * 0.05,
        )
        retention_tier = self.retention_tier(
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
            "retention_tier": retention_tier,
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
