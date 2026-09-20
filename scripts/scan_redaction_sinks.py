#!/usr/bin/env python3
"""Sentinel scan over every redaction sink for one session (Q08 artifact).

Manual audit tool: given a session id and a list of synthetic markers
(e.g. ``SENTINEL-SECRET-7``, an email, an AWS-style key), scan every sink
the redaction policy must cover and exit nonzero if any marker survives
where it is forbidden:

- ``sessions`` row — config / metadata columns (whole row is scanned),
- ``events`` rows — data and event_metadata columns,
- ``checkpoints`` rows — state and memory columns,
- the SSE stream served by ``GET /api/sessions/<id>/stream`` (captured for
  a few seconds while events flow).

Permitted survivors are NOT failures: the scan only reports markers found
in the sinks above. Structural ids (session id, event ids) are expected to
survive by design.

Usage::

    .venv-ci/bin/python scripts/scan_redaction_sinks.py SESSION_ID \\
        SENTINEL-SECRET-1 user@example.org AKIA... [--db-url URL] \\
        [--api-base http://localhost:8000] [--sse-seconds 5] [--skip-sse]

Exit codes: 0 = clean, 1 = marker found in a forbidden sink,
2 = operational error (bad usage, unreachable database, ...).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from storage.engine import get_database_url
from storage.models import CheckpointModel, EventModel, SessionModel

try:
    import httpx
except ImportError:  # pragma: no cover - httpx is a project dependency
    httpx = None  # type: ignore[assignment]


def _row_to_blob(row: Any) -> str:
    """Render every column of an ORM row into one scannable string."""
    parts: list[str] = []
    for column in row.__table__.columns:
        value = getattr(row, column.key)
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, default=str)
        parts.append(f"{column.key}={value!r}")
    return " ".join(parts)


async def scan_database(session_id: str, markers: list[str], db_url: str) -> tuple[list[str], dict[str, int]]:
    """Scan session/event/checkpoint rows; return (findings, row counts)."""
    engine = create_async_engine(db_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    findings: list[str] = []
    counts: dict[str, int] = {}
    try:
        async with session_factory() as session:
            for label, model, predicate in (
                ("sessions", SessionModel, SessionModel.id == session_id),
                ("events", EventModel, EventModel.session_id == session_id),
                ("checkpoints", CheckpointModel, CheckpointModel.session_id == session_id),
            ):
                rows = (await session.execute(select(model).where(predicate))).scalars().all()
                counts[label] = len(rows)
                for row in rows:
                    blob = _row_to_blob(row)
                    for marker in markers:
                        if marker in blob:
                            findings.append(f"DB {label}[{row.id}]: marker {marker!r} survived")
    finally:
        await engine.dispose()
    return findings, counts


async def scan_sse(
    session_id: str,
    markers: list[str],
    api_base: str,
    seconds: float,
) -> tuple[list[str], int]:
    """Capture the SSE stream briefly; return (findings, data frame count)."""
    if httpx is None:
        raise RuntimeError("httpx is required for SSE scanning")
    url = f"{api_base.rstrip('/')}/api/sessions/{session_id}/stream"
    captured: list[str] = []
    data_frames = 0
    loop = asyncio.get_event_loop()
    deadline = loop.time() + seconds
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, read=30.0)) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                captured.append(line)
                if line.startswith("data:"):
                    data_frames += 1
                if loop.time() >= deadline:
                    break
    findings = [
        f"SSE stream: marker {marker!r} survived"
        for marker in markers
        if any(marker in line for line in captured)
    ]
    return findings, data_frames


async def main_async(args: argparse.Namespace) -> int:
    db_url = args.db_url or get_database_url()
    print(f"Scanning session {args.session_id}")
    print(f"  markers: {args.markers}")
    print(f"  database: {db_url}")

    findings: list[str] = []
    try:
        db_findings, counts = await scan_database(args.session_id, args.markers, db_url)
    except Exception as exc:  # operational failure, not a policy result
        print(f"ERROR: database scan failed: {exc}", file=sys.stderr)
        return 2
    findings.extend(db_findings)
    for label, count in counts.items():
        print(f"  {label} rows scanned: {count}")
    if counts["sessions"] == 0:
        print("ERROR: session not found in the database", file=sys.stderr)
        return 2

    if args.skip_sse:
        print("  SSE stream: skipped (--skip-sse)")
    else:
        print(f"  SSE capture: {args.sse_seconds}s from {args.api_base}")
        try:
            sse_findings, frames = await scan_sse(
                args.session_id, args.markers, args.api_base, args.sse_seconds
            )
        except Exception as exc:
            print(f"WARNING: SSE scan skipped (unreachable API?): {exc}", file=sys.stderr)
            if args.require_sse:
                return 2
            sse_findings, frames = [], -1
        print(f"  SSE data frames captured: {frames}")
        findings.extend(sse_findings)

    if findings:
        print("\nFAIL — markers found in forbidden sinks:")
        for finding in findings:
            print(f"  - {finding}")
        return 1

    print("\nPASS — no marker survived in any scanned sink")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan every redaction sink (DB rows + SSE stream) for sentinel markers.",
    )
    parser.add_argument("session_id", help="Session id to audit")
    parser.add_argument("markers", nargs="+", help="Marker strings that must NOT appear in any sink")
    parser.add_argument("--db-url", default=None, help="Database URL (default: AGENT_DEBUGGER_DB_URL)")
    parser.add_argument("--api-base", default="http://localhost:8000", help="API base URL for the SSE stream")
    parser.add_argument("--sse-seconds", type=float, default=5.0, help="Seconds to capture the SSE stream")
    parser.add_argument("--skip-sse", action="store_true", help="Skip the SSE capture (database-only audit)")
    parser.add_argument(
        "--require-sse",
        action="store_true",
        help="Fail (exit 2) when the SSE stream cannot be captured instead of skipping",
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
