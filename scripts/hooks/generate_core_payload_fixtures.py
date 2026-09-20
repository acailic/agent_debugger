#!/usr/bin/env python3
"""Regenerate tests/contract/fixtures_core_payloads.json from the real app.

Seeds two benchmark sessions into a throwaway SQLite database, serves the app
in-process (httpx ASGITransport: no server, no network), and records verbatim
JSON responses for the core contract endpoints. The committed artifact is a
static file validated by scripts/hooks/check_api_contract.py without a running
app. Regenerate from the repo root after changing core schemas or routes:

    .venv-ci/bin/python scripts/hooks/generate_core_payload_fixtures.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from agent_debugger_sdk.core.context import configure_event_pipeline  # noqa: E402
from api import app_context  # noqa: E402
from api import services as api_services  # noqa: E402
from api.main import create_app  # noqa: E402
from benchmarks import run_evidence_grounding_session, run_replay_breakpoints_session  # noqa: E402
from collector.buffer import get_event_buffer  # noqa: E402
from collector.server import configure_storage  # noqa: E402
from storage import Base  # noqa: E402

EVIDENCE_SESSION = "q04-contract-evidence"
REPLAY_SESSION = "q04-contract-replay"
OUTPUT_PATH = REPO_ROOT / "tests/contract/fixtures_core_payloads.json"


async def _seed(engine, session_maker) -> None:
    app_context.engine = engine
    app_context.async_session_maker = session_maker
    buffer = get_event_buffer()
    buffer._events.clear()
    buffer._queues.clear()
    buffer._session_activity.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    configure_storage(session_maker)
    configure_event_pipeline(
        buffer,
        persist_event=api_services.persist_event,
        persist_checkpoint=api_services.persist_checkpoint,
        persist_session_start=api_services.persist_session_start,
        persist_session_update=api_services.persist_session_update,
    )
    await run_evidence_grounding_session(EVIDENCE_SESSION)
    await run_replay_breakpoints_session(REPLAY_SESSION)


async def _collect_payloads(client: AsyncClient) -> dict[str, dict]:
    async def get_json(path: str, params: dict | None = None) -> dict:
        response = await client.get(path, params=params)
        assert response.status_code == 200, f"{path} returned {response.status_code}: {response.text[:200]}"
        return response.json()

    session_detail = await get_json(f"/api/sessions/{EVIDENCE_SESSION}")
    bundle = await get_json(f"/api/sessions/{EVIDENCE_SESSION}/trace")
    replay = await get_json(
        f"/api/sessions/{REPLAY_SESSION}/replay", params={"mode": "highlights", "collapse_threshold": 0.6},
    )
    search = await get_json(
        "/api/traces/search",
        params={"query": "Belgrade", "session_id": EVIDENCE_SESSION, "event_type": "decision", "limit": 5},
    )
    checkpoint = await get_json(f"/api/checkpoints/{replay['checkpoints'][0]['id']}")
    rich_event = next(
        (event for event in bundle["events"] if event["event_type"] == "decision" and event.get("evidence")),
        bundle["events"][0],
    )
    collapsed_segment = replay["collapsed_segments"][0] if replay["collapsed_segments"] else None
    highlight = bundle["analysis"]["highlights"][0] if bundle["analysis"].get("highlights") else None
    payloads = {
        "Session": session_detail["session"],
        "TraceEvent": rich_event,
        "Checkpoint": checkpoint,
        "TraceBundle": bundle,
        "ReplayResponse": replay,
        "TraceSearchResponse": search,
        "Highlight": highlight,
        "CollapsedSegment": collapsed_segment,
    }
    expectations = {
        "Highlight": lambda p: p is not None,
        "CollapsedSegment": lambda p: p is not None,
        "TraceEvent": lambda p: p["evidence"] and p["evidence_event_ids"],
        "ReplayResponse": lambda p: p["collapsed_segments"] and p["highlight_indices"] and p["checkpoints"],
        "TraceSearchResponse": lambda p: p["results"] and p["total"] >= 1,
        "TraceBundle": lambda p: p["tree"] and p["analysis"]["highlights"],
    }
    for interface, holds in expectations.items():
        assert holds(payloads[interface]), f"{interface} fixture is not representative; adjust the seed sessions"
    return payloads


async def main() -> None:
    """Write the fixture file and print what was captured."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine = create_async_engine(f"sqlite+aiosqlite:///{Path(tmp_dir) / 'fixtures.db'}")
        session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            await _seed(engine, session_maker)
            transport = ASGITransport(app=create_app())
            async with AsyncClient(transport=transport, base_url="http://contract-fixtures") as client:
                payloads = await _collect_payloads(client)
        finally:
            configure_storage(None)
            configure_event_pipeline(None)
            await engine.dispose()
            app_context.engine = None
            app_context.async_session_maker = None
    fixtures = {
        "_meta": {
            "description": (
                "Static core response payloads for scripts/hooks/check_api_contract.py. "
                "Validated against the live Pydantic models and the frontend TS interfaces; "
                "the check itself never starts the app."
            ),
            "generated_by": "scripts/hooks/generate_core_payload_fixtures.py",
            "regenerate": ".venv-ci/bin/python scripts/hooks/generate_core_payload_fixtures.py",
            "method": (
                "Benchmark seed sessions written to a throwaway SQLite database, served by the "
                "in-process ASGI app, captured verbatim from the HTTP responses."
            ),
            "seed_sessions": {
                interface: f"{EVIDENCE_SESSION} ({REPLAY_SESSION} for ReplayResponse/CollapsedSegment)"
                if interface in {"ReplayResponse", "CollapsedSegment"}
                else EVIDENCE_SESSION
                for interface in payloads
            },
            "endpoints": {
                "Session": f"GET /api/sessions/{{id}} (.session) [seed {EVIDENCE_SESSION}]",
                "TraceEvent": "GET /api/sessions/{id}/trace (.events[] decision with evidence)",
                "Checkpoint": "GET /api/checkpoints/{checkpoint_id}",
                "TraceBundle": "GET /api/sessions/{id}/trace",
                "ReplayResponse": f"GET /api/sessions/{{id}}/replay?mode=highlights [seed {REPLAY_SESSION}]",
                "TraceSearchResponse": "GET /api/traces/search?query=Belgrade&event_type=decision",
                "Highlight": "GET /api/sessions/{id}/trace (.analysis.highlights[])",
                "CollapsedSegment": "GET /api/sessions/{id}/replay?mode=highlights (.collapsed_segments[])",
            },
        },
        "payloads": payloads,
    }
    OUTPUT_PATH.write_text(json.dumps(fixtures, indent=2) + "\n")
    print(f"Wrote {len(payloads)} payloads to {OUTPUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
