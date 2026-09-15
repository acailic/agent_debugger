"""Tests for collector/audit/who_when.py — the Who&When benchmark harness."""

from __future__ import annotations

import json
from pathlib import Path

from collector.audit.who_when import (
    _speaker_of,
    evaluate_records,
    history_to_events,
    load_who_when_records,
)

_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "who_when" / "Who&When"


def _fixture(relative: str) -> dict:
    return json.loads((_FIXTURE_ROOT / relative).read_text(encoding="utf-8"))


_RECORD = {
    "question_ID": "rec-1",
    "history": [
        {"content": "Compute the total.", "name": "Planner", "role": "user"},
        {"content": "result = compute(total  # bad syntax", "name": "Verifier_Expert", "role": "assistant"},
        {
            "content": "Traceback (most recent call last):\nSyntaxError: invalid syntax",
            "name": "Terminal",
            "role": "assistant",
        },
        {"content": "Final answer: 2732.", "name": "Planner", "role": "assistant"},
    ],
    "mistake_agent": "Verifier_Expert",
    "mistake_step": "0",
    "mistake_reason": "The Python code is incorrect.",
}


def test_history_to_events_marks_error_messages():
    events = history_to_events(_RECORD)

    assert len(events) == 4
    assert events[0].data["speaker"] == "Planner"
    error_events = [e for e in events if e.event_type.value == "error"]
    assert len(error_events) == 1
    assert error_events[0].data["speaker"] == "Terminal"
    assert error_events[0].id == "rec-1-m2"


def test_load_who_when_records_jsonl(tmp_path: Path):
    path = tmp_path / "sample.jsonl"
    path.write_text(json.dumps(_RECORD) + "\n\n", encoding="utf-8")

    records = load_who_when_records([path])
    assert len(records) == 1
    assert records[0]["question_ID"] == "rec-1"


def test_evaluate_localizes_error_step_deterministically():
    results = evaluate_records([_RECORD])

    assert results["total"] == 1
    assert results["localized_any_step"] == 1
    row = results["rows"][0]
    assert row["predicted_agent"] == "Verifier_Expert"
    assert row["agent_match"] is True
    assert row["step_match"] is True


def test_evaluate_counts_miss_when_agent_differs():
    record = dict(_RECORD, mistake_agent="Planner", mistake_step="1")
    results = evaluate_records([record])

    row = results["rows"][0]
    assert row["agent_match"] is False
    assert row["step_match"] is False
    assert results["agent_accuracy"] == 0.0
    assert results["step_accuracy"] == 0.0


def test_evaluate_handles_unlocalizable_records():
    quiet = {
        "question_ID": "rec-quiet",
        "history": [{"content": "hi", "name": "Planner", "role": "user"}],
        "mistake_agent": "Planner",
        "mistake_step": "9",
    }
    results = evaluate_records([quiet])

    assert results["localized_any_step"] == 0
    assert results["rows"][0]["predicted_agent"] is None


def test_evaluate_empty_input():
    results = evaluate_records([])
    assert results["total"] == 0
    assert results["agent_accuracy"] == 0.0
    assert results["rows"] == []


# ── speaker extraction: name OR role, with role-variant normalization ────────

def test_speaker_of_prefers_name_over_role():
    assert _speaker_of({"name": "Coder", "role": "assistant"}) == "Coder"


def test_speaker_of_falls_back_to_role_when_name_null():
    assert _speaker_of({"name": None, "role": "WebSurfer"}) == "WebSurfer"
    assert _speaker_of({"content": "hi", "role": "WebSurfer"}) == "WebSurfer"


def test_speaker_of_strips_role_parenthetical_variants():
    assert _speaker_of({"name": None, "role": "Orchestrator (thought)"}) == "Orchestrator"
    assert _speaker_of({"name": None, "role": "Orchestrator (-> WebSurfer)"}) == "Orchestrator"
    assert _speaker_of({"name": None, "role": "Orchestrator"}) == "Orchestrator"


def test_speaker_of_defaults_to_unknown():
    assert _speaker_of({}) == "unknown"
    assert _speaker_of({"name": None, "role": ""}) == "unknown"


def test_fixture_role_speaker_used_for_events_and_attribution():
    record = _fixture("Hand-Crafted/fx_hc_role.json")

    events = history_to_events(record)
    assert [event.data["speaker"] for event in events] == ["human", "WebSurfer", "Orchestrator"]

    results = evaluate_records([record])
    row = results["rows"][0]
    # The error surfaces in the Orchestrator's message; the responsible
    # message is the one immediately before it (WebSurfer's only message).
    assert row["predicted_agent"] == "WebSurfer"
    assert row["agent_match"] is True
    # WebSurfer's only message is index 0 (0-based) among its own messages.
    assert row["predicted_step"] == 0
    assert row["step_match"] is True


def test_fixture_role_variants_normalize_to_base_name():
    record = _fixture("Hand-Crafted/fx_hc_variant.json")

    events = history_to_events(record)
    assert [event.data["speaker"] for event in events] == [
        "human",
        "Orchestrator",
        "Coder",
        "Orchestrator",
        "Orchestrator",
        "WebSurfer",
    ]

    results = evaluate_records([record])
    row = results["rows"][0]
    assert row["predicted_agent"] == "Orchestrator"
    # Prediction: the message right before the error signal — the
    # delegation ask, Orchestrator's 2nd own message -> 0-based index 1.
    assert row["predicted_step"] == 1
    assert row["truth_step"] == 1
    assert row["step_match"] is True


# ── 0-based step indexing, agent and global scope ───────────────────────────

def test_fixture_agent_scope_step_is_zero_based():
    record = _fixture("Algorithm-Generated/fx_ag_multi.json")

    results = evaluate_records([record], step_scope="agent")
    row = results["rows"][0]
    assert row["predicted_agent"] == "Coder"
    # Prediction is the message before the traceback (Coder's 1st own
    # message) -> 0-based index 0; the annotation agrees.
    assert row["predicted_step"] == 0
    assert row["truth_step"] == 0
    assert row["step_match"] is True


def test_fixture_global_scope_step_is_zero_based():
    # The predicted mistake message (right before the traceback) sits at
    # whole-history index 1 (0-based).
    record = dict(_fixture("Algorithm-Generated/fx_ag_multi.json"), mistake_step="1")

    results = evaluate_records([record], step_scope="global")
    row = results["rows"][0]
    assert row["predicted_step"] == 1
    assert row["step_match"] is True
