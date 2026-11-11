"""EvidenceGateway tests: fake-upstream unit tests + real stdio integration tests."""

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from evidence.contracts import InMemoryEvidenceSink
from evidence.gateway.config import GatewayConfig
from evidence.gateway.proxy import (
    GATEWAY_DENIED,
    GATEWAY_PERSIST_FAILED,
    GATEWAY_UPSTREAM_LOST,
    EvidenceGateway,
)
from evidence.gateway.rpc import StdioUpstream, UpstreamLost
from evidence.schema import MCP_PROTOCOL_VERSION, EventType, ToolBinding, input_schema_hash
from evidence.signing import EvidenceSigner

FIXTURE_SERVER = Path(__file__).parent / "fixtures" / "fake_mcp_server.py"

CLAIM_SCHEMA = {
    "type": "object",
    "properties": {
        "claim_id": {"type": "string"},
        "status": {"type": "string"},
    },
    "required": ["claim_id", "status"],
}

DELETE_SCHEMA = {
    "type": "object",
    "properties": {"confirm": {"type": "boolean"}},
    "required": ["confirm"],
}

DRIFTED_SCHEMA = {
    "type": "object",
    "properties": {
        "claim_id": {"type": "string"},
        "status": {"type": "string"},
        "reason_code": {"type": "string"},
    },
    "required": ["claim_id", "status"],
}


def claim_binding(config_version: str = "cfg-1") -> ToolBinding:
    return ToolBinding(
        tool_name="update_claim_status",
        input_schema_hash=input_schema_hash(CLAIM_SCHEMA),
        approved_server="fake-mcp-server",
        config_version=config_version,
    )


def make_config(**overrides) -> GatewayConfig:
    values = dict(
        gateway_id="gw-test",
        principal="agent-claims-bot",
        policy_version="policy-1",
        config_version="cfg-1",
        bindings=[claim_binding()],
        upstream_command=[sys.executable, str(FIXTURE_SERVER)],
        idempotency_argument_name="idempotency_key",
        upstream_timeout_s=5.0,
    )
    values.update(overrides)
    return GatewayConfig(**values)


class FakeUpstream:
    """Duck-typed upstream: only ``request`` is required by the gateway."""

    def __init__(self, call_response=None, tools=None, journal=None) -> None:
        self.call_response = call_response or {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "claim CLM-1 status set to approved"}],
                "isError": False,
                "outcomeCode": "claim_status_updated",
            },
        }
        self.tools = tools if tools is not None else [
            {"name": "update_claim_status", "description": "mutating", "inputSchema": CLAIM_SCHEMA},
            {"name": "delete_everything", "description": "dangerous", "inputSchema": DELETE_SCHEMA},
        ]
        self.journal = journal if journal is not None else []
        self.calls: list[tuple[str, dict]] = []

    def request(self, method, params):
        self.calls.append((method, params))
        self.journal.append(("upstream", method))
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": 1, "result": {"tools": self.tools}}
        if method == "tools/call":
            if isinstance(self.call_response, Exception):
                raise self.call_response
            return self.call_response
        return {"jsonrpc": "2.0", "id": 1, "result": {}}

    def tools_call_count(self) -> int:
        return sum(1 for method, _ in self.calls if method == "tools/call")


class FlakySink(InMemoryEvidenceSink):
    """Reference sink that refuses to persist the given event types."""

    def __init__(self, fail_on: set[EventType]) -> None:
        super().__init__(EvidenceSigner.generate(), gateway_id="gw-test")
        self.fail_on = fail_on

    def append(self, draft):
        if draft.type in self.fail_on:
            raise RuntimeError("simulated persistence failure")
        return super().append(draft)


def make_gateway(
    config: GatewayConfig | None = None,
    upstream: FakeUpstream | None = None,
    sink: InMemoryEvidenceSink | None = None,
    on_execution_started=None,
) -> tuple[EvidenceGateway, InMemoryEvidenceSink, FakeUpstream]:
    sink = sink or InMemoryEvidenceSink(EvidenceSigner.generate(), gateway_id="gw-test")
    upstream = upstream or FakeUpstream()
    gateway = EvidenceGateway(config or make_config(), sink, upstream, on_execution_started)
    return gateway, sink, upstream


def rpc(method: str, msg_id=1, **params) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})


def call_tool(msg_id=1, name="update_claim_status", arguments=None) -> str:
    return rpc(
        "tools/call",
        msg_id=msg_id,
        name=name,
        arguments=arguments if arguments is not None else {"claim_id": "CLM-1", "status": "approved"},
    )


def event_types_of(sink: InMemoryEvidenceSink, gateway: EvidenceGateway) -> list[EventType]:
    return [record.event.type for record in sink.events(gateway.execution_id)]


def event_payloads_of(sink: InMemoryEvidenceSink, gateway: EvidenceGateway) -> list[dict]:
    return [record.event.payload for record in sink.events(gateway.execution_id)]


def outcome_payloads_of(sink: InMemoryEvidenceSink, gateway: EvidenceGateway) -> list[dict]:
    return [
        record.event.payload
        for record in sink.events(gateway.execution_id)
        if record.event.type == EventType.OUTCOME_RECORDED
    ]


class TestAllowedCall:
    def test_allowed_call_event_order_started_decision_outcome(self):
        gateway, sink, _ = make_gateway()
        response = gateway.handle_message(call_tool())
        assert response["result"]["outcomeCode"] == "claim_status_updated"
        assert event_types_of(sink, gateway) == [
            EventType.EXECUTION_STARTED,
            EventType.DECISION_RECORDED,
            EventType.OUTCOME_RECORDED,
        ]

    def test_allowed_decision_payload_fields(self):
        gateway, sink, _ = make_gateway()
        gateway.handle_message(call_tool())
        decision = event_payloads_of(sink, gateway)[1]
        assert decision["decision"] == "allow"
        assert decision["reason"] == "allow"
        assert decision["call_id"].startswith("call-")
        assert decision["principal"] == "agent-claims-bot"
        assert decision["identity_source"] == "declared"
        assert decision["policy_version"] == "policy-1"
        assert decision["tool_name"] == "update_claim_status"
        assert decision["input_schema_hash"] == input_schema_hash(CLAIM_SCHEMA)
        assert decision["config_version"] == "cfg-1"
        assert decision["idempotency_key"].startswith("idem-")

    def test_allowed_outcome_payload_fields(self):
        gateway, sink, _ = make_gateway()
        gateway.handle_message(call_tool())
        decision, outcome = event_payloads_of(sink, gateway)[1:]
        assert outcome["status"] == "success"
        assert outcome["call_id"] == decision["call_id"]
        assert outcome["outcome_code"] == "claim_status_updated"
        assert outcome["duration_ms"] >= 0
        assert outcome["idempotency_key"] == decision["idempotency_key"]

    def test_idempotency_key_injected_into_forwarded_arguments(self):
        gateway, sink, upstream = make_gateway()
        gateway.handle_message(call_tool())
        forwarded = upstream.calls[-1][1]["arguments"]
        decision = event_payloads_of(sink, gateway)[1]
        assert forwarded["idempotency_key"] == decision["idempotency_key"]
        assert forwarded["idempotency_key"].startswith("idem-")

    def test_client_supplied_idempotency_key_is_preserved(self):
        gateway, sink, upstream = make_gateway()
        response = gateway.handle_message(
            call_tool(arguments={"claim_id": "CLM-2", "status": "denied", "idempotency_key": "idem-client-1"})
        )
        assert "result" in response
        forwarded = upstream.calls[-1][1]["arguments"]
        assert forwarded["idempotency_key"] == "idem-client-1"
        decision, outcome = event_payloads_of(sink, gateway)[1:]
        assert decision["idempotency_key"] == "idem-client-1"
        assert outcome["idempotency_key"] == "idem-client-1"

    def test_no_idempotency_argument_configured_records_none(self):
        gateway, sink, upstream = make_gateway(config=make_config(idempotency_argument_name=None))
        gateway.handle_message(call_tool())
        decision, outcome = event_payloads_of(sink, gateway)[1:]
        assert decision["idempotency_key"] is None
        assert outcome["idempotency_key"] is None
        assert "idempotency_key" not in upstream.calls[-1][1]["arguments"]

    def test_execution_started_persisted_once_across_calls(self):
        started: list[str] = []
        gateway, sink, _ = make_gateway(on_execution_started=started.append)
        gateway.handle_message(call_tool(msg_id=1))
        gateway.handle_message(call_tool(msg_id=2))
        assert event_types_of(sink, gateway) == [
            EventType.EXECUTION_STARTED,
            EventType.DECISION_RECORDED,
            EventType.OUTCOME_RECORDED,
            EventType.DECISION_RECORDED,
            EventType.OUTCOME_RECORDED,
        ]
        assert started == [gateway.execution_id]

    def test_on_execution_started_hook_fires_before_first_forward(self):
        journal: list[tuple] = []
        upstream = FakeUpstream(journal=journal)
        gateway, _, _ = make_gateway(
            upstream=upstream, on_execution_started=lambda eid: journal.append(("hook", eid))
        )
        gateway.handle_message(call_tool())
        first_forward = next(i for i, entry in enumerate(journal) if entry == ("upstream", "tools/call"))
        hook_index = next(i for i, entry in enumerate(journal) if entry[0] == "hook")
        assert hook_index < first_forward


class TestDeniedCall:
    def test_unapproved_tool_denied_without_forward(self):
        gateway, sink, upstream = make_gateway()
        response = gateway.handle_message(call_tool(name="delete_everything"))
        assert response["error"]["code"] == GATEWAY_DENIED
        assert response["error"]["data"]["reason"] == "unapproved_tool"
        assert response["error"]["data"]["call_id"].startswith("call-")
        assert upstream.tools_call_count() == 0

    def test_denied_call_records_exactly_one_decision_event(self):
        gateway, sink, _ = make_gateway()
        gateway.handle_message(call_tool(name="delete_everything"))
        assert event_types_of(sink, gateway) == [EventType.DECISION_RECORDED]
        decision = event_payloads_of(sink, gateway)[0]
        assert decision["decision"] == "deny"
        assert decision["reason"] == "unapproved_tool"
        assert decision["tool_name"] == "delete_everything"
        assert decision["idempotency_key"] is None

    def test_denial_does_not_start_execution(self):
        gateway, sink, _ = make_gateway()
        gateway.handle_message(call_tool(name="delete_everything"))
        assert EventType.EXECUTION_STARTED not in event_types_of(sink, gateway)

    def test_schema_drift_denied_with_schema_changed_reason(self):
        drifted_tools = [{"name": "update_claim_status", "inputSchema": DRIFTED_SCHEMA}]
        gateway, sink, upstream = make_gateway(upstream=FakeUpstream(tools=drifted_tools))
        response = gateway.handle_message(call_tool())
        assert response["error"]["code"] == GATEWAY_DENIED
        assert response["error"]["data"]["reason"] == "schema_changed"
        assert upstream.tools_call_count() == 0
        decision = event_payloads_of(sink, gateway)[0]
        assert decision["decision"] == "deny"
        assert decision["reason"] == "schema_changed"
        # the recorded hash is the drifted one the gateway observed
        assert decision["input_schema_hash"] == input_schema_hash(DRIFTED_SCHEMA)


class TestFailClosedPersistence:
    def test_decision_append_failure_returns_error_and_blocks_forward(self):
        sink = FlakySink({EventType.DECISION_RECORDED})
        gateway, _, upstream = make_gateway(sink=sink)
        response = gateway.handle_message(call_tool())
        assert response["error"]["code"] == GATEWAY_PERSIST_FAILED
        assert response["error"]["message"] == "gateway_persist_failed"
        assert response["error"]["data"]["stage"] == "decision"
        assert upstream.tools_call_count() == 0
        # the decision (and outcome) never persisted; only the lazy
        # execution start happened before it
        assert event_types_of(sink, gateway) == [EventType.EXECUTION_STARTED]

    def test_execution_started_append_failure_blocks_forward(self):
        sink = FlakySink({EventType.EXECUTION_STARTED})
        gateway, _, upstream = make_gateway(sink=sink)
        response = gateway.handle_message(call_tool())
        assert response["error"]["code"] == GATEWAY_PERSIST_FAILED
        assert response["error"]["data"]["stage"] == "execution_started"
        assert upstream.tools_call_count() == 0
        assert sink.events(gateway.execution_id) == []

    def test_outcome_append_failure_hides_the_tool_result(self):
        sink = FlakySink({EventType.OUTCOME_RECORDED})
        gateway, _, upstream = make_gateway(sink=sink)
        response = gateway.handle_message(call_tool())
        assert response["error"]["code"] == GATEWAY_PERSIST_FAILED
        assert response["error"]["data"]["stage"] == "outcome"
        assert "result" not in response
        assert upstream.tools_call_count() == 1  # forwarded, but not answered to the client
        assert event_types_of(sink, gateway) == [
            EventType.EXECUTION_STARTED,
            EventType.DECISION_RECORDED,
        ]


class TestUnknownOutcome:
    def test_upstream_lost_records_unknown_and_never_retries(self):
        gateway, sink, upstream = make_gateway(
            upstream=FakeUpstream(call_response=UpstreamLost("server died mid-call"))
        )
        response = gateway.handle_message(call_tool())
        assert response["error"]["code"] == GATEWAY_UPSTREAM_LOST
        assert response["error"]["message"] == "gateway_upstream_lost"
        assert upstream.tools_call_count() == 1  # forwarded exactly once, never retried
        assert event_types_of(sink, gateway) == [
            EventType.EXECUTION_STARTED,
            EventType.DECISION_RECORDED,
            EventType.OUTCOME_RECORDED,
        ]
        decision, outcome = event_payloads_of(sink, gateway)[1:]
        assert outcome["status"] == "unknown"
        assert outcome["error_kind"] == "upstream_lost"
        assert outcome["call_id"] == decision["call_id"]
        assert response["error"]["data"]["call_id"] == decision["call_id"]
        assert outcome["idempotency_key"] == decision["idempotency_key"]


class TestToolRpcError:
    def test_tool_error_outcome_recorded_and_error_passed_through(self):
        tool_error = {"code": -32050, "message": "claim locked"}
        gateway, sink, _ = make_gateway(
            upstream=FakeUpstream(call_response={"jsonrpc": "2.0", "id": 1, "error": tool_error})
        )
        response = gateway.handle_message(call_tool())
        assert response["error"] == tool_error
        outcome = event_payloads_of(sink, gateway)[2]
        assert outcome["status"] == "error"
        assert outcome["error_kind"] == "rpc--32050"  # f"rpc-{code}" with a negative code
        assert outcome["idempotency_key"].startswith("idem-")


class TestOtherMethods:
    def test_initialize_answers_pinned_version_and_gateway_identity(self):
        gateway, _, upstream = make_gateway()
        response = gateway.handle_message(rpc("initialize", msg_id=1))
        assert response["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION
        assert response["result"]["serverInfo"]["name"] == "evidence-gateway"
        assert upstream.calls == []  # answered locally, no upstream work

    def test_tools_list_shows_only_approved_tools(self):
        gateway, _, upstream = make_gateway()
        response = gateway.handle_message(rpc("tools/list", msg_id=5))
        assert [tool["name"] for tool in response["result"]["tools"]] == ["update_claim_status"]
        assert any(method == "tools/list" for method, _ in upstream.calls)

    def test_tools_list_schema_cache_reused_for_later_decision(self):
        gateway, _, upstream = make_gateway()
        gateway.handle_message(rpc("tools/list", msg_id=5))
        gateway.handle_message(call_tool())
        list_calls = sum(1 for method, _ in upstream.calls if method == "tools/list")
        assert list_calls == 1  # the decision reused the discovery cache

    def test_malformed_json_returns_parse_error(self):
        gateway, _, _ = make_gateway()
        response = gateway.handle_message("{not json")
        assert response["error"]["code"] == -32700
        assert response["id"] is None

    def test_non_object_message_returns_invalid_request(self):
        gateway, _, _ = make_gateway()
        response = gateway.handle_message(json.dumps([1, 2, 3]))
        assert response["error"]["code"] == -32600

    def test_notification_yields_no_response(self):
        gateway, _, _ = make_gateway()
        notification = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert gateway.handle_message(notification) is None

    def test_generic_request_passthrough_forwards_without_evidence(self):
        gateway, sink, upstream = make_gateway()
        response = gateway.handle_message(rpc("ping", msg_id=9))
        assert response["result"] == {}
        assert upstream.calls[-1] == ("ping", {})
        assert sink.events(gateway.execution_id) == []

    def test_unknown_tool_not_served_by_upstream_is_denied_unapproved(self):
        gateway, sink, upstream = make_gateway()
        response = gateway.handle_message(call_tool(name="not_listed_tool"))
        assert response["error"]["code"] == GATEWAY_DENIED
        assert response["error"]["data"]["reason"] == "unapproved_tool"
        assert upstream.tools_call_count() == 0


# ---------------------------------------------------------------------------
# Subprocess integration tests through the real stdio path
# ---------------------------------------------------------------------------


def spawn_fake_server(tmp_path: Path, monkeypatch, mode: str, timeout_s: float = 10.0):
    """Start the fixture server; returns (upstream, apply-log path)."""
    apply_log = tmp_path / "apply.log"
    monkeypatch.setenv("FAKE_MODE", mode)
    monkeypatch.setenv("FAKE_APPLY_LOG", str(apply_log))
    monkeypatch.setenv("FAKE_IDEMPOTENCY_ARG", "idempotency_key")
    upstream = StdioUpstream([sys.executable, str(FIXTURE_SERVER)], timeout_s=timeout_s)
    return upstream, apply_log


class TestStdioIntegration:
    def test_stdio_roundtrip_full_evidence_chain(self, tmp_path, monkeypatch):
        sink = InMemoryEvidenceSink(EvidenceSigner.generate(), gateway_id="gw-test")

        with spawn_fake_server(tmp_path, monkeypatch, mode="normal")[0] as upstream:
            gateway = EvidenceGateway(make_config(), sink, upstream)

            initialized = gateway.handle_message(rpc("initialize", msg_id=1))
            assert initialized["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION

            listed = gateway.handle_message(rpc("tools/list", msg_id=2))
            assert [tool["name"] for tool in listed["result"]["tools"]] == ["update_claim_status"]

            response = gateway.handle_message(
                call_tool(msg_id=3, arguments={"claim_id": "CLM-7", "status": "approved"})
            )
            assert response["result"]["outcomeCode"] == "claim_status_updated"

        assert event_types_of(sink, gateway) == [
            EventType.EXECUTION_STARTED,
            EventType.DECISION_RECORDED,
            EventType.OUTCOME_RECORDED,
        ]
        decision, outcome = event_payloads_of(sink, gateway)[1:]
        assert decision["decision"] == "allow"
        assert outcome["status"] == "success"
        assert outcome["outcome_code"] == "claim_status_updated"
        assert outcome["call_id"] == decision["call_id"]

        # the gateway-injected key is the one the server actually applied
        apply_log = tmp_path / "apply.log"
        log_lines = apply_log.read_text().splitlines()
        assert len(log_lines) == 1
        assert decision["idempotency_key"] in log_lines[0]
        assert "claim=CLM-7" in log_lines[0]

    def test_stdio_retry_with_same_idempotency_key_applies_once(self, tmp_path, monkeypatch):
        sink = InMemoryEvidenceSink(EvidenceSigner.generate(), gateway_id="gw-test")
        arguments = {"claim_id": "CLM-9", "status": "denied", "idempotency_key": "idem-fixed-1"}

        with spawn_fake_server(tmp_path, monkeypatch, mode="normal")[0] as upstream:
            gateway = EvidenceGateway(make_config(), sink, upstream)
            first = gateway.handle_message(call_tool(msg_id=1, arguments=arguments))
            second = gateway.handle_message(call_tool(msg_id=2, arguments=arguments))

        assert first["result"] == second["result"]  # same result, no duplicate mutation
        apply_log = tmp_path / "apply.log"
        assert len(apply_log.read_text().splitlines()) == 1
        outcomes = outcome_payloads_of(sink, gateway)
        assert [payload["status"] for payload in outcomes] == ["success", "success"]
        assert [payload["idempotency_key"] for payload in outcomes] == ["idem-fixed-1", "idem-fixed-1"]

    def test_stdio_crash_after_apply_records_unknown_outcome(self, tmp_path, monkeypatch):
        sink = InMemoryEvidenceSink(EvidenceSigner.generate(), gateway_id="gw-test")

        with spawn_fake_server(tmp_path, monkeypatch, mode="crash_after_apply")[0] as upstream:
            gateway = EvidenceGateway(make_config(), sink, upstream)
            response = gateway.handle_message(
                call_tool(msg_id=1, arguments={"claim_id": "CLM-42", "status": "approved"})
            )

        assert response["error"]["code"] == GATEWAY_UPSTREAM_LOST
        assert event_types_of(sink, gateway) == [
            EventType.EXECUTION_STARTED,
            EventType.DECISION_RECORDED,
            EventType.OUTCOME_RECORDED,
        ]
        decision, outcome = event_payloads_of(sink, gateway)[1:]
        assert outcome["status"] == "unknown"
        assert outcome["error_kind"] == "upstream_lost"
        assert response["error"]["data"]["call_id"] == decision["call_id"]
        # exactly why outcome=unknown matters: the mutation DID apply
        apply_log = tmp_path / "apply.log"
        log_text = apply_log.read_text()
        assert "claim=CLM-42" in log_text
        assert decision["idempotency_key"] in log_text

    def test_stdio_slow_upstream_times_out_records_unknown(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FAKE_SLOW_SECONDS", "5")
        sink = InMemoryEvidenceSink(EvidenceSigner.generate(), gateway_id="gw-test")

        with spawn_fake_server(tmp_path, monkeypatch, mode="slow", timeout_s=0.5)[0] as upstream:
            gateway = EvidenceGateway(make_config(), sink, upstream)
            response = gateway.handle_message(
                call_tool(msg_id=1, arguments={"claim_id": "CLM-11", "status": "approved"})
            )

        assert response["error"]["code"] == GATEWAY_UPSTREAM_LOST
        outcome = event_payloads_of(sink, gateway)[2]
        assert outcome["status"] == "unknown"
        assert outcome["error_kind"] == "upstream_lost"


class TestGatewayConfigLoading:
    def test_from_json_file_roundtrip(self, tmp_path):
        config_path = tmp_path / "gw.json"
        config_path.write_text(
            json.dumps(
                {
                    "gateway_id": "gw-demo",
                    "principal": "agent-claims-bot",
                    "policy_version": "policy-1",
                    "config_version": "cfg-1",
                    "bindings": [claim_binding().model_dump(mode="json")],
                    "upstream_command": [sys.executable, str(FIXTURE_SERVER)],
                    "idempotency_argument_name": "idempotency_key",
                    "upstream_timeout_s": 2.5,
                }
            ),
            encoding="utf-8",
        )
        config = GatewayConfig.from_json_file(config_path)
        assert config.gateway_id == "gw-demo"
        assert config.upstream_timeout_s == 2.5
        assert config.bindings[0].tool_name == "update_claim_status"
        assert config.identity_source.value == "declared"

    def test_unknown_fields_rejected(self, tmp_path):
        config_path = tmp_path / "gw.json"
        config_path.write_text(json.dumps({"gateway_id": "gw", "unexpected": True}), encoding="utf-8")
        with pytest.raises(ValidationError):
            GatewayConfig.from_json_file(config_path)

    def test_from_dict_rejects_empty_upstream_command(self):
        with pytest.raises(ValidationError):
            GatewayConfig.from_dict(
                {
                    "gateway_id": "gw",
                    "principal": "p",
                    "policy_version": "pv",
                    "config_version": "cv",
                    "upstream_command": [],
                }
            )
