"""Agent Evidence Box — signed, offline-verifiable evidence for controlled MCP flows.

The package implements the trust boundary described in
``docs/plans/agent-evidence-box.md``: an MCP gateway records every
request decision and observed outcome into a per-execution Ed25519
hash chain; an independent checkpoint store pins expected executions;
an exporter bundles a package (``manifest.json``, ``events.ndjson``,
``signature``); a separately usable CLI verifies packages offline.

Subsystems (one owning module each):

- ``evidence.canonical``   — RFC 8785 canonical JSON subset (signed encoding)
- ``evidence.schema``      — the shared typed contract (events, manifests, verdicts)
- ``evidence.signing``     — Ed25519 sign/verify, key ids
- ``evidence.contracts``   — ``EvidenceSink`` protocol + in-memory reference sink
- ``evidence.ledger``      — atomic SQLite chain ledger (production sink)
- ``evidence.gateway``     — MCP stdio gateway (policy + fail-closed persistence)
- ``evidence.checkpoint``  — independent checkpoint store
- ``evidence.package``     — evidence package exporter
- ``evidence.verify``      — offline package verifier (stdlib + cryptography only)
- ``evidence.cli``         — ``peaky-peek-evidence`` command line
- ``evidence.adapter``     — maps verified packages onto the Peaky Peek timeline
"""

from evidence.canonical import CanonicalizationError, canonical_json, canonicalize, sha256_hex
from evidence.contracts import EvidenceSink, InMemoryEvidenceSink
from evidence.schema import (
    EVENT_SCHEMA_VERSION,
    GENESIS_PREV_HASH,
    MCP_PROTOCOL_VERSION,
    PACKAGE_FORMAT_VERSION,
    ChainHead,
    CheckpointRef,
    CoverageDescription,
    CoverageVerdict,
    DecisionKind,
    DecisionPayload,
    EventDraft,
    EventType,
    EvidenceEvent,
    ExecutionStartedPayload,
    ExecutionStartRecord,
    FinalCheckpoint,
    IntegrityFinding,
    IntegrityVerdict,
    OutcomePayload,
    OutcomeStatus,
    OutcomeSummary,
    PackageManifest,
    SignedEventRecord,
    ToolBinding,
    VerificationResult,
)
from evidence.signing import EvidenceSigner, SignatureError, verify_signature

__all__ = [
    "CanonicalizationError",
    "EvidenceSink",
    "InMemoryEvidenceSink",
    "GENESIS_PREV_HASH",
    "EVENT_SCHEMA_VERSION",
    "PACKAGE_FORMAT_VERSION",
    "MCP_PROTOCOL_VERSION",
    "ChainHead",
    "CheckpointRef",
    "CoverageDescription",
    "CoverageVerdict",
    "DecisionKind",
    "DecisionPayload",
    "EventDraft",
    "EventType",
    "EvidenceEvent",
    "ExecutionStartRecord",
    "ExecutionStartedPayload",
    "FinalCheckpoint",
    "IntegrityFinding",
    "IntegrityVerdict",
    "OutcomeStatus",
    "OutcomeSummary",
    "OutcomePayload",
    "PackageManifest",
    "SignedEventRecord",
    "ToolBinding",
    "VerificationResult",
    "EvidenceSigner",
    "SignatureError",
    "verify_signature",
    "canonical_json",
    "canonicalize",
    "sha256_hex",
]
