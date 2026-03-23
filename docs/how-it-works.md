# How It Works

This page explains how the system works today, not just how it is supposed to work on paper.

## What This Repo Is

`agent_debugger` is a trace-first debugger for AI agents.

At a high level, it does five things:

1. Capture agent execution as structured events.
2. Preserve parent/child and provenance relationships between events.
3. Stream those events live to a UI for debugging.
4. Persist sessions, events, and checkpoints to the database as they happen.
5. Expose replay and adaptive analysis over the same stored trace.

Instead of relying on plain logs, it records events such as:

- agent start and end
- decisions
- LLM requests and responses
- tool calls and results
- errors
- checkpoints
- safety checks, refusals, and policy violations
- prompt policy state and multi-agent turns
- behavior alerts

Those event types are defined in `agent_debugger_sdk/core/events.py`.

## Main Mental Model

There is now one main runtime path:

`agent code -> TraceContext/decorators/adapters -> EventBuffer + persistence hooks -> repository/database -> API -> UI`

The in-memory buffer is for live fan-out and SSE. The database is the durable source of truth for sessions, events, checkpoints, analysis inputs, and replay inputs.

## Current Runtime Flow

### 1. Event model

Everything starts with `TraceEvent` and a set of typed subclasses.

Each event has a few fields that matter a lot:

- every event has `session_id`
- every event can have `parent_id`
- every event has `event_type`, `data`, `metadata`, `importance`, and `upstream_event_ids`
- some events add richer provenance such as `evidence_event_ids`
- every event can be serialized through `to_dict()`

That turns out to be enough to drive most debugger views:

- timeline from timestamps
- tree from `parent_id`
- filtering from `event_type`, `importance`, and safety metadata
- replay from ordered events plus checkpoints
- adaptive ranking from severity, novelty, recurrence, and replay value

### 2. Trace capture

`TraceContext` in `agent_debugger_sdk/core/context.py` is the core runtime primitive.

When a traced run starts, `TraceContext`:

1. creates or accepts a `session_id`
2. sets async-local state with `contextvars`
3. creates or updates the session through configured persistence hooks
4. emits an `agent_start` event
5. records decisions, tool results, errors, checkpoints, and research-driven safety and multi-agent events
6. emits an `agent_end` event on exit
7. updates session counters and final session status

This design works for three reasons:

- async-safe state
- hierarchical traces through the current parent ID
- one context object coordinating both live fan-out and durable persistence

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

On FastAPI startup, `api/main.py` wires the SDK to the collector and storage with:

- `configure_event_pipeline(get_event_buffer(), persist_event=..., persist_checkpoint=..., persist_session_start=..., persist_session_update=...)`

From that point on, emitted SDK events are:

- published into the global `EventBuffer` from `collector/buffer.py`
- persisted through `TraceRepository`
- available to both live SSE subscribers and later query endpoints

`EventBuffer` does three jobs:

- stores recent session events in memory
- lets subscribers receive live events through `asyncio.Queue`
- applies basic memory bounds

This is the piece that makes live debugging work without becoming the durable source of truth.

### 5. API and streaming

The backend exposes:

- normalized session and trace query routes in `api/main.py`
- collector ingest routes in `collector/server.py`
- SSE streaming at `/api/sessions/{session_id}/stream`
- adaptive analysis at `/api/sessions/{session_id}/analysis`
- checkpoint-aware replay at `/api/sessions/{session_id}/replay`
- normalized frontend bundles at `/api/sessions/{session_id}/trace`
- cross-session trace search at `/api/traces/search`

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

This is the authoritative history layer used by:

- session list and detail views
- normalized trace bundles
- analysis ranking and clustering
- checkpoint-aware replay

### 7. Replay and analysis

Replay is handled by `collector/replay.py`.

It supports:

- full replay from the beginning
- replay from the nearest checkpoint before a focused event
- replay that jumps to the last failure-like event
- breakpoint rules on event type, tool name, confidence, and safety outcome

Analysis is handled by `collector/intelligence.py`.

It computes:

- event rankings
- failure clusters
- representative failures
- high replay value events
- loop-style behavior alerts

### 7. Frontend status

The frontend is now a working debugger surface, not a placeholder shell.

It currently assembles:

- session loading
- normalized trace bundle loading
- analysis ribbon
- replay controls
- timeline/tree/inspector components
- LLM and tool inspection
- event detail with provenance and scoring context

## What Is Already Good

- Event-first design: the system records agent semantics, not just low-level logs.
- Async-safe context management: `contextvars` are the right primitive.
- Parent/child event structure: useful for causality, trees, and replay.
- Provenance-aware event schema: useful for evidence-grounded debugging.
- Composite ranking: useful for attention guidance and replay triage.
- Clean separation between core SDK and framework adapters.
- Pragmatic live transport through SSE.
- Database-backed query surface shared by the UI and tests.

## What Is Incomplete

- Cross-session analysis is still shallow. Clustering is session-local and mostly fingerprint-based today.
- Replay is checkpoint-aware, but not yet true execution restoration with resumable agent state.
- The frontend is useful, but it is still one-screen and local-first rather than a hardened multi-user product.
- Auth, tenancy, retention, and redaction are still future work.

## Bottom Line

The core path is now coherent: trace capture, live streaming, persistence, analysis, replay, and UI all operate on the same event model. The next real step is not contract repair anymore. It is making the debugger deeper: better replay semantics, stronger benchmark corpora, richer clustering, and production hardening.
