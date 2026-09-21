"""Incident-bundle export: a captured session becomes an immutable regression case.

Roadmap W05 / queue item Q14 — the first slice of the incident-to-regression
workflow. :func:`export_session_bundle` reads one session through the
repository layer (read-only use; no HTTP routes) and emits a self-contained
JSON *incident bundle*:

* session metadata (ids, agent, framework, status, tags, config),
* the ordered events and checkpoints,
* the audit report computed by the existing
  :class:`~collector.audit.SessionAuditEngine` at export time, and
* the **expected assertions** derived from that report — the pinned contract
  a later run of the bundle must reproduce.

Design rules:

* Local-first and deterministic — no model calls, no wall-clock fields, no
  randomness: exporting the same stored session twice yields byte-identical
  output (pinned by the content hash), so a bundle committed as a test
  fixture pins its own expectations.
* The sanitized export (default) routes every event, the session config and
  the checkpoint state/memory through the same configured
  :class:`~redaction.pipeline.RedactionPipeline` the persistence path uses
  (see ``collector.server._persist_event_if_configured``), so a bundle is
  shareable. ``sanitized=False`` (the operator's raw flag) keeps the stored
  payloads verbatim for local debugging.
* The audit report is computed from the *sanitized* events — the exact
  objects the runner later rebuilds from the bundle — so the stored
  assertions are reproducible by construction rather than by luck.
* The content hash is sha256 over canonical JSON of the bundle minus the
  hash field itself; loaders refuse a bundle whose hash does not match
  (tamper guard) and one whose ``schema_version`` they do not understand.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_debugger_sdk.core.events import Checkpoint, Session
from collector.audit import SessionAuditEngine
from redaction.pipeline import RedactionPipeline, apply_payload_redaction
from storage import TraceRepository

#: Bundle schema version. Bump when the bundle shape changes in a way older
#: loaders cannot evaluate; loaders reject any other value loudly.
BUNDLE_SCHEMA_VERSION = 1

#: Discriminator recorded in every bundle so a file can be recognized before
#: it is parsed.
BUNDLE_KIND = "agent_debugger.incident_bundle"

#: Version of the audit-evaluator semantics this exporter/runner pair
#: encodes. Bump whenever :class:`~collector.audit.SessionAuditEngine`'s
#: report semantics change (new fields are fine; changed meanings are not)
#: so baseline/candidate comparisons can tell whether the two runs shared
#: an evaluator.
AUDIT_ENGINE_VERSION = "1"

#: Assertion kinds derived from an audit report. Each assertion is a pinned
#: (kind, path, expected) triple the runner re-evaluates against a fresh
#: report.
ASSERTION_TRUST_BAND = "trust_band"
ASSERTION_TRUST_SCORE = "trust_score"
ASSERTION_CLAIM_STATUS = "claim_verification_status"
ASSERTION_FAILURE_IDS = "failure_event_ids"
ASSERTION_NARRATIVE_MECHANISM = "failure_narrative_mechanism"
ASSERTION_SUMMARY_VERDICT = "summary_verdict"

ASSERTION_KINDS = (
    ASSERTION_TRUST_BAND,
    ASSERTION_TRUST_SCORE,
    ASSERTION_CLAIM_STATUS,
    ASSERTION_FAILURE_IDS,
    ASSERTION_NARRATIVE_MECHANISM,
    ASSERTION_SUMMARY_VERDICT,
)

#: Sections every schema-1 bundle must carry (beyond the version + hash,
#: which are validated explicitly).
_REQUIRED_SECTIONS = (
    "session",
    "sanitized",
    "events",
    "checkpoints",
    "audit_report",
    "expected_assertions",
    "engine",
)


# ---------------------------------------------------------------------------
# Errors — loud by design: a regression case that cannot be trusted must not
# evaluate to "pass".
# ---------------------------------------------------------------------------


class RegressionLabError(Exception):
    """Base class for every incident-bundle / regression-runner failure."""


class SessionNotFoundError(RegressionLabError):
    """The session to export does not exist in the repository."""


class MalformedBundleError(RegressionLabError):
    """The bundle is structurally invalid (missing sections, bad values)."""


class UnsupportedBundleSchemaError(RegressionLabError):
    """The bundle's ``schema_version`` is not understood by this code."""


class BundleTamperedError(RegressionLabError):
    """The bundle's content hash does not match its contents."""


# ---------------------------------------------------------------------------
# Canonical JSON + content hash
# ---------------------------------------------------------------------------


def canonical_json(value: Any) -> str:
    """Render *value* as a deterministic JSON string (sorted keys, no spaces)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def content_hash(bundle: dict[str, Any]) -> str:
    """sha256 over canonical JSON of the bundle minus the ``content_hash`` field."""
    payload = {key: value for key, value in bundle.items() if key != "content_hash"}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Sanitization (mirrors the persistence path's redaction entry points)
# ---------------------------------------------------------------------------


def policy_summary(pipeline: Any) -> dict[str, Any]:
    """Record the redaction policy that produced a sanitized bundle."""
    return {
        "redact_prompts": bool(getattr(pipeline, "redact_prompts", False)),
        "redact_tool_payloads": bool(getattr(pipeline, "redact_tool_payloads", False)),
        "redact_pii": bool(getattr(pipeline, "redact_pii", False)),
        "max_payload_kb": int(getattr(pipeline, "max_payload_kb", 0) or 0),
    }


def _sanitize_checkpoint(pipeline: Any, checkpoint: Checkpoint) -> Checkpoint:
    """Copy a checkpoint with its state and memory scrubbed by the policy."""
    return Checkpoint(
        id=checkpoint.id,
        session_id=checkpoint.session_id,
        event_id=checkpoint.event_id,
        sequence=checkpoint.sequence,
        state=apply_payload_redaction(pipeline, checkpoint.state or {}),
        memory=apply_payload_redaction(pipeline, checkpoint.memory or {}),
        timestamp=checkpoint.timestamp,
        importance=checkpoint.importance,
    )


def _normalized_ts(value: Any) -> str:
    """Comparable ISO string for a timestamp, assuming UTC when naive.

    Storage-reconstructed timestamps may be naive while SDK-fresh ones carry
    an offset; normalizing before comparison keeps ordering total.
    """
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""
    return _normalized_ts(parsed)


# ---------------------------------------------------------------------------
# Expected assertions
# ---------------------------------------------------------------------------


def _assertion(kind: str, path: str, expected: Any, subject: str | None = None) -> dict[str, Any]:
    assertion: dict[str, Any] = {"kind": kind, "path": path, "expected": expected}
    if subject is not None:
        assertion["subject"] = subject
    return assertion


def derive_expected_assertions(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive the pinned expected-assertion set from an audit report.

    Deterministic and ordered: scalar report-level pins first, then one row
    per claim (in the report's own claim order). Each assertion is evaluated
    independently by the runner, so a regression names exactly the pinned
    behaviour that changed.
    """
    trust = report.get("trust", {}) or {}
    assertions: list[dict[str, Any]] = [
        _assertion(ASSERTION_TRUST_BAND, "trust.band", trust.get("band")),
        _assertion(ASSERTION_TRUST_SCORE, "trust.score", trust.get("score")),
    ]
    for claim in report.get("claims", []) or []:
        event_id = str(claim.get("event_id") or "")
        if not event_id:
            continue
        assertions.append(
            _assertion(
                ASSERTION_CLAIM_STATUS,
                f"claims.{event_id}.verification_status",
                claim.get("verification_status"),
                subject=event_id,
            )
        )
    failure_ids = sorted(
        str(failure.get("event_id"))
        for failure in report.get("failures", []) or []
        if failure.get("event_id")
    )
    assertions.append(_assertion(ASSERTION_FAILURE_IDS, "failures.event_ids", failure_ids))
    narrative = report.get("failure_narrative", {}) or {}
    symptom = narrative.get("symptom", {}) or {}
    assertions.append(
        _assertion(
            ASSERTION_NARRATIVE_MECHANISM,
            "failure_narrative.symptom.mechanism_category",
            symptom.get("mechanism_category"),
        )
    )
    summary = report.get("summary", {}) or {}
    assertions.append(_assertion(ASSERTION_SUMMARY_VERDICT, "summary.verdict", summary.get("verdict")))
    return assertions


# ---------------------------------------------------------------------------
# Decision-node identity (spectrum keys)
# ---------------------------------------------------------------------------


def decision_node_keys(report: dict[str, Any]) -> list[dict[str, str]]:
    """Derive the stable identity of every decision node in an audit report.

    Decision nodes are the report's *claims* — one row per captured decision
    event, each already carrying the identity fields this derivation reuses
    (nothing is invented here). Two identities are recorded per node because
    no single one is stable in every corpus the regression lab ranks
    (Tarantula note, ``docs/papers/tarantula-test-information-fault-localization.md``:
    many runs turn a causal chain into a spectrum):

    * ``key`` — the decision's event id. A bundle pins its events, so the id
      is stable across every run of the *same* bundle and is the primary
      identity.
    * ``normalized_key`` — ``"{event_type}:{headline}"`` where ``event_type``
      is the claim's recorded type and ``headline`` the report's own decision
      headline (the causal-analyzer clip of the event name). Repeated
      recordings of one scenario exported as *separate bundles* mint fresh
      event ids per recording, so ids differ across those runs; type +
      headline is the identity that survives. DERIVATION RULE (documented
      cost): two decisions that share event type and headline collapse to a
      single node under this key — a repeated same-named decision counts
      once, never as two suspects.

    Claims without an event id are skipped (mirroring
    :func:`derive_expected_assertions`). Rows are sorted by ``key`` so the
    output is deterministic for a fixed report.

    CAUTION (Tarantula note): SBFL ranks, it does not convict. These keys
    exist to *order* first-bad-decision candidates; suspiciousness computed
    over them is never a verification status and must never feed the trust
    score.
    """
    keys: list[dict[str, str]] = []
    for claim in report.get("claims", []) or []:
        event_id = str(claim.get("event_id") or "")
        if not event_id:
            continue
        event_type = str(claim.get("event_type") or "decision")
        headline = str(claim.get("headline") or claim.get("claim") or "")
        keys.append(
            {
                "key": event_id,
                "normalized_key": f"{event_type}:{headline}",
            }
        )
    return sorted(keys, key=lambda node: node["key"])


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _session_metadata(session: Session) -> dict[str, Any]:
    status = session.status
    return {
        "id": session.id,
        "agent_name": session.agent_name,
        "framework": session.framework,
        "status": str(status) if status is not None else None,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "tags": list(session.tags or []),
    }


def _audit_session_dict(session_meta: dict[str, Any]) -> dict[str, Any]:
    """Session context for the audit engine (mirrors the API audit routes)."""
    return {
        "id": session_meta.get("id"),
        "status": session_meta.get("status"),
        "agent_name": session_meta.get("agent_name"),
        "started_at": session_meta.get("started_at"),
        "ended_at": session_meta.get("ended_at"),
    }


async def export_session_bundle(
    repo: TraceRepository,
    session_id: str,
    *,
    sanitized: bool = True,
    redaction_pipeline: Any = None,
    engine: Any = None,
) -> dict[str, Any]:
    """Export one stored session into a self-contained incident bundle.

    Args:
        repo: Repository to read from (read-only use; nothing is written).
        session_id: The session to export.
        sanitized: When True (default) every event, the session config and
            the checkpoint state/memory flow through the configured redaction
            pipeline so the bundle is shareable. When False the stored
            payloads are kept verbatim — the local operator's raw view.
        redaction_pipeline: Explicit pipeline to sanitize with; defaults to
            the configured :meth:`RedactionPipeline.from_config` policy,
            exactly like the persistence path.
        engine: Audit engine to compute the export-time report with; a fresh
            :class:`SessionAuditEngine` by default.

    Returns:
        The bundle dict (with ``content_hash`` filled in).

    Raises:
        SessionNotFoundError: The session does not exist.
    """
    session = await repo.get_session(session_id)
    if session is None:
        raise SessionNotFoundError(f"Session {session_id} not found")

    events = await repo.get_event_tree(session_id)
    checkpoints = await repo.list_checkpoints(session_id)

    policy = None
    if sanitized:
        policy = redaction_pipeline if redaction_pipeline is not None else RedactionPipeline.from_config()
        events = [policy.apply(event) for event in events]
        checkpoints = [_sanitize_checkpoint(policy, checkpoint) for checkpoint in checkpoints]

    # Deterministic ordering independent of the storage query: events by
    # (timestamp, id), checkpoints by (timestamp, sequence, id).
    events = sorted(events, key=lambda event: (_normalized_ts(event.timestamp), event.id))
    checkpoints = sorted(
        checkpoints,
        key=lambda checkpoint: (_normalized_ts(checkpoint.timestamp), checkpoint.sequence, checkpoint.id),
    )

    session_meta = _session_metadata(session)
    if sanitized:
        session_meta["config"] = apply_payload_redaction(policy, session.config or {})
    else:
        session_meta["config"] = dict(session.config or {})

    # The export-time report is computed from the exact (sanitized) events the
    # runner will rebuild, so the stored assertions are reproducible.
    report = (engine if engine is not None else SessionAuditEngine()).audit(
        events, checkpoints, session=_audit_session_dict(session_meta)
    )

    bundle: dict[str, Any] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "bundle_kind": BUNDLE_KIND,
        "session": session_meta,
        "sanitized": bool(sanitized),
        "redaction": policy_summary(policy) if sanitized else None,
        "events": [event.to_dict() for event in events],
        "checkpoints": [checkpoint.to_dict() for checkpoint in checkpoints],
        "audit_report": report,
        "expected_assertions": derive_expected_assertions(report),
        "engine": {"audit_engine_version": AUDIT_ENGINE_VERSION},
        "event_count": len(events),
        "checkpoint_count": len(checkpoints),
    }
    bundle["content_hash"] = content_hash(bundle)
    return bundle


# ---------------------------------------------------------------------------
# Save / load (with schema + tamper guards)
# ---------------------------------------------------------------------------


def bundle_bytes(bundle: dict[str, Any]) -> bytes:
    """Deterministic on-disk rendering of a bundle (sorted keys, 2-space indent)."""
    return (json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n").encode("utf-8")


def save_bundle(bundle: dict[str, Any], path: str | Path) -> Path:
    """Write a bundle to *path* deterministically; same bundle → same bytes."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(bundle_bytes(bundle))
    return target


def parse_bundle(raw: Any) -> dict[str, Any]:
    """Validate a parsed bundle dict (schema version, sections, content hash).

    Returns the bundle unchanged when it is trustworthy; raises loudly
    otherwise so an untrustworthy regression case can never evaluate to
    "pass".
    """
    if not isinstance(raw, dict):
        raise MalformedBundleError(f"Incident bundle must be a JSON object, got {type(raw).__name__}")
    version = raw.get("schema_version")
    if version != BUNDLE_SCHEMA_VERSION:
        raise UnsupportedBundleSchemaError(
            f"Unsupported incident-bundle schema_version {version!r}; this runner supports "
            f"{BUNDLE_SCHEMA_VERSION}. Re-export the session with the current code."
        )
    missing = [section for section in _REQUIRED_SECTIONS if section not in raw]
    if missing:
        raise MalformedBundleError(f"Incident bundle is missing sections: {', '.join(sorted(missing))}")
    recorded = raw.get("content_hash")
    recomputed = content_hash(raw)
    if not isinstance(recorded, str) or recorded != recomputed:
        raise BundleTamperedError(
            "Incident bundle content hash mismatch: the bundle was modified after export "
            f"(recorded {recorded!r}, recomputed {recomputed!r}). Re-export the session or "
            "re-sign an intentionally edited assertion set with content_hash()."
        )
    return raw


def load_bundle(path: str | Path) -> dict[str, Any]:
    """Read, parse and validate a bundle file."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MalformedBundleError(f"Could not read incident bundle {path}: {exc}") from exc
    return parse_bundle(raw)
