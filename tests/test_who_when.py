"""Tests for collector/audit/who_when.py — the Who&When benchmark harness."""

from __future__ import annotations

import json
from pathlib import Path

from collector.audit.who_when import (
    evaluate_records,
    history_to_events,
    load_who_when_records,
)

_RECORD = {
    "question_ID": "rec-1",
    "history": [
        {"content": "Compute the total.", "name": "Planner", "role": "user"},
        {"content": "Running code.", "name": "Terminal", "role": "assistant"},
        {
            "content": "Traceback (most recent call last):\nSyntaxError: invalid syntax",
            "name": "Verifier_Expert",
            "role": "assistant",
        },
        {"content": "Final answer: 2732.", "name": "Planner", "role": "assistant"},
    ],
    "mistake_agent": "Verifier_Expert",
    "mistake_step": "1",
    "mistake_reason": "The Python code is incorrect.",
}


def test_history_to_events_marks_error_messages():
    events = history_to_events(_RECORD)

    assert len(events) == 4
    assert events[0].data["speaker"] == "Planner"
    error_events = [e for e in events if e.event_type.value == "error"]
    assert len(error_events) == 1
    assert error_events[0].data["speaker"] == "Verifier_Expert"
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
    record = dict(_RECORD, mistake_agent="Planner", mistake_step="2")
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
