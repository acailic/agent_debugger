#!/usr/bin/env python3
"""Seed the synthetic CI baseline session and export it through the CLI.

Regenerates ``benchmarks/regression/baseline_session.json`` — the committed
incident bundle the pytest gate (``tests/test_regression_baseline.py``)
replays on every run. The session is fully hand-built: fixed ids, fixed
timestamps, obviously synthetic payloads. Nothing is read from a real
incident, no wall-clock value enters the export, so re-running this script
reproduces the identical bundle hash.

Session shape (one deterministic error-chain incident):

* ``agent_start`` — synthetic objective
* ``tool_call``/``tool_result`` (``search``) — a successful grounded fact
* ``decision`` citing that result — a ``verified`` claim row
* ``tool_call``/``tool_result`` (``deploy``) — a failing tool result
* ``error`` chained on the failing result — an ``upstream_runtime_error``
  finding (the localized failure the narrative mechanism pins)
* ``decision`` without evidence — an ``unsupported`` claim row

The export runs through ``scripts/regression_cli.py export`` (the same CLI
operators use) against the seeded temp database, with the redaction-policy
environment pinned to the repo defaults so a developer with local
``AGENT_DEBUGGER_*`` overrides still reproduces the committed hash.

Usage::

    .venv-ci/bin/python scripts/seed_regression_baseline.py \
        [--out benchmarks/regression/baseline_session.json]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from agent_debugger_sdk.core.events import Checkpoint, EventType, Session, SessionStatus, TraceEvent  # noqa: E402
from storage import Base, TraceRepository  # noqa: E402

#: The committed baseline's stable identifiers (also the bundle's session id).
SESSION_ID = "regbase-session-0001"

#: Fixed creation clock — every timestamp in the session is derived from it.
BASE_TS = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)

#: Default output: the committed CI baseline bundle.
DEFAULT_OUT = _REPO_ROOT / "benchmarks" / "regression" / "baseline_session.json"

#: Redaction-policy env pinned to the repo defaults for the CLI subprocess so
#: the recorded policy summary (and therefore the content hash) never depends
#: on a developer's local overrides.
_PINNED_ENV = {
    "AGENT_DEBUGGER_REDACT_PROMPTS": "false",
    "AGENT_DEBUGGER_REDACT_TOOL_PAYLOADS": "false",
    "AGENT_DEBUGGER_REDACT_PII": "false",
    "AGENT_DEBUGGER_MAX_PAYLOAD_KB": "100",
}


def _event(
    event_id: str,
    event_type: EventType,
    *,
    parent_id: str | None = None,
    upstream_event_ids: list[str] | None = None,
    timestamp: datetime | None = None,
    **data,
) -> TraceEvent:
    return TraceEvent(
        id=event_id,
        session_id=SESSION_ID,
        parent_id=parent_id,
        name=f"synthetic_{event_type}",
        event_type=event_type,
        timestamp=timestamp or BASE_TS,
        data=data,
        upstream_event_ids=upstream_event_ids or [],
    )


def _baseline_events() -> list[TraceEvent]:
    """The eight synthetic events of the error-chain baseline incident."""
    return [
        _event(
            "regbase-start",
            EventType.AGENT_START,
            timestamp=BASE_TS,
            content="Synthetic baseline: summarize the demo quarter report",
        ),
        _event(
            "regbase-search-call",
            EventType.TOOL_CALL,
            timestamp=BASE_TS.replace(minute=1),
            tool_name="search",
        ),
        _event(
            "regbase-search-result",
            EventType.TOOL_RESULT,
            parent_id="regbase-search-call",
            timestamp=BASE_TS.replace(minute=2),
            tool_name="search",
            result={"rows": 3},
        ),
        _event(
            "regbase-decision",
            EventType.DECISION,
            timestamp=BASE_TS.replace(minute=3),
            confidence=0.9,
            chosen_action="answer",
            reasoning="grounded in the synthetic search results",
            evidence_event_ids=["regbase-search-result"],
        ),
        _event(
            "regbase-deploy-call",
            EventType.TOOL_CALL,
            timestamp=BASE_TS.replace(minute=4),
            tool_name="deploy",
        ),
        _event(
            "regbase-deploy-result",
            EventType.TOOL_RESULT,
            parent_id="regbase-deploy-call",
            timestamp=BASE_TS.replace(minute=5),
            tool_name="deploy",
            error="connection reset by peer",
        ),
        _event(
            "regbase-error",
            EventType.ERROR,
            parent_id="regbase-deploy-result",
            upstream_event_ids=["regbase-deploy-call"],
            timestamp=BASE_TS.replace(minute=6),
            error="deploy failed: connection reset by peer",
        ),
        _event(
            "regbase-decision-2",
            EventType.DECISION,
            timestamp=BASE_TS.replace(minute=7),
            confidence=0.8,
            chosen_action="deploy",
            reasoning="assumed the deploy would succeed",
            evidence_event_ids=[],
        ),
    ]


async def _seed(db_url: str) -> None:
    """Create the schema + the baseline session in a fresh temp database."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db:
        repo = TraceRepository(db, tenant_id="local")
        await repo.create_session(
            Session(
                id=SESSION_ID,
                agent_name="regression-baseline-agent",
                framework="synthetic",
                status=SessionStatus.ERROR,
                started_at=BASE_TS,
                ended_at=BASE_TS.replace(minute=7),
                tags=["regression-baseline"],
                config={"contact": "regbase@example.com", "purpose": "synthetic CI baseline"},
            )
        )
        await repo.add_events_batch(_baseline_events())
        await repo.create_checkpoint(
            Checkpoint(
                id="regbase-checkpoint-1",
                session_id=SESSION_ID,
                event_id="regbase-search-result",
                sequence=1,
                state={"stage": 1},
                memory={"last_tool": "search"},
                timestamp=BASE_TS.replace(minute=2),
                importance=0.8,
            )
        )
        await db.commit()
    await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed the synthetic baseline session and export it via the regression CLI.",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help=f"Output bundle path (default: {DEFAULT_OUT.relative_to(_REPO_ROOT)})",
    )
    args = parser.parse_args(argv)

    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="regbase-seed-")
    os.close(fd)
    db_url = f"sqlite+aiosqlite:///{db_path}"
    try:
        asyncio.run(_seed(db_url))

        env = {key: value for key, value in os.environ.items() if not key.startswith("AGENT_DEBUGGER_")}
        env.update(_PINNED_ENV)
        export_cmd = [
            sys.executable,
            str(_REPO_ROOT / "scripts" / "regression_cli.py"),
            "export",
            "--session-id",
            SESSION_ID,
            "--out",
            args.out,
            "--db-url",
            db_url,
        ]
        result = subprocess.run(export_cmd, check=False, env=env, cwd=_REPO_ROOT)
        if result.returncode != 0:
            return result.returncode
    finally:
        os.unlink(db_path)

    from collector.regression import load_bundle  # noqa: E402

    bundle = load_bundle(args.out)
    print(f"Baseline bundle ready: {args.out}")
    print(f"  session: {bundle['session']['id']}  content_hash: {bundle['content_hash']}")
    print(
        f"  events: {bundle['event_count']}  checkpoints: {bundle['checkpoint_count']}"
        f"  assertions: {len(bundle['expected_assertions'])}"
    )
    print("Determinism check: re-running this script must print the same content_hash.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
