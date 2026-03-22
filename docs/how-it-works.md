# How It Works

This page explains how the system works today, not just how it is supposed to work on paper.

## What This Repo Is

`agent_debugger` is an instrumentation and observability MVP for AI agents.

At a high level, it is trying to do four things:

1. Capture agent execution as structured events.
2. Preserve parent/child relationships between events so a run can be reconstructed as a tree.
3. Stream those events live to a UI for debugging.
4. Persist sessions, events, and checkpoints so runs can be replayed later.

Instead of relying on plain logs, it records events such as:

- agent start and end
- decisions
- LLM requests and responses
- tool calls and results
- errors
- checkpoints

Those event types are defined in `agent_debugger_sdk/core/events.py`.

## Main Mental Model

The current live path looks like this:

`agent code -> TraceContext/decorators/adapters -> EventBuffer -> API/SSE -> UI`

There is also a second path for durable history:

`agent code -> persistence layer -> repository/database -> query endpoints`

That second path is not fully connected yet. The event model is in decent shape. The integration between live tracing, persistence, and the product surface is where things are still uneven.

## Current Runtime Flow

### 1. Event model

Everything starts with `TraceEvent` and a handful of more specific event types.

Each event has a few fields that matter a lot:

- every event has `session_id`
- every event can have `parent_id`
- every event has `event_type`, `data`, `metadata`, and `importance`
- every event can be serialized through `to_dict()`

That turns out to be enough to drive most debugger views:

- timeline from timestamps
- tree from `parent_id`
- filtering from `event_type` and `importance`
- replay from ordered events plus checkpoints

### 2. Trace capture

`TraceContext` in `agent_debugger_sdk/core/context.py` is the core runtime primitive.

When a traced run starts, `TraceContext`:

1. creates or accepts a `session_id`
2. sets async-local state with `contextvars`
3. emits an `agent_start` event
4. records later decisions, tool results, errors, and checkpoints
5. emits an `agent_end` event on exit

This design works for three reasons:

- async-safe state
- hierarchical traces through the current parent ID
- one context object coordinating a run

### 3. Instrumentation options

There are two integration layers:

- decorators in `agent_debugger_sdk/core/decorators.py`
- adapters in `agent_debugger_sdk/adapters/`

Decorators are the simplest place to start:

- `@trace_agent`
- `@trace_tool`
- `@trace_llm`

Adapters cover framework-specific integrations:

- `PydanticAIAdapter`
- `LangChainTracingHandler`

That split is sensible. The core tracing logic stays generic, and framework-specific behavior stays off to the side.

### 4. Live event pipeline

On FastAPI startup, `api/main.py` wires the SDK to the collector with:

- `configure_event_pipeline(get_event_buffer())`

From that point on, emitted SDK events are published into the global `EventBuffer` from `collector/buffer.py`.

`EventBuffer` currently does three jobs:

- stores recent session events in memory
- lets subscribers receive live events through `asyncio.Queue`
- applies basic memory bounds

This is the piece that makes live debugging work.

### 5. API and streaming

The backend exposes:

- session and trace query routes in `api/main.py`
- collector ingest routes in `collector/server.py`
- SSE streaming at `/api/sessions/{session_id}/stream`

The live stream path is straightforward:

1. client subscribes to a session stream
2. API subscribes to the in-memory buffer
3. new events are emitted as server-sent events
4. keepalive comments are sent periodically

This is one of the cleaner parts of the current implementation.

### 6. Storage layer

`storage/repository.py` defines a durable repository backed by SQLAlchemy models for:

- sessions
- events
- checkpoints

This is the right direction, but it is not yet the single source of truth for all runtime activity.

### 7. Frontend status

The frontend already points in the right direction:

- session loading
- SSE subscription
- timeline/tree/inspector components

What it does not have yet is a finished debugger experience. The shell in `frontend/src/App.tsx` is still a placeholder.

## What Is Already Good

- Event-first design: the system records agent semantics, not just low-level logs.
- Async-safe context management: `contextvars` are the right primitive.
- Parent/child event structure: useful for causality, trees, and replay.
- Importance scoring: a useful starting point for attention guidance.
- Clean separation between core SDK and framework adapters.
- Pragmatic live transport through SSE.

## What Is Incomplete

### Persistence is not fully wired into runtime

The biggest gap is simple: live events go into `EventBuffer`, while most query endpoints rely on the repository/database path.

So there are really two systems at the moment:

- live path in memory
- historical path in persistent storage

The bridge between them still needs to be built properly.

### Session handling is split

Session lifecycle exists in two places:

- in-memory `SessionManager`
- database-backed `TraceRepository`

That should be one system, not two.

### Docs and runtime still have some drift

The docs have already improved, but there are still places where the older intended design and the current implementation do not line up perfectly. A good example is the old WebSocket framing versus the current SSE implementation.

### Frontend and backend contracts need alignment

Some frontend expectations do not yet match the backend response shapes exactly.

## Bottom Line

The core idea is sound. The event model is useful, and the live tracing path already works. The next real step is to make persistence, session lifecycle, and frontend contracts line up end to end.
