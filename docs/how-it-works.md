# How It Works

This document explains what the repo is trying to build, how the current implementation behaves, and where the current boundaries are.

## What This Repo Is

`agent_debugger` is an instrumentation and observability MVP for AI agents.

At a high level, it wants to do four things:

1. Capture agent execution as structured events.
2. Preserve parent/child relationships between events so a run can be reconstructed as a tree.
3. Stream those events live to a UI for debugging.
4. Persist sessions, events, and checkpoints so runs can be replayed later.

Instead of relying on plain logs, the repo records semantic events such as:

- agent start and end
- decisions
- LLM requests and responses
- tool calls and results
- errors
- checkpoints

Those event types live in `agent_debugger_sdk/core/events.py`.

## Main Mental Model

The main runtime path is:

`agent code -> TraceContext/decorators/adapters -> EventBuffer -> API/SSE -> UI`

There is also an intended durable history path:

`agent code -> persistence layer -> repository/database -> query endpoints`

That second path is not fully connected yet. The strongest part of the current repo is the event model; the weakest part is the consistency of persistence and product integration.

## Current Runtime Flow

### 1. Event model

The SDK revolves around `TraceEvent` and specialized event types.

Important properties:

- every event has `session_id`
- every event can have `parent_id`
- every event has `event_type`, `data`, `metadata`, and `importance`
- every event can be serialized through `to_dict()`

This is a strong base abstraction because most debugger views can be derived from it:

- timeline from timestamps
- tree from `parent_id`
- filtering from `event_type` and `importance`
- replay from ordered events plus checkpoints

### 2. Trace capture

`TraceContext` in `agent_debugger_sdk/core/context.py` is the core runtime primitive.

When a traced run starts:

1. it creates or accepts a `session_id`
2. it sets async-local state with `contextvars`
3. it emits an `agent_start` event
4. it records later decisions, tool results, errors, and checkpoints
5. it emits an `agent_end` event on exit

Why this design works:

- async-safe state
- hierarchical traces through the current parent ID
- one context object coordinating a run

### 3. Instrumentation options

There are two integration layers:

- decorators in `agent_debugger_sdk/core/decorators.py`
- adapters in `agent_debugger_sdk/adapters/`

Decorators are the simplest starting point:

- `@trace_agent`
- `@trace_tool`
- `@trace_llm`

Adapters cover framework-specific integrations:

- `PydanticAIAdapter`
- `LangChainTracingHandler`

This separation is good. Generic tracing stays reusable, while framework specifics stay isolated.

### 4. Live event pipeline

On FastAPI startup, `api/main.py` connects the SDK to the collector with:

- `configure_event_pipeline(get_event_buffer())`

That causes emitted SDK events to be published into the global `EventBuffer` from `collector/buffer.py`.

`EventBuffer` currently does three jobs:

- stores recent session events in memory
- lets subscribers receive live events through `asyncio.Queue`
- applies basic memory bounds

This is the piece that powers live debugging.

### 5. API and streaming

The backend exposes:

- session and trace query routes in `api/main.py`
- collector ingest routes in `collector/server.py`
- SSE streaming at `/api/sessions/{session_id}/stream`

The live stream path is:

1. client subscribes to a session stream
2. API subscribes to the in-memory buffer
3. new events are emitted as server-sent events
4. keepalive comments are sent periodically

This is one of the cleanest parts of the MVP.

### 6. Storage layer

`storage/repository.py` defines a durable repository backed by SQLAlchemy models for:

- sessions
- events
- checkpoints

This is the right long-term direction, but it is not yet the single source of truth for all runtime activity.

### 7. Frontend status

The frontend already has the right concepts:

- session loading
- SSE subscription
- timeline/tree/inspector components

But the assembled debugger experience is still incomplete. The app shell in `frontend/src/App.tsx` is still placeholder-level.

## What Is Already Good

- Event-first design: the system records agent semantics, not just low-level logs.
- Async-safe context management: `contextvars` are the right primitive.
- Parent/child event structure: useful for causality, trees, and replay.
- Importance scoring: a useful starting point for attention guidance.
- Clean separation between core SDK and framework adapters.
- Pragmatic live transport through SSE.

## What Is Incomplete

### Persistence is not fully wired into runtime

The largest gap is that live events flow into `EventBuffer`, while most query endpoints rely on the repository/database path.

That creates two paths:

- live path in memory
- historical path in persistent storage

The bridge between those paths still needs to be completed.

### Session handling is split

Session lifecycle exists in two places:

- in-memory `SessionManager`
- database-backed `TraceRepository`

That should be unified.

### Docs and runtime still have some drift

The architecture doc historically referenced WebSocket, but the implemented live transport is SSE.

### Frontend and backend contracts need alignment

Some frontend expectations do not yet match the backend response shapes exactly.

## Bottom Line

The repo already contains a solid event model and a workable live tracing pipeline. The next level of maturity comes from making persistence, session lifecycle, and frontend contracts coherent end to end.
