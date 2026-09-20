"""Mutation tests for the committed core payload fixtures.

The fixtures are real response payloads captured from the in-process app (see
tests/contract/fixtures_core_payloads.json and the generator named in its
header). Each test here breaks the contract in one specific way and asserts
the checker reports it, proving CI fails on payload drift.
"""

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


def test_committed_fixtures_cover_every_pair_and_pass(contract, fixtures):
    assert set(fixtures["payloads"]) == set(checker.SCHEMA_PAIRS.values())
    assert checker.check_payload_fixtures(contract, fixtures) == []


def test_fixture_header_documents_regeneration(fixtures):
    meta = fixtures["_meta"]
    assert meta["regenerate"] == ".venv-ci/bin/python scripts/hooks/generate_core_payload_fixtures.py"
    assert meta["generated_by"].endswith("generate_core_payload_fixtures.py")
    assert meta["method"]


def test_fixture_value_type_drift_fails(contract, fixtures):
    changed = copy.deepcopy(fixtures)
    changed["payloads"]["TraceSearchResponse"]["total"] = "7"  # number sent as string
    drifts = checker.check_payload_fixtures(contract, changed)
    assert drifts == [{
        "type": "payload_frontend_mismatch", "interface": "TraceSearchResponse", "field": "total",
        "reason": "value_kind_mismatch", "value_kind": "string", "ts_kind": "number",
    }]


def test_fixture_value_invalid_for_backend_fails(contract, fixtures):
    changed = copy.deepcopy(fixtures)
    changed["payloads"]["Session"]["total_tokens"] = "not-a-number"
    drifts = checker.check_payload_fixtures(contract, changed)
    drift, = [d for d in drifts if d["type"] == "payload_backend_mismatch"]
    assert drift["interface"] == "Session"
    assert any("total_tokens" in error for error in drift["errors"])


def test_fixture_missing_required_field_fails(contract, fixtures):
    changed = copy.deepcopy(fixtures)
    del changed["payloads"]["Checkpoint"]["sequence"]
    drifts = checker.check_payload_fixtures(contract, changed)
    reasons = {(d["field"], d["reason"]) for d in drifts if d["type"] == "payload_frontend_mismatch"}
    assert ("sequence", "missing_required_property") in reasons
    assert any(d["type"] == "payload_backend_mismatch" for d in drifts)


def test_fixture_null_in_non_nullable_position_fails(contract, fixtures):
    changed = copy.deepcopy(fixtures)
    changed["payloads"]["Checkpoint"]["sequence"] = None
    drifts = checker.check_payload_fixtures(contract, changed)
    reasons = {(d["field"], d["reason"]) for d in drifts if d["type"] == "payload_frontend_mismatch"}
    assert ("sequence", "null_value") in reasons
    assert any(d["type"] == "payload_backend_mismatch" for d in drifts)


def test_fixture_null_in_nullable_position_passes(contract, fixtures):
    changed = copy.deepcopy(fixtures)
    changed["payloads"]["Session"]["ended_at"] = None  # TS: string | null, required
    assert checker.check_payload_fixtures(contract, changed) == []


def test_fixture_unknown_property_fails(contract, fixtures):
    changed = copy.deepcopy(fixtures)
    changed["payloads"]["Session"]["ghost_field"] = 1
    drifts = checker.check_payload_fixtures(contract, changed)
    assert drifts == [{
        "type": "payload_frontend_mismatch", "interface": "Session",
        "field": "ghost_field", "reason": "unexpected_property",
    }]


def test_fixture_against_stale_ts_type_fails(contract, fixtures):
    changed = copy.deepcopy(contract)
    changed["properties"]["TraceSearchResponse"]["total"]["kind"] = "string"
    drifts = checker.check_payload_fixtures(changed, fixtures)
    assert drifts == [{
        "type": "payload_frontend_mismatch", "interface": "TraceSearchResponse", "field": "total",
        "reason": "value_kind_mismatch", "value_kind": "number", "ts_kind": "string",
    }]


def test_fixture_omitted_optional_property_passes(contract, fixtures):
    reduced = copy.deepcopy(fixtures)
    del reduced["payloads"]["Session"]["fix_note"]  # optional on both sides
    assert checker.check_payload_fixtures(contract, reduced) == []


def test_malformed_fixture_files_are_setup_errors(tmp_path):
    missing = tmp_path / "missing.json"
    with pytest.raises(ValueError, match="Cannot read payload fixtures"):
        checker.load_payload_fixtures(missing)
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"payloads": {}}))
    with pytest.raises(ValueError, match="no payloads"):
        checker.load_payload_fixtures(empty)
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps({"payloads": {"Session": {"id": "x"}}}))
    with pytest.raises(ValueError, match="missing core interfaces"):
        checker.load_payload_fixtures(partial)
    unknown = tmp_path / "unknown.json"
    unknown.write_text(json.dumps({"payloads": {name: {} for name in checker.REQUIRED_FIXTURES | {"Widget"}}}))
    with pytest.raises(ValueError, match="outside SCHEMA_PAIRS"):
        checker.load_payload_fixtures(unknown)
