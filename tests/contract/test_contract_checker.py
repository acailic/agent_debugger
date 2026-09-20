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


def test_core_contract_is_aligned(contract):
    assert checker.check_shared_types(contract) == []


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


def test_cli_returns_nonzero_on_extraction_failure(monkeypatch, capsys):
    def fail(_):
        raise ValueError("missing TypeScript source")
    monkeypatch.setattr(checker, "extract_frontend_contract", fail)
    assert checker.main() == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"
