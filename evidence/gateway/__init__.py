"""MCP evidence gateway — policy-enforcing proxy with fail-closed evidence.

One client, one server, JSON-RPC 2.0 over stdio, protocol version
pinned to ``evidence.schema.MCP_PROTOCOL_VERSION``.  See
``evidence.gateway.proxy`` for the controlled ``tools/call`` flow and
the gateway-specific JSON-RPC error codes.
"""

from evidence.gateway.config import GatewayConfig
from evidence.gateway.policy import PolicyDecision, ToolPolicy
from evidence.gateway.proxy import (
    GATEWAY_DENIED,
    GATEWAY_PERSIST_FAILED,
    GATEWAY_UPSTREAM_LOST,
    EvidenceGateway,
    main,
)
from evidence.gateway.rpc import StdioUpstream, UpstreamLost
from evidence.gateway.runtime import GatewayRuntime, build_runtime, finalize_execution

__all__ = [
    "EvidenceGateway",
    "GatewayConfig",
    "GatewayRuntime",
    "ToolPolicy",
    "PolicyDecision",
    "StdioUpstream",
    "UpstreamLost",
    "GATEWAY_DENIED",
    "GATEWAY_UPSTREAM_LOST",
    "GATEWAY_PERSIST_FAILED",
    "build_runtime",
    "finalize_execution",
    "main",
]
