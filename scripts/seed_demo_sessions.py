#!/usr/bin/env python3
"""Seed the local database with reusable benchmark sessions."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent_debugger_sdk.core.context import configure_event_pipeline
from agent_debugger_sdk.core.events import Checkpoint, Session, TraceEvent
from benchmarks import DEFAULT_SEED_SESSION_IDS, iter_seed_scenarios
from collector.buffer import get_event_buffer
from collector.server import configure_storage
from storage import Base, TraceRepository

DATABASE_URL = os.environ.get("AGENT_DEBUGGER_DB_URL", "sqlite+aiosqlite:///./data/agent_debugger.db")


async def main() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def persist_session_start(session: Session) -> None:
        async with session_maker() as db_session:
            repo = TraceRepository(db_session)
            existing = await repo.get_session(session.id)
            if existing is None:
                await repo.create_session(session)

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

    async def persist_event(event: TraceEvent) -> None:
        async with session_maker() as db_session:
            repo = TraceRepository(db_session)
            await repo.add_event(event)

    async def persist_checkpoint(checkpoint: Checkpoint) -> None:
        async with session_maker() as db_session:
            repo = TraceRepository(db_session)
            await repo.create_checkpoint(checkpoint)

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
        print(f"seeded {session_id}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
