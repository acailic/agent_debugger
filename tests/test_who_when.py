"""Tests for collector/audit/who_when.py — the Who&When benchmark harness.

Contract under test: global 0-based step indexing (pinned upstream
convention), exact independent agent/step scoring, joint accuracy,
abstention, and annotation validation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from collector.audit.who_when import (
    _speaker_of,
    evaluate_records,
    history_to_events,
    load_who_when_records,
    validate_annotations,
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
    # Verifier_Expert's erroneous message sits at global index 1.
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
    assert error_events[0].data["speaker"] == "Terminal"
    assert error_events[0].id == "rec-1-m2"


def test_load_who_when_records_jsonl(tmp_path: Path):
    path = tmp_path / "sample.jsonl"
    path.write_text(json.dumps(_RECORD) + "\n\n", encoding="utf-8")

    records = load_who_when_records([path])
    assert len(records) == 1
    assert records[0]["question_ID"] == "rec-1"


def test_default_scope_is_global_and_localizes_error_step():
    results = evaluate_records([_RECORD])

    assert results["step_scope"] == "global"
    assert results["total"] == 1
    assert results["localized"] == 1
    assert results["abstained"] == 0
    row = results["rows"][0]
    assert row["predicted_agent"] == "Verifier_Expert"
    assert row["predicted_step"] == 1
    assert row["agent_match"] is True
    assert row["step_match"] is True
    assert row["joint_match"] is True
    assert results["metrics"]["agent_accuracy_exact"] == {
        "numerator": 1, "denominator": 1, "value": 1.0,
    }
    assert results["metrics"]["joint_accuracy_exact"]["numerator"] == 1


def test_step_is_scored_independently_of_agent():
    # Truth agent is wrong but the global step index is right: independent
    # step accuracy must credit the step even though agent and joint miss.
    record = dict(_RECORD, mistake_agent="Planner")
    results = evaluate_records([record])

    row = results["rows"][0]
    assert row["agent_match"] is False
    assert row["step_match"] is True
    assert row["joint_match"] is False
    assert results["metrics"]["agent_accuracy_exact"]["numerator"] == 0
    assert results["metrics"]["step_accuracy_exact_independent"]["numerator"] == 1
    assert results["metrics"]["joint_accuracy_exact"]["numerator"] == 0


def test_agent_match_with_wrong_step_scores_agent_but_not_joint():
    record = dict(_RECORD, mistake_step="0")
    results = evaluate_records([record])

    row = results["rows"][0]
    assert row["agent_match"] is True
    assert row["step_match"] is False
    assert row["joint_match"] is False


def test_evaluate_handles_unlocalizable_records():
    quiet = {
        "question_ID": "rec-quiet",
        "history": [{"content": "hi", "name": "Planner", "role": "user"}],
        "mistake_agent": "Planner",
        "mistake_step": "0",
    }
    results = evaluate_records([quiet])

    assert results["localized"] == 0
    assert results["abstained"] == 1
    row = results["rows"][0]
    assert row["abstained"] is True
    assert row["predicted_agent"] is None
    assert row["agent_match"] is False
    assert results["metrics"]["abstention_rate"] == {
        "numerator": 1, "denominator": 1, "value": 1.0,
    }


def test_evaluate_empty_input():
    results = evaluate_records([])
    assert results["total"] == 0
    assert results["metrics"]["agent_accuracy_exact"]["value"] == 0.0
    assert results["rows"] == []


def test_rejects_unknown_step_scope():
    with pytest.raises(ValueError, match="step_scope"):
        evaluate_records([_RECORD], step_scope="utterance")


def test_legacy_agent_scope_still_reproduces_old_protocol():
    # The superseded 2026-09-15 protocol read mistake_step per-agent; keep
    # it reproducible for labeled legacy results only.
    record = dict(_RECORD, mistake_step="0")
    results = evaluate_records([record], step_scope="agent")

    assert results["step_scope"] == "agent"
    row = results["rows"][0]
    assert row["predicted_step"] == 0
    assert row["step_match"] is True


# ── annotation validation (global convention gate) ───────────────────────────

def test_validate_flags_out_of_range_global_steps():
    record = dict(_RECORD, mistake_step="9")
    report = validate_annotations([record])

    assert report["invalid_count"] == 1
    assert report["invalid"][0]["issue"] == "step_out_of_range"
    assert report["invalid"][0]["scope"] == "global"
    assert report["speaker_mismatch_count"] == 0


def test_validate_flags_non_integer_steps():
    record = dict(_RECORD, mistake_step="soon")
    report = validate_annotations([record])

    assert report["invalid_count"] == 1
    assert report["invalid"][0]["issue"] == "non_integer_step"


def test_validate_reports_speaker_mismatch_without_failing():
    # Step in range but spoken by another agent: upstream annotation noise.
    record = dict(_RECORD, mistake_agent="Planner")
    report = validate_annotations([record])

    assert report["invalid_count"] == 0
    assert report["speaker_mismatch_count"] == 1
    assert report["speaker_mismatches"][0]["speaker_at_step"] == "Verifier_Expert"


def test_validate_agent_scope_explains_the_superseded_misreading():
    # A correct global annotation reads out-of-range under the per-agent
    # scope — the defect that invalidated the 2026-09-15 protocol.
    report = validate_annotations([_RECORD], step_scope="agent")

    assert report["invalid_count"] == 1
    assert report["invalid"][0]["issue"] == "step_out_of_range"


def test_validation_is_embedded_in_results():
    record = dict(_RECORD, mistake_step="9")
    results = evaluate_records([record])

    assert results["validation"]["invalid_count"] == 1


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


# ── fixtures: role speakers and global step indexes ──────────────────────────

def test_fixture_role_speaker_used_for_events_and_attribution():
    record = _fixture("Hand-Crafted/fx_hc_role.json")

    events = history_to_events(record)
    assert [event.data["speaker"] for event in events] == ["human", "WebSurfer", "Orchestrator"]

    results = evaluate_records([record])
    row = results["rows"][0]
    # The error surfaces in the Orchestrator's message; the responsible
    # message is the one immediately before it — WebSurfer's only message,
    # which sits at global history index 1.
    assert row["predicted_agent"] == "WebSurfer"
    assert row["agent_match"] is True
    assert row["predicted_step"] == 1
    assert row["truth_step"] == 1
    assert row["joint_match"] is True


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
    # delegation ask at global history index 3.
    assert row["predicted_step"] == 3
    assert row["truth_step"] == 3
    assert row["joint_match"] is True


def test_fixture_global_scope_step_is_zero_based():
    record = _fixture("Algorithm-Generated/fx_ag_multi.json")

    results = evaluate_records([record])
    row = results["rows"][0]
    assert row["predicted_agent"] == "Coder"
    # Prediction is the message before the traceback — global index 1.
    assert row["predicted_step"] == 1
    assert row["truth_step"] == 1
    assert row["joint_match"] is True
