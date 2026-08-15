"""Who&When benchmark harness.

Evaluates the audit engine's deterministic failure localization against
the public Who&When benchmark (Zhang et al., ICML 2025,
https://github.com/mingyin1/Agents_Failure_Attribution — dataset also on
Hugging Face as ``Kevin355/Who_and_When``): 184 annotated failure logs
from LLM multi-agent systems, each labeling the failure-responsible agent
(``mistake_agent``) and the decisive error step (``mistake_step``).

The benchmark's own LLM-judge methods reach 53.5% agent accuracy and only
14.2% step accuracy; this harness measures what deterministic
trace-derived attribution achieves on the same annotations.

Record schema (one JSON object per line)::

    {
      "question_ID": "...",
      "history": [{"content": "...", "name": "Speaker_Expert", "role": "assistant"}, ...],
      "mistake_agent": "Speaker_Expert",
      "mistake_step": "3",
      "mistake_reason": "..."
    }

Step indexing: ``mistake_step`` is interpreted as the 1-based index of the
erroneous message among the messages spoken by ``mistake_agent`` (the
benchmark's per-agent step convention; switch ``step_scope="global"`` for
whole-history indexing).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from agent_debugger_sdk.core.events import EventType, TraceEvent
from collector.audit import SessionAuditEngine

#: Substrings that mark a history message as an error/failure signal when
#: converting conversation logs to trace events. Tracebacks and explicit
#: error markers only — plain mentions of the word in prose are too noisy.
_ERROR_MARKERS = ("Traceback (most recent call last):", "SyntaxError", "Execution failed")


def load_who_when_records(paths: Iterable[Path]) -> list[dict[str, Any]]:
    """Load benchmark records from JSONL file(s)."""
    records: list[dict[str, Any]] = []
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def history_to_events(record: dict[str, Any]) -> list[TraceEvent]:
    """Convert one Who&When conversation history into trace events.

    Each history message becomes an AGENT_TURN carrying the speaker and
    content; messages containing traceback/error markers additionally
    become ERROR events so the audit engine's failure localization has
    deterministic failure signals to work with.
    """
    question_id = str(record.get("question_ID") or record.get("question_id") or "who-when")
    events: list[TraceEvent] = []
    for index, message in enumerate(record.get("history", [])):
        speaker = str(message.get("name") or "unknown")
        content = str(message.get("content") or "")
        is_error = any(marker in content for marker in _ERROR_MARKERS)
        events.append(
            TraceEvent(
                id=f"{question_id}-m{index}",
                session_id=question_id,
                event_type=EventType.ERROR if is_error else EventType.AGENT_TURN,
                name=speaker,
                data={"speaker": speaker, "content": content},
                importance=0.9 if is_error else 0.5,
            )
        )
    return events


def _localize_first_bad_step(
    events: list[TraceEvent],
) -> tuple[str | None, str | None]:
    """Run the audit engine and return (first_bad_event_id, first_failure_event_id)."""
    report = SessionAuditEngine().audit(events)
    where = report.get("questions", {}).get("where_it_failed", {}) or {}
    return where.get("first_bad_decision"), where.get("first_failure")


def _step_index_of(
    event_id: str | None, events: list[TraceEvent], step_scope: str
) -> tuple[str | None, int | None]:
    """Map an event id back to (speaker, 1-based step index)."""
    if event_id is None:
        return None, None
    target = next((event for event in events if event.id == event_id), None)
    if target is None:
        return None, None
    speaker = str((target.data or {}).get("speaker") or target.name or "unknown")
    if step_scope == "global":
        return speaker, next(
            (idx + 1 for idx, event in enumerate(events) if event.id == event_id), None
        )
    same_speaker = [
        event for event in events
        if str((event.data or {}).get("speaker") or event.name or "unknown") == speaker
    ]
    for idx, event in enumerate(same_speaker):
        if event.id == event_id:
            return speaker, idx + 1
    return speaker, None


def evaluate_records(
    records: list[dict[str, Any]], *, step_scope: str = "agent"
) -> dict[str, Any]:
    """Score deterministic failure attribution against the annotations.

    Returns aggregate agent-level and step-level accuracy plus per-record
    rows for inspection. A prediction only counts at step level when both
    the agent and the step match the annotation.
    """
    rows: list[dict[str, Any]] = []
    agent_hits = 0
    step_hits = 0
    localized = 0

    for record in records:
        question_id = str(record.get("question_ID") or record.get("question_id") or "?")
        events = history_to_events(record)
        first_bad, first_failure = _localize_first_bad_step(events)
        predicted_id = first_bad or first_failure
        predicted_agent, predicted_step = _step_index_of(predicted_id, events, step_scope)

        truth_agent = str(record.get("mistake_agent") or "")
        try:
            truth_step = int(str(record.get("mistake_step") or "0"))
        except ValueError:
            truth_step = None

        agent_match = bool(truth_agent) and predicted_agent == truth_agent
        step_match = agent_match and predicted_step is not None and predicted_step == truth_step

        if predicted_id is not None:
            localized += 1
        if agent_match:
            agent_hits += 1
        if step_match:
            step_hits += 1

        rows.append(
            {
                "question_ID": question_id,
                "truth_agent": truth_agent,
                "truth_step": truth_step,
                "predicted_agent": predicted_agent,
                "predicted_step": predicted_step,
                "agent_match": agent_match,
                "step_match": step_match,
            }
        )

    total = len(records)
    return {
        "total": total,
        "localized_any_step": localized,
        "agent_accuracy": round(agent_hits / total, 4) if total else 0.0,
        "step_accuracy": round(step_hits / total, 4) if total else 0.0,
        "step_scope": step_scope,
        "rows": rows,
    }
