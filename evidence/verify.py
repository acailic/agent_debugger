"""Offline verification of exported evidence packages.

This is the auditor's half of the Agent Evidence Box: it runs on a
machine of the auditor's choosing, with no access to the gateway, its
key material or any database.  Inputs are the exported package
directory (``manifest.json``, ``events.ndjson``, ``signature``), a key
registry the customer controls, and — when available — a
:class:`~evidence.schema.FinalCheckpoint` obtained independently from
the checkpoint store.

Design rules inherited from ``docs/plans/agent-evidence-box.md``:

- The verifier never raises on a bad package: every problem becomes an
  :class:`~evidence.schema.IntegrityFinding` with a stable snake_case
  ``kind`` so other tooling can match on it.
- Unknown key ids are verification failures (``unknown_key``), never
  exceptions.  Retired keys keep verifying — the registry exists so
  historical packages remain verifiable after key rotation.
- Integrity, execution coverage and outcome knownness are reported as
  three independent sections; a missing checkpoint marks the package
  incomplete without invalidating the integrity of what is present.
- The module depends only on the shared contract
  (``evidence.schema`` / ``evidence.canonical`` / ``evidence.signing``)
  so it stays independently usable and distributable.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple

from pydantic import BaseModel, ValidationError

from evidence.canonical import CanonicalizationError, sha256_hex
from evidence.schema import (
    GENESIS_PREV_HASH,
    CoverageVerdict,
    EventType,
    FinalCheckpoint,
    IntegrityFinding,
    IntegrityVerdict,
    OutcomeStatus,
    OutcomeSummary,
    PackageManifest,
    SignedEventRecord,
    VerificationResult,
    checkpoint_body_bytes,
    event_content_bytes,
    manifest_bytes,
)
from evidence.signing import SignatureError, load_public_key, verify_signature

__all__ = ["RegistryKey", "KeyRegistry", "verify_package"]


# ---------------------------------------------------------------------------
# Key registry — the trust anchor the customer controls
# ---------------------------------------------------------------------------


class RegistryKey(BaseModel):
    """One entry of the customer-controlled public key registry.

    ``status`` and the validity window are bookkeeping for the customer;
    verification only requires the key id to be listed.  Retired keys
    therefore keep verifying historical packages after rotation, which
    is exactly what the registry is for.
    """

    key_id: str
    public_key_pem: str
    status: str = "active"
    valid_from: str | None = None
    valid_to: str | None = None
    role: str = "any"


class KeyRegistry:
    """Pre-verified set of Ed25519 public keys, loaded from a JSON file.

    File format::

        {"keys": [{"key_id": "...", "public_key_pem": "...", "status": "active",
                   "valid_from": "ISO", "valid_to": null, "role": "gateway"}]}

    Loading raises :class:`ValueError` (or :class:`OSError`) for an
    unreadable or malformed registry — that is an environment problem
    for the caller to fix, unlike an unknown key inside a package,
    which is a verification failure.
    """

    def __init__(self, entries: list[RegistryKey]) -> None:
        self._by_id: dict[str, RegistryKey] = {entry.key_id: entry for entry in entries}

    @classmethod
    def load(cls, path: Path | str) -> KeyRegistry:
        """Load a registry from *path* (JSON, see the class docstring)."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> KeyRegistry:
        """Build a registry from an already-parsed mapping."""
        raw_keys = data.get("keys") if isinstance(data, Mapping) else None
        if not isinstance(raw_keys, list):
            raise ValueError("key registry must be a JSON object with a 'keys' list")
        entries: list[RegistryKey] = []
        seen: set[str] = set()
        for index, raw in enumerate(raw_keys):
            try:
                entry = RegistryKey.model_validate(raw)
            except ValidationError as exc:
                reason = exc.errors()[0]
                raise ValueError(f"registry entry {index} is invalid: {reason.get('msg', exc)}") from exc
            if entry.key_id in seen:
                raise ValueError(f"duplicate key_id in registry: {entry.key_id}")
            seen.add(entry.key_id)
            try:
                load_public_key(entry.public_key_pem)
            except SignatureError as exc:
                raise ValueError(f"registry entry {index} ({entry.key_id}): {exc}") from exc
            entries.append(entry)
        return cls(entries)

    def pem_for(self, key_id: str) -> str | None:
        """PEM of *key_id*, or None when the key is not in the registry."""
        entry = self._by_id.get(key_id)
        return entry.public_key_pem if entry is not None else None

    def is_known(self, key_id: str) -> bool:
        """True when *key_id* is listed in the registry."""
        return key_id in self._by_id

    def known_key_ids(self) -> list[str]:
        """Sorted list of every key id in the registry."""
        return sorted(self._by_id)


# ---------------------------------------------------------------------------
# Package verification
# ---------------------------------------------------------------------------


class _Event(NamedTuple):
    """One parseable ndjson line, with its canonical content precomputed."""

    line: int
    record: SignedEventRecord
    content: bytes
    content_hash: str


def verify_package(
    package_dir: Path | str,
    registry: KeyRegistry,
    checkpoint: FinalCheckpoint | None = None,
    expected_executions: list[str] | None = None,
) -> VerificationResult:
    """Verify an evidence package directory offline and return the verdict.

    Never raises for package content problems — each problem is
    reported as an integrity finding.  ``ok`` is True only when the
    integrity section has no findings AND coverage is complete (a
    matching checkpoint was provided and the package's execution is
    among the expected ones, when expectations were given).
    """
    package_path = Path(package_dir)
    findings: list[IntegrityFinding] = []
    verified_key_ids: set[str] = set()

    manifest = _load_manifest(package_path, findings)
    _verify_manifest_signature(package_path, manifest, registry, findings, verified_key_ids)
    events = _load_events(package_path, findings)
    verified_events = _verify_event_records(events, registry, findings, verified_key_ids)
    _verify_chain(events, findings)
    execution_id = _verify_consistency(events, manifest, findings)
    _verify_manifest_totals(events, manifest, findings)
    checkpoint_matches = _verify_checkpoint(checkpoint, manifest, registry, findings, verified_key_ids)
    coverage = _coverage_verdict(execution_id, checkpoint, checkpoint_matches, expected_executions)
    integrity = IntegrityVerdict(
        ok=not findings,
        findings=findings,
        verified_events=verified_events,
        verified_key_ids=sorted(verified_key_ids),
    )
    return VerificationResult(
        ok=integrity.ok and coverage.complete,
        package_path=str(package_path),
        execution_id=execution_id,
        integrity=integrity,
        coverage=coverage,
        outcomes=_summarize_outcomes(events),
    )


# ---------------------------------------------------------------------------
# Loading steps
# ---------------------------------------------------------------------------


def _load_manifest(package_path: Path, findings: list[IntegrityFinding]) -> PackageManifest | None:
    if not package_path.is_dir():
        findings.append(
            IntegrityFinding(kind="manifest_malformed", detail=f"package directory not found: {package_path}")
        )
        return None
    try:
        text = (package_path / "manifest.json").read_text(encoding="utf-8")
    except OSError as exc:
        findings.append(IntegrityFinding(kind="manifest_malformed", detail=f"cannot read manifest.json: {exc}"))
        return None
    try:
        return PackageManifest.model_validate_json(text)
    except ValidationError as exc:
        reason = exc.errors()[0]
        findings.append(
            IntegrityFinding(
                kind="manifest_malformed", detail=f"manifest.json is not a valid package manifest: {reason.get('msg')}"
            )
        )
        return None


def _load_events(package_path: Path, findings: list[IntegrityFinding]) -> list[_Event]:
    path = package_path / "events.ndjson"
    if not path.is_file():
        findings.append(IntegrityFinding(kind="event_malformed", detail="events.ndjson not found in package"))
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        findings.append(IntegrityFinding(kind="event_malformed", detail=f"cannot read events.ndjson: {exc}"))
        return []
    events: list[_Event] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = SignedEventRecord.model_validate_json(line)
            content = event_content_bytes(record.event)
        except ValidationError as exc:
            reason = exc.errors()[0]
            findings.append(
                IntegrityFinding(
                    kind="event_malformed",
                    detail=f"line {line_number}: not a valid signed event record: {reason.get('msg')}",
                )
            )
            continue
        except CanonicalizationError as exc:
            findings.append(
                IntegrityFinding(
                    kind="event_malformed",
                    detail=f"line {line_number}: event content not representable in canonical JSON: {exc}",
                )
            )
            continue
        events.append(
            _Event(line=line_number, record=record, content=content, content_hash=sha256_hex(content))
        )
    return events


# ---------------------------------------------------------------------------
# Signature and hash checks
# ---------------------------------------------------------------------------


def _verify_manifest_signature(
    package_path: Path,
    manifest: PackageManifest | None,
    registry: KeyRegistry,
    findings: list[IntegrityFinding],
    verified_key_ids: set[str],
) -> None:
    path = package_path / "signature"
    try:
        signature = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        findings.append(IntegrityFinding(kind="signature_file_malformed", detail=f"cannot read signature file: {exc}"))
        return
    if not signature:
        findings.append(IntegrityFinding(kind="signature_file_malformed", detail="signature file is empty"))
        return
    try:
        bytes.fromhex(signature)
    except ValueError:
        findings.append(
            IntegrityFinding(kind="signature_file_malformed", detail="signature file is not a hex-encoded signature")
        )
        return
    if manifest is None:
        return  # nothing parseable to verify the signature over
    pem = registry.pem_for(manifest.key_id)
    if pem is None:
        findings.append(
            IntegrityFinding(
                kind="unknown_key",
                execution_id=manifest.execution_id,
                detail=f"manifest key_id {manifest.key_id} is not in the key registry",
            )
        )
        return
    if not verify_signature(pem, manifest_bytes(manifest), signature):
        findings.append(
            IntegrityFinding(
                kind="manifest_signature_invalid",
                execution_id=manifest.execution_id,
                detail=f"manifest signature does not verify under registry key {manifest.key_id}",
            )
        )
        return
    verified_key_ids.add(manifest.key_id)


def _verify_event_records(
    events: list[_Event], registry: KeyRegistry, findings: list[IntegrityFinding], verified_key_ids: set[str]
) -> int:
    verified = 0
    for item in events:
        record = item.record
        event = record.event
        hash_ok = record.hash == item.content_hash
        if not hash_ok:
            findings.append(
                IntegrityFinding(
                    kind="event_hash_mismatch",
                    execution_id=event.execution_id,
                    seq=event.seq,
                    detail=(
                        f"line {item.line}: seq {event.seq} stored hash {record.hash[:16]}... does not match the"
                        f" recomputed content hash {item.content_hash[:16]}..."
                    ),
                )
            )
        pem = registry.pem_for(event.key_id)
        if pem is None:
            findings.append(
                IntegrityFinding(
                    kind="unknown_key",
                    execution_id=event.execution_id,
                    seq=event.seq,
                    detail=f"line {item.line}: event key_id {event.key_id} is not in the key registry",
                )
            )
            continue
        if not verify_signature(pem, item.content, record.signature):
            findings.append(
                IntegrityFinding(
                    kind="event_signature_invalid",
                    execution_id=event.execution_id,
                    seq=event.seq,
                    detail=(
                        f"line {item.line}: seq {event.seq} signature does not verify under registry key"
                        f" {event.key_id}"
                    ),
                )
            )
            continue
        verified_key_ids.add(event.key_id)
        if hash_ok:
            verified += 1
    return verified


# ---------------------------------------------------------------------------
# Chain and consistency checks
# ---------------------------------------------------------------------------


def _verify_chain(events: list[_Event], findings: list[IntegrityFinding]) -> None:
    seen: set[int] = set()
    previous_hash: str | None = None  # None until the first event in file order
    for item in events:
        event = item.record.event
        if event.seq in seen:
            findings.append(
                IntegrityFinding(
                    kind="seq_duplicate",
                    execution_id=event.execution_id,
                    seq=event.seq,
                    detail=f"line {item.line}: seq {event.seq} appears more than once in events.ndjson",
                )
            )
        seen.add(event.seq)
        expected_prev = GENESIS_PREV_HASH if previous_hash is None else previous_hash
        if event.prev_hash != expected_prev:
            findings.append(
                IntegrityFinding(
                    kind="chain_broken",
                    execution_id=event.execution_id,
                    seq=event.seq,
                    detail=(
                        f"line {item.line}: seq {event.seq} prev_hash {event.prev_hash[:16]}... does not link to the"
                        f" preceding event hash {expected_prev[:16]}..."
                    ),
                )
            )
        previous_hash = item.content_hash
    if seen:
        top = max(seen)
        for missing in sorted(set(range(1, top + 1)) - seen):
            findings.append(
                IntegrityFinding(
                    kind="seq_gap", detail=f"seq {missing} is missing (chain is not contiguous 1..{top})"
                )
            )


def _verify_consistency(
    events: list[_Event], manifest: PackageManifest | None, findings: list[IntegrityFinding]
) -> str:
    if not events:
        return manifest.execution_id if manifest is not None else ""
    first = events[0].record.event
    execution_ref = manifest.execution_id if manifest is not None else first.execution_id
    gateway_ref = manifest.gateway_id if manifest is not None else first.gateway_id
    for item in events:
        event = item.record.event
        if event.execution_id != execution_ref:
            findings.append(
                IntegrityFinding(
                    kind="execution_mismatch",
                    execution_id=event.execution_id,
                    seq=event.seq,
                    detail=(
                        f"line {item.line}: seq {event.seq} belongs to execution {event.execution_id},"
                        f" expected {execution_ref}"
                    ),
                )
            )
        if event.gateway_id != gateway_ref:
            findings.append(
                IntegrityFinding(
                    kind="gateway_mismatch",
                    execution_id=event.execution_id,
                    seq=event.seq,
                    detail=(
                        f"line {item.line}: seq {event.seq} gateway_id {event.gateway_id} differs from {gateway_ref}"
                    ),
                )
            )
    return execution_ref


def _verify_manifest_totals(
    events: list[_Event], manifest: PackageManifest | None, findings: list[IntegrityFinding]
) -> None:
    if manifest is None:
        return
    if manifest.event_count != len(events):
        findings.append(
            IntegrityFinding(
                kind="count_mismatch",
                execution_id=manifest.execution_id,
                detail=(
                    f"manifest declares {manifest.event_count} events, events.ndjson contains {len(events)}"
                    " parseable events"
                ),
            )
        )
    if events:
        last_hash = events[-1].content_hash
        if manifest.final_hash != last_hash:
            findings.append(
                IntegrityFinding(
                    kind="final_hash_mismatch",
                    execution_id=manifest.execution_id,
                    detail=(
                        f"manifest final_hash {manifest.final_hash[:16]}... does not match the last event's hash"
                        f" {last_hash[:16]}..."
                    ),
                )
            )


# ---------------------------------------------------------------------------
# Checkpoint verification — how truncation and omission are caught
# ---------------------------------------------------------------------------


def _verify_checkpoint(
    checkpoint: FinalCheckpoint | None,
    manifest: PackageManifest | None,
    registry: KeyRegistry,
    findings: list[IntegrityFinding],
    verified_key_ids: set[str],
) -> bool:
    if checkpoint is None:
        return False
    pem = registry.pem_for(checkpoint.checkpoint_key_id)
    if pem is None:
        findings.append(
            IntegrityFinding(
                kind="unknown_key",
                execution_id=checkpoint.execution_id,
                detail=f"checkpoint key_id {checkpoint.checkpoint_key_id} is not in the key registry",
            )
        )
        return False
    if not verify_signature(pem, checkpoint_body_bytes(checkpoint), checkpoint.signature):
        findings.append(
            IntegrityFinding(
                kind="checkpoint_signature_invalid",
                execution_id=checkpoint.execution_id,
                detail=f"checkpoint signature does not verify under registry key {checkpoint.checkpoint_key_id}",
            )
        )
        return False
    verified_key_ids.add(checkpoint.checkpoint_key_id)
    if manifest is None:
        findings.append(
            IntegrityFinding(
                kind="checkpoint_mismatch",
                execution_id=checkpoint.execution_id,
                detail="manifest is malformed; the checkpoint cannot be compared to the package",
            )
        )
        return False
    mismatches: list[str] = []
    if checkpoint.execution_id != manifest.execution_id:
        mismatches.append(f"execution_id {checkpoint.execution_id} != {manifest.execution_id}")
    if checkpoint.event_count != manifest.event_count:
        mismatches.append(f"event_count {checkpoint.event_count} != {manifest.event_count}")
    if checkpoint.final_hash != manifest.final_hash:
        mismatches.append(f"final_hash {checkpoint.final_hash[:16]}... != {manifest.final_hash[:16]}...")
    if mismatches:
        findings.append(
            IntegrityFinding(
                kind="checkpoint_mismatch",
                execution_id=manifest.execution_id,
                detail="checkpoint does not match the package manifest: " + "; ".join(mismatches),
            )
        )
        return False
    return True


def _coverage_verdict(
    execution_id: str,
    checkpoint: FinalCheckpoint | None,
    checkpoint_matches: bool,
    expected_executions: list[str] | None,
) -> CoverageVerdict:
    parts: list[str] = []
    if checkpoint is None:
        parts.append("missing final checkpoint (package remains marked incomplete)")
    expected_ok = expected_executions is None or execution_id in expected_executions
    if not expected_ok:
        shown = execution_id or "<unknown>"
        parts.append(f"unexpected execution: {shown} is not among the expected executions")
    missing_executions: list[str] = []
    if expected_executions is not None and len(expected_executions) == 1 and not expected_ok:
        missing_executions = [expected_executions[0]]
        parts.append(f"missing executions: {missing_executions[0]}")
    return CoverageVerdict(
        complete=checkpoint_matches and expected_ok,
        missing_executions=missing_executions,
        missing_final_checkpoint=checkpoint is None,
        detail="; ".join(parts),
    )


def _summarize_outcomes(events: list[_Event]) -> OutcomeSummary:
    known = 0
    unknown = 0
    unknown_call_ids: list[str] = []
    for item in events:
        event = item.record.event
        if event.type != EventType.OUTCOME_RECORDED:
            continue
        status = event.payload.get("status")
        call_id = event.payload.get("call_id")
        if status in (OutcomeStatus.SUCCESS.value, OutcomeStatus.ERROR.value):
            known += 1
        else:
            unknown += 1
            if isinstance(call_id, str) and call_id:
                unknown_call_ids.append(call_id)
    return OutcomeSummary(known=known, unknown=unknown, unknown_call_ids=unknown_call_ids)
