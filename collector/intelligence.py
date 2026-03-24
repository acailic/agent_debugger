"""Session-level trace analysis and adaptive ranking."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from agent_debugger_sdk.core.events import Checkpoint, EventType, TraceEvent


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
    """Compute replay-centric analysis from session events."""

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

    def _clip(self, value: Any, limit: int = 120) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return f"{text[: limit - 1].rstrip()}…"

    def _relation_label(self, relation: str) -> str:
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

    def _iter_direct_causes(
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

    def _candidate_rationale(self, event: TraceEvent, relation: str, explicit: bool) -> str:
        relation_label = self._relation_label(relation)
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

    def _rank_failure_candidates(
        self,
        failure_event: TraceEvent,
        *,
        events: list[TraceEvent],
        id_lookup: dict[str, TraceEvent],
        index_lookup: dict[str, int],
        ranking_by_event_id: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        candidate_map: dict[str, dict[str, Any]] = {}
        queue: list[tuple[TraceEvent, int, float, list[str]]] = [(failure_event, 0, 1.0, [failure_event.id])]

        while queue:
            current_event, depth, path_strength, path = queue.pop(0)
            if depth >= 3:
                continue

            for cause, relation, explicit, relation_weight in self._iter_direct_causes(
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
                    "headline": self.event_headline(cause),
                    "score": round(score, 4),
                    "causal_depth": depth + 1,
                    "relation": relation,
                    "relation_label": self._relation_label(relation),
                    "explicit": explicit,
                    "supporting_event_ids": next_path,
                    "rationale": self._candidate_rationale(cause, relation, explicit),
                }
                if existing is None or score > float(existing["score"]):
                    candidate_map[cause.id] = candidate_payload
                    queue.append((cause, depth + 1, path_strength * relation_weight, next_path))

        return sorted(candidate_map.values(), key=lambda item: (-float(item["score"]), item["causal_depth"]))[:3]

    def _failure_mode(self, failure_event: TraceEvent, top_candidate: dict[str, Any] | None, id_lookup: dict[str, TraceEvent]) -> str:
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

    def _failure_symptom(self, failure_event: TraceEvent) -> str:
        if failure_event.event_type == EventType.TOOL_RESULT:
            return (
                f'Tool "{self.event_headline(failure_event)}" failed'
                f' with {self._clip(_event_value(failure_event, "error", "unknown error"), 72)}'
            )
        if failure_event.event_type == EventType.ERROR:
            return (
                f'{_event_value(failure_event, "error_type", "RuntimeError")} raised'
                f' with {self._clip(_event_value(failure_event, "error_message", "no message"), 72)}'
            )
        if failure_event.event_type == EventType.REFUSAL:
            return f"Request was refused: {self._clip(_event_value(failure_event, 'reason', 'no reason provided'), 88)}"
        if failure_event.event_type == EventType.POLICY_VIOLATION:
            return f"Policy violation: {self._clip(_event_value(failure_event, 'violation_type', failure_event.name or 'unknown'), 72)}"
        if failure_event.event_type == EventType.BEHAVIOR_ALERT:
            return self._clip(_event_value(failure_event, "signal", failure_event.name or "behavior alert"), 96)
        if failure_event.event_type == EventType.SAFETY_CHECK:
            return (
                f'Safety check "{_event_value(failure_event, "policy_name", "policy")}"'
                f' returned {_event_value(failure_event, "outcome", "pass")}'
            )
        return self._clip(self.event_headline(failure_event), 96)

    def _likely_cause_text(self, candidate: dict[str, Any] | None, id_lookup: dict[str, TraceEvent]) -> str:
        if not candidate:
            return "No strong upstream cause was identified from the captured links."
        cause = id_lookup.get(candidate["event_id"])
        if cause is None:
            return "Most likely cause event could not be resolved."

        description = f'{str(cause.event_type).replace("_", " ")} "{self.event_headline(cause)}"'
        if cause.event_type == EventType.DECISION:
            confidence = float(_event_value(cause, "confidence", 0.5) or 0.5)
            evidence = _event_value(cause, "evidence", []) or []
            evidence_note = "with evidence" if evidence else "without evidence"
            return f"{description} appears upstream via {candidate['relation_label']} at confidence {confidence:.2f} {evidence_note}."
        if cause.event_type == EventType.TOOL_RESULT and _event_value(cause, "error"):
            return f"{description} already failed upstream via {candidate['relation_label']}."
        return f"{description} is the strongest upstream suspect via {candidate['relation_label']}."

    def _build_failure_explanations(
        self,
        events: list[TraceEvent],
        ranking_by_event_id: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        id_lookup = {event.id: event for event in events}
        index_lookup = {event.id: index for index, event in enumerate(events)}
        explanations: list[dict[str, Any]] = []

        for failure_event in events:
            if not self.is_failure_event(failure_event):
                continue

            candidates = self._rank_failure_candidates(
                failure_event,
                events=events,
                id_lookup=id_lookup,
                index_lookup=index_lookup,
                ranking_by_event_id=ranking_by_event_id,
            )
            top_candidate = candidates[0] if candidates else None
            failure_mode = self._failure_mode(failure_event, top_candidate, id_lookup)
            symptom = self._failure_symptom(failure_event)
            likely_cause = self._likely_cause_text(top_candidate, id_lookup)
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
                    "failure_headline": self.event_headline(failure_event),
                    "failure_mode": failure_mode,
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

    def fingerprint(self, event: TraceEvent) -> str:
        """Return a coarse fingerprint used for recurrence clustering."""
        match event.event_type:
            case EventType.ERROR:
                return f"error:{_event_value(event, 'error_type', 'unknown')}:{_event_value(event, 'error_message', '')}"
            case EventType.TOOL_RESULT:
                return f"tool:{_event_value(event, 'tool_name', 'unknown')}:{bool(_event_value(event, 'error'))}"
            case EventType.REFUSAL:
                return f"refusal:{_event_value(event, 'policy_name', 'unknown')}:{_event_value(event, 'risk_level', 'medium')}"
            case EventType.POLICY_VIOLATION:
                return f"policy:{_event_value(event, 'policy_name', 'unknown')}:{_event_value(event, 'violation_type', 'unknown')}"
            case EventType.BEHAVIOR_ALERT:
                return f"alert:{_event_value(event, 'alert_type', 'unknown')}"
            case EventType.SAFETY_CHECK:
                return f"safety:{_event_value(event, 'policy_name', 'unknown')}:{_event_value(event, 'outcome', 'pass')}"
            case EventType.DECISION:
                return f"decision:{_event_value(event, 'chosen_action', 'unknown')}"
            case _:
                return f"{event.event_type}:{event.name}"

    def severity(self, event: TraceEvent) -> float:
        """Compute an event severity score."""
        severity = self.severity_weights.get(event.event_type, 0.3)
        if event.event_type == EventType.DECISION:
            confidence = float(_event_value(event, "confidence", 0.5) or 0.5)
            evidence = _event_value(event, "evidence", []) or []
            severity += (1 - confidence) * 0.25
            if not evidence:
                severity += 0.08
        if event.event_type == EventType.TOOL_RESULT and _event_value(event, "error"):
            severity += 0.28
        if event.event_type == EventType.SAFETY_CHECK and _event_value(event, "outcome", "pass") != "pass":
            severity += 0.15
        if event.event_type == EventType.LLM_RESPONSE:
            severity += min(float(_event_value(event, "cost_usd", 0.0) or 0.0) / 0.05, 0.12)
        return min(severity, 1.0)

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

    def build_live_summary(self, events: list[TraceEvent], checkpoints: list[Checkpoint]) -> dict[str, Any]:
        """Build a live monitoring summary from the current persisted session state."""
        if not events:
            return {
                "event_count": 0,
                "checkpoint_count": len(checkpoints),
                "latest": {
                    "decision_event_id": None,
                    "tool_event_id": None,
                    "safety_event_id": None,
                    "turn_event_id": None,
                    "policy_event_id": None,
                    "checkpoint_id": checkpoints[-1].id if checkpoints else None,
                },
                "rolling_summary": "Awaiting richer live summaries",
                "recent_alerts": [],
            }

        latest_decision = next((event for event in reversed(events) if event.event_type == EventType.DECISION), None)
        latest_tool = next(
            (
                event
                for event in reversed(events)
                if event.event_type in {EventType.TOOL_CALL, EventType.TOOL_RESULT}
            ),
            None,
        )
        latest_safety = next(
            (
                event
                for event in reversed(events)
                if event.event_type in {EventType.SAFETY_CHECK, EventType.REFUSAL, EventType.POLICY_VIOLATION}
            ),
            None,
        )
        latest_turn = next((event for event in reversed(events) if event.event_type == EventType.AGENT_TURN), None)
        latest_policy = next((event for event in reversed(events) if event.event_type == EventType.PROMPT_POLICY), None)

        recent_events = events[-12:]
        recent_alerts: list[dict[str, Any]] = [
            {
                "alert_type": _event_value(event, "alert_type", "behavior_alert"),
                "severity": _event_value(event, "severity", "medium"),
                "signal": _event_value(event, "signal", event.name),
                "event_id": event.id,
                "source": "captured",
            }
            for event in recent_events
            if event.event_type == EventType.BEHAVIOR_ALERT
        ]

        recent_tool_calls = [event for event in recent_events if event.event_type == EventType.TOOL_CALL]
        last_three_tool_calls = recent_tool_calls[-3:]
        if len(last_three_tool_calls) == 3:
            tool_name = _event_value(last_three_tool_calls[-1], "tool_name", "")
            if tool_name and all(_event_value(event, "tool_name", "") == tool_name for event in last_three_tool_calls):
                recent_alerts.append(
                    {
                        "alert_type": "tool_loop",
                        "severity": "high",
                        "signal": f"Three consecutive calls to {tool_name}",
                        "event_id": last_three_tool_calls[-1].id,
                        "source": "derived",
                    }
                )

        recent_guardrails = [
            event
            for event in recent_events
            if (
                event.event_type == EventType.REFUSAL
                or event.event_type == EventType.POLICY_VIOLATION
                or (
                    event.event_type == EventType.SAFETY_CHECK
                    and _event_value(event, "outcome", "pass") != "pass"
                )
            )
        ]
        if len(recent_guardrails) >= 2:
            recent_alerts.append(
                {
                    "alert_type": "guardrail_pressure",
                    "severity": "high" if len(recent_guardrails) >= 3 else "medium",
                    "signal": f"{len(recent_guardrails)} recent blocked or warned actions",
                    "event_id": recent_guardrails[-1].id,
                    "source": "derived",
                }
            )

        recent_policies = [event for event in recent_events if event.event_type == EventType.PROMPT_POLICY]
        unique_policies = {
            _event_value(event, "template_id", event.name)
            for event in recent_policies
            if _event_value(event, "template_id", event.name)
        }
        if len(unique_policies) >= 2:
            recent_alerts.append(
                {
                    "alert_type": "policy_shift",
                    "severity": "medium",
                    "signal": f"{len(unique_policies)} prompt policies active in the recent window",
                    "event_id": recent_policies[-1].id,
                    "source": "derived",
                }
            )

        recent_decisions = [event for event in recent_events if event.event_type == EventType.DECISION]
        last_two_decisions = recent_decisions[-2:]
        if len(last_two_decisions) == 2:
            previous_action = _event_value(last_two_decisions[0], "chosen_action", last_two_decisions[0].name)
            latest_action = _event_value(last_two_decisions[1], "chosen_action", last_two_decisions[1].name)
            if previous_action != latest_action:
                recent_alerts.append(
                    {
                        "alert_type": "strategy_change",
                        "severity": "medium",
                        "signal": f'Decision shifted from "{previous_action}" to "{latest_action}"',
                        "event_id": last_two_decisions[-1].id,
                        "source": "derived",
                    }
                )

        rolling_summary = (
            (_event_value(latest_turn, "state_summary", "") if latest_turn else "")
            or (_event_value(latest_policy, "state_summary", "") if latest_policy else "")
            or (_event_value(latest_decision, "reasoning", "") if latest_decision else "")
            or (recent_alerts[-1]["signal"] if recent_alerts else "Awaiting richer live summaries")
        )

        return {
            "event_count": len(events),
            "checkpoint_count": len(checkpoints),
            "latest": {
                "decision_event_id": latest_decision.id if latest_decision else None,
                "tool_event_id": latest_tool.id if latest_tool else None,
                "safety_event_id": latest_safety.id if latest_safety else None,
                "turn_event_id": latest_turn.id if latest_turn else None,
                "policy_event_id": latest_policy.id if latest_policy else None,
                "checkpoint_id": checkpoints[-1].id if checkpoints else None,
            },
            "rolling_summary": rolling_summary,
            "recent_alerts": recent_alerts[-6:],
        }

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
            replay_value += 0.1 if event.event_type in {EventType.DECISION, EventType.REFUSAL, EventType.POLICY_VIOLATION} else 0.0
            replay_value += 0.1 if bool(_event_value(event, "upstream_event_ids", getattr(event, "upstream_event_ids", []))) else 0.0
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
        failure_explanations = self._build_failure_explanations(events, ranking_by_event_id)
        checkpoint_rankings: list[dict[str, Any]] = []
        total_cost = sum(
            float(_event_value(event, "cost_usd", 0.0) or 0.0)
            for event in events
            if event.event_type == EventType.LLM_RESPONSE
        )
        high_severity_count = sum(1 for ranking in event_rankings if ranking["severity"] >= 0.9)
        top_composites = [ranking["composite"] for ranking in sorted(event_rankings, key=lambda item: item["composite"], reverse=True)[:5]]
        checkpoint_values: list[float] = []

        max_sequence = max((checkpoint.sequence for checkpoint in checkpoints), default=0)
        for checkpoint in checkpoints:
            event_ranking = ranking_by_event_id.get(checkpoint.event_id)
            event_replay = float(event_ranking["replay_value"]) if event_ranking else 0.0
            event_composite = float(event_ranking["composite"]) if event_ranking else 0.0
            sequence_weight = checkpoint.sequence / max(max_sequence, 1)
            restore_value = min(1.0, event_replay * 0.45 + event_composite * 0.2 + checkpoint.importance * 0.2 + sequence_weight * 0.15)
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
        }
