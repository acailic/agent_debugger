"""Compare frontend HTTP calls with the routes registered on the real app.

Extraction covers exported functions in client.ts using the existing fetch
wrappers or EventSource. Unsupported URL/options expressions fail explicitly.
Query values, payloads, response shapes and runtime routing order are out of scope.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any


def extract_frontend_contract(
    repo_root: Path,
    client_content: str | None = None,
    types_content: str | None = None,
) -> dict[str, Any]:
    """Extract requests, interface fields and literal unions via TypeScript AST."""
    client = repo_root / "frontend/src/api/client.ts"
    types = repo_root / "frontend/src/types/index.ts"
    overrides = {}
    if client_content is not None:
        overrides[str(client)] = client_content
    if types_content is not None:
        overrides[str(types)] = types_content
    try:
        process = subprocess.run(
            ["node", str(repo_root / "scripts/hooks/extract_ts_contract.cjs"), str(client), str(types)],
            input=json.dumps(overrides), capture_output=True, text=True, check=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        detail = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise RuntimeError(f"TypeScript contract extraction failed (run npm ci in frontend): {detail}") from exc
    result = json.loads(process.stdout)
    if result["errors"]:
        raise ValueError("TypeScript contract extraction failed: " + "; ".join(result["errors"]))
    if not result["requests"]:
        raise ValueError("No frontend requests found; refusing an empty route check")
    return result


def _normalize(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path)


def check_routes(requests: list[dict[str, Any]], paths: dict[str, Any]) -> list[dict[str, Any]]:
    """Check literal segments and HTTP verbs, ignoring path parameter names."""
    registered: dict[str, set[str]] = {}
    for path, operations in paths.items():
        registered.setdefault(_normalize(path), set()).update(
            method.upper() for method in operations
            if method.lower() in {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
        )
    drifts = []
    for request in requests:
        methods = registered.get(_normalize(request["path"]), set())
        if request["method"] not in methods:
            kind = "route_method_mismatch" if methods else "missing_backend_route"
            drifts.append({
                **request,
                "type": kind,
                "allowed_methods": sorted(methods),
                "message": (
                    f"{request['function']}: {request['method']} {request['path']} "
                    "has no matching backend route"
                ),
            })
    return drifts


def check_route_contract(
    repo_root: Path, app: Any = None, client_content: str | None = None,
) -> dict[str, Any]:
    """Load actual app routes without starting its lifespan or making requests."""
    if app is None:
        from api.main import app
    contract = extract_frontend_contract(repo_root, client_content)
    drifts = check_routes(contract["requests"], app.openapi()["paths"])
    return {"status": "drift" if drifts else "pass", "drifts": drifts, "checked_routes": len(contract["requests"])}
