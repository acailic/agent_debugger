#!/usr/bin/env python3
"""Check core response fields, types, payload fixtures, SDK enums, and HTTP routes.

Uses live Pydantic models, the installed TypeScript compiler, and the committed
payload fixtures, without starting services or contacting the network. Requires
server dependencies and `npm ci` in frontend. Prints JSON; exits 0 on success,
1 on drift, and 2 on setup/parser errors.

Field checks cover the explicitly paired core responses below, not every
backend-only response model. Beyond field names, each pair is compared for
nullability and structural type kind (string/number/boolean/array/object/
union-of-literals), and each fixture payload is validated against both its
backend model and its frontend interface. Response models always serialize
defaults, so optional-in-backend plus required-in-frontend is not drift; the
reverse direction (always-emitted field marked optional in TS) is, except for
the documented deviations below.
"""

from __future__ import annotations

import datetime
import enum
import json
import sys
import types
import typing
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent_debugger_sdk.core.events import EventType, RiskLevel, SafetyOutcome  # noqa: E402
from api import schemas  # noqa: E402
from scripts.hooks.route_contract import check_routes, extract_frontend_contract  # noqa: E402

SCHEMA_PAIRS = {
    "SessionSchema": "Session",
    "TraceEventSchema": "TraceEvent",
    "CheckpointSchema": "Checkpoint",
    "TraceBundleResponse": "TraceBundle",
    "ReplayResponse": "ReplayResponse",
    "TraceSearchResponse": "TraceSearchResponse",
    "HighlightSchema": "Highlight",
    "CollapsedSegmentSchema": "CollapsedSegment",
}
INTERFACE_TO_MODEL = {interface: model for model, interface in SCHEMA_PAIRS.items()}
ENUMS = {"EventType": EventType, "RiskLevel": RiskLevel, "SafetyOutcome": SafetyOutcome}
# collector.replay.build_tree synthesizes this event for multiple trace roots.
SYNTHETIC_ENUM_VALUES = {"EventType": {"trace_root"}}
# The backend always serializes these required fields, but the frontend types
# deliberately treat them as optional (cosmetic data TS may render conditionally).
INTENTIONAL_TS_OPTIONAL = {("SessionSchema", "replay_value")}
FIXTURES_PATH = REPO_ROOT / "tests/contract/fixtures_core_payloads.json"
REQUIRED_FIXTURES = {
    "Session", "TraceEvent", "Checkpoint", "TraceBundle", "ReplayResponse", "TraceSearchResponse",
}


def _classify_annotation(annotation: Any) -> tuple[str, bool]:
    """Reduce a Pydantic annotation to a JSON type kind and a nullable flag."""
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = typing.get_args(annotation)
        nullable = type(None) in args
        remaining = [arg for arg in args if arg is not type(None)]
        if len(remaining) == 1:
            kind, inner_nullable = _classify_annotation(remaining[0])
            return kind, nullable or inner_nullable
        if remaining and all(_classify_annotation(arg)[0] in {"union", "string"} for arg in remaining):
            return "union", nullable
        return "unknown", nullable
    if origin is typing.Literal:
        return "union", False
    if isinstance(origin, type):
        if issubclass(origin, Sequence) and not issubclass(origin, (str, bytes)):
            return "array", False
        if issubclass(origin, Mapping):
            return "object", False
    elif origin is not None:
        return "unknown", False
    if annotation is Any:
        return "unknown", False
    if annotation is type(None):
        return "null", True
    if isinstance(annotation, type):
        if issubclass(annotation, enum.Enum):
            return "union", False
        if issubclass(annotation, bool):
            return "boolean", False
        if issubclass(annotation, (str, datetime.date, uuid.UUID)):
            return "string", False
        if issubclass(annotation, (int, float)):
            return "number", False
        if issubclass(annotation, (list, set, frozenset, tuple)):
            return "array", False
        if issubclass(annotation, dict):
            return "object", False
        if issubclass(annotation, BaseModel):
            return "object", False
    return "unknown", False


def _kinds_compatible(backend_kind: str, frontend_kind: str) -> bool:
    """Literal unions serialize as strings, and unknown accepts anything."""
    if "unknown" in (backend_kind, frontend_kind):
        return True
    return backend_kind == frontend_kind or {backend_kind, frontend_kind} == {"string", "union"}


def _json_kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def check_shared_types(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Compare named core fields and complete enum values; missing types fail."""
    drifts: list[dict[str, Any]] = []
    for model_name, interface_name in SCHEMA_PAIRS.items():
        frontend_fields = contract["interfaces"].get(interface_name)
        if frontend_fields is None:
            drifts.append({"type": "missing_interface", "interface": interface_name})
            continue
        backend_fields = set(getattr(schemas, model_name).model_fields)
        missing = sorted(backend_fields - set(frontend_fields))
        extra = sorted(set(frontend_fields) - backend_fields)
        if missing or extra:
            drifts.append({
                "type": "field_mismatch", "model": model_name, "interface": interface_name,
                "missing_in_frontend": missing, "missing_in_backend": extra,
            })
    for name, enum_class in ENUMS.items():
        frontend_values = contract["unions"].get(name)
        if frontend_values is None:
            drifts.append({"type": "missing_union", "union": name})
            continue
        expected = {member.value for member in enum_class} | SYNTHETIC_ENUM_VALUES.get(name, set())
        missing = sorted(expected - set(frontend_values))
        extra = sorted(set(frontend_values) - expected)
        if missing or extra:
            drifts.append({
                "type": "enum_mismatch", "union": name,
                "missing_in_frontend": missing, "unexpected_in_frontend": extra,
            })
    return drifts


def check_field_types(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Compare required-ness, nullability, and type kind per paired field.

    Fields missing from either side are skipped here; the name check above
    already reports them.
    """
    drifts: list[dict[str, Any]] = []
    for model_name, interface_name in SCHEMA_PAIRS.items():
        properties = contract.get("properties", {}).get(interface_name, {})
        for field_name, field_info in sorted(getattr(schemas, model_name).model_fields.items()):
            if field_name not in properties:
                continue
            backend_kind, backend_nullable = _classify_annotation(field_info.annotation)
            ts_optional = properties[field_name].get("optional", False)
            ts_nullable = properties[field_name].get("nullable", False)
            ts_kind = properties[field_name].get("kind", "unknown")
            common = {"model": model_name, "interface": interface_name, "field": field_name}
            if (
                field_info.is_required() and not backend_nullable and ts_optional
                and (model_name, field_name) not in INTENTIONAL_TS_OPTIONAL
            ):
                drifts.append({**common, "type": "required_mismatch", "direction": "backend_required_ts_optional"})
            if backend_nullable and not ts_nullable and not ts_optional:
                drifts.append({
                    **common, "type": "nullability_mismatch", "direction": "backend_nullable_ts_required_non_null",
                })
            if ts_nullable and not backend_nullable:
                drifts.append({
                    **common, "type": "nullability_mismatch", "direction": "ts_nullable_backend_non_null",
                })
            if not _kinds_compatible(backend_kind, ts_kind):
                drifts.append({
                    **common, "type": "type_kind_mismatch", "backend_kind": backend_kind, "ts_kind": ts_kind,
                })
    return drifts


def load_payload_fixtures(path: Path | None = None) -> dict[str, Any]:
    """Load the committed payload fixtures; structural problems are setup errors."""
    if path is None:
        path = FIXTURES_PATH
    try:
        fixtures = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read payload fixtures at {path}: {exc}") from exc
    payloads = fixtures.get("payloads")
    if not isinstance(payloads, dict) or not payloads:
        raise ValueError(f"Payload fixtures at {path} have no payloads")
    unknown = sorted(set(payloads) - set(SCHEMA_PAIRS.values()))
    if unknown:
        raise ValueError(f"Payload fixtures contain interfaces outside SCHEMA_PAIRS: {unknown}")
    missing = sorted(REQUIRED_FIXTURES - set(payloads))
    if missing:
        raise ValueError(f"Payload fixtures missing core interfaces: {missing}")
    return fixtures


def check_payload_fixtures(contract: dict[str, Any], fixtures: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate each fixture payload against its backend model and frontend interface.

    The backend side runs full Pydantic validation; the frontend side compares
    the JSON value kind, nullability, and optionality of every top-level
    property against the extracted TypeScript interface.
    """
    drifts: list[dict[str, Any]] = []
    for interface, payload in fixtures["payloads"].items():
        model = getattr(schemas, INTERFACE_TO_MODEL[interface])
        try:
            model.model_validate(payload)
        except ValidationError as exc:
            errors = [f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()]
            drifts.append({"type": "payload_backend_mismatch", "interface": interface, "errors": errors[:5]})
        properties = contract.get("properties", {}).get(interface, {})
        for field_name in sorted(payload):
            if field_name not in properties:
                drifts.append({
                    "type": "payload_frontend_mismatch", "interface": interface, "field": field_name,
                    "reason": "unexpected_property",
                })
        for field_name, property_info in sorted(properties.items()):
            if field_name not in payload:
                if not property_info.get("optional", False):
                    drifts.append({
                        "type": "payload_frontend_mismatch", "interface": interface, "field": field_name,
                        "reason": "missing_required_property",
                    })
                continue
            value_kind = _json_kind(payload[field_name])
            ts_kind = property_info.get("kind", "unknown")
            accepts_null = property_info.get("nullable", False) or property_info.get("optional", False)
            if value_kind == "null" and not accepts_null:
                drifts.append({
                    "type": "payload_frontend_mismatch", "interface": interface, "field": field_name,
                    "reason": "null_value", "ts_kind": ts_kind,
                })
            elif value_kind != "null" and not _kinds_compatible(value_kind, ts_kind):
                drifts.append({
                    "type": "payload_frontend_mismatch", "interface": interface, "field": field_name,
                    "reason": "value_kind_mismatch", "value_kind": value_kind, "ts_kind": ts_kind,
                })
    return drifts


def main() -> int:
    """Print a machine-readable report and return a CI exit status."""
    try:
        contract = extract_frontend_contract(REPO_ROOT)
        if contract.get("errors"):
            raise ValueError(contract["errors"])
        fixtures = load_payload_fixtures()
        from api.main import app

        drifts = (
            check_shared_types(contract)
            + check_field_types(contract)
            + check_payload_fixtures(contract, fixtures)
            + check_routes(contract["requests"], app.openapi()["paths"])
        )
        result = {
            "status": "drift" if drifts else "pass",
            "checked_schemas": len(SCHEMA_PAIRS),
            "checked_enums": len(ENUMS),
            "checked_field_types": sum(len(getattr(schemas, m).model_fields) for m in SCHEMA_PAIRS),
            "checked_payloads": len(fixtures["payloads"]),
            "checked_routes": len(contract["requests"]),
            "drifts": drifts,
        }
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 1 if drifts else 0


if __name__ == "__main__":
    sys.exit(main())
