"""Who&When benchmark harness.

Evaluates a deterministic, trace-derived failure-localization heuristic
against the public Who&When benchmark (Zhang et al., ICML 2025,
https://github.com/mingyin1/Agents_Failure_Attribution — dataset also on
Hugging Face as ``Kevin355/Who_and_When``): 184 annotated failure logs
from LLM multi-agent systems, each labeling the failure-responsible agent
(``mistake_agent``) and the decisive error step (``mistake_step``).

This harness is a standalone text-marker heuristic. It does not invoke
``SessionAuditEngine``, ``CausalAnalyzer``, or any native captured
evidence; its scores are not native-engine accuracy.

Record schema (one JSON object per line)::

    {
      "question_ID": "...",
      "history": [{"content": "...", "name": "Speaker_Expert", "role": "assistant"}, ...],
      "mistake_agent": "Speaker_Expert",
      "mistake_step": "3",
      "mistake_reason": "..."
    }

Step indexing — upstream convention (default ``step_scope="global"``):
``mistake_step`` is the 0-based index of the erroneous message in the
WHOLE conversation. The pinned upstream inference prompt
(Agents_Failure_Attribution @ b2bae5c5b06d681d04ea5e9b63b7a30525c04925,
``Automated_FA/Lib/utils.py``) numbers every entry of the conversation
("If the second speech by 'agent a' contains the mistake, the step number
is 3"). Empirical check on the 184-record corpus agrees: every annotation
is in range globally, while 95/184 would be out of range under a
per-agent reading. ``step_scope="agent"`` (index among the mistake
agent's own messages) is retained ONLY to reproduce the superseded
2026-09-15 result, which was produced under that misreading.

Scoring contract — exact and independent: agent accuracy requires exact
speaker-name equality; step accuracy requires the exact integer and is
scored independently of the agent; joint accuracy requires both. The
denominator for every rate is the total record count, including
abstentions (records with no error marker yield no prediction). The
pinned upstream evaluator (``Automated_FA/evaluate.py``) instead scores
agent and step by substring membership, so the paper's 53.5%/14.2%
LLM-judge numbers are context, not a matched comparison.

Speakers: Algorithm-Generated records carry the speaker in
``history[].name``; Hand-Crafted records leave ``name`` null and carry it
in ``history[].role`` instead, including parenthetical variants such as
``Orchestrator (thought)`` — the trailing parenthetical is stripped at
read time so the speaker matches the ``mistake_agent`` annotations.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from agent_debugger_sdk.core.events import EventType, TraceEvent

#: Upstream revision the indexing convention and scoring reference. The
#: seeding script pins its fetch to this commit.
UPSTREAM_REPO = "https://github.com/mingyin1/Agents_Failure_Attribution"
UPSTREAM_COMMIT = "b2bae5c5b06d681d04ea5e9b63b7a30525c04925"

#: Substrings that mark a history message as an error/failure signal when
#: converting conversation logs to trace events. Tracebacks plus the common
#: runtime-log error phrasings (AutoGen-style tool failures, raised
#: exceptions, non-zero exits) — still pure substring matches, no semantics.
_ERROR_MARKERS = (
    "Traceback (most recent call last):",
    "SyntaxError",
    "Execution failed",
    "Error:",
    "error:",
    "exited with",
    "failed to",
    "ERROR",
    "encountered an error",
    "Exception",
)

#: Strips one trailing parenthetical from a role-derived speaker name,
#: e.g. "Orchestrator (thought)" -> "Orchestrator".
_ROLE_PARENTHETICAL = re.compile(r"\s*\([^)]*\)$")

#: Step-index interpretation. "global" is the upstream convention and the
#: default; "agent" is the superseded 2026-09-15 misreading, kept only to
#: reproduce that legacy result.
SUPPORTED_STEP_SCOPES = ("global", "agent")
DEFAULT_STEP_SCOPE = "global"


def _speaker_of(message: dict[str, Any]) -> str:
    """name when present; otherwise role with one trailing parenthetical stripped."""
    name = message.get("name")
    if name:
        return str(name)
    role = str(message.get("role") or "").strip()
    if role:
        return _ROLE_PARENTHETICAL.sub("", role).strip() or role
    return "unknown"


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


def _truth_step_of(record: dict[str, Any]) -> int | None:
    """Parsed annotation step, or None when it is not an integer string."""
    try:
        return int(str(record.get("mistake_step") or ""))
    except (TypeError, ValueError):
        return None


def validate_annotations(
    records: list[dict[str, Any]], *, step_scope: str = DEFAULT_STEP_SCOPE
) -> dict[str, Any]:
    """Check annotations against the active step-index convention.

    ``invalid`` lists records whose ``mistake_step`` is not an integer or is
    out of range for the active scope; a published run must report zero of
    these. ``speaker_mismatches`` (global scope only) lists records where the
    message at the annotated index was spoken by someone other than
    ``mistake_agent`` — measured upstream annotation noise (6/184 on the
    pinned corpus), reported but not fatal.
    """
    invalid: list[dict[str, Any]] = []
    speaker_mismatches: list[dict[str, Any]] = []

    for record in records:
        question_id = str(record.get("question_ID") or record.get("question_id") or "?")
        history = record.get("history") or []
        truth_agent = str(record.get("mistake_agent") or "")
        truth_step = _truth_step_of(record)

        if truth_step is None:
            invalid.append(
                {"question_ID": question_id, "issue": "non_integer_step",
                 "mistake_step": record.get("mistake_step")}
            )
            continue

        if step_scope == "global":
            in_range = 0 <= truth_step < len(history)
        else:
            own = [m for m in history if _speaker_of(m) == truth_agent]
            in_range = 0 <= truth_step < len(own)
        if not in_range:
            invalid.append(
                {"question_ID": question_id, "issue": "step_out_of_range",
                 "mistake_step": truth_step, "history_len": len(history),
                 "scope": step_scope}
            )
            continue

        if step_scope == "global" and _speaker_of(history[truth_step]) != truth_agent:
            speaker_mismatches.append(
                {"question_ID": question_id, "annotated_step": truth_step,
                 "mistake_agent": truth_agent,
                 "speaker_at_step": _speaker_of(history[truth_step])}
            )

    return {
        "step_scope": step_scope,
        "records": len(records),
        "invalid": invalid,
        "invalid_count": len(invalid),
        "speaker_mismatches": speaker_mismatches,
        "speaker_mismatch_count": len(speaker_mismatches),
    }


def history_to_events(record: dict[str, Any]) -> list[TraceEvent]:
    """Convert one Who&When conversation history into trace events.

    Each history message becomes an AGENT_TURN carrying the speaker and
    content; messages containing traceback/error markers additionally
    become ERROR events so failure localization has deterministic failure
    signals to work with.
    """
    question_id = str(record.get("question_ID") or record.get("question_id") or "who-when")
    events: list[TraceEvent] = []
    for index, message in enumerate(record.get("history", [])):
        speaker = _speaker_of(message)
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
    """Predict the mistake event for a conversation-only trace.

    Deterministic attribution heuristic for post-hoc conversation logs:
    the responsible agent's erroneous message usually PRECEDES the first
    visible error signal — the error itself typically surfaces in a
    downstream agent's message. So the prediction is the message
    immediately before the first ERROR event; when the first message IS the
    error signal, that message itself is the prediction.

    Returns (mistake_event_id, first_failure_event_id); (None, None) when
    the conversation contains no error signal at all (an abstention).
    """
    first_error_idx = next(
        (idx for idx, event in enumerate(events) if event.event_type == EventType.ERROR),
        None,
    )
    if first_error_idx is None:
        return None, None
    mistake_idx = max(first_error_idx - 1, 0)
    return events[mistake_idx].id, events[first_error_idx].id


def _step_index_of(
    event_id: str | None, events: list[TraceEvent], step_scope: str
) -> tuple[str | None, int | None]:
    """Map an event id back to (speaker, 0-based step index)."""
    if event_id is None:
        return None, None
    target = next((event for event in events if event.id == event_id), None)
    if target is None:
        return None, None
    speaker = str((target.data or {}).get("speaker") or target.name or "unknown")
    if step_scope == "global":
        return speaker, next(
            (idx for idx, event in enumerate(events) if event.id == event_id), None
        )
    same_speaker = [
        event for event in events
        if str((event.data or {}).get("speaker") or event.name or "unknown") == speaker
    ]
    for idx, event in enumerate(same_speaker):
        if event.id == event_id:
            return speaker, idx
    return speaker, None


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": round(numerator / denominator, 4) if denominator else 0.0,
    }


def evaluate_records(
    records: list[dict[str, Any]], *, step_scope: str = DEFAULT_STEP_SCOPE
) -> dict[str, Any]:
    """Score deterministic failure attribution against the annotations.

    Agent and step are scored independently by exact equality; joint
    requires both. Every rate's denominator is the total record count,
    including abstentions. See the module docstring for the pinned
    upstream conventions this contract follows.
    """
    if step_scope not in SUPPORTED_STEP_SCOPES:
        raise ValueError(f"step_scope must be one of {SUPPORTED_STEP_SCOPES}, got {step_scope!r}")

    rows: list[dict[str, Any]] = []
    agent_hits = 0
    step_hits = 0
    joint_hits = 0
    localized = 0

    for record in records:
        question_id = str(record.get("question_ID") or record.get("question_id") or "?")
        events = history_to_events(record)
        first_bad, _first_failure = _localize_first_bad_step(events)
        predicted_id = first_bad or _first_failure
        predicted_agent, predicted_step = _step_index_of(predicted_id, events, step_scope)

        truth_agent = str(record.get("mistake_agent") or "")
        truth_step = _truth_step_of(record)

        abstained = predicted_id is None
        agent_match = (not abstained) and bool(truth_agent) and predicted_agent == truth_agent
        step_match = (not abstained) and predicted_step is not None and predicted_step == truth_step
        joint_match = agent_match and step_match

        if not abstained:
            localized += 1
        if agent_match:
            agent_hits += 1
        if step_match:
            step_hits += 1
        if joint_match:
            joint_hits += 1

        rows.append(
            {
                "question_ID": question_id,
                "truth_agent": truth_agent,
                "truth_step": truth_step,
                "predicted_agent": predicted_agent,
                "predicted_step": predicted_step,
                "abstained": abstained,
                "agent_match": agent_match,
                "step_match": step_match,
                "joint_match": joint_match,
            }
        )

    total = len(records)
    abstained_count = total - localized
    return {
        "step_scope": step_scope,
        "total": total,
        "localized": localized,
        "abstained": abstained_count,
        "agent_exact": agent_hits,
        "step_exact": step_hits,
        "joint_exact": joint_hits,
        "metrics": {
            "agent_accuracy_exact": _rate(agent_hits, total),
            "step_accuracy_exact_independent": _rate(step_hits, total),
            "joint_accuracy_exact": _rate(joint_hits, total),
            "abstention_rate": _rate(abstained_count, total),
        },
        "validation": validate_annotations(records, step_scope=step_scope),
        "rows": rows,
    }
