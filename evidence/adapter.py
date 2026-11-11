"""Investigation adapter: verified evidence packages onto the Peaky Peek timeline.

This module is the read side of the Agent Evidence Box inside Peaky Peek
(``docs/plans/agent-evidence-box.md``, "Ugradnja u Peaky Peek").  It never
records or verifies anything itself: packages are produced by the evidence
gateway/exporter and verified offline by ``evidence.verify`` (separate
lifecycle).  The adapter parses exported package files with plain JSON +
pydantic, maps each signed event onto one :class:`EvidenceEntry` timeline
row carrying ``run_id`` / ``call_id``, the verified source and a reference
to the original record, and merges a verifier-produced
:class:`~evidence.schema.VerificationResult` onto the package and its
entries.

Display-side redaction (plan: "Privatnost i prenosivost"): every string
field that originates from an event payload (``reason``, ``tool_name``,
``outcome_code``, ``principal``) is scrubbed before entries leave this
module.  The scrub reuses the existing pipeline entry point
``redaction.pipeline.apply_payload_redaction`` (which routes dicts through
``RedactionPipeline.scrub_payload``) with an always-on display policy —
``RedactionPipeline(redact_pii=True)`` — so PII/secret patterns are masked
for investigators even when the gateway-side policy was configured more
permissively.  The scrub is defensive: values it leaves untouched pass
through unchanged, and a scrub failure never breaks timeline mapping.

The cryptographic verification result and Peaky Peek's existing behavior
assessment stay SEPARATE fields by construction: ``integrity`` /
``coverage`` carry only the verifier's verdict, and the audit engine's
trust/claim statuses remain wherever the audit pipeline computed them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from evidence.schema import (
    DecisionPayload,
    EventType,
    OutcomeStatus,
    PackageManifest,
    SignedEventRecord,
    VerificationResult,
)
from redaction.pipeline import RedactionPipeline, apply_payload_redaction

__all__ = [
    "EvidenceEntry",
    "PackageSummary",
    "PackageLoadError",
    "EvidenceTimelineAdapter",
    "flagged_package_summary",
    "display_redaction_pipeline",
]

#: Per-entry / per-package verdict of the offline verifier, kept separate
#: from any behavioral audit assessment.
IntegrityStatus = Literal["verified", "unverified", "failed"]

#: What the verifier could establish about execution coverage.
CoverageStatus = Literal["complete", "incomplete", "unknown"]

#: Payload-origin string fields that pass through display-side redaction.
_REDACTED_FIELDS = ("reason", "tool_name", "outcome_code", "principal")


class EvidenceEntry(BaseModel):
    """One signed evidence event mapped onto the investigation timeline.

    ``verified_source`` names the evidence gateway that signed the record
    and ``original_ref`` points back into the exported package
    (``<package>#events.ndjson:L<line>``) so an auditor can trace every
    displayed row to the exact signed line offline.
    """

    execution_id: str
    seq: int = Field(ge=1)
    event_type: EventType
    recorded_at: str
    call_id: str | None = None
    decision: Literal["allow", "deny"] | None = None
    reason: str | None = None
    outcome_status: OutcomeStatus | None = None
    outcome_code: str | None = None
    run_id: str | None = None
    tool_name: str | None = None
    principal: str | None = None
    gateway_id: str
    key_id: str
    verified_source: str
    original_ref: str
    integrity: IntegrityStatus = "unverified"
    coverage: CoverageStatus = "unknown"


class PackageSummary(BaseModel):
    """A loaded evidence package: manifest, mapped entries, verifier verdict."""

    package_name: str
    execution_id: str
    manifest: PackageManifest | None = None
    entries: list[EvidenceEntry] = Field(default_factory=list)
    verification: VerificationResult | None = None
    integrity: IntegrityStatus = "unverified"
    coverage: CoverageStatus = "unknown"
    error: str | None = None


class PackageLoadError(ValueError):
    """A package directory exists but cannot be identified (no/broken manifest)."""


def display_redaction_pipeline() -> RedactionPipeline:
    """Always-on scrub policy for the evidence display side.

    ``redact_pii=True`` runs the pipeline's PII + secret pattern scrub
    (``RedactionPipeline.scrub_payload``); whole-field prompt/tool-payload
    redaction is event-type specific and intentionally not applied to the
    allow-listed evidence metadata.
    """
    return RedactionPipeline(redact_pii=True)


def flagged_package_summary(package_dir: Path, error: str) -> PackageSummary:
    """Summary for a package directory that failed to load.

    Kept identifiable (directory name) so listings and detail views can
    surface the failure instead of hiding or crashing on it.
    """
    return PackageSummary(
        package_name=package_dir.name,
        execution_id=package_dir.name,
        integrity="failed",
        coverage="unknown",
        error=error,
    )


class EvidenceTimelineAdapter:
    """Maps exported evidence packages onto Peaky Peek timeline entries."""

    def __init__(self, redaction: RedactionPipeline | None = None) -> None:
        self._redaction = redaction if redaction is not None else display_redaction_pipeline()

    # -- loading -----------------------------------------------------------

    def load_package(self, package_dir: Path) -> PackageSummary:
        """Parse ``manifest.json`` + ``events.ndjson`` from *package_dir*.

        Raises :class:`PackageLoadError` when the manifest is missing or
        unparseable (the package cannot even be identified).  Malformed
        ``events.ndjson`` lines are skipped and flagged in ``error`` — the
        intact lines still map, with line numbers preserved for
        ``original_ref``.
        """
        package_dir = Path(package_dir)
        manifest_path = package_dir / "manifest.json"
        events_path = package_dir / "events.ndjson"

        if not manifest_path.is_file():
            raise PackageLoadError(f"{package_dir.name}: manifest.json not found")
        try:
            manifest = PackageManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            raise PackageLoadError(f"{package_dir.name}: invalid manifest.json: {exc}") from exc

        entries: list[EvidenceEntry] = []
        errors: list[str] = []
        if not events_path.is_file():
            errors.append("events.ndjson not found")
        else:
            for line_nr, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    record = SignedEventRecord.model_validate_json(line)
                except ValidationError:
                    errors.append(f"malformed event record at line {line_nr}")
                    continue
                entries.append(self._entry_from_record(record, package_dir.name, line_nr))

        return PackageSummary(
            package_name=package_dir.name,
            execution_id=manifest.execution_id,
            manifest=manifest,
            entries=entries,
            error="; ".join(errors) or None,
        )

    # -- verification merge -------------------------------------------------

    def apply_verification(self, summary: PackageSummary, result: VerificationResult) -> PackageSummary:
        """Merge an offline verifier verdict onto *summary* (mutating it).

        Package level — integrity is ``"verified"`` iff the whole result is
        ok, ``"failed"`` iff the integrity section failed, else
        ``"unverified"``; coverage is ``"complete"``/``"incomplete"`` from
        the coverage verdict.  Entry level — a chain-intact event is
        ``"verified"``; events cited by integrity findings, or sitting
        beyond the last verified event of a broken chain, are ``"failed"``.
        """
        summary.verification = result
        summary.integrity = self._package_integrity(result)
        summary.coverage = "complete" if result.coverage.complete else "incomplete"
        for entry in summary.entries:
            entry.integrity = self._entry_integrity(entry, result)
            entry.coverage = summary.coverage
        return summary

    @staticmethod
    def _package_integrity(result: VerificationResult) -> IntegrityStatus:
        if result.ok:
            return "verified"
        if result.integrity.ok is False:
            return "failed"
        return "unverified"

    @staticmethod
    def _entry_integrity(entry: EvidenceEntry, result: VerificationResult) -> IntegrityStatus:
        finding_seqs = {finding.seq for finding in result.integrity.findings if finding.seq is not None}
        if entry.seq in finding_seqs:
            return "failed"
        if entry.seq <= result.integrity.verified_events:
            # Chain intact up to and including this event.
            return "verified"
        if result.integrity.ok is False:
            # Beyond the last chain-intact event of a broken chain.
            return "failed"
        return "unverified"

    # -- lookup --------------------------------------------------------------

    @staticmethod
    def find_by_call_id(summary: PackageSummary, call_id: str) -> list[EvidenceEntry]:
        """All entries of *summary* recorded for *call_id*, ordered by seq."""
        return [entry for entry in summary.entries if entry.call_id == call_id]

    # -- entry mapping ---------------------------------------------------------

    def _entry_from_record(self, record: SignedEventRecord, package_name: str, line_nr: int) -> EvidenceEntry:
        event = record.event
        payload = event.payload if isinstance(event.payload, dict) else {}
        common: dict[str, object] = {
            "execution_id": event.execution_id,
            "seq": event.seq,
            "event_type": event.type,
            "recorded_at": event.recorded_at.isoformat(),
            "gateway_id": event.gateway_id,
            "key_id": event.key_id,
            "verified_source": f"evidence-gateway:{event.gateway_id}",
            "original_ref": f"{package_name}#events.ndjson:L{line_nr}",
        }

        if event.type is EventType.EXECUTION_STARTED:
            common.update(self._started_fields(payload))
        elif event.type is EventType.DECISION_RECORDED:
            common.update(self._decision_fields(payload))
        elif event.type is EventType.OUTCOME_RECORDED:
            common.update(self._outcome_fields(payload))

        entry = EvidenceEntry(**common)  # type: ignore[arg-type]
        return self._redact_entry(entry)

    @staticmethod
    def _started_fields(payload: dict) -> dict[str, object]:
        run_id = payload.get("run_id")
        principal = payload.get("principal")
        return {
            "run_id": run_id if isinstance(run_id, str) else None,
            "principal": principal if isinstance(principal, str) else None,
        }

    @staticmethod
    def _decision_fields(payload: dict) -> dict[str, object]:
        try:
            typed = DecisionPayload.model_validate(payload)
        except ValidationError:
            decision = payload.get("decision")
            call_id = payload.get("call_id")
            reason = payload.get("reason")
            run_id = payload.get("run_id")
            tool_name = payload.get("tool_name")
            principal = payload.get("principal")
            return {
                "decision": decision if decision in ("allow", "deny") else None,
                "call_id": call_id if isinstance(call_id, str) else None,
                "reason": reason if isinstance(reason, str) else None,
                "run_id": run_id if isinstance(run_id, str) else None,
                "tool_name": tool_name if isinstance(tool_name, str) else None,
                "principal": principal if isinstance(principal, str) else None,
            }
        return {
            "decision": typed.decision.value,
            "reason": typed.reason,
            "call_id": typed.call_id,
            "run_id": typed.run_id,
            "tool_name": typed.tool_name,
            "principal": typed.principal,
        }

    @staticmethod
    def _outcome_fields(payload: dict) -> dict[str, object]:
        status = payload.get("status")
        call_id = payload.get("call_id")
        outcome_code = payload.get("outcome_code")
        known = {member.value for member in OutcomeStatus}
        return {
            "call_id": call_id if isinstance(call_id, str) else None,
            "outcome_status": status if status in known else OutcomeStatus.UNKNOWN,
            "outcome_code": outcome_code if isinstance(outcome_code, str) else None,
        }

    def _redact_entry(self, entry: EvidenceEntry) -> EvidenceEntry:
        """Scrub payload-origin strings via the shared pipeline, defensively.

        Reuses ``redaction.pipeline.apply_payload_redaction`` (routing
        through ``RedactionPipeline.scrub_payload``).  Any pipeline failure
        or non-string value leaves the field untouched — redaction must
        never break timeline mapping, and it must never widen into the
        structural fields (ids, refs, hashes) that trace linkage needs.
        """
        payload = {field: getattr(entry, field) for field in _REDACTED_FIELDS if getattr(entry, field) is not None}
        if not payload:
            return entry
        try:
            scrubbed = apply_payload_redaction(self._redaction, payload)
        except Exception:  # noqa: BLE001 — display-side defense only
            return entry
        for field, value in scrubbed.items():
            if isinstance(value, str):
                setattr(entry, field, value)
        return entry
