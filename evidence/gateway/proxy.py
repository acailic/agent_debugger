"""The evidence gateway: one MCP client, one MCP server, fail-closed evidence.

Sits between an agent (single client, JSON-RPC 2.0 over stdio) and one
upstream MCP server, and turns every controlled tool call into signed
chain events:

- ``execution.started`` — persisted before the *first forwarded call*
  of the execution (denials never start an execution);
- ``decision.recorded`` — persisted before forwarding, with the
  identity, policy version and the observed schema hash.  If this
  append fails the call is refused (fail closed) and nothing is
  forwarded;
- ``outcome.recorded`` — persisted after the upstream answers and
  *before* the answer is returned to the client.  A lost/timeout
  upstream yields outcome ``unknown`` and is never retried.

Discovery is covered too: ``tools/list`` is filtered down to tools the
policy approves (name + schema hash), so the agent never sees
unapproved or schema-drifted tools.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from collections.abc import Callable
from typing import Any

from evidence.contracts import EvidenceSink
from evidence.gateway.config import GatewayConfig
from evidence.gateway.policy import ToolPolicy
from evidence.gateway.rpc import UpstreamLost
from evidence.schema import (
    MCP_PROTOCOL_VERSION,
    DecisionKind,
    DecisionPayload,
    EventDraft,
    EventType,
    ExecutionStartedPayload,
    OutcomePayload,
    OutcomeStatus,
    input_schema_hash,
    utc_now,
)

__all__ = [
    "GATEWAY_DENIED",
    "GATEWAY_UPSTREAM_LOST",
    "GATEWAY_PERSIST_FAILED",
    "GATEWAY_SERVER_NAME",
    "EvidenceGateway",
    "main",
]

#: JSON-RPC error codes reserved by the gateway (application space).
GATEWAY_DENIED = -32001
GATEWAY_UPSTREAM_LOST = -32002
GATEWAY_PERSIST_FAILED = -32003

GATEWAY_SERVER_NAME = "evidence-gateway"
GATEWAY_SERVER_VERSION = "0.1.0"
GATEWAY_CLIENT_INFO = {"name": GATEWAY_SERVER_NAME, "version": GATEWAY_SERVER_VERSION}

_JSONRPC_PARSE_ERROR = -32700
_JSONRPC_INVALID_REQUEST = -32600
_JSONRPC_INTERNAL_ERROR = -32603


def _rpc_error(code: int, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": None, "error": error}


class EvidenceGateway:
    """Policy-enforcing MCP proxy that persists signed evidence.

    ``upstream`` is anything with ``.request(method, params)`` (tests
    pass a fake; production wraps :class:`~evidence.gateway.rpc.StdioUpstream`).
    """

    def __init__(
        self,
        config: GatewayConfig,
        sink: EvidenceSink,
        upstream: Any,
        on_execution_started: Callable[[str], None] | None = None,
    ) -> None:
        self.config = config
        self.sink = sink
        self.upstream = upstream
        self.on_execution_started = on_execution_started
        self.policy = ToolPolicy(config.bindings)
        #: Execution ids are issued by the gateway (pilot: no external
        #: execution service yet) and persisted lazily.
        self.execution_id = f"exec-{uuid.uuid4().hex}"
        self._execution_started = False
        self._upstream_ready = False
        self._tool_schemas: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Message dispatch
    # ------------------------------------------------------------------

    def handle_message(self, raw: str) -> dict[str, Any] | None:
        """Handle one JSON-RPC message; return the response or ``None``.

        ``None`` means "no response expected" (a notification) or "no
        response to send".  Malformed input yields a standard JSON-RPC
        error object.
        """
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            return _rpc_error(_JSONRPC_PARSE_ERROR, "Parse error")
        if not isinstance(message, dict) or not isinstance(message.get("method"), str):
            msg_id = message.get("id") if isinstance(message, dict) else None
            return _rpc_error(_JSONRPC_INVALID_REQUEST, "Invalid Request", None) | {
                "id": msg_id
            }
        method = message["method"]
        params = message.get("params")
        if not isinstance(params, dict):
            params = {}
        msg_id = message.get("id")
        expects_response = message.get("id") is not None

        def respond(payload: dict[str, Any]) -> dict[str, Any] | None:
            if not expects_response:
                return None
            return {"jsonrpc": "2.0", "id": msg_id, **payload}

        if method == "initialize":
            return self._handle_initialize(respond)
        if method == "tools/list":
            return self._handle_tools_list(params, respond)
        if method == "tools/call":
            return self._handle_tools_call(params, respond)
        return self._handle_passthrough(method, params, respond, expects_response)

    def _handle_initialize(self, respond: Callable) -> dict[str, Any] | None:
        result = {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": GATEWAY_SERVER_NAME, "version": GATEWAY_SERVER_VERSION},
        }
        return respond({"result": result})

    def _handle_tools_list(self, params: dict, respond: Callable) -> dict[str, Any] | None:
        try:
            self._ensure_upstream_ready()
            response = self.upstream.request("tools/list", dict(params))
        except UpstreamLost as exc:
            return respond(
                {"error": {"code": GATEWAY_UPSTREAM_LOST, "message": "gateway_upstream_lost",
                           "data": {"detail": str(exc)}}}
            )
        if response.get("error") is not None:
            return respond({"error": response["error"]})
        tools = self._tools_from_response(response)
        self._cache_tool_schemas(tools)
        return respond({"result": {"tools": self.policy.visible_tools(tools)}})

    def _handle_passthrough(
        self, method: str, params: dict, respond: Callable, expects_response: bool
    ) -> dict[str, Any] | None:
        """Anything the gateway does not interpret: forward, best effort.

        No evidence events — only interpreted methods produce evidence.
        """
        if not expects_response:
            notify = getattr(self.upstream, "notify", None)
            if callable(notify):
                try:
                    self._ensure_upstream_ready()
                    notify(method, params)
                except Exception:
                    pass  # best effort
            return None
        try:
            self._ensure_upstream_ready()
            response = self.upstream.request(method, params)
        except UpstreamLost as exc:
            return respond(
                {"error": {"code": GATEWAY_UPSTREAM_LOST, "message": "gateway_upstream_lost",
                           "data": {"detail": str(exc)}}}
            )
        if response.get("error") is not None:
            return respond({"error": response["error"]})
        return respond({"result": response.get("result")})

    # ------------------------------------------------------------------
    # tools/call — the controlled flow
    # ------------------------------------------------------------------

    def _handle_tools_call(self, params: dict, respond: Callable) -> dict[str, Any] | None:
        name = str(params.get("name") or "")
        arguments = dict(params.get("arguments") or {})
        call_id = "call-" + uuid.uuid4().hex[:12]

        # 1-2. Observe the tool schema (fetching discovery if needed) and
        # decide.  If discovery itself is lost we cannot honestly evaluate
        # the policy, so we fail with no evidence and no forward.
        try:
            schema = self._tool_schema_for(name)
        except UpstreamLost as exc:
            return respond(
                {"error": {"code": GATEWAY_UPSTREAM_LOST, "message": "gateway_upstream_lost",
                           "data": {"call_id": call_id, "detail": f"tool discovery failed: {exc}"}}}
            )
        decision = self.policy.check(name, schema)
        observed_hash = input_schema_hash(schema)

        # An allowed call starts the execution before anything else is
        # recorded: execution.started is the chain's first event and the
        # checkpoint hook fires before the first forward.  Denials never
        # start an execution.
        if decision.allowed:
            try:
                self._ensure_execution_started()
            except Exception:
                return respond(
                    {"error": _persist_failed(call_id, "execution_started")}
                )

        # Idempotency key: inject before forwarding so the decision event
        # records exactly the arguments that will be sent.  A key the
        # client already supplied is honoured as-is.
        idempotency_key: str | None = None
        arg_name = self.config.idempotency_argument_name
        if decision.allowed and arg_name is not None:
            if arg_name in arguments:
                idempotency_key = arguments[arg_name]
            else:
                idempotency_key = "idem-" + call_id
                arguments[arg_name] = idempotency_key

        # 3. FAIL-CLOSED PERSIST of the decision, before any forwarding.
        try:
            self._append(
                EventType.DECISION_RECORDED,
                DecisionPayload(
                    decision=DecisionKind.ALLOW if decision.allowed else DecisionKind.DENY,
                    reason=decision.reason,
                    call_id=call_id,
                    principal=self.config.principal,
                    identity_source=self.config.identity_source,
                    policy_version=self.config.policy_version,
                    tool_name=name,
                    input_schema_hash=observed_hash,
                    config_version=(
                        decision.binding.config_version
                        if decision.binding is not None
                        else self.config.config_version
                    ),
                    idempotency_key=idempotency_key,
                ),
            )
        except Exception:
            return respond({"error": _persist_failed(call_id, "decision")})

        # 4. Denied: no forward, no outcome event.
        if not decision.allowed:
            return respond(
                {"error": {"code": GATEWAY_DENIED, "message": "gateway_denied",
                           "data": {"reason": decision.reason, "call_id": call_id}}}
            )

        # 6. Forward (exactly once — no retries, ever).
        started = time.perf_counter()
        try:
            response = self.upstream.request("tools/call", {"name": name, "arguments": arguments})
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            # 9. Outcome unknown: the mutation may or may not have applied.
            try:
                self._append(
                    EventType.OUTCOME_RECORDED,
                    OutcomePayload(
                        call_id=call_id,
                        status=OutcomeStatus.UNKNOWN,
                        error_kind="upstream_lost",
                        duration_ms=duration_ms,
                        idempotency_key=idempotency_key,
                    ),
                )
            except Exception:
                return respond({"error": _persist_failed(call_id, "outcome_unknown")})
            return respond(
                {"error": {"code": GATEWAY_UPSTREAM_LOST, "message": "gateway_upstream_lost",
                           "data": {"call_id": call_id, "detail": str(exc)}}}
            )
        duration_ms = int((time.perf_counter() - started) * 1000)

        if response.get("error") is not None:
            # 8. The tool answered with a JSON-RPC error: record outcome
            # "error" and pass the tool's error through untouched.
            try:
                self._append(
                    EventType.OUTCOME_RECORDED,
                    OutcomePayload(
                        call_id=call_id,
                        status=OutcomeStatus.ERROR,
                        error_kind=f"rpc-{response['error'].get('code')}",
                        duration_ms=duration_ms,
                        idempotency_key=idempotency_key,
                    ),
                )
            except Exception:
                return respond({"error": _persist_failed(call_id, "outcome_error")})
            return respond({"error": response["error"]})

        # 7. Success: persist the outcome BEFORE returning the result —
        # an unrecorded outcome is never handed to the client.
        result = response.get("result") or {}
        outcome_code = result.get("outcomeCode") if isinstance(result, dict) else None
        try:
            self._append(
                EventType.OUTCOME_RECORDED,
                OutcomePayload(
                    call_id=call_id,
                    status=OutcomeStatus.SUCCESS,
                    outcome_code=outcome_code,
                    duration_ms=duration_ms,
                    idempotency_key=idempotency_key,
                ),
            )
        except Exception:
            return respond({"error": _persist_failed(call_id, "outcome")})
        return respond({"result": result})

    # ------------------------------------------------------------------
    # Evidence helpers
    # ------------------------------------------------------------------

    def _append(self, event_type: EventType, payload: Any) -> None:
        """Append one event; raises propagate to the caller (fail closed)."""
        self.sink.append(
            EventDraft(
                type=event_type,
                execution_id=self.execution_id,
                recorded_at=utc_now(),
                payload=payload.model_dump(mode="json"),
            )
        )

    def _ensure_execution_started(self) -> None:
        """Persist ``execution.started`` and notify the hook (once, before
        the first forwarded call).  A failing append or hook blocks the
        forward; the event is never appended twice."""
        if self._execution_started:
            return
        self._append(
            EventType.EXECUTION_STARTED,
            ExecutionStartedPayload(
                principal=self.config.principal,
                identity_source=self.config.identity_source,
                policy_version=self.config.policy_version,
            ),
        )
        self._execution_started = True
        if self.on_execution_started is not None:
            self.on_execution_started(self.execution_id)

    # ------------------------------------------------------------------
    # Upstream helpers
    # ------------------------------------------------------------------

    def _ensure_upstream_ready(self) -> None:
        """Lazily run the upstream MCP handshake (real clients only)."""
        if self._upstream_ready:
            return
        initialize = getattr(self.upstream, "initialize", None)
        if callable(initialize):
            initialize(GATEWAY_CLIENT_INFO)
        self._upstream_ready = True

    def _tool_schema_for(self, name: str) -> dict[str, Any]:
        """The tool's currently served inputSchema ({} when unknown)."""
        if name not in self._tool_schemas:
            self._refresh_tool_schemas()
        return self._tool_schemas.get(name, {})

    def _refresh_tool_schemas(self) -> None:
        self._ensure_upstream_ready()
        response = self.upstream.request("tools/list", {})
        if isinstance(response, dict) and response.get("error") is None:
            self._cache_tool_schemas(self._tools_from_response(response))

    @staticmethod
    def _tools_from_response(response: dict[str, Any]) -> list[dict[str, Any]]:
        result = response.get("result")
        if not isinstance(result, dict):
            return []
        tools = result.get("tools")
        return tools if isinstance(tools, list) else []

    def _cache_tool_schemas(self, tools: list[dict[str, Any]]) -> None:
        for tool in tools:
            if isinstance(tool, dict) and isinstance(tool.get("name"), str):
                schema = tool.get("inputSchema")
                self._tool_schemas[tool["name"]] = schema if isinstance(schema, dict) else {}

    # ------------------------------------------------------------------
    # Stdio serving loop
    # ------------------------------------------------------------------

    def serve(self, stdin: Any = sys.stdin, stdout: Any = sys.stdout) -> None:
        """Read newline-delimited JSON-RPC from ``stdin`` until EOF."""
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                response = self.handle_message(line)
            except Exception:  # defensive: the loop must keep serving
                response = _rpc_error(_JSONRPC_INTERNAL_ERROR, "internal error")
            if response is not None:
                stdout.write(json.dumps(response) + "\n")
                stdout.flush()


def _persist_failed(call_id: str, stage: str) -> dict[str, Any]:
    return {
        "code": GATEWAY_PERSIST_FAILED,
        "message": "gateway_persist_failed",
        "data": {"call_id": call_id, "stage": stage},
    }


def main(argv: list[str] | None = None) -> int:
    """``python3 -m evidence.gateway --config gw.json``.

    Durable wiring comes from the config's ``"runtime"`` section —
    gateway key PEM, ledger database, independent checkpoint store
    (see :mod:`evidence.gateway.runtime`).  Without it the process
    runs demo-style: a fresh in-memory sink and a fresh key.
    """
    parser = argparse.ArgumentParser(
        prog="evidence.gateway",
        description="MCP evidence gateway (JSON-RPC 2.0 over stdio)",
    )
    parser.add_argument("--config", required=True, help="path to the gateway JSON config")
    args = parser.parse_args(argv)

    # Imported here, not at module top: runtime.py imports this module
    # (EvidenceGateway), so a top-level import would be circular.
    from evidence.gateway.runtime import build_runtime, finalize_execution

    runtime = build_runtime(args.config)
    if not runtime.durable:
        print(
            "evidence-gateway: no 'runtime' section — demo mode (in-memory sink, fresh key)",
            file=sys.stderr,
        )
    try:
        runtime.gateway.serve(stdin=sys.stdin, stdout=sys.stdout)
        checkpoint = finalize_execution(runtime)
        if checkpoint is not None:
            print(
                f"evidence-gateway: finalized checkpoint for {checkpoint.execution_id}: "
                f"{checkpoint.event_count} events, head {checkpoint.final_hash[:16]}…",
                file=sys.stderr,
            )
    finally:
        runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
