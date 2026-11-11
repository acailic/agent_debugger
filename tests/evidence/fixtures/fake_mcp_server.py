#!/usr/bin/env python3
"""Standalone fake MCP stdio server for gateway subprocess tests.

Speaks newline-delimited JSON-RPC 2.0 over stdin/stdout (stdlib only —
this script must run without the repo package on sys.path).

Tools:

- ``update_claim_status`` (claim_id, status) — the one approved-style
  mutating tool.
- ``delete_everything`` — exists only so tests can assert that an
  unapproved tool is denied and hidden.

Environment knobs:

- ``FAKE_MODE``: ``normal`` (default), ``crash_after_apply`` (apply the
  mutation, then ``os._exit(1)`` *before* responding — the gateway must
  record an unknown outcome while the mutation really happened), or
  ``slow`` (sleep past the client timeout before answering tools/call —
  also an unknown outcome).
- ``FAKE_IDEMPOTENCY_ARG``: name of the argument carrying the
  idempotency key.  When set, a second ``tools/call`` with the same key
  returns the stored first result WITHOUT re-applying the mutation —
  "retry sa istim ključem ne duplira mutaciju".
- ``FAKE_APPLY_LOG``: file that gets one line per actually-applied
  mutation, so tests can assert dedupe.
- ``FAKE_SLOW_SECONDS``: how long ``slow`` mode sleeps (default 10).
"""

from __future__ import annotations

import json
import os
import sys
import time

# Pinned together with evidence.schema.MCP_PROTOCOL_VERSION; kept as a
# literal so this script stays standalone (no repo imports).
PROTOCOL_VERSION = "2025-06-18"

UPDATE_CLAIM_STATUS_SCHEMA = {
    "type": "object",
    "properties": {
        "claim_id": {"type": "string"},
        "status": {"type": "string"},
    },
    "required": ["claim_id", "status"],
}

DELETE_EVERYTHING_SCHEMA = {
    "type": "object",
    "properties": {"confirm": {"type": "boolean"}},
    "required": ["confirm"],
}


class ToolError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _tools() -> list[dict]:
    return [
        {
            "name": "update_claim_status",
            "description": "Set the status of one insurance claim (mutating).",
            "inputSchema": UPDATE_CLAIM_STATUS_SCHEMA,
        },
        {
            "name": "delete_everything",
            "description": "Dangerous tool that must never be approved.",
            "inputSchema": DELETE_EVERYTHING_SCHEMA,
        },
    ]


class FakeServer:
    def __init__(self) -> None:
        self.mode = os.environ.get("FAKE_MODE", "normal")
        self.idempotency_arg = os.environ.get("FAKE_IDEMPOTENCY_ARG")
        self.apply_log = os.environ.get("FAKE_APPLY_LOG")
        self.slow_seconds = float(os.environ.get("FAKE_SLOW_SECONDS", "10"))
        # idempotency key -> result stored at first application
        self.applied: dict[str, dict] = {}

    def _log_apply(self, key: str | None, claim_id: str, status: str) -> None:
        if self.apply_log:
            with open(self.apply_log, "a", encoding="utf-8") as handle:
                handle.write(f"key={key if key is not None else '-'} claim={claim_id} status={status}\n")

    def call_tool(self, name: str, arguments: dict) -> dict:
        if name == "delete_everything":
            self._log_apply(None, "ALL", "deleted")
            return {
                "content": [{"type": "text", "text": "everything deleted"}],
                "isError": False,
                "outcomeCode": "everything_deleted",
            }
        if name != "update_claim_status":
            raise ToolError(-32602, f"unknown tool: {name}")

        claim_id = arguments.get("claim_id")
        status = arguments.get("status")
        if not isinstance(claim_id, str) or not isinstance(status, str):
            raise ToolError(-32602, "claim_id and status are required strings")

        key = arguments.get(self.idempotency_arg) if self.idempotency_arg else None
        if key is not None and key in self.applied:
            # Same key: return the SAME result without re-applying.
            return self.applied[key]

        if self.mode == "slow":
            time.sleep(self.slow_seconds)

        result = {
            "content": [{"type": "text", "text": f"claim {claim_id} status set to {status}"}],
            "isError": False,
            "outcomeCode": "claim_status_updated",
        }
        self._log_apply(key, claim_id, status)
        if key is not None:
            self.applied[key] = result
        if self.mode == "crash_after_apply":
            # Mutation applied and logged, but the response never arrives.
            sys.stdout.flush()
            os._exit(1)
        return result


def _ok(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _handle(server: FakeServer, method: str, params: dict, msg_id) -> dict:
    if method == "initialize":
        return _ok(
            msg_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-mcp-server", "version": "1.0.0"},
            },
        )
    if method == "tools/list":
        return _ok(msg_id, {"tools": _tools()})
    if method == "tools/call":
        try:
            result = server.call_tool(params.get("name"), params.get("arguments") or {})
        except ToolError as exc:
            return _err(msg_id, exc.code, exc.message)
        return _ok(msg_id, result)
    if method == "ping":
        return _ok(msg_id, {})
    return _err(msg_id, -32601, f"method not found: {method}")


def _write(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def main() -> None:
    server = FakeServer()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            _write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        if not isinstance(message, dict) or not isinstance(message.get("method"), str):
            _write({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}})
            continue
        if message.get("id") is None:
            continue  # notification — nothing to answer
        _write(_handle(server, message["method"], message.get("params") or {}, message["id"]))


if __name__ == "__main__":
    main()
