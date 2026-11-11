"""Agent Evidence Box read API.

Serves evidence packages exported by the evidence gateway
(``EVIDENCE_PACKAGE_DIR``, one package directory per execution) so the
investigation side of Peaky Peek can display cryptographically verified
evidence next to its existing behavioral audit.  Endpoints are read-only;
recording, export and offline verification live in the ``evidence``
package with their own lifecycle (``docs/evidence-box.md``).

The backing store is a local directory (like the analytics SQLite file),
so routes follow the same exposure pattern: open in local mode, Bearer-key
authenticated in hosted/cloud mode via ``require_hosted_auth``.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.analytics_db import record_event
from api.dependencies import require_hosted_auth
from api.exceptions import NotFoundError
from evidence.adapter import (
    EvidenceEntry,
    EvidenceTimelineAdapter,
    PackageLoadError,
    PackageSummary,
    flagged_package_summary,
)
from evidence.schema import PackageManifest, VerificationResult

router = APIRouter(prefix="/api/evidence", tags=["evidence"])

#: Directory holding exported evidence packages (one sub-directory per execution).
EVIDENCE_PACKAGE_DIR_ENV = "EVIDENCE_PACKAGE_DIR"
DEFAULT_EVIDENCE_PACKAGE_DIR = "data/evidence"

_adapter = EvidenceTimelineAdapter()


def get_evidence_package_root() -> Path:
    """Resolve the evidence package root from the environment.

    Relative paths resolve against the server working directory, matching
    how the analytics database resolves its default ``./data`` location.
    """
    return Path(os.environ.get(EVIDENCE_PACKAGE_DIR_ENV, DEFAULT_EVIDENCE_PACKAGE_DIR))


class EvidencePackageSummaryResponse(BaseModel):
    """List-view summary of one evidence package."""

    execution_id: str
    package_name: str
    created_at: datetime | None = None
    event_count: int = 0
    integrity: Literal["verified", "unverified", "failed"] = "unverified"
    coverage: Literal["complete", "incomplete", "unknown"] = "unknown"
    outcomes_known: int = 0
    outcomes_unknown: int = 0
    run_ids: list[str] = Field(default_factory=list)
    gateway_id: str | None = None
    key_id: str | None = None
    error: str | None = None


class EvidencePackageDetailResponse(EvidencePackageSummaryResponse):
    """Full package view: summary fields plus manifest, verifier verdict and entries."""

    manifest: PackageManifest | None = None
    verification: VerificationResult | None = None
    entries: list[EvidenceEntry] = Field(default_factory=list)


def _to_summary_response(summary: PackageSummary) -> EvidencePackageSummaryResponse:
    outcomes_known = sum(1 for entry in summary.entries if entry.outcome_status in ("success", "error"))
    outcomes_unknown = sum(1 for entry in summary.entries if entry.outcome_status == "unknown")
    run_ids: list[str] = []
    for entry in summary.entries:
        if entry.run_id and entry.run_id not in run_ids:
            run_ids.append(entry.run_id)
    gateway_id = summary.manifest.gateway_id if summary.manifest else None
    key_id = summary.manifest.key_id if summary.manifest else None
    if gateway_id is None and summary.entries:
        gateway_id = summary.entries[0].gateway_id
    if key_id is None and summary.entries:
        key_id = summary.entries[0].key_id
    return EvidencePackageSummaryResponse(
        execution_id=summary.execution_id,
        package_name=summary.package_name,
        created_at=summary.manifest.created_at if summary.manifest else None,
        event_count=summary.manifest.event_count if summary.manifest else len(summary.entries),
        integrity=summary.integrity,
        coverage=summary.coverage,
        outcomes_known=outcomes_known,
        outcomes_unknown=outcomes_unknown,
        run_ids=run_ids,
        gateway_id=gateway_id,
        key_id=key_id,
        error=summary.error,
    )


def _load_or_flag(package_dir: Path) -> PackageSummary:
    try:
        return _adapter.load_package(package_dir)
    except PackageLoadError as exc:
        return flagged_package_summary(package_dir, str(exc))


@router.get("/packages", response_model=list[EvidencePackageSummaryResponse])
async def list_evidence_packages(
    _auth: None = Depends(require_hosted_auth),
) -> list[EvidencePackageSummaryResponse]:
    """List every exported evidence package as a summary row.

    Returns an empty list (not 404) when no packages exist.  A malformed
    package is not skipped silently: it keeps its directory-name identity
    with ``integrity="failed"`` and an ``error`` note, so an operator sees
    that an unloadable package is present.
    """
    root = get_evidence_package_root()
    summaries: list[EvidencePackageSummaryResponse] = []
    if root.is_dir():
        for package_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            summaries.append(_to_summary_response(_load_or_flag(package_dir)))
    record_event("evidence_packages_listed")
    return summaries


@router.get("/packages/{execution_id}", response_model=EvidencePackageDetailResponse)
async def get_evidence_package(
    execution_id: str,
    _auth: None = Depends(require_hosted_auth),
) -> EvidencePackageDetailResponse:
    """Return one evidence package with its manifest, verdict and mapped entries.

    404 when no package directory exists for *execution_id*.  A package
    directory that exists but cannot be parsed is returned as a flagged
    result (``integrity="failed"`` plus an ``error`` note) rather than a
    5xx, so the failure itself is auditable.
    """
    if execution_id in {".", ".."} or "/" in execution_id or "\\" in execution_id:
        # Package directories are identified by a plain directory name;
        # anything else is not a package we could ever load.
        raise NotFoundError(f"Evidence package {execution_id} not found")

    root = get_evidence_package_root()
    package_dir = root / execution_id
    if not package_dir.is_dir():
        raise NotFoundError(f"Evidence package {execution_id} not found")

    summary = _load_or_flag(package_dir)
    base = _to_summary_response(summary)
    record_event("evidence_package_viewed", session_id=execution_id)
    return EvidencePackageDetailResponse(
        **base.model_dump(),
        manifest=summary.manifest,
        verification=summary.verification,
        entries=summary.entries,
    )
