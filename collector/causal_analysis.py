"""Causal analysis: BFS-based candidate ranking for failure events."""

from __future__ import annotations

from typing import Any

from agent_debugger_sdk.core.events import EventType, TraceEvent


def _event_value(event: TraceEvent | None, key: str, default: Any = None) -> Any:
    if event is None:
        return default
    if hasattr(event, key):
        return getattr(event, key)
    return event.data.get(key, default)


class CausalAnalyzer:
    """Walk the event graph to surface the most likely upstream causes of failures."""

    def __init__(self, severity_weights: dict[EventType, float] | None = None) -> None:
        if severity_weights is None:
            severity_weights = {
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
        self.severity_weights = severity_weights

    # ------------------------------------------------------------------
    # Shared helpers (also needed by FailureDiagnostics)
    # ------------------------------------------------------------------

    def relation_label(self, relation: str) -> str:
        labels = {
            "parent": "parent link",
            "upstream": "upstream dependency",
            "evidence": "evidence provenance",
            "related": "related event",
            "inferred_tool_call": "inferred tool invocation",
            "inferred_decision": "inferred decision",
            "inferred_guardrail": "inferred guardrail",
            "inferred_policy": "inferred prompt policy",
            "inferred_llm_response": "inferred model output",
            "inferred_tool_result": "inferred tool result",
        }
        return labels.get(relation, relation.replace("_", " "))

    def severity(self, event: TraceEvent) -> float:
        """Compute an event severity score."""
        sev = self.severity_weights.get(event.event_type, 0.3)
        if event.event_type == EventType.DECISION:
            confidence = float(_event_value(event, "confidence", 0.5) or 0.5)
            evidence = _event_value(event, "evidence", []) or []
            sev += (1 - confidence) * 0.25
            if not evidence:
                sev += 0.08
        if event.event_type == EventType.TOOL_RESULT and _event_value(event, "error"):
            sev += 0.28
        if event.event_type == EventType.SAFETY_CHECK and _event_value(event, "outcome", "pass") != "pass":
            sev += 0.15
        if event.event_type == EventType.LLM_RESPONSE:
            sev += min(float(_event_value(event, "cost_usd", 0.0) or 0.0) / 0.05, 0.12)
        return min(sev, 1.0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clip(self, value: Any, limit: int = 120) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return f"{text[: limit - 1].rstrip()}…"

    def _find_previous_event(
        self,
        events: list[TraceEvent],
        *,
        start_index: int,
        predicate,
        max_distance: int = 6,
    ) -> TraceEvent | None:
        window_start = max(0, start_index - max_distance)
        for index in range(start_index - 1, window_start - 1, -1):
            event = events[index]
            if predicate(event):
                return event
        return None

    def iter_direct_causes(
        self,
        event: TraceEvent,
        *,
        events: list[TraceEvent],
        id_lookup: dict[str, TraceEvent],
        index_lookup: dict[str, int],
    ) -> list[tuple[TraceEvent, str, bool, float]]:
        direct_causes: list[tuple[TraceEvent, str, bool, float]] = []
        seen_ids: set[str] = set()
        event_index = index_lookup.get(event.id, 0)

        def add(event_id: str | None, relation: str, explicit: bool, weight: float) -> None:
            if not event_id or event_id == event.id or event_id in seen_ids:
                return
            cause = id_lookup.get(event_id)
            if cause is None:
                return
            seen_ids.add(event_id)
            direct_causes.append((cause, relation, explicit, weight))

        add(event.parent_id, "parent", True, 0.86)

        for upstream_id in _event_value(event, "upstream_event_ids", getattr(event, "upstream_event_ids", [])) or []:
            add(upstream_id, "upstream", True, 0.98)
        for evidence_id in _event_value(event, "evidence_event_ids", []) or []:
            add(evidence_id, "evidence", True, 0.94)
        for related_id in _event_value(event, "related_event_ids", []) or []:
            add(related_id, "related", True, 0.76)

        tool_name = _event_value(event, "tool_name", "")
        previous_decision = self._find_previous_event(
            events,
            start_index=event_index,
            predicate=lambda candidate: candidate.event_type == EventType.DECISION,
            max_distance=6,
        )
        previous_policy = self._find_previous_event(
            events,
            start_index=event_index,
            predicate=lambda candidate: candidate.event_type == EventType.PROMPT_POLICY,
            max_distance=8,
        )
        previous_guardrail = self._find_previous_event(
            events,
            start_index=event_index,
            predicate=lambda candidate: (
                candidate.event_type in {EventType.SAFETY_CHECK, EventType.REFUSAL, EventType.POLICY_VIOLATION}
            ),
            max_distance=6,
        )
        previous_llm_response = self._find_previous_event(
            events,
            start_index=event_index,
            predicate=lambda candidate: candidate.event_type == EventType.LLM_RESPONSE,
            max_distance=5,
        )
        previous_tool_call = self._find_previous_event(
            events,
            start_index=event_index,
            predicate=lambda candidate: (
                candidate.event_type == EventType.TOOL_CALL
                and bool(tool_name)
                and _event_value(candidate, "tool_name", "") == tool_name
            ),
            max_distance=6,
        )
        previous_tool_result = self._find_previous_event(
            events,
            start_index=event_index,
            predicate=lambda candidate: (
                candidate.event_type == EventType.TOOL_RESULT
                and bool(tool_name)
                and _event_value(candidate, "tool_name", "") == tool_name
            ),
            max_distance=6,
        )

        if event.event_type == EventType.DECISION:
            add(previous_llm_response.id if previous_llm_response else None, "inferred_llm_response", False, 0.6)
            add(previous_guardrail.id if previous_guardrail else None, "inferred_guardrail", False, 0.52)

        if event.event_type == EventType.TOOL_RESULT and bool(_event_value(event, "error")):
            add(previous_tool_call.id if previous_tool_call else None, "inferred_tool_call", False, 0.82)
            add(previous_decision.id if previous_decision else None, "inferred_decision", False, 0.72)

        if event.event_type in {EventType.ERROR, EventType.REFUSAL, EventType.POLICY_VIOLATION}:
            add(previous_decision.id if previous_decision else None, "inferred_decision", False, 0.74)
            add(previous_guardrail.id if previous_guardrail else None, "inferred_guardrail", False, 0.8)
            add(previous_policy.id if previous_policy else None, "inferred_policy", False, 0.66)
            add(previous_tool_result.id if previous_tool_result else None, "inferred_tool_result", False, 0.62)

        if event.event_type == EventType.SAFETY_CHECK and _event_value(event, "outcome", "pass") != "pass":
            add(previous_decision.id if previous_decision else None, "inferred_decision", False, 0.68)
            add(previous_policy.id if previous_policy else None, "inferred_policy", False, 0.78)

        if event.event_type == EventType.BEHAVIOR_ALERT:
            add(previous_decision.id if previous_decision else None, "inferred_decision", False, 0.62)
            add(previous_tool_call.id if previous_tool_call else None, "inferred_tool_call", False, 0.72)

        return direct_causes

    def candidate_rationale(self, event: TraceEvent, relation: str, explicit: bool) -> str:
        relation_label = self.relation_label(relation)
        rationale = f"{'Explicit' if explicit else 'Inferred'} {relation_label}"

        if event.event_type == EventType.DECISION:
            confidence = float(_event_value(event, "confidence", 0.5) or 0.5)
            evidence = _event_value(event, "evidence", []) or []
            if confidence < 0.4:
                rationale += f"; low confidence {confidence:.2f}"
            if not evidence:
                rationale += "; missing evidence"
        elif event.event_type == EventType.TOOL_RESULT and _event_value(event, "error"):
            rationale += f"; tool error {self._clip(_event_value(event, 'error', ''), 60)}"
        elif event.event_type == EventType.ERROR:
            rationale += f"; {_event_value(event, 'error_type', 'runtime error')}"
        elif event.event_type == EventType.SAFETY_CHECK:
            rationale += f"; outcome {_event_value(event, 'outcome', 'pass')}"
        elif event.event_type == EventType.REFUSAL:
            rationale += f"; risk {_event_value(event, 'risk_level', 'unknown')}"

        return rationale

    def rank_failure_candidates(
        self,
        failure_event: TraceEvent,
        *,
        events: list[TraceEvent],
        id_lookup: dict[str, TraceEvent],
        index_lookup: dict[str, int],
        ranking_by_event_id: dict[str, dict[str, Any]],
        event_headline_fn,
    ) -> list[dict[str, Any]]:
        """Return the top-3 upstream suspects for *failure_event* via BFS."""
        candidate_map: dict[str, dict[str, Any]] = {}
        queue: list[tuple[TraceEvent, int, float, list[str]]] = [(failure_event, 0, 1.0, [failure_event.id])]

        while queue:
            current_event, depth, path_strength, path = queue.pop(0)
            if depth >= 3:
                continue

            for cause, relation, explicit, relation_weight in self.iter_direct_causes(
                current_event,
                events=events,
                id_lookup=id_lookup,
                index_lookup=index_lookup,
            ):
                next_path = [*path, cause.id]
                ranking = ranking_by_event_id.get(cause.id, {})
                severity = float(ranking.get("severity", self.severity(cause)))
                composite = float(ranking.get("composite", severity))
                depth_bonus = max(0.0, 0.1 - depth * 0.03)
                decision_penalty = 0.0
                if cause.event_type == EventType.DECISION:
                    confidence = float(_event_value(cause, "confidence", 0.5) or 0.5)
                    decision_penalty += (1 - confidence) * 0.12
                    if not (_event_value(cause, "evidence", []) or []):
                        decision_penalty += 0.06

                score = min(
                    1.0,
                    path_strength * relation_weight * 0.42
                    + severity * 0.22
                    + composite * 0.18
                    + float(cause.importance or 0.0) * 0.08
                    + depth_bonus
                    + decision_penalty,
                )

                existing = candidate_map.get(cause.id)
                candidate_payload = {
                    "event_id": cause.id,
                    "event_type": str(cause.event_type),
                    "headline": event_headline_fn(cause),
                    "score": round(score, 4),
                    "causal_depth": depth + 1,
                    "relation": relation,
                    "relation_label": self.relation_label(relation),
                    "explicit": explicit,
                    "supporting_event_ids": next_path,
                    "rationale": self.candidate_rationale(cause, relation, explicit),
                }
                if existing is None or score > float(existing["score"]):
                    candidate_map[cause.id] = candidate_payload
                    queue.append((cause, depth + 1, path_strength * relation_weight, next_path))

        return sorted(candidate_map.values(), key=lambda item: (-float(item["score"]), item["causal_depth"]))[:3]
