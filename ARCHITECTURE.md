# Agent Debugger & Visualizer - Architecture Design

**Version**: 1.0 (MVP)
**Date**: 2026-03-20

---

## Overview

A visual debugging tool for AI agents that captures execution traces, visualizes decision trees, enables time-travel debugging, and provides real-time monitoring. Built on principles from scientific papers on neural debugging, memory-aware replay, and evidence-grounded reasoning.

### Design Philosophy

From `@ai_context/IMPLEMENTATION_PHILOSOPHY.md`:
- **Ruthless simplicity**: Every abstraction must justify itself
- **Start minimal**: MVP focuses on core debugging flows
- **Direct integration**: Minimal wrappers around frameworks
- **80/20 principle**: High-value features first

From `@ai_context/MODULAR_DESIGN_PHILOSOPHY.md`:
- **Bricks & studs**: Self-contained modules with clear contracts
- **Contract-first**: Define interfaces before implementation
- **Regeneration-ready**: Structure allows rebuilding individual modules

---

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              VISUALIZATION LAYER                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  Decision   │  │   Tool      │  │   LLM       │  │     Session         │ │
│  │   Tree      │  │  Inspector  │  │  Viewer     │  │      Replay         │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│                              │                                              │
│                              ▼                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     React Frontend (Vite + TypeScript)                 │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────────┐ │  │
│  │  │    D3.js    │  │  WebSocket  │  │    State Management (Zustand)   │ │  │
│  │  │   (Trees)   │  │   Client    │  │                                 │ │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ REST + WebSocket
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                API LAYER                                     │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    FastAPI Server (Python 3.11+)                       │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────────┐ │  │
│  │  │  Sessions   │  │   Traces    │  │     Real-time Events (SSE)      │ │  │
│  │  │   CRUD      │  │   Query     │  │                                 │ │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ SQLite / PostgreSQL
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              STORAGE LAYER                                   │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         Trace Store                                     │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────────┐ │  │
│  │  │  Sessions   │  │   Events    │  │     Checkpoints (Snapshots)     │ │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ▲
                                      │ Trace Collection Protocol
                                      │
┌─────────────────────────────────────────────────────────────────────────────┐
│                            COLLECTION LAYER                                  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                      Trace Collector                                   │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────────┐ │  │
│  │  │  Importance │  │  Buffering  │  │     Background Persistence      │ │  │
│  │  │   Scoring   │  │   (Queue)   │  │                                 │ │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ▲
                                      │ SDK Hooks
                                      │
┌─────────────────────────────────────────────────────────────────────────────┐
│                               SDK LAYER                                      │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     Framework-Agnostic Core                            │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │  @trace_agent, @trace_tool, @trace_llm, TraceContext            │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │ PydanticAI      │  │ LangChain/      │  │    AutoGen                   │  │
│  │   Adapter       │  │ LangGraph       │  │      Adapter                 │  │
│  │                 │  │   Adapter       │  │                              │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Module Breakdown

### 2.1 SDK Layer (`agent_debugger_sdk/`)

**Purpose**: Framework-agnostic instrumentation for agents

```
agent_debugger_sdk/
├── __init__.py              # Public API exports
├── core/
│   ├── __init__.py
│   ├── context.py           # TraceContext - thread-local state
│   ├── decorators.py        # @trace_agent, @trace_tool, @trace_llm
│   ├── events.py            # Event types (ToolCall, LLMRequest, Decision)
│   └── session.py           # Session management
├── adapters/
│   ├── __init__.py
│   ├── base.py              # Protocol for adapters
│   ├── pydantic_ai.py       # PydanticAI instrumentation
│   ├── langchain.py         # LangChain/LangGraph instrumentation
│   └── autogen.py           # AutoGen instrumentation (stub for MVP)
└── collector/
    ├── __init__.py
    ├── client.py            # TraceCollectorClient
    └── transport.py         # HTTP/WebSocket transport
```

**Module Contracts**:

| Module | Input | Output | Side Effects |
|--------|-------|--------|--------------|
| `context.py` | None | `TraceContext` instance | Thread-local state |
| `decorators.py` | Function/coroutine | Wrapped function | Emits events to collector |
| `events.py` | Raw data | `TraceEvent` dataclass | None |
| `client.py` | `TraceEvent` | Confirmation | HTTP POST to collector |

### 2.2 Collection Layer (`collector/`)

**Purpose**: Receive, score, buffer, and persist traces

```
collector/
├── __init__.py
├── server.py                # FastAPI endpoints for trace ingestion
├── scorer.py                # Importance scoring (MSSR-inspired)
├── buffer.py                # Async buffer with overflow handling
└── persistence.py           # Background writer to storage
```

**Module Contracts**:

| Module | Input | Output | Side Effects |
|--------|-------|--------|--------------|
| `server.py` | HTTP POST `/traces` | 202 Accepted | Queues event |
| `scorer.py` | `TraceEvent` | `score: float` | None |
| `buffer.py` | `TraceEvent` | None | Stores in memory queue |
| `persistence.py` | Queue items | None | Writes to database |

### 2.3 Storage Layer (`storage/`)

**Purpose**: Efficient storage and retrieval of traces

```
storage/
├── __init__.py
├── schema.py                # SQLAlchemy models
├── repository.py            # Data access layer
├── migrations/              # Alembic migrations
│   └── versions/
│       └── 001_initial.py
└── compression.py           # Trace compression utilities
```

### 2.4 API Layer (`api/`)

**Purpose**: REST and real-time interfaces

```
api/
├── __init__.py
├── main.py                  # FastAPI app factory
├── routes/
│   ├── __init__.py
│   ├── sessions.py          # Session CRUD
│   ├── traces.py            # Trace query endpoints
│   └── replay.py            # Time-travel endpoints
├── websocket.py             # Real-time event streaming
└── dependencies.py          # Dependency injection
```

### 2.5 Visualization Layer (`frontend/`)

**Purpose**: React-based debugging UI

```
frontend/
├── src/
│   ├── App.tsx
│   ├── components/
│   │   ├── DecisionTree.tsx     # D3.js tree visualization
│   │   ├── ToolInspector.tsx    # Tool call viewer
│   │   ├── LLMViewer.tsx        # Prompt/response viewer
│   │   ├── SessionReplay.tsx    # Time-travel controls
│   │   └── TraceTimeline.tsx    # Event timeline
│   ├── hooks/
│   │   ├── useWebSocket.ts      # Real-time updates
│   │   └── useTrace.ts          # Trace fetching
│   ├── stores/
│   │   └── sessionStore.ts      # Zustand state
│   └── api/
│       └── client.ts            # API client
├── package.json
└── vite.config.ts
```

---

## 3. Data Models

### 3.1 Core Event Types

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
import uuid

class EventType(str, Enum):
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    DECISION = "decision"
    ERROR = "error"
    CHECKPOINT = "checkpoint"

@dataclass
class TraceEvent:
    """Base event for all trace points"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    parent_id: Optional[str] = None
    event_type: EventType = EventType.AGENT_START
    timestamp: datetime = field(default_factory=datetime.utcnow)
    name: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Importance score (0.0-1.0) from MSSR-inspired scoring
    importance: float = 0.5

@dataclass
class ToolCallEvent(TraceEvent):
    event_type: EventType = EventType.TOOL_CALL
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)

@dataclass
class ToolResultEvent(TraceEvent):
    event_type: EventType = EventType.TOOL_RESULT
    tool_name: str = ""
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0

@dataclass
class LLMRequestEvent(TraceEvent):
    event_type: EventType = EventType.LLM_REQUEST
    model: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)

@dataclass
class LLMResponseEvent(TraceEvent):
    event_type: EventType = EventType.LLM_RESPONSE
    model: str = ""
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    duration_ms: float = 0.0

@dataclass
class DecisionEvent(TraceEvent):
    event_type: EventType = EventType.DECISION
    reasoning: str = ""
    confidence: float = 0.0
    evidence: list[dict[str, Any]] = field(default_factory=list)
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    chosen_action: str = ""
```

### 3.2 Session Model

```python
@dataclass
class Session:
    """Agent debugging session"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str = ""
    framework: str = ""  # pydantic_ai, langchain, autogen
    started_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    status: str = "running"  # running, completed, error

    # Summary stats
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    tool_calls: int = 0
    llm_calls: int = 0
    errors: int = 0

    # Configuration snapshot
    config: dict[str, Any] = field(default_factory=dict)

    # Tags for filtering
    tags: list[str] = field(default_factory=list)
```

### 3.3 Checkpoint Model (Time-Travel)

```python
@dataclass
class Checkpoint:
    """Snapshot of agent state at a point in time"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    event_id: str = ""  # Event that triggered checkpoint
    sequence: int = 0   # Order in session

    # Agent state snapshot
    state: dict[str, Any] = field(default_factory=dict)

    # Memory snapshot (for MSSR-style replay)
    memory: dict[str, Any] = field(default_factory=dict)

    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Importance for selective replay
    importance: float = 0.5
```

---

## 4. API Contracts

### 4.1 REST Endpoints

```
POST   /api/sessions                    # Create session
GET    /api/sessions                    # List sessions (paginated)
GET    /api/sessions/{id}               # Get session details
DELETE /api/sessions/{id}               # Delete session

GET    /api/sessions/{id}/traces        # Get all traces for session
GET    /api/sessions/{id}/traces/{eid}  # Get specific trace event
GET    /api/sessions/{id}/tree          # Get decision tree

GET    /api/sessions/{id}/checkpoints   # List checkpoints
GET    /api/checkpoints/{cid}           # Get checkpoint state
POST   /api/sessions/{id}/replay        # Start replay from checkpoint

POST   /api/traces                      # Ingest trace event (from SDK)
GET    /api/traces/search               # Search traces across sessions
```

### 4.2 WebSocket Events

**Client → Server**:
```typescript
{
  "type": "subscribe",
  "session_id": "uuid"
}

{
  "type": "unsubscribe",
  "session_id": "uuid"
}
```

**Server → Client**:
```typescript
{
  "type": "trace_event",
  "session_id": "uuid",
  "event": TraceEvent
}

{
  "type": "session_end",
  "session_id": "uuid",
  "summary": SessionSummary
}
```

### 4.3 SSE for Real-time Updates

```
GET /api/sessions/{id}/stream

# Response (text/event-stream):
event: trace
data: {"event_type": "tool_call", ...}

event: checkpoint
data: {"id": "uuid", "sequence": 5, ...}

event: session_end
data: {"status": "completed", ...}
```

---

## 5. SDK Interface Design

### 5.1 Core Decorators

```python
from agent_debugger_sdk import trace_agent, trace_tool, trace_llm, TraceContext

# Instrument an entire agent
@trace_agent(name="my_agent", framework="pydantic_ai")
async def my_agent(prompt: str) -> str:
    ...

# Instrument a tool
@trace_tool(name="search_web")
async def search_web(query: str) -> list[str]:
    ...

# Instrument LLM calls
@trace_llm(model="gpt-4o")
async def call_llm(messages: list) -> str:
    ...
```

### 5.2 Context Manager

```python
from agent_debugger_sdk import TraceContext

# Manual context management
async with TraceContext(session_id="my-session") as ctx:
    ctx.record_decision(
        reasoning="User asked about weather",
        confidence=0.9,
        evidence=[{"source": "user_input", "content": "What's the weather?"}],
        chosen_action="call_weather_tool"
    )

    result = await search_web("weather today")
    ctx.record_tool_result("search_web", result)
```

### 5.3 PydanticAI Adapter

```python
from pydantic_ai import Agent
from agent_debugger_sdk.adapters import PydanticAIAdapter

# Wrap existing agent
agent = Agent('openai:gpt-4o')
debugged_agent = PydanticAIAdapter(agent).instrument()

# Or use as context manager
async with PydanticAIAdapter(agent).trace() as session:
    result = await agent.run("Hello")
    print(f"Session ID: {session.id}")
```

### 5.4 LangChain Adapter

```python
from langchain.agents import create_openai_functions_agent
from agent_debugger_sdk.adapters import LangChainAdapter

agent = create_openai_functions_agent(llm, tools, prompt)
adapter = LangChainAdapter(agent)

# Automatic instrumentation
result = await adapter.arun({"input": "Hello"})
```

---

## 6. Storage Schema

### 6.1 SQLite/PostgreSQL Schema

```sql
-- Sessions table
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    framework TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'running',
    total_tokens INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0.0,
    tool_calls INTEGER DEFAULT 0,
    llm_calls INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    config JSONB,
    tags JSONB
);

CREATE INDEX idx_sessions_started ON sessions(started_at DESC);
CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_agent ON sessions(agent_name);

-- Trace events table
CREATE TABLE trace_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    parent_id TEXT REFERENCES trace_events(id),
    event_type TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    name TEXT,
    data JSONB NOT NULL,
    metadata JSONB,
    importance REAL DEFAULT 0.5,
    sequence INTEGER NOT NULL
);

CREATE INDEX idx_events_session ON trace_events(session_id, sequence);
CREATE INDEX idx_events_type ON trace_events(event_type);
CREATE INDEX idx_events_timestamp ON trace_events(timestamp);
CREATE INDEX idx_events_importance ON trace_events(importance DESC);

-- Checkpoints table (for time-travel)
CREATE TABLE checkpoints (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    event_id TEXT NOT NULL REFERENCES trace_events(id),
    sequence INTEGER NOT NULL,
    state JSONB NOT NULL,
    memory JSONB,
    timestamp TIMESTAMP NOT NULL,
    importance REAL DEFAULT 0.5
);

CREATE INDEX idx_checkpoints_session ON checkpoints(session_id, sequence);
CREATE INDEX idx_checkpoints_importance ON checkpoints(importance DESC);

-- Full-text search index (PostgreSQL)
CREATE INDEX idx_events_data_fts ON trace_events USING GIN (to_tsvector('english', data::text));
```

### 6.2 Query Patterns

```sql
-- Get session with all events (for replay)
SELECT * FROM trace_events
WHERE session_id = ?
ORDER BY sequence ASC;

-- Get decision tree (parent-child relationships)
WITH RECURSIVE tree AS (
    SELECT * FROM trace_events WHERE session_id = ? AND parent_id IS NULL
    UNION ALL
    SELECT e.* FROM trace_events e
    JOIN tree t ON e.parent_id = t.id
    WHERE e.session_id = ?
)
SELECT * FROM tree;

-- Get high-importance checkpoints (MSSR-inspired)
SELECT * FROM checkpoints
WHERE session_id = ?
ORDER BY importance DESC, sequence ASC
LIMIT 10;

-- Get LLM cost summary
SELECT
    session_id,
    SUM((data->>'cost_usd')::float) as total_cost,
    SUM((data->'usage'->>'input_tokens')::int) as input_tokens,
    SUM((data->'usage'->>'output_tokens')::int) as output_tokens
FROM trace_events
WHERE event_type = 'llm_response'
GROUP BY session_id;
```

---

## 7. Real-time Communication

### 7.1 Architecture Choice: SSE over WebSocket

**Decision**: Use Server-Sent Events (SSE) for real-time updates.

**Rationale**:
- Simpler than WebSocket for one-way server→client updates
- Native browser support
- Automatic reconnection
- Works through proxies/firewalls
- Aligns with `@ai_context/IMPLEMENTATION_PHILOSOPHY.md` SSE patterns

**Implementation**:

```python
# api/routes/stream.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from collector.buffer import EventBuffer
import asyncio

router = APIRouter()

@router.get("/sessions/{session_id}/stream")
async def stream_session(session_id: str):
    """SSE endpoint for real-time trace events"""

    async def event_generator():
        queue = await EventBuffer.subscribe(session_id)
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"event: {event.event_type}\n"
                yield f"data: {event.to_json()}\n\n"
        except asyncio.TimeoutError:
            # Send keepalive
            yield ": keepalive\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
```

### 7.2 Event Buffer Architecture

```python
# collector/buffer.py
import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import AsyncQueue
import weakref

@dataclass
class EventBuffer:
    """Simple async buffer with subscriber support"""

    _queues: dict[str, list[AsyncQueue]] = defaultdict(list)
    _lock: asyncio.Lock = asyncio.Lock()

    async def publish(self, session_id: str, event: TraceEvent):
        """Publish event to all subscribers"""
        async with self._lock:
            queues = self._queues.get(session_id, [])
            dead_queues = []

            for queue in queues:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    dead_queues.append(queue)

            # Clean up dead subscribers
            for q in dead_queues:
                self._queues[session_id].remove(q)

    async def subscribe(self, session_id: str) -> AsyncQueue:
        """Subscribe to events for a session"""
        queue: AsyncQueue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._queues[session_id].append(queue)
        return queue

    async def unsubscribe(self, session_id: str, queue: AsyncQueue):
        """Unsubscribe from events"""
        async with self._lock:
            if queue in self._queues[session_id]:
                self._queues[session_id].remove(queue)
```

---

## 8. Integration Points

### 8.1 PydanticAI Integration

PydanticAI already has OpenTelemetry instrumentation. We hook into this:

```python
# adapters/pydantic_ai.py
from pydantic_ai import Agent
from pydantic_ai.models.instrumented import InstrumentationSettings
from opentelemetry.trace import TracerProvider
from typing import Any, TypeVar

from ..core.events import TraceEvent, LLMRequestEvent, LLMResponseEvent
from ..collector.client import TraceCollectorClient

T = TypeVar('T')

class PydanticAIAdapter:
    """Adapter to trace PydanticAI agents"""

    def __init__(self, agent: Agent[Any, T], collector: TraceCollectorClient):
        self.agent = agent
        self.collector = collector
        self._session_id: str | None = None

    def instrument(self) -> Agent[Any, T]:
        """Return instrumented agent"""
        # Create custom tracer provider that forwards to our collector
        provider = CustomTracerProvider(self.collector)
        settings = InstrumentationSettings(tracer_provider=provider)

        # PydanticAI's instrument() wraps the model
        self.agent.instrument(settings)
        return self.agent

    async def trace(self) -> 'TraceContext':
        """Context manager for tracing a run"""
        from ..core.context import TraceContext
        return TraceContext(self.collector, framework="pydantic_ai")
```

### 8.2 LangChain/LangGraph Integration

```python
# adapters/langchain.py
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.agents import AgentAction, AgentFinish
from typing import Any
import uuid

from ..core.events import TraceEvent, ToolCallEvent, LLMRequestEvent
from ..collector.client import TraceCollectorClient

class LangChainTracingHandler(AsyncCallbackHandler):
    """Callback handler for LangChain tracing"""

    def __init__(self, collector: TraceCollectorClient, session_id: str):
        self.collector = collector
        self.session_id = session_id
        self._parent_map: dict[str, str] = {}

    async def on_llm_start(self, serialized, prompts, **kwargs):
        event = LLMRequestEvent(
            session_id=self.session_id,
            name=kwargs.get("name", "llm"),
            model=kwargs.get("invocation_params", {}).get("model", "unknown"),
            messages=[{"role": "user", "content": p} for p in prompts],
        )
        await self.collector.emit(event)
        self._parent_map[kwargs["run_id"]] = event.id

    async def on_llm_end(self, response, **kwargs):
        parent_id = self._parent_map.get(kwargs["run_id"])
        event = LLMResponseEvent(
            session_id=self.session_id,
            parent_id=parent_id,
            content=response.generations[0][0].text,
            usage=response.llm_output.get("token_usage", {}),
        )
        await self.collector.emit(event)

    async def on_tool_start(self, serialized, input_str, **kwargs):
        event = ToolCallEvent(
            session_id=self.session_id,
            name=serialized.get("name", "tool"),
            tool_name=serialized.get("name", "unknown"),
            arguments={"input": input_str},
        )
        await self.collector.emit(event)
        self._parent_map[kwargs["run_id"]] = event.id

    async def on_tool_end(self, output, **kwargs):
        parent_id = self._parent_map.get(kwargs["run_id"])
        event = ToolResultEvent(
            session_id=self.session_id,
            parent_id=parent_id,
            tool_name=kwargs.get("name", "unknown"),
            result=output,
        )
        await self.collector.emit(event)
```

---

## 9. Importance Scoring (MSSR-Inspired)

From the MSSR paper: importance sampling selects which experiences to replay based on their learning value.

```python
# collector/scorer.py
from dataclasses import dataclass
from typing import Any
import re

from ..core.events import TraceEvent, EventType

@dataclass
class ImportanceScorer:
    """Score events for importance (0.0-1.0)"""

    # Weights for different factors
    error_weight: float = 0.4
    decision_weight: float = 0.3
    cost_weight: float = 0.15
    duration_weight: float = 0.15

    def score(self, event: TraceEvent) -> float:
        """Calculate importance score for an event"""

        # Base score by event type
        base_scores = {
            EventType.ERROR: 0.9,
            EventType.DECISION: 0.7,
            EventType.TOOL_RESULT: 0.5,
            EventType.LLM_RESPONSE: 0.5,
            EventType.TOOL_CALL: 0.4,
            EventType.LLM_REQUEST: 0.3,
            EventType.AGENT_START: 0.2,
            EventType.AGENT_END: 0.2,
            EventType.CHECKPOINT: 0.6,
        }
        score = base_scores.get(event.event_type, 0.3)

        # Boost for errors
        if event.event_type == EventType.TOOL_RESULT:
            if event.data.get("error"):
                score += self.error_weight

        # Boost for high cost
        if event.event_type == EventType.LLM_RESPONSE:
            cost = event.data.get("cost_usd", 0)
            if cost > 0.01:
                score += self.cost_weight * min(cost / 0.1, 1.0)

        # Boost for long duration
        duration = event.data.get("duration_ms", 0)
        if duration > 1000:
            score += self.duration_weight * min(duration / 10000, 1.0)

        # Boost for high confidence decisions (or low confidence)
        if event.event_type == EventType.DECISION:
            confidence = event.data.get("confidence", 0.5)
            # Both very high and very low confidence are interesting
            score += self.decision_weight * (1 - abs(0.5 - confidence) * 2)

        return min(score, 1.0)
```

---

## 10. Performance Considerations

### 10.1 SDK Overhead Target

**Goal**: < 5% performance impact on agent execution

**Strategies**:
1. **Async I/O**: All collector calls are non-blocking
2. **Batching**: Buffer events and flush in background
3. **Sampling**: Option to sample only high-importance events
4. **Compression**: Compress large payloads before transport

```python
# collector/client.py
class TraceCollectorClient:
    def __init__(self, endpoint: str, batch_size: int = 50, flush_interval: float = 0.5):
        self.endpoint = endpoint
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._buffer: list[TraceEvent] = []
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None

    async def emit(self, event: TraceEvent):
        """Emit event (non-blocking, buffered)"""
        async with self._lock:
            self._buffer.append(event)
            if len(self._buffer) >= self.batch_size:
                await self._flush()

    async def _flush(self):
        """Flush buffer to collector"""
        if not self._buffer:
            return

        events = self._buffer
        self._buffer = []

        # Fire-and-forget HTTP POST
        asyncio.create_task(self._send_batch(events))

    async def _send_batch(self, events: list[TraceEvent]):
        """Send batch to collector"""
        # Implementation uses aiohttp for async HTTP
        ...
```

### 10.2 Database Optimization

**Indexing Strategy**:
- `(session_id, sequence)` for replay queries
- `(event_type)` for filtering
- `(importance DESC)` for selective replay
- GIN index on JSONB for search

**Compression**:
- Compress `data` and `state` JSONB fields > 1KB
- Use gzip or zstd compression
- Store compressed size for metrics

---

## 11. MVP Scope

### In Scope (Phase 1)

- [x] SDK core decorators and context
- [x] PydanticAI adapter
- [x] LangChain adapter (basic)
- [x] Trace collection and storage
- [x] Session CRUD API
- [x] Decision tree visualization
- [x] Tool call inspector
- [x] LLM request/response viewer
- [x] Basic time-travel (checkpoint-based)
- [x] Real-time SSE updates

### Out of Scope (Future Phases)

- [ ] AutoGen adapter (Phase 2)
- [ ] Conditional breakpoints (Phase 2)
- [ ] Neural debugger integration (Phase 2+)
- [ ] Multi-agent comparison view
- [ ] Cost optimization suggestions
- [ ] Export to external tools (LangSmith, etc.)

---

## 12. File Structure

```
agent_debugger/
├── pyproject.toml
├── README.md
├── ARCHITECTURE.md
├── agent_debugger_sdk/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── context.py
│   │   ├── decorators.py
│   │   ├── events.py
│   │   └── session.py
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── pydantic_ai.py
│   │   ├── langchain.py
│   │   └── autogen.py
│   └── collector/
│       ├── __init__.py
│       ├── client.py
│       └── transport.py
├── collector/
│   ├── __init__.py
│   ├── server.py
│   ├── scorer.py
│   ├── buffer.py
│   └── persistence.py
├── storage/
│   ├── __init__.py
│   ├── schema.py
│   ├── repository.py
│   ├── migrations/
│   │   └── versions/
│   │       └── 001_initial.py
│   └── compression.py
├── api/
│   ├── __init__.py
│   ├── main.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── sessions.py
│   │   ├── traces.py
│   │   └── replay.py
│   ├── websocket.py
│   └── dependencies.py
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    └── src/
        ├── App.tsx
        ├── main.tsx
        ├── components/
        ├── hooks/
        ├── stores/
        └── api/
```

---

## 13. Next Steps

1. **Implement SDK Core** (`agent_debugger_sdk/core/`)
   - Start with `events.py` data models
   - Implement `context.py` for thread-local state
   - Create `decorators.py` for instrumentation

2. **Build Collector** (`collector/`)
   - `server.py` FastAPI endpoints
   - `buffer.py` async event buffer
   - `persistence.py` database writer

3. **Create Storage Layer** (`storage/`)
   - `schema.py` SQLAlchemy models
   - Initial migration
   - `repository.py` data access

4. **Implement API** (`api/`)
   - Session CRUD
   - Trace query endpoints
   - SSE streaming

5. **Build Frontend** (`frontend/`)
   - React app setup
   - Decision tree component
   - Tool inspector
   - LLM viewer

6. **Create Adapters** (`agent_debugger_sdk/adapters/`)
   - PydanticAI adapter
   - LangChain adapter

---

## Attribution

Architecture influenced by:
- PydanticAI's OpenTelemetry instrumentation patterns
- LangChain's callback handler design
- OpenTelemetry GenAI semantic conventions
- MSSR importance sampling concepts
- CXReasonAgent evidence-grounded reasoning

---

**Document Status**: Draft for review
**Author**: Zen Architect (AI Agent)
**Date**: 2026-03-20
