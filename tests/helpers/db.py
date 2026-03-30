"""Composable database fixtures for isolated unit tests.

These fixtures create temp-file or in-memory SQLite databases for each test,
independent of the global app_context. Use them when testing service
functions that accept a session_maker parameter or need a direct session.
"""

from __future__ import annotations

import os
import tempfile

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from storage import Base, TraceRepository


@pytest.fixture
async def db_session_maker():
    """Provide an isolated session maker for tests.

    Uses a temp file so that separate connections share the same database.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()
    os.unlink(db_path)


@pytest_asyncio.fixture
async def db_session():
    """Provide an in-memory SQLite session for tests.

    Creates a fresh database for each test function.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def repo(db_session_maker: async_sessionmaker[AsyncSession]):
    """Provide a TraceRepository backed by an in-memory database."""
    async with db_session_maker() as session:
        yield TraceRepository(session)
