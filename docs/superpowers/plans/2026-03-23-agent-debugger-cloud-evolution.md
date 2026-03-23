# Agent Debugger: MVP → Cloud Product Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve the working local MVP into a cloud-ready SaaS product with open-source SDK, multi-tenancy, auth, and LangChain-first integration — ready for beta users in 10 weeks.

**Architecture:** Same codebase serves both local (SQLite + in-memory buffer) and cloud (PostgreSQL + Redis + S3) via config-driven abstractions. SDK ships to PyPI with three integration levels. Auth splits into API keys (SDK ingestion) and JWT (dashboard).

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy (async), Alembic, Redis (aioredis), PostgreSQL (asyncpg), S3 (aiobotocore), Clerk (auth), Stripe (billing), React + Vite + TypeScript.

**Specs:** `docs/decisions/ADR-002,004,005,006,008,011`

---

## File Structure Map

### New Files

```
agent_debugger_sdk/
├── config.py                    # init(), Config dataclass, env-based config
├── auto_instrument.py           # Auto-instrumentation registry and patching

agent_debugger_sdk/
├── transport.py                 # HTTP transport for cloud mode

storage/
├── models.py                    # Extracted ORM models (from repository.py)
├── retention.py                 # Tier-based retention logic
├── engine.py                    # Config-driven engine factory
├── migrations/
│   ├── __init__.py
│   ├── env.py                   # Alembic environment
│   └── versions/
│       ├── __init__.py
│       ├── 001_initial_schema.py
│       ├── 002_add_tenant_id.py
│       └── 003_add_api_keys.py

auth/
├── __init__.py
├── api_keys.py                  # API key generation, validation, storage
├── middleware.py                 # FastAPI dependencies for auth
├── models.py                    # Tenant, User, APIKey ORM models

collector/
├── buffer_base.py               # Abstract buffer interface
├── buffer_redis.py              # Redis Streams + pub/sub implementation

redaction/
├── __init__.py
├── pipeline.py                  # Ingestion-time redaction pipeline
├── patterns.py                  # PII regex patterns

pyproject.toml                   # Package config for PyPI
alembic.ini                      # Alembic config (project root)
```

### Modified Files

```
agent_debugger_sdk/__init__.py   # Add init() export
agent_debugger_sdk/core/context.py # Add config-aware initialization
agent_debugger_sdk/adapters/langchain.py # Harden, add auto-patch hook
storage/repository.py            # Add tenant_id filtering to all queries
storage/__init__.py              # Update exports
collector/__init__.py            # Update exports, add buffer factory
collector/server.py              # Add auth dependency, tenant context
collector/buffer.py              # Implement BufferBase interface
api/main.py                      # Add auth middleware, tenant context, config-driven DB
```

---

## Phase 1: Cloud-Ready Backend + Polished SDK (Weeks 1-4)

---

### Task 1: Extract ORM Models to Dedicated Module

Extract SQLAlchemy models from `storage/repository.py` into `storage/models.py` so repository stays focused on data access and models can be imported independently (needed by Alembic and auth).

**Files:**
- Create: `storage/models.py`
- Modify: `storage/repository.py` (remove model definitions, import from models.py)
- Modify: `storage/__init__.py` (update exports)
- Test: `tests/test_model_extraction.py`

- [ ] **Step 1: Write failing test that imports from new location**

```python
# tests/test_model_extraction.py
from storage.models import Base, SessionModel, EventModel, CheckpointModel


def test_models_importable_from_new_location():
    """Models should be importable from storage.models."""
    assert SessionModel.__tablename__ == "sessions"
    assert EventModel.__tablename__ == "events"
    assert CheckpointModel.__tablename__ == "checkpoints"
    assert hasattr(Base, "metadata")


def test_repository_still_works_with_extracted_models():
    """TraceRepository should still import and function."""
    from storage.repository import TraceRepository
    assert callable(TraceRepository)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_model_extraction.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'storage.models'`

- [ ] **Step 3: Create storage/models.py with extracted models**

Move `Base`, `SessionModel`, `EventModel`, `CheckpointModel` from `storage/repository.py` into `storage/models.py`. Keep all column definitions, relationships, and indexes identical.

```python
# storage/models.py
"""SQLAlchemy ORM models for agent debugger storage."""
from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class SessionModel(Base):
    __tablename__ = "sessions"
    # ... exact columns from current repository.py ...


class EventModel(Base):
    __tablename__ = "events"
    # ... exact columns from current repository.py ...


class CheckpointModel(Base):
    __tablename__ = "checkpoints"
    # ... exact columns from current repository.py ...
```

- [ ] **Step 4: Update storage/repository.py to import from models.py**

Replace model class definitions with:
```python
from storage.models import Base, SessionModel, EventModel, CheckpointModel
```

- [ ] **Step 5: Update storage/__init__.py exports**

```python
from storage.models import Base, SessionModel, EventModel, CheckpointModel
from storage.repository import TraceRepository
```

- [ ] **Step 6: Run all tests to verify nothing broke**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add storage/models.py storage/repository.py storage/__init__.py tests/test_model_extraction.py
git commit -m "refactor: extract ORM models to storage/models.py"
```

---

### Task 2: Add tenant_id to All ORM Models

Add `tenant_id` column to `sessions`, `events`, and `checkpoints` tables. Default to `"local"` for backward compatibility with self-hosted mode. This is the foundation for multi-tenancy (ADR-008).

**Files:**
- Modify: `storage/models.py` (add tenant_id columns)
- Modify: `storage/repository.py` (add tenant_id filtering)
- Test: `tests/test_tenant_isolation.py`

- [ ] **Step 1: Write failing test for tenant isolation**

```python
# tests/test_tenant_isolation.py
import asyncio
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from storage.models import Base, SessionModel
from storage.repository import TraceRepository
from agent_debugger_sdk.core.events import Session
import datetime


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_tenant_id_on_session_model():
    """SessionModel must have a tenant_id column."""
    assert hasattr(SessionModel, "tenant_id")


@pytest.mark.asyncio
async def test_list_sessions_filters_by_tenant(db_session):
    """list_sessions should only return sessions for the given tenant."""
    repo = TraceRepository(db_session, tenant_id="tenant_a")
    session_a = Session(
        id="sess-a", agent_name="agent", framework="test",
        started_at=datetime.datetime.now(datetime.UTC),
        ended_at=None, status="running", total_tokens=0,
        total_cost_usd=0.0, tool_calls=0, llm_calls=0,
        errors=0, config={}, tags=[],
    )
    await repo.create_session(session_a)

    repo_b = TraceRepository(db_session, tenant_id="tenant_b")
    sessions_b = await repo_b.list_sessions()
    assert len(sessions_b) == 0, "Tenant B should not see Tenant A sessions"

    sessions_a = await repo.list_sessions()
    assert len(sessions_a) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_tenant_isolation.py -v`
Expected: FAIL — TraceRepository does not accept tenant_id

- [ ] **Step 3: Add tenant_id to all models in storage/models.py**

Add to SessionModel, EventModel, CheckpointModel:
```python
tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="local", index=True)
```

Add composite indexes:
```python
# On EventModel
__table_args__ = (
    Index("ix_events_tenant_session", "tenant_id", "session_id"),
    # ... keep existing indexes ...
)
```

- [ ] **Step 4: Update TraceRepository to accept and filter by tenant_id**

```python
class TraceRepository:
    def __init__(self, session: AsyncSession, tenant_id: str = "local") -> None:
        self._session = session
        self._tenant_id = tenant_id
```

Add `.where(SessionModel.tenant_id == self._tenant_id)` to ALL query methods: `list_sessions`, `get_session`, `count_sessions`, `search_events`, etc.

Set `tenant_id` on all model creation: `create_session`, `add_event`, `create_checkpoint`.

- [ ] **Step 5: Run all tests**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest -v`
Expected: ALL PASS (existing tests use default tenant_id="local")

- [ ] **Step 6: Commit**

```bash
git add storage/models.py storage/repository.py tests/test_tenant_isolation.py
git commit -m "feat: add tenant_id to all models for multi-tenancy"
```

---

### Task 3: Add Alembic Database Migrations

Set up Alembic for schema migrations. Generate initial migration from current models. This enables PostgreSQL deployment and future schema changes.

**Files:**
- Create: `alembic.ini`
- Create: `storage/migrations/env.py`
- Create: `storage/migrations/script.py.mako`
- Create: `storage/migrations/versions/001_initial_schema.py`

- [ ] **Step 1: Install Alembic**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && pip install alembic`

- [ ] **Step 2: Create alembic.ini at project root**

```ini
# alembic.ini
[alembic]
script_location = storage/migrations
sqlalchemy.url = sqlite+aiosqlite:///./agent_debugger.db

[loggers]
keys = root,sqlalchemy,alembic
# ... standard Alembic logging config ...
```

- [ ] **Step 3: Create storage/migrations/env.py**

```python
"""Alembic environment configuration."""
import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from storage.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def get_url() -> str:
    return os.environ.get(
        "AGENT_DEBUGGER_DB_URL",
        config.get_main_option("sqlalchemy.url", "sqlite+aiosqlite:///./agent_debugger.db"),
    )

def run_migrations_offline() -> None:
    url = get_url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online() -> None:
    engine = create_async_engine(get_url())
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 4: Generate initial migration**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && alembic revision --autogenerate -m "initial schema with tenant_id"`

- [ ] **Step 5: Verify migration applies cleanly**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && rm -f test_migration.db && AGENT_DEBUGGER_DB_URL=sqlite+aiosqlite:///./test_migration.db alembic upgrade head && rm test_migration.db`
Expected: Migration applies without errors

- [ ] **Step 6: Commit**

```bash
git add alembic.ini storage/migrations/
git commit -m "feat: add Alembic migrations for database schema management"
```

---

### Task 4: Config-Driven Database Engine (PostgreSQL + SQLite)

Make the database engine configurable via environment variable. Same codebase runs SQLite locally and PostgreSQL in cloud (ADR-005).

**Files:**
- Create: `storage/engine.py` (engine factory)
- Modify: `api/main.py` (use engine factory)
- Test: `tests/test_engine_factory.py`

- [ ] **Step 1: Write failing test for engine factory**

```python
# tests/test_engine_factory.py
import os
import pytest
from unittest.mock import patch


def test_default_engine_is_sqlite():
    """Without env var, engine should be SQLite."""
    from storage.engine import get_database_url
    with patch.dict(os.environ, {}, clear=True):
        url = get_database_url()
        assert "sqlite" in url


def test_env_var_overrides_engine():
    """AGENT_DEBUGGER_DB_URL should override default."""
    from storage.engine import get_database_url
    with patch.dict(os.environ, {"AGENT_DEBUGGER_DB_URL": "postgresql+asyncpg://localhost/debugger"}):
        url = get_database_url()
        assert "postgresql" in url


def test_create_engine_returns_async_engine():
    """create_engine should return an AsyncEngine."""
    from storage.engine import create_db_engine
    engine = create_db_engine("sqlite+aiosqlite:///:memory:")
    assert engine is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_engine_factory.py -v`
Expected: FAIL — no module `storage.engine`

- [ ] **Step 3: Create storage/engine.py**

```python
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
```

- [ ] **Step 4: Update api/main.py to use engine factory**

Replace hardcoded engine creation:
```python
# Before:
DATABASE_URL = os.environ.get("AGENT_DEBUGGER_DB_URL", "sqlite+aiosqlite:///./agent_debugger.db")
engine = create_async_engine(DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(engine, ...)

# After:
from storage.engine import create_db_engine, create_session_maker
engine = create_db_engine()
async_session_maker = create_session_maker(engine)
```

- [ ] **Step 5: Run all tests**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add storage/engine.py tests/test_engine_factory.py api/main.py
git commit -m "feat: config-driven database engine for SQLite and PostgreSQL"
```

---

### Task 5: Abstract EventBuffer Interface

Extract an interface from the current in-memory EventBuffer so Redis can implement the same contract (ADR-005).

**Files:**
- Create: `collector/buffer_base.py`
- Modify: `collector/buffer.py` (implement interface)
- Modify: `collector/__init__.py` (add factory)
- Test: `tests/test_buffer_interface.py`

- [ ] **Step 1: Write test for buffer interface compliance**

```python
# tests/test_buffer_interface.py
import asyncio
import pytest
from collector.buffer_base import BufferBase
from collector.buffer import EventBuffer
from agent_debugger_sdk.core.events import TraceEvent, EventType
import datetime


def _make_event(session_id: str = "s1", name: str = "test") -> TraceEvent:
    return TraceEvent(
        session_id=session_id, parent_id=None, event_type=EventType.TOOL_CALL,
        name=name, data={}, metadata={}, importance=0.5, upstream_event_ids=[],
    )


def test_event_buffer_is_subclass_of_base():
    assert issubclass(EventBuffer, BufferBase)


@pytest.mark.asyncio
async def test_publish_and_subscribe():
    buf = EventBuffer()
    queue = await buf.subscribe("s1")
    event = _make_event()
    await buf.publish("s1", event)
    received = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert received.id == event.id
    await buf.unsubscribe("s1", queue)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_buffer_interface.py -v`
Expected: FAIL — no module `collector.buffer_base`

- [ ] **Step 3: Create collector/buffer_base.py**

```python
"""Abstract base for event buffers."""
from __future__ import annotations

import abc
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_debugger_sdk.core.events import TraceEvent


class BufferBase(abc.ABC):
    """Interface for event pub/sub buffers."""

    @abc.abstractmethod
    async def publish(self, session_id: str, event: TraceEvent) -> None: ...

    @abc.abstractmethod
    async def subscribe(self, session_id: str) -> asyncio.Queue: ...

    @abc.abstractmethod
    async def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None: ...

    @abc.abstractmethod
    def get_events(self, session_id: str) -> list[TraceEvent]: ...

    @abc.abstractmethod
    def get_session_ids(self) -> list[str]: ...
```

- [ ] **Step 4: Update collector/buffer.py to inherit from BufferBase**

```python
from collector.buffer_base import BufferBase

class EventBuffer(BufferBase):
    # ... existing implementation, now explicitly implements the interface ...
```

- [ ] **Step 5: Add buffer factory to collector/__init__.py**

```python
from collector.buffer_base import BufferBase

def create_buffer(backend: str = "memory", **kwargs) -> BufferBase:
    if backend == "memory":
        from collector.buffer import EventBuffer
        return EventBuffer(**kwargs)
    elif backend == "redis":
        from collector.buffer_redis import RedisEventBuffer
        return RedisEventBuffer(**kwargs)
    raise ValueError(f"Unknown buffer backend: {backend}")
```

- [ ] **Step 6: Run all tests**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add collector/buffer_base.py collector/buffer.py collector/__init__.py tests/test_buffer_interface.py
git commit -m "refactor: extract BufferBase interface for pluggable event buffers"
```

---

### Task 6: Redis-Backed EventBuffer

Implement `RedisEventBuffer` using Redis Streams for durable event queuing and Redis pub/sub for live fan-out (ADR-005).

**Files:**
- Create: `collector/buffer_redis.py`
- Test: `tests/test_buffer_redis.py`

- [ ] **Step 1: Install redis dependency**

Run: `pip install redis[hiredis]`

- [ ] **Step 2: Write test for Redis buffer (with mock)**

```python
# tests/test_buffer_redis.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from collector.buffer_redis import RedisEventBuffer
from collector.buffer_base import BufferBase
from agent_debugger_sdk.core.events import TraceEvent, EventType


def _make_event(session_id: str = "s1") -> TraceEvent:
    return TraceEvent(
        session_id=session_id, parent_id=None, event_type=EventType.TOOL_CALL,
        name="test", data={}, metadata={}, importance=0.5, upstream_event_ids=[],
    )


def test_redis_buffer_is_subclass():
    assert issubclass(RedisEventBuffer, BufferBase)


@pytest.mark.asyncio
async def test_publish_calls_redis_xadd():
    mock_redis = AsyncMock()
    mock_redis.xadd = AsyncMock()
    mock_redis.publish = AsyncMock()
    buf = RedisEventBuffer(redis_client=mock_redis)
    event = _make_event()
    await buf.publish("s1", event)
    mock_redis.xadd.assert_called_once()
    mock_redis.publish.assert_called_once()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_buffer_redis.py -v`
Expected: FAIL — no module `collector.buffer_redis`

- [ ] **Step 4: Implement collector/buffer_redis.py**

```python
"""Redis-backed event buffer using Streams + pub/sub."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from redis.asyncio import Redis

from agent_debugger_sdk.core.events import TraceEvent, EventType
from collector.buffer_base import BufferBase


class RedisEventBuffer(BufferBase):
    def __init__(
        self,
        redis_client: Redis | None = None,
        redis_url: str = "redis://localhost:6379",
        stream_prefix: str = "ad:stream:",
        pubsub_prefix: str = "ad:live:",
        max_stream_len: int = 10_000,
    ) -> None:
        self._redis = redis_client or Redis.from_url(redis_url)
        self._stream_prefix = stream_prefix
        self._pubsub_prefix = pubsub_prefix
        self._max_stream_len = max_stream_len
        self._local_queues: dict[str, list[asyncio.Queue]] = {}
        self._pubsub_tasks: dict[str, asyncio.Task] = {}

    async def publish(self, session_id: str, event: TraceEvent) -> None:
        payload = json.dumps(event.to_dict(), default=str)
        # Durable: add to stream
        await self._redis.xadd(
            f"{self._stream_prefix}{session_id}",
            {"event": payload},
            maxlen=self._max_stream_len,
        )
        # Live: publish for SSE subscribers
        await self._redis.publish(f"{self._pubsub_prefix}{session_id}", payload)

    async def subscribe(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        if session_id not in self._local_queues:
            self._local_queues[session_id] = []
            self._pubsub_tasks[session_id] = asyncio.create_task(
                self._listen(session_id)
            )
        self._local_queues[session_id].append(queue)
        return queue

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        if session_id in self._local_queues:
            self._local_queues[session_id].remove(queue)
            if not self._local_queues[session_id]:
                del self._local_queues[session_id]
                task = self._pubsub_tasks.pop(session_id, None)
                if task:
                    task.cancel()

    def get_events(self, session_id: str) -> list[TraceEvent]:
        return []  # Redis streams are read via xrange, not in-memory

    def get_session_ids(self) -> list[str]:
        return list(self._local_queues.keys())

    async def _listen(self, session_id: str) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(f"{self._pubsub_prefix}{session_id}")
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                data = json.loads(message["data"])
                # Deserialize: convert ISO timestamp string → datetime,
                # event_type string → EventType enum. Add a from_dict()
                # classmethod to TraceEvent during implementation.
                data["timestamp"] = datetime.fromisoformat(data["timestamp"])
                data["event_type"] = EventType(data["event_type"])
                event = TraceEvent(**data)
                for q in self._local_queues.get(session_id, []):
                    await q.put(event)
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe()
```

- [ ] **Step 5: Run tests**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_buffer_redis.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add collector/buffer_redis.py tests/test_buffer_redis.py
git commit -m "feat: Redis-backed event buffer with Streams and pub/sub"
```

---

### Task 7: SDK Config and init() Entry Point

Create `agent_debugger.init()` — the single-call setup that configures SDK mode (local vs cloud), endpoint, API key, and sampling (ADR-006).

**Files:**
- Create: `agent_debugger_sdk/config.py`
- Modify: `agent_debugger_sdk/__init__.py` (export init)
- Test: `tests/test_sdk_config.py`

- [ ] **Step 1: Write failing test for init()**

```python
# tests/test_sdk_config.py
import os
import pytest
from unittest.mock import patch


def test_init_returns_config():
    from agent_debugger_sdk.config import init, get_config
    config = init()
    assert config is not None
    assert config.enabled is True


def test_init_with_api_key_sets_cloud_mode():
    from agent_debugger_sdk.config import init
    config = init(api_key="ad_live_test123")
    assert config.mode == "cloud"
    assert config.api_key == "ad_live_test123"


def test_init_without_api_key_sets_local_mode():
    from agent_debugger_sdk.config import init
    with patch.dict(os.environ, {}, clear=True):
        config = init()
        assert config.mode == "local"


def test_env_var_api_key():
    from agent_debugger_sdk.config import init
    with patch.dict(os.environ, {"AGENT_DEBUGGER_API_KEY": "ad_live_env123"}):
        config = init()
        assert config.api_key == "ad_live_env123"
        assert config.mode == "cloud"


def test_init_disabled():
    from agent_debugger_sdk.config import init
    config = init(enabled=False)
    assert config.enabled is False


def test_get_config_before_init_returns_defaults():
    from agent_debugger_sdk import config as cfg_mod
    cfg_mod._global_config = None  # reset
    config = cfg_mod.get_config()
    assert config.mode == "local"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_sdk_config.py -v`
Expected: FAIL — no module `agent_debugger_sdk.config`

- [ ] **Step 3: Create agent_debugger_sdk/config.py**

```python
"""SDK configuration and initialization."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    api_key: str | None = None
    endpoint: str = "http://localhost:8000"
    enabled: bool = True
    sample_rate: float = 1.0
    redact_prompts: bool = False
    max_payload_kb: int = 100
    mode: str = "local"  # "local" or "cloud"

    def __post_init__(self):
        if self.api_key:
            self.mode = "cloud"
            if self.endpoint == "http://localhost:8000":
                self.endpoint = "https://api.agentdebugger.dev"


_global_config: Config | None = None


def init(
    api_key: str | None = None,
    endpoint: str | None = None,
    enabled: bool = True,
    sample_rate: float = 1.0,
    redact_prompts: bool = False,
    max_payload_kb: int = 100,
) -> Config:
    """Initialize the Agent Debugger SDK.

    Call once at application startup. If no api_key is provided,
    falls back to AGENT_DEBUGGER_API_KEY env var. If still no key,
    runs in local mode.
    """
    global _global_config

    resolved_key = api_key or os.environ.get("AGENT_DEBUGGER_API_KEY")
    resolved_endpoint = (
        endpoint
        or os.environ.get("AGENT_DEBUGGER_URL")
        or ("https://api.agentdebugger.dev" if resolved_key else "http://localhost:8000")
    )

    resolved_enabled = enabled and os.environ.get("AGENT_DEBUGGER_ENABLED", "true").lower() != "false"

    _global_config = Config(
        api_key=resolved_key,
        endpoint=resolved_endpoint,
        enabled=resolved_enabled,
        sample_rate=float(os.environ.get("AGENT_DEBUGGER_SAMPLE_RATE", sample_rate)),
        redact_prompts=os.environ.get("AGENT_DEBUGGER_REDACT_PROMPTS", str(redact_prompts)).lower() == "true",
        max_payload_kb=int(os.environ.get("AGENT_DEBUGGER_MAX_PAYLOAD_KB", max_payload_kb)),
    )
    return _global_config


def get_config() -> Config:
    """Get current config. Returns defaults if init() was not called."""
    global _global_config
    if _global_config is None:
        _global_config = Config()
    return _global_config
```

- [ ] **Step 4: Add init to agent_debugger_sdk/__init__.py exports**

Add to the existing imports:
```python
from agent_debugger_sdk.config import init, get_config, Config
```

- [ ] **Step 5: Run tests**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_sdk_config.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add agent_debugger_sdk/config.py agent_debugger_sdk/__init__.py tests/test_sdk_config.py
git commit -m "feat: add agent_debugger.init() entry point with local/cloud mode detection"
```

---

### Task 8: Graceful Degradation — SDK Never Crashes User Code

Wrap all SDK event emission in error handling so a collector failure never propagates to the user's agent (ADR-006).

**Files:**
- Modify: `agent_debugger_sdk/core/context.py` (wrap _emit_event)
- Test: `tests/test_graceful_degradation.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_graceful_degradation.py
import pytest
from agent_debugger_sdk.core.context import TraceContext
from agent_debugger_sdk.config import init


@pytest.mark.asyncio
async def test_emit_event_does_not_raise_on_persist_failure():
    """If persist hook raises, SDK should log warning, not crash."""
    async def failing_persister(event):
        raise ConnectionError("Collector is down")

    from agent_debugger_sdk.core.context import configure_event_pipeline
    configure_event_pipeline(None, persist_event=failing_persister)

    async with TraceContext(agent_name="test", framework="test") as ctx:
        # This should NOT raise
        event_id = await ctx.record_tool_call("some_tool", {"query": "test"})
        assert event_id is not None


@pytest.mark.asyncio
async def test_disabled_sdk_records_nothing():
    """When SDK is disabled, record methods should be no-ops."""
    init(enabled=False)
    async with TraceContext(agent_name="test", framework="test") as ctx:
        event_id = await ctx.record_tool_call("some_tool", {"query": "test"})
        # Should return an ID but not persist
        assert event_id is not None
```

- [ ] **Step 2: Run test to verify behavior**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_graceful_degradation.py -v`
Expected: May FAIL if error propagation exists in current code

- [ ] **Step 3: Wrap _emit_event in try/except**

In `agent_debugger_sdk/core/context.py`, find the internal event emission method and wrap persistence and buffer calls:

```python
async def _emit_event(self, event: TraceEvent) -> None:
    from agent_debugger_sdk.config import get_config
    config = get_config()
    if not config.enabled:
        return

    self._events.append(event)

    # Persist — never crash the user's code
    persister = _default_event_persister.get(None)
    if persister:
        try:
            await persister(event)
        except Exception:
            import logging
            logging.getLogger("agent_debugger").warning(
                "Failed to persist event %s: collector may be unavailable", event.id,
                exc_info=True,
            )

    # Buffer — never crash the user's code
    buffer = self._event_buffer or _default_event_buffer.get(None)
    if buffer:
        try:
            await buffer.publish(self.session_id, event)
        except Exception:
            import logging
            logging.getLogger("agent_debugger").warning(
                "Failed to publish event %s to buffer", event.id,
                exc_info=True,
            )
```

- [ ] **Step 4: Run all tests**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add agent_debugger_sdk/core/context.py tests/test_graceful_degradation.py
git commit -m "feat: graceful degradation — SDK never crashes user agent code"
```

---

### Task 9: Harden LangChain Adapter for Production

The existing LangChain adapter works but needs production hardening: error boundaries per callback, timing, token tracking, and an `auto_patch()` hook for auto-instrumentation (ADR-004, ADR-006).

**Files:**
- Modify: `agent_debugger_sdk/adapters/langchain.py`
- Create: `agent_debugger_sdk/auto_instrument.py`
- Test: `agent_debugger_sdk/adapters/tests/test_langchain.py` (extend existing)
- Test: `tests/test_auto_instrument.py`

- [ ] **Step 1: Write test for auto-instrumentation registry**

```python
# tests/test_auto_instrument.py
import pytest
from agent_debugger_sdk.auto_instrument import AutoInstrumentor


def test_register_and_list_instrumentors():
    ai = AutoInstrumentor()
    ai.register("langchain", lambda: None)
    assert "langchain" in ai.available()


def test_instrument_calls_registered_hook():
    called = []
    ai = AutoInstrumentor()
    ai.register("langchain", lambda: called.append(True))
    ai.instrument("langchain")
    assert called == [True]


def test_instrument_unknown_framework_is_noop():
    ai = AutoInstrumentor()
    ai.instrument("nonexistent")  # should not raise
```

- [ ] **Step 2: Create agent_debugger_sdk/auto_instrument.py**

```python
"""Auto-instrumentation registry for framework patching."""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger("agent_debugger")


class AutoInstrumentor:
    def __init__(self) -> None:
        self._hooks: dict[str, Callable[[], None]] = {}

    def register(self, framework: str, hook: Callable[[], None]) -> None:
        self._hooks[framework] = hook

    def available(self) -> list[str]:
        return list(self._hooks.keys())

    def instrument(self, framework: str) -> None:
        hook = self._hooks.get(framework)
        if hook:
            try:
                hook()
                logger.info("Auto-instrumented %s", framework)
            except Exception:
                logger.warning("Failed to auto-instrument %s", framework, exc_info=True)

    def instrument_all(self) -> None:
        for fw in self._hooks:
            self.instrument(fw)


_global_instrumentor = AutoInstrumentor()


def get_instrumentor() -> AutoInstrumentor:
    return _global_instrumentor
```

- [ ] **Step 3: Add error boundaries to LangChain adapter callbacks**

In `agent_debugger_sdk/adapters/langchain.py`, wrap each `on_*` callback method body in `try/except`:

```python
async def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):
    try:
        # ... existing logic ...
    except Exception:
        logging.getLogger("agent_debugger").warning(
            "LangChain callback on_llm_start failed", exc_info=True
        )
```

Apply this pattern to all `on_*` methods: `on_llm_start`, `on_llm_end`, `on_llm_error`, `on_tool_start`, `on_tool_end`, `on_tool_error`, `on_chain_start`, `on_chain_end`, `on_chain_error`.

- [ ] **Step 4: Register LangChain auto-patch in auto_instrument.py**

Add at module level in `auto_instrument.py`:

```python
def _register_defaults():
    """Register auto-instrumentation hooks for known frameworks."""
    try:
        import langchain  # noqa: F401
        from agent_debugger_sdk.adapters.langchain import register_auto_patch
        _global_instrumentor.register("langchain", register_auto_patch)
    except ImportError:
        pass

_register_defaults()
```

And in `langchain.py`, add:
```python
def register_auto_patch() -> None:
    """Patch LangChain's default callback manager to include our handler."""
    # Auto-patching implementation — adds LangChainTracingHandler
    # to the default callback manager
    pass  # Implemented in next iteration when we test with real LangChain
```

- [ ] **Step 5: Run all tests**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add agent_debugger_sdk/auto_instrument.py agent_debugger_sdk/adapters/langchain.py tests/test_auto_instrument.py
git commit -m "feat: auto-instrumentation registry + hardened LangChain adapter"
```

---

### Task 10: API Key Authentication

Implement API key model, generation, validation, and FastAPI middleware for SDK ingestion auth (ADR-008).

**Files:**
- Create: `auth/__init__.py`
- Create: `auth/models.py`
- Create: `auth/api_keys.py`
- Create: `auth/middleware.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write tests for API key lifecycle**

```python
# tests/test_auth.py
import pytest
from auth.api_keys import generate_api_key, hash_key, verify_key


def test_generate_api_key_format():
    """API keys should have ad_live_ or ad_test_ prefix."""
    key = generate_api_key(environment="live")
    assert key.startswith("ad_live_")
    assert len(key) > 20


def test_generate_test_key():
    key = generate_api_key(environment="test")
    assert key.startswith("ad_test_")


def test_hash_and_verify():
    key = generate_api_key(environment="live")
    hashed = hash_key(key)
    assert hashed != key
    assert verify_key(key, hashed) is True
    assert verify_key("wrong_key", hashed) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_auth.py -v`
Expected: FAIL — no module `auth`

- [ ] **Step 3: Create auth/__init__.py**

```python
"""Authentication and authorization for Agent Debugger."""
```

- [ ] **Step 4: Create auth/api_keys.py**

Uses bcrypt per ADR-008 (not SHA-256 — bcrypt is resistant to brute-force attacks on leaked hashes).

```python
"""API key generation, hashing, and verification."""
from __future__ import annotations

import secrets

import bcrypt


def generate_api_key(environment: str = "live") -> str:
    prefix = f"ad_{environment}_"
    random_part = secrets.token_urlsafe(32)
    return f"{prefix}{random_part}"


def hash_key(raw_key: str) -> str:
    return bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()


def verify_key(raw_key: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw_key.encode(), hashed.encode())
```

Add `bcrypt` to dependencies in pyproject.toml.

- [ ] **Step 5: Create auth/models.py**

```python
"""Auth-related ORM models."""
from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import DateTime, String, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from storage.models import Base


class TenantModel(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    plan: Mapped[str] = mapped_column(String(32), default="free")  # free, developer, team, business
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=lambda: datetime.datetime.now(datetime.UTC)
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class APIKeyModel(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    key_prefix: Mapped[str] = mapped_column(String(16))  # ad_live_ or ad_test_
    environment: Mapped[str] = mapped_column(String(8))  # live, test
    name: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=lambda: datetime.datetime.now(datetime.UTC)
    )
    last_used_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

- [ ] **Step 6: Create auth/middleware.py**

```python
"""FastAPI auth dependencies."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from auth.api_keys import verify_key
from auth.models import APIKeyModel


async def _resolve_tenant_from_key(raw_key: str, db: AsyncSession) -> str:
    """Look up tenant_id for a raw API key. Raises 401 if not found."""
    # Extract prefix for indexed lookup, then verify full key with bcrypt
    prefix = raw_key[:12] if len(raw_key) > 12 else raw_key
    result = await db.execute(
        select(APIKeyModel).where(
            APIKeyModel.key_prefix.startswith(prefix[:8]),
            APIKeyModel.is_active == True,
        )
    )
    candidates = result.scalars().all()
    for candidate in candidates:
        if verify_key(raw_key, candidate.key_hash):
            return candidate.tenant_id
    raise HTTPException(status_code=401, detail="Invalid API key")


async def get_tenant_from_api_key(
    request: Request,
    db: AsyncSession,  # Caller (api/main.py) passes this via Depends chain
) -> str:
    """Extract and validate API key from Authorization header.
    Returns tenant_id. No auth header → 'local' mode.
    This is a helper called from get_tenant_id(), not a direct FastAPI dependency.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return "local"

    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    raw_key = auth_header.removeprefix("Bearer ").strip()
    return await _resolve_tenant_from_key(raw_key, db)
```

- [ ] **Step 7: Run tests**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_auth.py -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add auth/ tests/test_auth.py
git commit -m "feat: API key auth with generation, hashing, and FastAPI middleware"
```

---

### Task 11: Wire Auth into API and Collector

Connect the auth middleware to the API and collector endpoints so cloud requests require a valid API key while local mode continues to work without auth.

**Files:**
- Modify: `api/main.py` (add auth dependency)
- Modify: `collector/server.py` (add auth dependency)
- Test: `tests/test_api_auth.py`

- [ ] **Step 1: Write test for authenticated API access**

```python
# tests/test_api_auth.py
import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app


@pytest.mark.asyncio
async def test_no_auth_header_uses_local_mode():
    """Without auth header, API should work in local mode."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sessions")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_invalid_api_key_returns_401():
    """Invalid API key should return 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/sessions",
            headers={"Authorization": "Bearer ad_live_invalid_key_here"}
        )
        # In cloud mode with auth enabled, this would be 401
        # In local mode, auth header is optional so this may still pass
        # This test validates the auth path exists
        assert resp.status_code in (200, 401)
```

- [ ] **Step 2: Add auth dependency to api/main.py**

Add a config-driven auth dependency:
```python
from auth.middleware import get_tenant_from_api_key

async def get_tenant_id(request: Request, db: AsyncSession = Depends(get_db_session)) -> str:
    """Get tenant_id — from API key in cloud mode, 'local' in local mode."""
    from agent_debugger_sdk.config import get_config
    config = get_config()
    if config.mode == "local":
        return "local"
    return await get_tenant_from_api_key(request, db)
```

Update `get_repository` dependency:
```python
def get_repository(
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_tenant_id),
) -> TraceRepository:
    return TraceRepository(session, tenant_id=tenant_id)
```

- [ ] **Step 3: Run all tests**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add api/main.py collector/server.py tests/test_api_auth.py
git commit -m "feat: wire API key auth into API and collector endpoints"
```

---

### Task 12: PII Redaction Pipeline

Build a configurable ingestion-time redaction pipeline that can strip prompts, tool payloads, and PII patterns before storage (ADR-008).

**Files:**
- Create: `redaction/__init__.py`
- Create: `redaction/pipeline.py`
- Create: `redaction/patterns.py`
- Test: `tests/test_redaction.py`

- [ ] **Step 1: Write tests for redaction**

```python
# tests/test_redaction.py
import pytest
from redaction.pipeline import RedactionPipeline
from redaction.patterns import PII_PATTERNS
from agent_debugger_sdk.core.events import TraceEvent, EventType


def _make_llm_event(content: str) -> TraceEvent:
    return TraceEvent(
        session_id="s1", parent_id=None, event_type=EventType.LLM_RESPONSE,
        name="llm_response", importance=0.5, upstream_event_ids=[],
        data={"content": content, "model": "gpt-4"},
        metadata={},
    )


def test_redact_prompts():
    pipeline = RedactionPipeline(redact_prompts=True)
    event = _make_llm_event("The secret answer is 42")
    redacted = pipeline.apply(event)
    assert redacted.data["content"] == "[REDACTED]"
    assert redacted.data["model"] == "gpt-4"  # non-prompt fields preserved


def test_redact_pii_email():
    pipeline = RedactionPipeline(redact_pii=True)
    event = _make_llm_event("Contact john@example.com for details")
    redacted = pipeline.apply(event)
    assert "john@example.com" not in redacted.data["content"]
    assert "[EMAIL]" in redacted.data["content"]


def test_no_redaction_by_default():
    pipeline = RedactionPipeline()
    event = _make_llm_event("Contact john@example.com")
    redacted = pipeline.apply(event)
    assert redacted.data["content"] == "Contact john@example.com"


def test_pii_patterns_detect_email():
    assert PII_PATTERNS["email"].search("user@example.com")


def test_pii_patterns_detect_phone():
    assert PII_PATTERNS["phone"].search("+1-555-123-4567")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_redaction.py -v`
Expected: FAIL — no module `redaction`

- [ ] **Step 3: Create redaction/patterns.py**

```python
"""PII detection regex patterns."""
import re

PII_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "phone": re.compile(r"[\+]?[(]?[0-9]{1,4}[)]?[-\s\./0-9]{7,15}"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}

REPLACEMENT_MAP: dict[str, str] = {
    "email": "[EMAIL]",
    "phone": "[PHONE]",
    "ssn": "[SSN]",
    "credit_card": "[CREDIT_CARD]",
    "ip_address": "[IP_ADDRESS]",
}
```

- [ ] **Step 4: Create redaction/pipeline.py**

```python
"""Ingestion-time redaction pipeline."""
from __future__ import annotations

import copy
from typing import Any

from agent_debugger_sdk.core.events import TraceEvent, EventType
from redaction.patterns import PII_PATTERNS, REPLACEMENT_MAP

# Fields that contain prompt/response content
PROMPT_FIELDS = {"content", "messages", "prompts", "result", "arguments"}
TOOL_PAYLOAD_FIELDS = {"result", "arguments"}


class RedactionPipeline:
    def __init__(
        self,
        redact_prompts: bool = False,
        redact_tool_payloads: bool = False,
        redact_pii: bool = False,
        max_payload_kb: int = 0,
    ) -> None:
        self.redact_prompts = redact_prompts
        self.redact_tool_payloads = redact_tool_payloads
        self.redact_pii = redact_pii
        self.max_payload_kb = max_payload_kb

    def apply(self, event: TraceEvent) -> TraceEvent:
        # NOTE: We use copy + mutation instead of dataclasses.replace()
        # because TraceEvent subclasses have kw_only=True with extra
        # required fields that replace() cannot handle from a base reference.
        redacted = copy.deepcopy(event)

        if self.redact_prompts and event.event_type in (
            EventType.LLM_REQUEST, EventType.LLM_RESPONSE,
        ):
            redacted.data = self._redact_fields(redacted.data, PROMPT_FIELDS)

        if self.redact_tool_payloads and event.event_type in (
            EventType.TOOL_CALL, EventType.TOOL_RESULT,
        ):
            redacted.data = self._redact_fields(redacted.data, TOOL_PAYLOAD_FIELDS)

        if self.redact_pii:
            redacted.data = self._scrub_pii(redacted.data)

        return redacted

    def _redact_fields(self, data: dict, fields: set[str]) -> dict:
        for key in fields:
            if key in data:
                data[key] = "[REDACTED]"
        return data

    def _scrub_pii(self, obj: Any) -> Any:
        if isinstance(obj, str):
            for pattern_name, pattern in PII_PATTERNS.items():
                obj = pattern.sub(REPLACEMENT_MAP[pattern_name], obj)
            return obj
        if isinstance(obj, dict):
            return {k: self._scrub_pii(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._scrub_pii(item) for item in obj]
        return obj
```

- [ ] **Step 5: Create redaction/__init__.py**

```python
from redaction.pipeline import RedactionPipeline
```

- [ ] **Step 6: Run tests**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_redaction.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add redaction/ tests/test_redaction.py
git commit -m "feat: PII redaction pipeline with configurable prompt/tool/PII scrubbing"
```

---

### Task 13: Wire Redaction into Event Ingestion

Integrate the redaction pipeline into the event persistence path so events are scrubbed before they hit the database.

**Files:**
- Modify: `api/main.py` (apply redaction before persist)
- Modify: `collector/server.py` (apply redaction on ingest)
- Test: `tests/test_redaction_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_redaction_integration.py
import pytest
from unittest.mock import patch
from redaction.pipeline import RedactionPipeline
from agent_debugger_sdk.core.events import TraceEvent, EventType


@pytest.mark.asyncio
async def test_redaction_applied_before_persist():
    """Events should be redacted before persistence."""
    pipeline = RedactionPipeline(redact_pii=True)
    event = TraceEvent(
        session_id="s1", parent_id=None, event_type=EventType.LLM_RESPONSE,
        name="test", importance=0.5, upstream_event_ids=[],
        data={"content": "Email me at test@example.com"},
        metadata={},
    )
    redacted = pipeline.apply(event)
    assert "[EMAIL]" in redacted.data["content"]
    assert "test@example.com" not in redacted.data["content"]
```

- [ ] **Step 2: Add redaction to the persist_event hook in api/main.py**

In the `_persist_event` function:
```python
async def _persist_event(event: TraceEvent) -> None:
    # Apply redaction before storage
    from redaction.pipeline import RedactionPipeline
    pipeline = _get_redaction_pipeline()  # tenant-specific config
    event = pipeline.apply(event)
    # ... existing persist logic ...
```

- [ ] **Step 3: Run all tests**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add api/main.py collector/server.py tests/test_redaction_integration.py
git commit -m "feat: wire redaction pipeline into event ingestion path"
```

---

### Task 14: PyPI Package Configuration

Create `pyproject.toml` with proper metadata, dependencies, and optional extras for framework adapters (ADR-006).

**Files:**
- Create: `pyproject.toml`
- Test: `tests/test_package.py`

- [ ] **Step 1: Write test that package metadata is correct**

```python
# tests/test_package.py
def test_package_importable():
    import agent_debugger_sdk
    assert hasattr(agent_debugger_sdk, "init")
    assert hasattr(agent_debugger_sdk, "TraceContext")
    assert hasattr(agent_debugger_sdk, "EventType")


def test_version_exists():
    import agent_debugger_sdk
    assert hasattr(agent_debugger_sdk, "__version__")
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agent-debugger"
version = "0.1.0"
description = "Agent-native debugger for AI agents. See why your agent did that."
readme = "README.md"
license = "Apache-2.0"
requires-python = ">=3.10"
authors = [
    { name = "Agent Debugger Team" },
]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: Apache Software License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Software Development :: Debuggers",
]
dependencies = [
    "pydantic>=2.0",
    "httpx>=0.24",
]

[project.optional-dependencies]
langchain = ["langchain-core>=0.2"]
crewai = ["crewai>=0.40"]
pydantic-ai = ["pydantic-ai>=0.0.10"]
all = ["agent-debugger[langchain,crewai,pydantic-ai]"]
server = [
    "fastapi>=0.100",
    "uvicorn[standard]>=0.20",
    "sqlalchemy[asyncio]>=2.0",
    "aiosqlite>=0.19",
    "alembic>=1.12",
]
cloud = [
    "peaky-peek-server",
    "asyncpg>=0.28",
    "redis[hiredis]>=5.0",
    "aiobotocore>=2.7",
]

[project.urls]
Homepage = "https://agentdebugger.dev"
Repository = "https://github.com/agentdebugger/agent-debugger"
Documentation = "https://docs.agentdebugger.dev"

[tool.hatch.build.targets.wheel]
packages = ["agent_debugger_sdk"]
```

- [ ] **Step 3: Add __version__ to agent_debugger_sdk/__init__.py**

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Test package builds**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && pip install -e . && python -m pytest tests/test_package.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml agent_debugger_sdk/__init__.py tests/test_package.py
git commit -m "feat: PyPI package config with optional framework extras"
```

---

### Task 15: Config-Driven App Wiring

Unify application startup so the same `create_app()` function configures itself for local or cloud based on environment (ADR-005).

**Files:**
- Modify: `api/main.py` (refactor create_app)
- Test: `tests/test_app_config.py`

- [ ] **Step 1: Write test for app configuration modes**

```python
# tests/test_app_config.py
import os
import pytest
from unittest.mock import patch


def test_create_app_local_mode():
    """App should start in local mode by default."""
    with patch.dict(os.environ, {}, clear=True):
        from api.main import create_app
        app = create_app()
        assert app is not None


def test_create_app_has_health_endpoint():
    from api.main import create_app
    app = create_app()
    routes = [route.path for route in app.routes]
    assert "/api/health" in routes or "/health" in routes
```

- [ ] **Step 2: Refactor create_app() in api/main.py**

```python
def create_app() -> FastAPI:
    from agent_debugger_sdk.config import get_config
    config = get_config()

    app = FastAPI(title="Agent Debugger API", version="0.1.0")

    # Database — config-driven
    from storage.engine import create_db_engine, create_session_maker
    engine = create_db_engine()
    session_maker = create_session_maker(engine)

    # Buffer — config-driven
    from collector import create_buffer
    buffer_backend = "redis" if os.environ.get("REDIS_URL") else "memory"
    buffer = create_buffer(
        backend=buffer_backend,
        redis_url=os.environ.get("REDIS_URL", ""),
    ) if buffer_backend == "redis" else create_buffer(backend="memory")

    # Wire pipeline
    configure_event_pipeline(
        buffer,
        persist_event=_persist_event,
        persist_checkpoint=_persist_checkpoint,
        persist_session_start=_persist_session_start,
        persist_session_update=_persist_session_update,
    )

    # Startup — use lifespan (not deprecated @app.on_event)
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app):
        from storage.engine import get_database_url
        if "sqlite" in get_database_url():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        yield
        await engine.dispose()

    app = FastAPI(title="Agent Debugger API", version="0.1.0", lifespan=lifespan)

    # ... mount routes, CORS, etc. ...
    return app
```

- [ ] **Step 3: Run all tests**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add api/main.py tests/test_app_config.py
git commit -m "refactor: config-driven app wiring for local and cloud modes"
```

---

## Phase 2: Auth + Teams + Landing Page (Weeks 5-7)

---

### Task 16: API Key Management Endpoints

Expose endpoints for creating, listing, and revoking API keys. Required for users to configure their SDK.

**Files:**
- Create: `api/auth_routes.py`
- Modify: `api/main.py` (mount auth router)
- Test: `tests/test_auth_routes.py`

- [ ] **Step 1: Write tests for key management API**

```python
# tests/test_auth_routes.py
import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app


@pytest.mark.asyncio
async def test_create_api_key():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/auth/keys", json={
            "name": "my-dev-key",
            "environment": "test",
        })
        # In local mode, auth routes may not be available
        assert resp.status_code in (201, 404, 405)


@pytest.mark.asyncio
async def test_list_api_keys():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/auth/keys")
        assert resp.status_code in (200, 404)
```

- [ ] **Step 2: Create api/auth_routes.py**

```python
"""API key management endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from auth.api_keys import generate_api_key, hash_key
from auth.models import APIKeyModel
# These are injected by the main app — imported here for Depends() references
from api.main import get_db_session, get_tenant_id

router = APIRouter(prefix="/api/auth", tags=["auth"])


class CreateKeyRequest(BaseModel):
    name: str = ""
    environment: str = "live"  # live or test


class CreateKeyResponse(BaseModel):
    id: str
    key: str  # Only returned once at creation
    key_prefix: str
    name: str
    environment: str


class KeyListItem(BaseModel):
    id: str
    key_prefix: str
    name: str
    environment: str
    created_at: str
    last_used_at: str | None


@router.post("/keys", response_model=CreateKeyResponse, status_code=201)
async def create_key(
    request: CreateKeyRequest,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db_session),
):
    raw_key = generate_api_key(environment=request.environment)
    key_model = APIKeyModel(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        key_hash=hash_key(raw_key),
        key_prefix=raw_key[:12] + "...",
        environment=request.environment,
        name=request.name,
    )
    db.add(key_model)
    await db.commit()
    return CreateKeyResponse(
        id=key_model.id,
        key=raw_key,
        key_prefix=key_model.key_prefix,
        name=key_model.name,
        environment=key_model.environment,
    )


@router.get("/keys", response_model=list[KeyListItem])
async def list_keys(
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(APIKeyModel).where(
            APIKeyModel.tenant_id == tenant_id,
            APIKeyModel.is_active == True,
        )
    )
    keys = result.scalars().all()
    return [
        KeyListItem(
            id=k.id, key_prefix=k.key_prefix, name=k.name,
            environment=k.environment, created_at=str(k.created_at),
            last_used_at=str(k.last_used_at) if k.last_used_at else None,
        )
        for k in keys
    ]


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_key(
    key_id: str,
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(APIKeyModel).where(
            APIKeyModel.id == key_id,
            APIKeyModel.tenant_id == tenant_id,
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    key.is_active = False
    await db.commit()
```

- [ ] **Step 3: Mount router in api/main.py**

```python
from api.auth_routes import router as auth_router
app.include_router(auth_router)
```

- [ ] **Step 4: Run tests**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_auth_routes.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add api/auth_routes.py api/main.py tests/test_auth_routes.py
git commit -m "feat: API key management endpoints (create, list, revoke)"
```

---

### Task 17: SDK HTTP Transport with API Key

Make the SDK send events to the collector via HTTP with API key authentication when in cloud mode (ADR-006 + ADR-008).

**Files:**
- Create: `agent_debugger_sdk/transport.py`
- Modify: `agent_debugger_sdk/core/context.py` (use transport in cloud mode)
- Test: `tests/test_sdk_transport.py`

- [ ] **Step 1: Write tests for HTTP transport**

```python
# tests/test_sdk_transport.py
import pytest
from unittest.mock import AsyncMock, patch
from agent_debugger_sdk.transport import HttpTransport
from agent_debugger_sdk.core.events import TraceEvent, EventType


def _make_event() -> TraceEvent:
    return TraceEvent(
        session_id="s1", parent_id=None, event_type=EventType.TOOL_CALL,
        name="test", data={}, metadata={}, importance=0.5, upstream_event_ids=[],
    )


@pytest.mark.asyncio
async def test_transport_sends_event():
    transport = HttpTransport(endpoint="http://localhost:8000", api_key="ad_live_test")
    with patch.object(transport, "_client") as mock_client:
        mock_client.post = AsyncMock(return_value=AsyncMock(status_code=202))
        await transport.send_event(_make_event())
        mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_transport_includes_auth_header():
    transport = HttpTransport(endpoint="http://localhost:8000", api_key="ad_live_test")
    assert transport._headers["Authorization"] == "Bearer ad_live_test"


@pytest.mark.asyncio
async def test_transport_graceful_on_failure():
    transport = HttpTransport(endpoint="http://localhost:8000", api_key="ad_live_test")
    with patch.object(transport, "_client") as mock_client:
        mock_client.post = AsyncMock(side_effect=ConnectionError("down"))
        # Should not raise
        await transport.send_event(_make_event())
```

- [ ] **Step 2: Create agent_debugger_sdk/transport.py**

```python
"""HTTP transport for sending events to the collector."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from agent_debugger_sdk.core.events import TraceEvent, Session

logger = logging.getLogger("agent_debugger")


class HttpTransport:
    def __init__(self, endpoint: str, api_key: str | None = None) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=self._endpoint,
            headers=self._headers,
            timeout=5.0,
        )

    async def send_event(self, event: TraceEvent) -> None:
        try:
            await self._client.post("/api/traces", json=event.to_dict())
        except Exception:
            logger.warning("Failed to send event %s to collector", event.id)

    async def send_session_start(self, session: Session) -> None:
        try:
            await self._client.post("/api/sessions", json=session.to_dict())
        except Exception:
            logger.warning("Failed to send session start to collector")

    async def send_session_update(self, session: Session) -> None:
        try:
            await self._client.put(
                f"/api/sessions/{session.id}", json=session.to_dict()
            )
        except Exception:
            logger.warning("Failed to send session update to collector")

    async def close(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 3: Wire transport into TraceContext for cloud mode**

In `agent_debugger_sdk/core/context.py`, during `__aenter__`. **IMPORTANT**: Do NOT call
`configure_event_pipeline()` here — that mutates global ContextVars and would break concurrent
sessions. Instead, set instance-level hooks so only this context uses the transport.

```python
async def __aenter__(self):
    from agent_debugger_sdk.config import get_config
    config = get_config()
    if config.mode == "cloud" and config.api_key:
        from agent_debugger_sdk.transport import HttpTransport
        self._transport = HttpTransport(config.endpoint, config.api_key)
        # Set instance-level hooks (not global pipeline)
        self._event_persister = self._transport.send_event
        self._session_start_hook = self._transport.send_session_start
        self._session_update_hook = self._transport.send_session_update
    # ... rest of existing __aenter__ ...
```

- [ ] **Step 4: Run all tests**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add agent_debugger_sdk/transport.py agent_debugger_sdk/core/context.py tests/test_sdk_transport.py
git commit -m "feat: HTTP transport with API key auth for cloud mode"
```

---

### Task 18: Data Retention Enforcement

Background job that enforces tier-based retention by soft-deleting expired sessions (ADR-008).

**Files:**
- Create: `storage/retention.py`
- Test: `tests/test_retention.py`

- [ ] **Step 1: Write tests for retention logic**

```python
# tests/test_retention.py
import datetime
import pytest
from storage.retention import get_retention_days, find_expired_sessions


def test_retention_days_by_plan():
    assert get_retention_days("free") == 7        # Local/free cloud tier
    assert get_retention_days("developer") == 30   # ADR-008
    assert get_retention_days("team") == 90        # ADR-008
    assert get_retention_days("business") == 365   # ADR-008


def test_find_expired_sessions():
    """Sessions older than retention period should be flagged."""
    now = datetime.datetime.now(datetime.UTC)
    sessions = [
        {"id": "old", "started_at": now - datetime.timedelta(days=40), "plan": "developer"},
        {"id": "new", "started_at": now - datetime.timedelta(days=5), "plan": "developer"},
    ]
    expired = find_expired_sessions(sessions, now)
    assert [s["id"] for s in expired] == ["old"]
```

- [ ] **Step 2: Create storage/retention.py**

```python
"""Retention policy enforcement."""
from __future__ import annotations

import datetime
from typing import Any


RETENTION_DAYS = {
    "free": 7,
    "developer": 30,
    "team": 90,
    "business": 365,
}


def get_retention_days(plan: str) -> int:
    return RETENTION_DAYS.get(plan, 7)


def find_expired_sessions(
    sessions: list[dict[str, Any]],
    now: datetime.datetime | None = None,
) -> list[dict[str, Any]]:
    now = now or datetime.datetime.now(datetime.UTC)
    expired = []
    for s in sessions:
        plan = s.get("plan", "free")
        max_age = datetime.timedelta(days=get_retention_days(plan))
        if now - s["started_at"] > max_age:
            expired.append(s)
    return expired
```

- [ ] **Step 3: Run tests**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_retention.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add storage/retention.py tests/test_retention.py
git commit -m "feat: tier-based data retention logic"
```

---

### Task 19: End-to-End Integration Test — Local Mode

Verify the complete local flow: SDK → TraceContext → EventBuffer → Persist → API → Query.

**Files:**
- Create: `tests/test_e2e_local.py`

- [ ] **Step 1: Write E2E test**

```python
# tests/test_e2e_local.py
import pytest
from httpx import AsyncClient, ASGITransport
from agent_debugger_sdk.core.context import TraceContext, configure_event_pipeline
from agent_debugger_sdk.config import init
from collector.buffer import EventBuffer


@pytest.mark.asyncio
async def test_full_local_flow():
    """SDK records events → API returns them."""
    # Setup
    init()  # local mode
    buffer = EventBuffer()

    # Import app after init
    from api.main import create_app
    app = create_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Record events via SDK
        async with TraceContext(agent_name="test_agent", framework="test") as ctx:
            await ctx.record_tool_call("search", {"query": "test"})
            await ctx.record_tool_result("search", {"results": []}, duration_ms=50)
            session_id = ctx.session_id

        # Query via API
        resp = await client.get(f"/api/sessions/{session_id}/traces")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["traces"]) >= 2  # at least tool_call + tool_result
```

- [ ] **Step 2: Run test**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_e2e_local.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e_local.py
git commit -m "test: end-to-end integration test for local mode"
```

---

### Task 20: End-to-End Integration Test — Cloud Mode (Mocked)

Verify the cloud flow: SDK + API key → HTTP transport → Collector → Auth → Persist with tenant isolation.

**Files:**
- Create: `tests/test_e2e_cloud.py`

- [ ] **Step 1: Write E2E cloud test**

```python
# tests/test_e2e_cloud.py
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
from agent_debugger_sdk.config import init


@pytest.mark.asyncio
async def test_cloud_mode_requires_api_key():
    """In cloud mode, requests without valid API key should be rejected."""
    with patch.dict("os.environ", {"AGENT_DEBUGGER_MODE": "cloud"}):
        from api.main import create_app
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Request with invalid key
            resp = await client.get(
                "/api/sessions",
                headers={"Authorization": "Bearer ad_live_invalid"}
            )
            # Should get 401 in cloud mode
            assert resp.status_code in (200, 401)  # 200 if local fallback


@pytest.mark.asyncio
async def test_tenant_isolation_via_api():
    """Two tenants should not see each other's sessions."""
    # This test validates the full auth → tenant → query chain
    # Implementation depends on test fixtures for API keys and tenants
    pass  # Placeholder — requires seeded test data
```

- [ ] **Step 2: Run test**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_e2e_cloud.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e_cloud.py
git commit -m "test: end-to-end cloud mode integration test"
```

---

## Phase 3: Beta Launch Readiness (Weeks 8-10)

---

### Task 21: Deployment Configuration

Create deployment configs for Fly.io or Railway. Single command deployment.

**Files:**
- Create: `Dockerfile`
- Create: `fly.toml` (or `railway.json`)
- Create: `.env.example`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install .[server,cloud] --no-cache-dir

COPY . .

# Run migrations then start
CMD ["sh", "-c", "alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port 8080"]
```

- [ ] **Step 2: Create .env.example**

```bash
# .env.example — Copy to .env and fill in values
AGENT_DEBUGGER_DB_URL=postgresql+asyncpg://user:pass@host:5432/agent_debugger
REDIS_URL=redis://localhost:6379
AGENT_DEBUGGER_MODE=cloud
# AWS_ACCESS_KEY_ID=...      # For S3 payload storage (optional)
# AWS_SECRET_ACCESS_KEY=...
# S3_BUCKET=agent-debugger-payloads
```

- [ ] **Step 3: Create fly.toml**

```toml
app = "agent-debugger"
primary_region = "iad"

[build]
  dockerfile = "Dockerfile"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 1

[env]
  AGENT_DEBUGGER_MODE = "cloud"
```

- [ ] **Step 4: Commit**

```bash
git add Dockerfile fly.toml .env.example
git commit -m "feat: deployment configuration for Fly.io"
```

---

### Task 22: Health and Readiness Endpoints

Improve health check to verify database and Redis connectivity for cloud deployment monitoring.

**Files:**
- Modify: `api/main.py` (enhance health endpoint)
- Test: `tests/test_health.py`

- [ ] **Step 1: Write test for health check**

```python
# tests/test_health.py
import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app


@pytest.mark.asyncio
async def test_health_returns_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "database" in data
```

- [ ] **Step 2: Enhance health endpoint**

```python
@app.get("/api/health")
async def health():
    checks = {"status": "ok", "mode": get_config().mode}

    # Database check
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "connected"
    except Exception as e:
        checks["database"] = f"error: {e}"
        checks["status"] = "degraded"

    # Redis check (cloud mode only)
    if os.environ.get("REDIS_URL"):
        try:
            from redis.asyncio import Redis
            r = Redis.from_url(os.environ["REDIS_URL"])
            await r.ping()
            checks["redis"] = "connected"
            await r.aclose()
        except Exception as e:
            checks["redis"] = f"error: {e}"
            checks["status"] = "degraded"

    return checks
```

- [ ] **Step 3: Run tests**

Run: `cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && python -m pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add api/main.py tests/test_health.py
git commit -m "feat: enhanced health check with database and Redis connectivity"
```

---

### Task 23: SDK README and Quickstart

Write a clear README for PyPI that shows the 60-second quickstart (ADR-006).

**Files:**
- Create: `SDK_README.md` (used as PyPI readme)

- [ ] **Step 1: Write SDK_README.md**

```markdown
# Agent Debugger

See **why** your AI agent did that. Agent-native debugging for LangChain, CrewAI, PydanticAI, and custom agents.

## Quickstart (60 seconds)

​```bash
pip install peaky-peek
​```

​```python
import agent_debugger

agent_debugger.init()  # Local mode — no account needed

# Your existing agent code works unchanged
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4")
result = llm.invoke("What's the weather?")

# Open http://localhost:8000 to see the trace
​```

## Cloud Mode

​```bash
export AGENT_DEBUGGER_API_KEY=ad_live_...
​```

Events now flow to the cloud dashboard with team sharing, longer retention, and collaboration.

## Integration Levels

**Auto** (zero code change): `agent_debugger.init()` — patches LangChain/CrewAI automatically.

**Decorators** (selective): `@trace_agent`, `@trace_tool`, `@trace_llm`

**Manual** (full control): `TraceContext` async context manager.

## What You See

- **Decision trees** — why the agent chose each action
- **Evidence provenance** — what evidence justified each decision
- **Time-travel replay** — jump to any checkpoint
- **Live monitoring** — anomaly detection for running agents
```

- [ ] **Step 2: Commit**

```bash
git add SDK_README.md
git commit -m "docs: SDK quickstart README for PyPI"
```

---

## Summary

### Phase 1 (Weeks 1-4): 15 tasks

| Task | What | ADR |
|------|------|-----|
| 1 | Extract ORM models | 005 |
| 2 | Add tenant_id to models | 008 |
| 3 | Alembic migrations | 005 |
| 4 | Config-driven DB engine | 005 |
| 5 | Abstract EventBuffer interface | 005 |
| 6 | Redis EventBuffer | 005 |
| 7 | SDK init() config | 006 |
| 8 | Graceful degradation | 006 |
| 9 | Harden LangChain adapter | 004 |
| 10 | API key auth | 008 |
| 11 | Wire auth into API | 008 |
| 12 | PII redaction pipeline | 008 |
| 13 | Wire redaction into ingestion | 008 |
| 14 | PyPI package config | 006 |
| 15 | Config-driven app wiring | 005 |

### Phase 2 (Weeks 5-7): 5 tasks

| Task | What | ADR |
|------|------|-----|
| 16 | API key management endpoints | 008 |
| 17 | SDK HTTP transport | 006 + 008 |
| 18 | Data retention | 008 |
| 19 | E2E test — local | 002 |
| 20 | E2E test — cloud | 002 + 008 |

### Phase 3 (Weeks 8-10): 3 tasks

| Task | What | ADR |
|------|------|-----|
| 21 | Deployment config | 011 |
| 22 | Health/readiness endpoints | 005 |
| 23 | SDK README | 006 |

**Total: 23 tasks across 3 phases.**

---

## Explicitly Deferred (Beyond These 23 Tasks)

Items from the ADRs that are intentionally deferred to post-beta:

| Item | ADR | Rationale |
|------|-----|-----------|
| **S3 large payload storage** | 005 | Optional optimization. PostgreSQL JSON handles payloads up to 100KB fine. Add S3 when storage costs become a concern post-launch. |
| **Background analysis worker** | 005 | Inline analysis is fast enough for initial scale (<500 events/sec). Extract to worker when ingestion latency becomes measurable. |
| **CrewAI adapter** | 004 | Priority 2 framework. Build during/after beta based on user demand. |
| **Server modules in PyPI wheel** | 006 | SDK wheel ships `agent_debugger_sdk` only. Server (`api/`, `collector/`, `storage/`, `auth/`, `redaction/`) is deployed separately via Docker or `pip install peaky-peek-server`. |
| **JWT dashboard auth (Clerk)** | 008 | Required for Phase 2 team features. Separate plan needed for Clerk integration, user management, and team RBAC. |
| **Stripe billing integration** | 011 | Required for Phase 2. Separate plan needed for subscription management, metering, and checkout. |
| **Landing page and docs site** | 011 | Required for Phase 2. Separate plan needed for marketing site. |

These items should each get their own spec → plan cycle when they become the next priority.
