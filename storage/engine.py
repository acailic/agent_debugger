"""Config-driven database engine factory."""
import os

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./agent_debugger.db"


def get_database_url() -> str:
    return os.environ.get("AGENT_DEBUGGER_DB_URL", DEFAULT_SQLITE_URL)


def create_db_engine(url: str | None = None, **kwargs) -> AsyncEngine:
    db_url = url or get_database_url()
    defaults = {"echo": False}
    if "sqlite" in db_url:
        defaults["connect_args"] = {"check_same_thread": False}
    defaults.update(kwargs)
    return create_async_engine(db_url, **defaults)


def create_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)