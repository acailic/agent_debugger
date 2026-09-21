"""Regression laboratory: incident bundles, local runner, baseline comparison.

Roadmap W05 / queue item Q14 — the incident-to-regression workflow:

1. :func:`export_session_bundle` turns a captured session into a sanitized,
   self-contained, content-hashed JSON *incident bundle* whose expected
   assertions pin the audit engine's verdict on that incident.
2. :func:`run_bundle` replays a bundle through the current audit engine
   (analysis only — no agent or tool execution) and evaluates the stored
   assertions.
3. :func:`compare_run_results` diffs a candidate run against a baseline run
   of the same bundle, naming exactly the assertions that regressed.

Deterministic throughout: no model calls, no wall-clock values inside a
bundle, so the same bundle + same engine semantics always yield the same
verdict.
"""

from __future__ import annotations

from .bundles import (
    ASSERTION_CLAIM_STATUS,
    ASSERTION_FAILURE_IDS,
    ASSERTION_KINDS,
    ASSERTION_NARRATIVE_MECHANISM,
    ASSERTION_SUMMARY_VERDICT,
    ASSERTION_TRUST_BAND,
    ASSERTION_TRUST_SCORE,
    AUDIT_ENGINE_VERSION,
    BUNDLE_KIND,
    BUNDLE_SCHEMA_VERSION,
    BundleTamperedError,
    MalformedBundleError,
    RegressionLabError,
    SessionNotFoundError,
    UnsupportedBundleSchemaError,
    bundle_bytes,
    canonical_json,
    content_hash,
    derive_expected_assertions,
    export_session_bundle,
    load_bundle,
    parse_bundle,
    policy_summary,
    save_bundle,
)
from .runner import (
    RUN_RESULT_VERSION,
    ComparisonPreconditionError,
    checkpoints_from_bundle,
    compare_run_results,
    evaluate_assertion,
    events_from_bundle,
    run_bundle,
)

__all__ = [
    "ASSERTION_CLAIM_STATUS",
    "ASSERTION_FAILURE_IDS",
    "ASSERTION_KINDS",
    "ASSERTION_NARRATIVE_MECHANISM",
    "ASSERTION_SUMMARY_VERDICT",
    "ASSERTION_TRUST_BAND",
    "ASSERTION_TRUST_SCORE",
    "AUDIT_ENGINE_VERSION",
    "BUNDLE_KIND",
    "BUNDLE_SCHEMA_VERSION",
    "RUN_RESULT_VERSION",
    "BundleTamperedError",
    "ComparisonPreconditionError",
    "MalformedBundleError",
    "RegressionLabError",
    "SessionNotFoundError",
    "UnsupportedBundleSchemaError",
    "bundle_bytes",
    "canonical_json",
    "checkpoints_from_bundle",
    "compare_run_results",
    "content_hash",
    "derive_expected_assertions",
    "evaluate_assertion",
    "events_from_bundle",
    "export_session_bundle",
    "load_bundle",
    "parse_bundle",
    "policy_summary",
    "run_bundle",
    "save_bundle",
]
