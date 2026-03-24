"""Failure diagnostics: derive human-readable explanations for failure events."""

from __future__ import annotations

from typing import Any

from agent_debugger_sdk.core.events import EventType, TraceEvent

from .causal_analysis import CausalAnalyzer, _event_value


class FailureDiagnostics:
    """Build structured failure explanations using a :class:`CausalAnalyzer`."""

    def __init__(self, causal: CausalAnalyzer) -> None:
        self._causal = causal

    # ------------------------------------------------------------------
    # Failure classification
    # ------------------------------------------------------------------

    def failure_mode(
        self,
        failure_event: TraceEvent,
        top_candidate: dict[str, Any] | None,
        id_lookup: dict[str, TraceEvent],
    ) -> str:
        if failure_event.event_type == EventType.BEHAVIOR_ALERT:
            alert_type = _event_value(failure_event, "alert_type", "")
            if alert_type == "tool_loop":
                return "looping_behavior"
            return "behavior_anomaly"
        if failure_event.event_type in {EventType.REFUSAL, EventType.SAFETY_CHECK}:
            return "guardrail_block"
        if failure_event.event_type == EventType.POLICY_VIOLATION:
            return "policy_mismatch"
        if failure_event.event_type == EventType.TOOL_RESULT and _event_value(failure_event, "error"):
            if top_candidate:
                candidate_event = id_lookup.get(top_candidate["event_id"])
                if candidate_event and candidate_event.event_type == EventType.DECISION:
                    confidence = float(_event_value(candidate_event, "confidence", 0.5) or 0.5)
                    if confidence < 0.4 or not (_event_value(candidate_event, "evidence", []) or []):
                        return "ungrounded_decision"
            return "tool_execution_failure"
        if failure_event.event_type == EventType.ERROR:
            return "upstream_runtime_error"
        return "diagnostic_review"

    def failure_symptom(self, failure_event: TraceEvent, event_headline_fn) -> str:
        if failure_event.event_type == EventType.TOOL_RESULT:
            return (
                f'Tool "{event_headline_fn(failure_event)}" failed'
                f' with {self._causal._clip(_event_value(failure_event, "error", "unknown error"), 72)}'
            )
        if failure_event.event_type == EventType.ERROR:
            return (
                f'{_event_value(failure_event, "error_type", "RuntimeError")} raised'
                f' with {self._causal._clip(_event_value(failure_event, "error_message", "no message"), 72)}'
            )
        if failure_event.event_type == EventType.REFUSAL:
            return f"Request was refused: {self._causal._clip(_event_value(failure_event, 'reason', 'no reason provided'), 88)}"
        if failure_event.event_type == EventType.POLICY_VIOLATION:
            return f"Policy violation: {self._causal._clip(_event_value(failure_event, 'violation_type', failure_event.name or 'unknown'), 72)}"
        if failure_event.event_type == EventType.BEHAVIOR_ALERT:
            return self._causal._clip(_event_value(failure_event, "signal", failure_event.name or "behavior alert"), 96)
        if failure_event.event_type == EventType.SAFETY_CHECK:
            return (
                f'Safety check "{_event_value(failure_event, "policy_name", "policy")}"'
                f' returned {_event_value(failure_event, "outcome", "pass")}'
            )
        return self._causal._clip(event_headline_fn(failure_event), 96)

    # ------------------------------------------------------------------
    # Likely-cause narrative
    # ------------------------------------------------------------------

    def _likely_cause_text(
        self,
        candidate: dict[str, Any] | None,
        id_lookup: dict[str, TraceEvent],
        event_headline_fn,
    ) -> str:
        if not candidate:
            return "No strong upstream cause was identified from the captured links."
        cause = id_lookup.get(candidate["event_id"])
        if cause is None:
            return "Most likely cause event could not be resolved."

        description = f'{str(cause.event_type).replace("_", " ")} "{event_headline_fn(cause)}"'
        if cause.event_type == EventType.DECISION:
            confidence = float(_event_value(cause, "confidence", 0.5) or 0.5)
            evidence = _event_value(cause, "evidence", []) or []
            evidence_note = "with evidence" if evidence else "without evidence"
            return f"{description} appears upstream via {candidate['relation_label']} at confidence {confidence:.2f} {evidence_note}."
        if cause.event_type == EventType.TOOL_RESULT and _event_value(cause, "error"):
            return f"{description} already failed upstream via {candidate['relation_label']}."
        return f"{description} is the strongest upstream suspect via {candidate['relation_label']}."

    # ------------------------------------------------------------------
    # Public entry-point
    # ------------------------------------------------------------------

    def is_failure_event(self, event: TraceEvent) -> bool:
        """Return whether an event should receive post-hoc diagnosis."""
        return (
            event.event_type == EventType.ERROR
            or event.event_type == EventType.REFUSAL
            or event.event_type == EventType.POLICY_VIOLATION
            or event.event_type == EventType.BEHAVIOR_ALERT
            or (event.event_type == EventType.TOOL_RESULT and bool(_event_value(event, "error")))
            or (
                event.event_type == EventType.SAFETY_CHECK
                and _event_value(event, "outcome", "pass") != "pass"
            )
        )

    def build_failure_explanations(
        self,
        events: list[TraceEvent],
        ranking_by_event_id: dict[str, dict[str, Any]],
        event_headline_fn,
    ) -> list[dict[str, Any]]:
        id_lookup = {event.id: event for event in events}
        index_lookup = {event.id: index for index, event in enumerate(events)}
        explanations: list[dict[str, Any]] = []

        for failure_event in events:
            if not self.is_failure_event(failure_event):
                continue

            candidates = self._causal.rank_failure_candidates(
                failure_event,
                events=events,
                id_lookup=id_lookup,
                index_lookup=index_lookup,
                ranking_by_event_id=ranking_by_event_id,
                event_headline_fn=event_headline_fn,
            )
            top_candidate = candidates[0] if candidates else None
            mode = self.failure_mode(failure_event, top_candidate, id_lookup)
            symptom = self.failure_symptom(failure_event, event_headline_fn)
            likely_cause = self._likely_cause_text(top_candidate, id_lookup, event_headline_fn)
            confidence = float(top_candidate["score"]) if top_candidate else 0.0
            supporting_event_ids = [failure_event.id]
            if top_candidate:
                for event_id in top_candidate["supporting_event_ids"]:
                    if event_id not in supporting_event_ids:
                        supporting_event_ids.append(event_id)

            narrative = symptom
            if top_candidate:
                narrative += f" The strongest upstream suspect is {likely_cause.lower()}"
            else:
                narrative += " Inspect the nearest checkpoint and surrounding decisions to establish the upstream cause."

            explanations.append(
                {
                    "failure_event_id": failure_event.id,
                    "failure_event_type": str(failure_event.event_type),
                    "failure_headline": event_headline_fn(failure_event),
                    "failure_mode": mode,
                    "symptom": symptom,
                    "likely_cause": likely_cause,
                    "likely_cause_event_id": top_candidate["event_id"] if top_candidate else None,
                    "confidence": round(confidence, 4),
                    "supporting_event_ids": supporting_event_ids,
                    "next_inspection_event_id": top_candidate["event_id"] if top_candidate else failure_event.id,
                    "narrative": narrative,
                    "candidates": candidates,
                }
            )

        explanations.sort(key=lambda item: (-item["confidence"], item["failure_event_id"]))
        return explanations
