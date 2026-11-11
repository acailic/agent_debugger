"""Evidence package exporter — the auditor-facing delivery unit.

``export_package`` writes the package layout of
``docs/plans/agent-evidence-box.md`` §"Isporuka auditoru" into a
directory:

- ``manifest.json`` — the :class:`PackageManifest` dumped with
  ``indent=2`` so a human can read and diff it;
- ``events.ndjson`` — one :class:`SignedEventRecord` per line, in seq
  order, written verbatim (signed records are never re-encoded or
  touched);
- ``signature`` — a JSON sidecar
  ``{"algorithm": "ed25519", "key_id": ..., "signed_object":
  "manifest.canonical", "signature": "<hex>"}`` whose signature is over
  ``manifest_bytes(manifest)`` — the CANONICAL JSON of the manifest
  content, NOT the pretty file bytes.  The offline verifier re-parses
  ``manifest.json``, rebuilds the manifest model, recomputes
  ``manifest_bytes`` and only then checks the signature; pretty-printing
  is representation, never signed surface.

Export is fail-closed, as defense-in-depth on top of gateway-side
redaction.  Before anything is written the exporter validates that the
records form exactly one execution's contiguous chain (seq 1..N), that
every hash and signature verifies against the gateway public key, and
that every payload key is on the per-type allowlist derived from the
typed payload models — "arguments and results are omitted by default"
is enforced here too: anything outside the allowlist is refused, not
scrubbed.
"""

from __future__ import annotations

import json
from pathlib import Path

from evidence.canonical import CanonicalizationError
from evidence.schema import (
    DEFAULT_COVERAGE,
    EVENT_SCHEMA_VERSION,
    PACKAGE_FORMAT_VERSION,
    CheckpointRef,
    CoverageDescription,
    DecisionPayload,
    EventType,
    ExecutionStartedPayload,
    FinalCheckpoint,
    OutcomePayload,
    PackageManifest,
    SignedEventRecord,
    event_content_bytes,
    event_hash,
    manifest_bytes,
    utc_now,
)
from evidence.signing import ALGORITHM, EvidenceSigner, verify_signature

__all__ = ["PackageError", "export_package", "read_events", "read_manifest"]

MANIFEST_FILENAME = "manifest.json"
EVENTS_FILENAME = "events.ndjson"
SIGNATURE_FILENAME = "signature"

#: What the ``signature`` file's ``signed_object`` field names.
SIGNED_OBJECT = "manifest.canonical"

#: Payload allowlist per event type: exactly the field names the typed
#: payload models in ``evidence.schema`` emit via ``model_dump`` (pydantic
#: v2 dumps every declared field, optional ones as ``null`` — there are no
#: other artifacts, so the model field names are the precise allowlist).
_PAYLOAD_FIELDS: dict[EventType, frozenset[str]] = {
    EventType.EXECUTION_STARTED: frozenset(ExecutionStartedPayload.model_fields),
    EventType.DECISION_RECORDED: frozenset(DecisionPayload.model_fields),
    EventType.OUTCOME_RECORDED: frozenset(OutcomePayload.model_fields),
}


class PackageError(ValueError):
    """Export refused: invalid chain, bad hash/signature, or off-allowlist payload."""


def export_package(
    out_dir: Path | str,
    records: list[SignedEventRecord],
    signer: EvidenceSigner,
    gateway_id: str,
    gateway_public_pem: bytes,
    coverage: CoverageDescription | None = None,
    checkpoint: FinalCheckpoint | None = None,
) -> PackageManifest:
    """Validate and write one execution's signed event chain as a package.

    Nothing is written unless *every* pre-export validation passes — the
    exporter never emits a package it would refuse to verify.
    """
    ordered = list(records)
    _validate_chain(ordered)
    for record in ordered:
        _verify_record(record, gateway_public_pem)
        _validate_payload_allowlist(record)

    last = ordered[-1]
    manifest = PackageManifest(
        schema_version=EVENT_SCHEMA_VERSION,
        package_format_version=PACKAGE_FORMAT_VERSION,
        gateway_id=gateway_id,
        execution_id=last.event.execution_id,
        event_count=len(ordered),
        final_hash=last.hash,
        key_id=signer.key_id,
        created_at=utc_now(),
        coverage=coverage if coverage is not None else DEFAULT_COVERAGE,
        checkpoint=_checkpoint_ref(checkpoint) if checkpoint is not None else None,
    )

    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    # Pretty on disk for humans; the signature below is over the canonical
    # encoding of the manifest content, so formatting changes nothing.
    (directory / MANIFEST_FILENAME).write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    (directory / EVENTS_FILENAME).write_text(
        "".join(record.model_dump_json() + "\n" for record in ordered), encoding="utf-8"
    )
    signature_hex = signer.sign(manifest_bytes(manifest))
    (directory / SIGNATURE_FILENAME).write_text(
        _signature_document(manifest.key_id, signature_hex), encoding="utf-8"
    )
    return manifest


def read_manifest(directory: Path | str) -> PackageManifest:
    """Parse ``manifest.json`` from an exported package."""
    return PackageManifest.model_validate_json(
        (Path(directory) / MANIFEST_FILENAME).read_text(encoding="utf-8")
    )


def read_events(directory: Path | str) -> list[SignedEventRecord]:
    """Parse ``events.ndjson`` from an exported package (seq order on disk)."""
    lines = (Path(directory) / EVENTS_FILENAME).read_text(encoding="utf-8").splitlines()
    return [SignedEventRecord.model_validate_json(line) for line in lines if line.strip()]


def _signature_document(key_id: str, signature_hex: str) -> str:
    return json.dumps(
        {
            "algorithm": ALGORITHM,
            "key_id": key_id,
            "signed_object": SIGNED_OBJECT,
            "signature": signature_hex,
        },
        indent=2,
    ) + "\n"


def _checkpoint_ref(checkpoint: FinalCheckpoint) -> CheckpointRef:
    return CheckpointRef(
        event_count=checkpoint.event_count,
        final_hash=checkpoint.final_hash,
        checkpoint_signature=checkpoint.signature,
    )


def _validate_chain(records: list[SignedEventRecord]) -> None:
    if not records:
        raise PackageError("cannot export an empty event chain")
    execution_ids = {record.event.execution_id for record in records}
    if len(execution_ids) != 1:
        raise PackageError(f"records span multiple executions: {sorted(execution_ids)}")
    seqs = [record.event.seq for record in records]
    expected = list(range(1, len(records) + 1))
    if seqs != expected:
        raise PackageError(f"event sequence must be contiguous 1..{len(records)} in order, got {seqs}")


def _verify_record(record: SignedEventRecord, gateway_public_pem: bytes) -> None:
    seq = record.event.seq
    try:
        content = event_content_bytes(record.event)
    except CanonicalizationError as exc:
        raise PackageError(f"event seq {seq} is not canonicalizable: {exc}") from exc
    if event_hash(record.event) != record.hash:
        raise PackageError(f"event seq {seq}: recomputed hash does not match record hash")
    try:
        verified = verify_signature(gateway_public_pem, content, record.signature)
    except ValueError as exc:
        # Malformed public key or signature encoding — fail closed.
        raise PackageError(f"event seq {seq}: signature check error: {exc}") from exc
    if not verified:
        raise PackageError(f"event seq {seq}: signature verification failed")


def _validate_payload_allowlist(record: SignedEventRecord) -> None:
    event = record.event
    allowed = _PAYLOAD_FIELDS.get(event.type)
    if allowed is None:
        raise PackageError(f"event seq {event.seq}: unknown event type {event.type!r}")
    extra = set(event.payload) - allowed
    if extra:
        raise PackageError(
            f"event seq {event.seq} ({event.type.value}): payload keys outside the "
            f"allowlist for this event type: {sorted(extra)}"
        )
