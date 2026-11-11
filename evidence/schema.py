"""Typed data contract for the Agent Evidence Box.

This module is the stable contract shared across the whole evidence
pipeline — chain ledger, MCP gateway, checkpoint store, package
exporter, offline verifier, CLI and the Peaky Peek adapter all speak
these types.  Treat changes here as contract changes and bump
``EVENT_SCHEMA_VERSION`` / ``PACKAGE_FORMAT_VERSION`` accordingly.

Rules inherited from ``docs/plans/agent-evidence-box.md``:

- Events carry an allow-listed metadata payload only.  Tool arguments
  and results are omitted by default; any permitted field passes
  redaction before signing, storage and export.
- The signed unit is the canonical JSON encoding (RFC 8785 subset,
  ``evidence.canonical``) of the :class:`EvidenceEvent` content.
  ``hash`` and ``signature`` live on the enclosing
  :class:`SignedEventRecord`, never inside the signed content.
- ``seq`` is a monotonic per-execution sequence starting at 1.  Chains
  are per-execution; the genesis ``prev_hash`` is 64 zeros.
- Timestamps are timezone-aware UTC and serialize as ISO-8601 strings.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from evidence.canonical import canonicalize, sha256_hex

__all__ = [
    "EVENT_SCHEMA_VERSION",
    "PACKAGE_FORMAT_VERSION",
    "GENESIS_PREV_HASH",
    "MCP_PROTOCOL_VERSION",
    "EventType",
    "DecisionKind",
    "OutcomeStatus",
    "IdentitySource",
    "EventDraft",
    "EvidenceEvent",
    "SignedEventRecord",
    "ChainHead",
    "ExecutionStartedPayload",
    "DecisionPayload",
    "OutcomePayload",
    "ToolBinding",
    "CoverageDescription",
    "DEFAULT_COVERAGE",
    "CheckpointRef",
    "PackageManifest",
    "ExecutionStartRecord",
    "FinalCheckpoint",
    "IntegrityFinding",
    "IntegrityVerdict",
    "CoverageVerdict",
    "OutcomeSummary",
    "VerificationResult",
    "utc_now",
    "event_content_bytes",
    "event_hash",
    "checkpoint_body_bytes",
    "manifest_bytes",
    "input_schema_hash",
]

#: Version of the event/record schema carried by every signed event.
EVENT_SCHEMA_VERSION = 1

#: Version of the exported package layout (manifest.json, events.ndjson, signature).
PACKAGE_FORMAT_VERSION = 1

#: ``prev_hash`` of the first event (seq 1) of every execution chain.
GENESIS_PREV_HASH = "0" * 64

#: The pilot pins one MCP protocol version and one transport (JSON-RPC 2.0 over stdio).
MCP_PROTOCOL_VERSION = "2025-06-18"


def utc_now() -> datetime:
    """Timezone-aware UTC now — the only clock used inside signed content."""
    return datetime.now(timezone.utc)


class EventType(str, Enum):
    EXECUTION_STARTED = "execution.started"
    DECISION_RECORDED = "decision.recorded"
    OUTCOME_RECORDED = "outcome.recorded"


class DecisionKind(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class OutcomeStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    UNKNOWN = "unknown"


class IdentitySource(str, Enum):
    #: Pilot: principal configured on the gateway instance (stdio transport).
    DECLARED = "declared"
    #: Identity established through authentication.
    AUTHENTICATED = "authenticated"


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


class EventDraft(BaseModel):
    """Unsigned event content handed by the gateway to its ``EvidenceSink``.

    The sink owns sequence numbering, chain linkage, gateway identity and
    signing, so drafts carry only what the emitting component observed.
    """

    type: EventType
    execution_id: str = Field(min_length=1, max_length=128)
    recorded_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class EvidenceEvent(BaseModel):
    """A fully numbered, chain-linked event ready for signing.

    The canonical JSON encoding of this model (as a plain dict) is the
    signed content: seq assignment, ``prev_hash`` linkage and the
    signature over it must happen atomically in the ledger.
    """

    schema_version: int = EVENT_SCHEMA_VERSION
    type: EventType
    execution_id: str = Field(min_length=1, max_length=128)
    seq: int = Field(ge=1)
    prev_hash: str
    gateway_id: str = Field(min_length=1)
    key_id: str = Field(min_length=1)
    recorded_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class SignedEventRecord(BaseModel):
    """An :class:`EvidenceEvent` plus its content hash and Ed25519 signature."""

    event: EvidenceEvent
    hash: str
    signature: str


class ChainHead(BaseModel):
    """Head of one execution's chain, as maintained by the evidence sink."""

    execution_id: str
    last_seq: int = Field(ge=1)
    last_hash: str
    event_count: int = Field(ge=1)


# ---------------------------------------------------------------------------
# Typed event payloads (allow-listed metadata; no arguments/results by default)
# ---------------------------------------------------------------------------


class ExecutionStartedPayload(BaseModel):
    principal: str
    identity_source: IdentitySource = IdentitySource.DECLARED
    policy_version: str
    run_id: str | None = None


class DecisionPayload(BaseModel):
    decision: DecisionKind
    reason: str
    call_id: str
    principal: str
    identity_source: IdentitySource = IdentitySource.DECLARED
    policy_version: str
    tool_name: str
    input_schema_hash: str
    config_version: str
    run_id: str | None = None
    idempotency_key: str | None = None


class OutcomePayload(BaseModel):
    call_id: str
    status: OutcomeStatus
    outcome_code: str | None = None
    error_kind: str | None = None
    duration_ms: int | None = None
    idempotency_key: str | None = None


class ToolBinding(BaseModel):
    """Approved binding of a tool name+schema to a server identity and config version.

    A schema change (different ``input_schema_hash``) requires explicit
    re-approval before the gateway allows the tool again.
    """

    tool_name: str
    input_schema_hash: str
    approved_server: str
    config_version: str


# ---------------------------------------------------------------------------
# Package manifest and coverage
# ---------------------------------------------------------------------------


class CoverageDescription(BaseModel):
    """Plain-language statement of what the evidence does and does not prove."""

    in_scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)


DEFAULT_COVERAGE = CoverageDescription(
    in_scope=[
        "MCP tools/list and tools/call routed through the evidence gateway (single client, single server)",
        "Gateway-observed request decisions, forwarded calls and observed outcomes",
    ],
    out_of_scope=[
        "shell commands",
        "local file access",
        "model provider calls",
        "direct calls to other services",
    ],
)


class CheckpointRef(BaseModel):
    """Expected execution totals an independently obtained checkpoint must match."""

    event_count: int = Field(ge=1)
    final_hash: str
    checkpoint_signature: str | None = None


class PackageManifest(BaseModel):
    manifest_schema_version: int = Field(default=1)
    schema_version: int = EVENT_SCHEMA_VERSION
    package_format_version: int = PACKAGE_FORMAT_VERSION
    gateway_id: str
    execution_id: str
    event_count: int = Field(ge=1)
    final_hash: str
    key_id: str
    created_at: datetime
    coverage: CoverageDescription = Field(default_factory=CoverageDescription)
    checkpoint: CheckpointRef | None = None


# ---------------------------------------------------------------------------
# Independent checkpoint store records
# ---------------------------------------------------------------------------


class ExecutionStartRecord(BaseModel):
    """Recorded before the first forwarded call of an execution."""

    execution_id: str
    gateway_id: str
    recorded_at: datetime
    principal: str
    policy_version: str


class FinalCheckpoint(BaseModel):
    """Signed closing statement: event count and final chain hash of an execution."""

    execution_id: str
    gateway_id: str
    event_count: int = Field(ge=1)
    final_hash: str
    checkpoint_key_id: str
    recorded_at: datetime
    signature: str


# ---------------------------------------------------------------------------
# Verifier verdicts — produced by the offline verifier, consumed by the
# Peaky Peek adapter.  Three independent sections per the plan: integrity,
# execution coverage, and outcome knownness.
# ---------------------------------------------------------------------------


class IntegrityFinding(BaseModel):
    kind: str
    detail: str
    execution_id: str | None = None
    seq: int | None = None


class IntegrityVerdict(BaseModel):
    ok: bool = False
    findings: list[IntegrityFinding] = Field(default_factory=list)
    verified_events: int = 0
    verified_key_ids: list[str] = Field(default_factory=list)


class CoverageVerdict(BaseModel):
    complete: bool = False
    missing_executions: list[str] = Field(default_factory=list)
    missing_final_checkpoint: bool = False
    detail: str = ""


class OutcomeSummary(BaseModel):
    known: int = 0
    unknown: int = 0
    unknown_call_ids: list[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    ok: bool = False
    package_path: str = ""
    execution_id: str = ""
    integrity: IntegrityVerdict = Field(default_factory=IntegrityVerdict)
    coverage: CoverageVerdict = Field(default_factory=CoverageVerdict)
    outcomes: OutcomeSummary = Field(default_factory=OutcomeSummary)
    verified_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Hash/signature input helpers — the single source of "what gets signed"
# ---------------------------------------------------------------------------


def event_content_bytes(event: EvidenceEvent) -> bytes:
    """Canonical bytes of an event — the input to hashing and signing."""
    return canonicalize(event.model_dump(mode="json"))


def event_hash(event: EvidenceEvent) -> str:
    """SHA-256 hex of the canonical event content."""
    return sha256_hex(event_content_bytes(event))


def checkpoint_body_bytes(checkpoint: FinalCheckpoint) -> bytes:
    """Canonical bytes of a final checkpoint, excluding its ``signature``."""
    body = checkpoint.model_dump(mode="json", exclude={"signature"})
    return canonicalize(body)


def manifest_bytes(manifest: PackageManifest) -> bytes:
    """Canonical bytes of a package manifest — the input to the package signature."""
    return canonicalize(manifest.model_dump(mode="json"))


def input_schema_hash(schema: dict[str, Any]) -> str:
    """Hash of an MCP tool input schema, used for tool bindings."""
    return sha256_hex(canonicalize(schema))
