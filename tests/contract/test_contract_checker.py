"""Exercise the CI gate with real types and deliberate contract regressions."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.hooks import check_api_contract as checker
from scripts.hooks.route_contract import extract_frontend_contract

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def contract():
    return extract_frontend_contract(ROOT)


@pytest.fixture(scope="module")
def fixtures():
    return checker.load_payload_fixtures()


def test_core_contract_is_aligned(contract):
    assert checker.check_shared_types(contract) == []


def test_core_field_types_are_aligned(contract):
    assert checker.check_field_types(contract) == []


@pytest.mark.parametrize("interface,field", [("Session", "id"), ("Checkpoint", "sequence")])
def test_required_backend_field_marked_optional_fails(contract, interface, field):
    changed = copy.deepcopy(contract)
    changed["properties"][interface][field]["optional"] = True
    drift, = checker.check_field_types(changed)
    assert drift["type"] == "required_mismatch"
    assert drift["field"] == field
    assert drift["direction"] == "backend_required_ts_optional"


def test_documented_deviation_is_not_drift(contract):
    assert ("SessionSchema", "replay_value") in checker.INTENTIONAL_TS_OPTIONAL
    changed = copy.deepcopy(contract)
    changed["properties"]["Session"]["replay_value"]["optional"] = True
    assert checker.check_field_types(changed) == []


def test_backend_default_with_required_frontend_is_not_drift(contract):
    # Response models always serialize defaulted fields, so a required TS
    # property backed by a defaulted backend field is not drift.
    changed = copy.deepcopy(contract)
    changed["properties"]["ReplayResponse"]["collapsed_segments"]["optional"] = False
    assert checker.check_field_types(changed) == []


@pytest.mark.parametrize("interface,field,direction", [
    ("Session", "ended_at", "backend_nullable_ts_required_non_null"),
    ("Session", "id", "ts_nullable_backend_non_null"),
    ("Checkpoint", "sequence", "ts_nullable_backend_non_null"),
])
def test_nullability_flip_fails(contract, interface, field, direction):
    changed = copy.deepcopy(contract)
    changed["properties"][interface][field]["nullable"] = not changed["properties"][interface][field]["nullable"]
    drifts = [d for d in checker.check_field_types(changed) if d["field"] == field]
    assert {d["type"] for d in drifts} == {"nullability_mismatch"}
    assert drifts[0]["direction"] == direction


def test_nullable_backend_with_optional_frontend_is_not_drift(contract):
    changed = copy.deepcopy(contract)
    changed["properties"]["TraceEvent"]["model"]["nullable"] = False  # stays optional
    assert checker.check_field_types(changed) == []


@pytest.mark.parametrize("interface,field,ts_kind", [
    ("Checkpoint", "sequence", "string"),
    ("Session", "id", "object"),
    ("Session", "tags", "object"),
    ("Checkpoint", "state", "array"),
])
def test_kind_mismatch_fails(contract, interface, field, ts_kind):
    changed = copy.deepcopy(contract)
    changed["properties"][interface][field]["kind"] = ts_kind
    drift, = [d for d in checker.check_field_types(changed) if d["field"] == field]
    assert drift["type"] == "type_kind_mismatch"
    assert drift["ts_kind"] == ts_kind


def test_string_and_literal_union_stay_interchangeable(contract):
    changed = copy.deepcopy(contract)
    changed["properties"]["ReplayResponse"]["mode"]["kind"] = "string"  # backend str
    changed["properties"]["Highlight"]["event_type"]["kind"] = "union"  # backend str
    assert checker.check_field_types(changed) == []


def test_ast_reads_optionality_kinds_and_nullability():
    content = """
    export type Status = 'active' | 'done';
    export interface Example {
      id: string
      count?: number
      tags: string[]
      meta: Record<string, unknown> | null
      status: Status
      literal: 'a' | 'b'
      nested: { inner: string }
      anything?: unknown
      list: Array<{ role: string }>
    }
    """
    properties = extract_frontend_contract(ROOT, types_content=content)["properties"]["Example"]
    assert properties == {
        "id": {"optional": False, "kind": "string", "nullable": False},
        "count": {"optional": True, "kind": "number", "nullable": False},
        "tags": {"optional": False, "kind": "array", "nullable": False},
        "meta": {"optional": False, "kind": "object", "nullable": True},
        "status": {"optional": False, "kind": "union", "nullable": False},
        "literal": {"optional": False, "kind": "union", "nullable": False},
        "nested": {"optional": False, "kind": "object", "nullable": False},
        "anything": {"optional": True, "kind": "unknown", "nullable": False},
        "list": {"optional": False, "kind": "array", "nullable": False},
    }


def test_ts_source_optional_flip_is_drift_beyond_field_names():
    source = (ROOT / "frontend/src/types/index.ts").read_text()
    changed = source.replace("  tags: string[]", "  tags?: string[]", 1)
    contract = extract_frontend_contract(ROOT, types_content=changed)
    assert checker.check_shared_types(contract) == []
    drift, = checker.check_field_types(contract)
    assert drift == {
        "type": "required_mismatch", "model": "SessionSchema", "interface": "Session", "field": "tags",
        "direction": "backend_required_ts_optional",
    }


def test_ts_source_dropped_null_is_drift():
    source = (ROOT / "frontend/src/types/index.ts").read_text()
    changed = source.replace("  ended_at: string | null", "  ended_at: string", 1)
    contract = extract_frontend_contract(ROOT, types_content=changed)
    drift, = [d for d in checker.check_field_types(contract) if d["field"] == "ended_at"]
    assert drift["type"] == "nullability_mismatch"
    assert drift["direction"] == "backend_nullable_ts_required_non_null"


def test_ts_source_kind_change_is_drift():
    source = (ROOT / "frontend/src/types/index.ts").read_text()
    changed = source.replace("  sequence: number", "  sequence: string", 1)
    contract = extract_frontend_contract(ROOT, types_content=changed)
    drift, = [d for d in checker.check_field_types(contract) if d["field"] == "sequence"]
    assert drift == {
        "type": "type_kind_mismatch", "model": "CheckpointSchema", "interface": "Checkpoint",
        "field": "sequence", "backend_kind": "number", "ts_kind": "string",
    }


@pytest.mark.parametrize("value", ["drift", "trace_root"])
def test_missing_event_value_fails(contract, value):
    changed = copy.deepcopy(contract)
    changed["unions"]["EventType"].remove(value)
    assert checker.check_shared_types(changed) == [{
        "type": "enum_mismatch", "union": "EventType",
        "missing_in_frontend": [value], "unexpected_in_frontend": [],
    }]


def test_unknown_event_value_fails(contract):
    changed = copy.deepcopy(contract)
    changed["unions"]["EventType"].append("unknown_event")
    assert checker.check_shared_types(changed)[0]["unexpected_in_frontend"] == ["unknown_event"]


@pytest.mark.parametrize("interface,field", [("Session", "id"), ("TraceEvent", "data"), ("Checkpoint", "sequence")])
def test_missing_shared_field_fails(contract, interface, field):
    changed = copy.deepcopy(contract)
    changed["interfaces"][interface].remove(field)
    drift, = checker.check_shared_types(changed)
    assert drift["interface"] == interface
    assert drift["missing_in_frontend"] == [field]


def test_unsupported_frontend_field_fails(contract):
    changed = copy.deepcopy(contract)
    changed["interfaces"]["Session"].append("nonexistent")
    assert checker.check_shared_types(changed)[0]["missing_in_backend"] == ["nonexistent"]


def test_missing_type_definitions_cannot_pass(contract):
    changed = copy.deepcopy(contract)
    del changed["interfaces"]["Session"]
    del changed["unions"]["EventType"]
    assert {drift["type"] for drift in checker.check_shared_types(changed)} == {"missing_interface", "missing_union"}


def test_ast_reads_indented_fields_and_multiline_union():
    source = (ROOT / "frontend/src/types/index.ts").read_text()
    changed = source.replace("  | 'drift'", "  // removed SDK value for regression test")
    contract = extract_frontend_contract(ROOT, types_content=changed)
    assert "id" in contract["interfaces"]["Session"]
    assert "input_tokens" not in contract["interfaces"]["TraceEvent"]
    assert checker.check_shared_types(contract)[0]["missing_in_frontend"] == ["drift"]


def test_cli_returns_nonzero_on_drift(monkeypatch, capsys, contract):
    changed = copy.deepcopy(contract)
    changed["unions"]["EventType"].remove("drift")
    monkeypatch.setattr(checker, "extract_frontend_contract", lambda _: changed)
    assert checker.main() == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "drift"
    assert result["checked_routes"] > 0
    assert result["checked_field_types"] > 0
    assert result["checked_payloads"] == len(checker.REQUIRED_FIXTURES) + 2


def test_cli_returns_nonzero_on_payload_drift(monkeypatch, capsys, contract, fixtures):
    drifted = copy.deepcopy(fixtures)
    drifted["payloads"]["Checkpoint"]["sequence"] = "not-a-number"
    monkeypatch.setattr(checker, "extract_frontend_contract", lambda _: contract)
    monkeypatch.setattr(checker, "load_payload_fixtures", lambda: drifted)
    assert checker.main() == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "drift"
    assert result["drifts"][0]["type"] == "payload_backend_mismatch"


def test_cli_returns_error_when_fixtures_are_unreadable(monkeypatch, capsys, contract, tmp_path):
    monkeypatch.setattr(checker, "extract_frontend_contract", lambda _: contract)
    monkeypatch.setattr(checker, "FIXTURES_PATH", tmp_path / "missing.json")
    assert checker.main() == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"


def test_cli_returns_nonzero_on_extraction_failure(monkeypatch, capsys):
    def fail(_):
        raise ValueError("missing TypeScript source")
    monkeypatch.setattr(checker, "extract_frontend_contract", fail)
    assert checker.main() == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"
