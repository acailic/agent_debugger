#!/usr/bin/env python3
"""Seed the local database with reusable benchmark sessions."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent_debugger_sdk.core.context import configure_event_pipeline
from agent_debugger_sdk.core.events import Checkpoint, Session, TraceEvent
from benchmarks import DEFAULT_SEED_SESSION_IDS, iter_seed_scenarios
from collector.buffer import get_event_buffer
from collector.server import configure_storage
from storage import Base, TraceRepository
from storage.models import AnomalyAlertModel

DATABASE_URL = os.environ.get("AGENT_DEBUGGER_DB_URL", "sqlite+aiosqlite:///./data/agent_debugger.db")

# Session enrichment data: realistic values for demo sessions
# Note: failure_count is computed in API layer (services.py) as errors count
# behavior_alert_count is computed in API layer from AnomalyAlertModel records
def validate_session_enrichment(session_id: str, enrichment: dict[str, object]) -> None:
    """Validate curated enrichment metrics for demo seed sessions."""
    total_tokens = enrichment.get("total_tokens")
    total_cost_usd = enrichment.get("total_cost_usd")

    if not isinstance(total_tokens, int) or total_tokens <= 0:
        raise ValueError(f"Seed enrichment for {session_id} must define positive total_tokens")

    if not isinstance(total_cost_usd, (int, float)) or float(total_cost_usd) <= 0:
        raise ValueError(f"Seed enrichment for {session_id} must define positive total_cost_usd")


SESSION_ENRICHMENT = {
    "seed-prompt-injection": {
        "total_tokens": 856,
        "total_cost_usd": 0.0042,
        "retention_tier": "summarized",
        "fix_note": "Added input sanitization and prompt boundary checks",
        "errors": 0,
        "behavior_alerts": 1,
    },
    "seed-evidence-grounding": {
        "total_tokens": 140,
        "total_cost_usd": 0.0021,
        "retention_tier": "summarized",
        "fix_note": None,
        "errors": 0,
        "behavior_alerts": 0,
    },
    "seed-multi-agent-dialogue": {
        "total_tokens": 412,
        "total_cost_usd": 0.0038,
        "retention_tier": "summarized",
        "fix_note": None,
        "errors": 0,
        "behavior_alerts": 0,
    },
    "seed-prompt-policy-shift": {
        "total_tokens": 164,
        "total_cost_usd": 0.0028,
        "retention_tier": "summarized",
        "fix_note": "Added policy consistency checks across turns",
        "errors": 0,
        "behavior_alerts": 1,
    },
    "seed-safety-escalation": {
        "total_tokens": 1987,
        "total_cost_usd": 0.0142,
        "retention_tier": "full",
        "fix_note": "Added output validation after tool call",
        "errors": 1,
        "behavior_alerts": 1,
    },
    "seed-looping-behavior": {
        "total_tokens": 1245,
        "total_cost_usd": 0.0089,
        "retention_tier": "summarized",
        "fix_note": "Added max iteration limit with circuit breaker",
        "errors": 0,
        "behavior_alerts": 2,
    },
    "seed-failure-cluster": {
        "total_tokens": 1567,
        "total_cost_usd": 0.0112,
        "retention_tier": "full",
        "fix_note": "Added pre-call validation and error recovery",
        "errors": 0,
        "behavior_alerts": 1,
    },
    "seed-replay-determinism": {
        "total_tokens": 289,
        "total_cost_usd": 0.0031,
        "retention_tier": "summarized",
        "fix_note": None,
        "errors": 0,
        "behavior_alerts": 0,
    },
}


def validate_session_metrics(total_tokens: int, total_cost_usd: float, *, context: str) -> None:
    """Validate curated session metrics before persisting demo seed data."""
    if total_tokens < 0:
        raise ValueError(f"{context}: total_tokens must be non-negative, got {total_tokens}")
    if total_cost_usd < 0:
        raise ValueError(f"{context}: total_cost_usd must be non-negative, got {total_cost_usd}")

    has_tokens = total_tokens > 0
    has_cost = total_cost_usd > 0
    if has_tokens != has_cost:
        raise ValueError(
            f"{context}: total_tokens and total_cost_usd must either both be zero or both be positive "
            f"(got total_tokens={total_tokens}, total_cost_usd={total_cost_usd})"
        )


async def enrich_session(session_id: str, session_maker: async_sessionmaker[AsyncSession]) -> None:
    """Enrich a session with realistic data fields and behavior alerts."""
    enrichment = SESSION_ENRICHMENT.get(session_id, {})
    if not enrichment:
        return

    validate_session_enrichment(session_id, enrichment)

    total_tokens = enrichment.get("total_tokens", 0)
    total_cost_usd = enrichment.get("total_cost_usd", 0.0)
    validate_session_metrics(total_tokens, total_cost_usd, context=f"seed enrichment for {session_id}")

    async with session_maker() as db_session:
        repo = TraceRepository(db_session)

        # Update session fields
        update_data = {
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost_usd,
            "errors": enrichment.get("errors", 0),
        }

        if enrichment.get("fix_note"):
            update_data["fix_note"] = enrichment["fix_note"]

        await repo.update_session(session_id, **update_data)

        # Update retention_tier directly on the ORM model
        from sqlalchemy import update

        from storage.models import SessionModel

        if enrichment.get("retention_tier"):
            await db_session.execute(
                update(SessionModel)
                .where(SessionModel.id == session_id)
                .values(retention_tier=enrichment["retention_tier"])
            )

        # Create behavior alerts if needed
        behavior_alerts = enrichment.get("behavior_alerts", 0)
        if behavior_alerts > 0:
            # Get session events for alert context
            events = await repo.list_events(session_id, limit=10)
            event_ids = [e.id for e in events[:behavior_alerts]] if events else []

            for i in range(behavior_alerts):
                alert = AnomalyAlertModel(
                    id=str(uuid.uuid4()),
                    tenant_id="local",
                    session_id=session_id,
                    alert_type="looping_behavior",
                    severity=0.7 + (i * 0.1),
                    signal=f"Detected repeated tool call pattern (iteration {i + 1})",
                    event_ids=event_ids[i : i + 1] if i < len(event_ids) else [],
                    detection_source="demo_seed",
                    detection_config={"threshold": 3, "window": 60},
                )
                await repo.create_anomaly_alert(alert)

        await db_session.commit()


async def main() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def persist_session_start(session: Session) -> None:
        async with session_maker() as db_session:
            repo = TraceRepository(db_session)
            existing = await repo.get_session(session.id)
            if existing is None:
                await repo.create_session(session)
                await db_session.commit()

    async def persist_session_update(session: Session) -> None:
        async with session_maker() as db_session:
            repo = TraceRepository(db_session)
            await repo.update_session(
                session.id,
                agent_name=session.agent_name,
                framework=session.framework,
                ended_at=session.ended_at,
                status=session.status,
                total_tokens=session.total_tokens,
                total_cost_usd=session.total_cost_usd,
                tool_calls=session.tool_calls,
                llm_calls=session.llm_calls,
                errors=session.errors,
                config=session.config,
                tags=session.tags,
            )
            await db_session.commit()

    async def persist_event(event: TraceEvent) -> None:
        async with session_maker() as db_session:
            repo = TraceRepository(db_session)
            await repo.add_event(event)
            await db_session.commit()

    async def persist_checkpoint(checkpoint: Checkpoint) -> None:
        async with session_maker() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_checkpoint(checkpoint)
            await db_session.commit()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    configure_storage(session_maker)
    configure_event_pipeline(
        get_event_buffer(),
        persist_event=persist_event,
        persist_checkpoint=persist_checkpoint,
        persist_session_start=persist_session_start,
        persist_session_update=persist_session_update,
    )

    for name, runner in iter_seed_scenarios():
        session_id = DEFAULT_SEED_SESSION_IDS[name]
        async with session_maker() as db_session:
            repo = TraceRepository(db_session)
            await repo.delete_session(session_id)
        await runner(session_id)
        await enrich_session(session_id, session_maker)
        print(f"seeded {session_id}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
