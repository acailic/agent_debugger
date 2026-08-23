"""Agent audit layer.

Turns a captured session into an evidence-backed audit report that answers
the five operator questions (what / why / evidence / outcome / where-failed)
and produces an explainable trust score.

The engine is deterministic and inspectable: every number it emits is
derivable from captured event fields, never from an opaque model call.
"""

from __future__ import annotations

from .audit_engine import SessionAuditEngine, SessionAuditReport
from .failure_narrative import build_failure_narrative
from .who_when import evaluate_records, load_who_when_records

__all__ = [
    "SessionAuditEngine",
    "SessionAuditReport",
    "build_failure_narrative",
    "evaluate_records",
    "load_who_when_records",
]
