"""Contract tests ensuring API schemas match frontend TypeScript types.

This test parses the frontend TS type definitions and compares them
against the Pydantic schemas to detect drift early.

Run with: pytest tests/contract/test_schema_alignment.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from api.schemas import SessionSchema, TraceEventSchema


def _parse_ts_interface_fields(ts_source: str, interface_name: str) -> set[str]:
    """Extract field names from a TypeScript interface definition."""
    # Find the interface block
    pattern = rf"export interface {interface_name}\s*\{{([^}}]+)\}}"
    match = re.search(pattern, ts_source, re.DOTALL)
    if not match:
        return set()
    body = match.group(1)
    # Extract field names (lines with identifier before colon)
    fields = set()
    for line in body.split("\n"):
        line = line.strip()
        # Skip comment lines and closing braces
        if not line or line.startswith(("//", "}")):
            continue
        field_match = re.match(r"^(\w+)(\??):", line)
        if field_match:
            fields.add(field_match.group(1))
    return fields


def _get_ts_source() -> str:
    """Read the frontend types file."""
    types_path = Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "types" / "index.ts"
    if not types_path.exists():
        pytest.skip("Frontend types file not found (frontend not built?)")
    return types_path.read_text()


class TestSessionSchemaAlignment:
    """Ensure SessionSchema fields match the frontend Session interface."""

    def test_session_fields_match(self) -> None:
        ts_source = _get_ts_source()
        ts_fields = _parse_ts_interface_fields(ts_source, "Session")

        py_fields = set(SessionSchema.model_fields.keys())

        # Python-only fields (not in TS) are acceptable if they're
        # server-internal fields the frontend doesn't consume.
        py_fields - ts_fields
        ts_only = ts_fields - py_fields

        if ts_only:
            pytest.fail(
                f"Frontend Session interface has fields not in Python SessionSchema: {ts_only}\n"
                f"Add the missing fields to api/schemas_core.py:SessionSchema"
            )

    def test_trace_event_core_fields_match(self) -> None:
        """Check that the core TraceEvent fields exist in both."""
        ts_source = _get_ts_source()
        ts_fields = _parse_ts_interface_fields(ts_source, "TraceEvent")

        py_fields = set(TraceEventSchema.model_fields.keys())

        # Every frontend field must exist in the Python schema
        missing_in_py = ts_fields - py_fields
        if missing_in_py:
            pytest.fail(
                f"Frontend TraceEvent has fields missing from Python TraceEventSchema: {missing_in_py}\n"
                f"Add the missing fields to api/schemas_core.py:TraceEventSchema"
            )
