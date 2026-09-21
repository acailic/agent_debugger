"""Session completeness computation (roadmap W02).

Pure, read-only analysis over a session's persisted events: an operator must
be able to tell whether a session is complete without guessing. The report
covers structural integrity (parents resolvable, ids unique, emission
sequence gapless), payload fidelity (truncation and redaction markers the
ingestion pipeline stamps onto events) and ordering sanity.

Marker sources (no new columns — everything is computed on read):

- truncation: ``RedactionPipeline.apply`` sets ``metadata["_truncated"]``
  and embeds the ``"[TRUNCATED]"`` marker into oversized string/container
  values (redaction/pipeline.py).
- redaction: whole-field replacement writes ``"[REDACTED]"`` and the PII /
  secret scrub writes the replacement tokens from
  ``redaction.patterns.REPLACEMENT_MAP`` / ``SECRET_REPLACEMENT_MAP``
  (``"[EMAIL]"``, ``"[AWS_ACCESS_KEY]"``, ...).
- emission order / expected count: ``EventEmitter.emit`` stamps
  ``metadata["sequence"]`` (1-based, incrementing per emitted event), which
  survives persistence. When every persisted event carries the marker, the
  highest sequence is the emitted (expected) count and gaps in the
  1..expected range are events that never landed — the server-side
  delivery-loss signal. Callers holding their own expected count (imports,
  spool replay) can pass it as an explicit hint, which takes precedence.

Ordering sanity counts adjacent timestamp regressions in emission order
(sequence markers) or, when markers are absent, in the order the caller
provides the events.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agent_debugger_sdk.core.events import TraceEvent
from redaction.patterns import REPLACEMENT_MAP, SECRET_REPLACEMENT_MAP
from redaction.pipeline import TRUNCATED_MARKER

# metadata flag written by RedactionPipeline.apply when a payload is truncated
TRUNCATION_FLAG = "_truncated"
# whole-field marker written by RedactionPipeline._redact_fields
REDACTED_MARKER = "[REDACTED]"
# metadata key written by EventEmitter.emit (1-based emission sequence)
SEQUENCE_KEY = "sequence"

REDACTION_MARKERS = frozenset(
    {REDACTED_MARKER, *REPLACEMENT_MAP.values(), *SECRET_REPLACEMENT_MAP.values()}
)

# Capped listing for id samples so one pathological session cannot flood the
# report; counts always reflect the full set.
ID_SAMPLE_CAP = 20

EXPECTED_SOURCE_HINT = "hint"
EXPECTED_SOURCE_SEQUENCE = "sequence_markers"


@dataclass
class SessionCompletenessReport:
    """Structured completeness report for one session's persisted events."""

    total_events: int = 0
    received_event_count: int = 0
    expected_event_count: int | None = None
    expected_source: str | None = None
    count_match: bool | None = None
    missing_sequence_count: int = 0
    missing_sequence_values: list[int] = field(default_factory=list)
    missing_parents_count: int = 0
    missing_parent_event_ids: list[str] = field(default_factory=list)
    duplicate_id_count: int = 0
    duplicate_ids: list[str] = field(default_factory=list)
    truncated: bool = False
    truncated_event_count: int = 0
    truncated_event_ids: list[str] = field(default_factory=list)
    redaction_applied: bool = False
    redacted_event_count: int = 0
    redacted_event_ids: list[str] = field(default_factory=list)
    non_monotonic_timestamp_count: int = 0
    warnings: list[str] = field(default_factory=list)
    complete: bool = False

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready mapping (the API response body minus session_id)."""
        return {
            "total_events": self.total_events,
            "received_event_count": self.received_event_count,
            "expected_event_count": self.expected_event_count,
            "expected_source": self.expected_source,
            "count_match": self.count_match,
            "missing_sequence_count": self.missing_sequence_count,
            "missing_sequence_values": list(self.missing_sequence_values),
            "missing_parents_count": self.missing_parents_count,
            "missing_parent_event_ids": list(self.missing_parent_event_ids),
            "duplicate_id_count": self.duplicate_id_count,
            "duplicate_ids": list(self.duplicate_ids),
            "truncated": self.truncated,
            "truncated_event_count": self.truncated_event_count,
            "truncated_event_ids": list(self.truncated_event_ids),
            "redaction_applied": self.redaction_applied,
            "redacted_event_count": self.redacted_event_count,
            "redacted_event_ids": list(self.redacted_event_ids),
            "non_monotonic_timestamp_count": self.non_monotonic_timestamp_count,
            "warnings": list(self.warnings),
            "complete": self.complete,
        }


def _capped(values: list[str], cap: int) -> list[str]:
    """First ``cap`` sorted values; counts elsewhere keep the full size."""
    return sorted(values)[:cap]


def _normalize_timestamp(value: datetime) -> datetime:
    """Treat naive persisted timestamps as UTC so comparisons are safe."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _contains_any_marker(obj: Any, markers: frozenset[str]) -> bool:
    """True when any string at any depth contains one of the markers."""
    if isinstance(obj, str):
        return any(marker in obj for marker in markers)
    if isinstance(obj, dict):
        return any(_contains_any_marker(value, markers) for value in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(_contains_any_marker(item, markers) for item in obj)
    return False


def _event_is_truncated(event: TraceEvent) -> bool:
    """Truncation detection: pipeline metadata flag or embedded marker."""
    if event.metadata.get(TRUNCATION_FLAG):
        return True
    return _contains_any_marker(event.data, frozenset({TRUNCATED_MARKER})) or _contains_any_marker(
        event.metadata, frozenset({TRUNCATED_MARKER})
    )


def _event_is_redacted(event: TraceEvent) -> bool:
    """Redaction detection: replacement tokens in data or metadata."""
    return _contains_any_marker(event.data, REDACTION_MARKERS) or _contains_any_marker(
        event.metadata, REDACTION_MARKERS
    )


def _sequence_of(event: TraceEvent) -> int | None:
    """Emission sequence marker, or None when absent/non-integral."""
    value = event.metadata.get(SEQUENCE_KEY)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _emission_ordered(events: list[TraceEvent]) -> list[TraceEvent]:
    """Events in emission order: by sequence marker when complete, else as given."""
    if events and all(_sequence_of(event) is not None for event in events):
        return sorted(events, key=_sequence_of)
    return list(events)


def _compute_expected(
    events: list[TraceEvent],
    hint: int | None,
) -> tuple[int | None, str | None, bool | None, int, list[int]]:
    """Resolve expected count, source, match flag and sequence gaps.

    An explicit hint wins; otherwise a gapless set of sequence markers on
    every event derives expected = max(sequence) (1-based emission counter
    set by EventEmitter.emit). When neither is available the expected count
    is honestly absent (None), never guessed.
    """
    sequences = [_sequence_of(event) for event in events]
    markers_complete = bool(events) and all(value is not None for value in sequences)

    if hint is not None:
        present = {value for value in sequences if value is not None}
        missing_values = sorted(set(range(1, hint + 1)) - present) if markers_complete else []
        return hint, EXPECTED_SOURCE_HINT, hint == len(events), len(missing_values), missing_values[:ID_SAMPLE_CAP]

    if not markers_complete:
        return None, None, None, 0, []

    expected = max(value for value in sequences if value is not None)
    present = {value for value in sequences if value is not None}
    missing_values = sorted(set(range(1, expected + 1)) - present)
    count_match = expected == len(events)
    return expected, EXPECTED_SOURCE_SEQUENCE, count_match, len(missing_values), missing_values[:ID_SAMPLE_CAP]


def compute_session_completeness(
    events: list[TraceEvent],
    *,
    expected_event_count: int | None = None,
) -> SessionCompletenessReport:
    """Compute the completeness report for a session's persisted events.

    Args:
        events: The session's events as loaded from storage (any order; the
            report re-orders by emission sequence marker when present).
        expected_event_count: Optional session-level hint for the emitted
            (expected) count, e.g. from an import manifest or spool replay.
            Takes precedence over the sequence-marker derivation.

    Returns:
        SessionCompletenessReport with counts, capped id samples, operator
        warnings and a single ``complete`` verdict.
    """
    report = SessionCompletenessReport(
        total_events=len(events),
        received_event_count=len(events),
    )

    # Expected vs received ------------------------------------------------
    (
        report.expected_event_count,
        report.expected_source,
        report.count_match,
        report.missing_sequence_count,
        report.missing_sequence_values,
    ) = _compute_expected(events, expected_event_count)

    # Missing parents -----------------------------------------------------
    known_ids = {event.id for event in events}
    orphans = [event for event in events if event.parent_id and event.parent_id not in known_ids]
    report.missing_parents_count = len(orphans)
    report.missing_parent_event_ids = _capped([event.id for event in orphans], ID_SAMPLE_CAP)

    # Duplicate ids -------------------------------------------------------
    id_counts = Counter(event.id for event in events)
    duplicate_ids = [event_id for event_id, count in id_counts.items() if count > 1]
    report.duplicate_id_count = len(duplicate_ids)
    report.duplicate_ids = _capped(duplicate_ids, ID_SAMPLE_CAP)

    # Truncation / redaction markers ---------------------------------------
    truncated_events = [event for event in events if _event_is_truncated(event)]
    report.truncated = bool(truncated_events)
    report.truncated_event_count = len(truncated_events)
    report.truncated_event_ids = _capped([event.id for event in truncated_events], ID_SAMPLE_CAP)

    redacted_events = [event for event in events if _event_is_redacted(event)]
    report.redaction_applied = bool(redacted_events)
    report.redacted_event_count = len(redacted_events)
    report.redacted_event_ids = _capped([event.id for event in redacted_events], ID_SAMPLE_CAP)

    # Ordering sanity -------------------------------------------------------
    ordered = _emission_ordered(events)
    timestamps = [_normalize_timestamp(event.timestamp) for event in ordered]
    report.non_monotonic_timestamp_count = sum(
        1 for previous, current in zip(timestamps, timestamps[1:]) if current < previous
    )

    _populate_warnings(report)
    report.complete = (
        report.missing_parents_count == 0
        and report.duplicate_id_count == 0
        and report.missing_sequence_count == 0
        and report.count_match is not False
        and not report.truncated
        and report.non_monotonic_timestamp_count == 0
    )
    return report


def _populate_warnings(report: SessionCompletenessReport) -> None:
    """Human-readable operator warnings, one entry per detected condition."""
    if report.missing_parents_count:
        report.warnings.append(
            f"{report.missing_parents_count} event(s) reference a parent id not present in the session"
        )
    if report.duplicate_id_count:
        report.warnings.append(f"{report.duplicate_id_count} duplicate event id(s) in the persisted set")
    if report.missing_sequence_count:
        sample = ", ".join(str(value) for value in report.missing_sequence_values[:5])
        report.warnings.append(
            f"{report.missing_sequence_count} emission sequence position(s) missing (at: {sample})"
        )
    if report.expected_event_count is not None and report.count_match is False:
        report.warnings.append(
            f"expected {report.expected_event_count} event(s) but received {report.received_event_count}"
        )
    if report.truncated:
        report.warnings.append(f"{report.truncated_event_count} event payload(s) truncated at ingestion")
    if report.redaction_applied:
        report.warnings.append(f"redaction applied to {report.redacted_event_count} event(s)")
    if report.non_monotonic_timestamp_count:
        report.warnings.append(
            f"{report.non_monotonic_timestamp_count} timestamp(s) regress relative to emission order"
        )


__all__ = [
    "ID_SAMPLE_CAP",
    "REDACTED_MARKER",
    "REDACTION_MARKERS",
    "SEQUENCE_KEY",
    "TRUNCATION_FLAG",
    "SessionCompletenessReport",
    "compute_session_completeness",
]
