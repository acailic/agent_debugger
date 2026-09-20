#!/usr/bin/env python3
"""Check core response fields, SDK enums, and frontend HTTP routes.

Uses live Pydantic models and the installed TypeScript compiler, without starting
services or contacting the network. Requires server dependencies and `npm ci` in
frontend. Prints JSON; exits 0 on success, 1 on drift, and 2 on setup/parser errors.
Field checks cover the explicitly paired core responses below, not structural
TypeScript compatibility or every backend-only response model.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

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
ENUMS = {"EventType": EventType, "RiskLevel": RiskLevel, "SafetyOutcome": SafetyOutcome}
# collector.replay.build_tree synthesizes this event for multiple trace roots.
SYNTHETIC_ENUM_VALUES = {"EventType": {"trace_root"}}


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
    for name, enum in ENUMS.items():
        frontend_values = contract["unions"].get(name)
        if frontend_values is None:
            drifts.append({"type": "missing_union", "union": name})
            continue
        expected = {member.value for member in enum} | SYNTHETIC_ENUM_VALUES.get(name, set())
        missing = sorted(expected - set(frontend_values))
        extra = sorted(set(frontend_values) - expected)
        if missing or extra:
            drifts.append({
                "type": "enum_mismatch", "union": name,
                "missing_in_frontend": missing, "unexpected_in_frontend": extra,
            })
    return drifts


def main() -> int:
    """Print a machine-readable report and return a CI exit status."""
    try:
        contract = extract_frontend_contract(REPO_ROOT)
        if contract.get("errors"):
            raise ValueError(contract["errors"])
        from api.main import app

        drifts = check_shared_types(contract) + check_routes(contract["requests"], app.openapi()["paths"])
        result = {
            "status": "drift" if drifts else "pass",
            "checked_schemas": len(SCHEMA_PAIRS),
            "checked_enums": len(ENUMS),
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
