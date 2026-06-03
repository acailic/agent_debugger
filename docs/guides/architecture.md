# Architecture

This page describes the system shape. It covers both the design and the parts that are already real in code.

## High-Level Layers

The project falls into five layers:

1. SDK layer
2. collection layer
3. storage layer
4. API layer
5. visualization layer

Two cross-cutting modules also matter:

- `auth/` for API key and tenant resolution helpers
- `redaction/` for ingestion-time privacy controls

## Layer Overview

### SDK layer

Location:

- `agent_debugger_sdk/core/`
- `agent_debugger_sdk/adapters/`

Responsibilities:

- define event types
- manage trace context
- expose decorators
- integrate with external agent frameworks
- expose environment-driven initialization through `init()`

Key modules:

- `events.py`
- `context.py`
- `decorators.py`
- `adapters/pydantic_ai.py`
- `adapters/langchain.py`

### Collection layer

Location:

- `collector/`

Responsibilities:

- accept events
- score importance
- buffer events for live consumers
- compute replay slices
- compute session-level ranking and clustering

Key modules:

- `server.py`
- `buffer.py`
- `scorer.py`
- `replay.py`
- `intelligence.py`

### Storage layer

Location:

- `storage/`

Responsibilities:

- define durable session/event/checkpoint models
- support querying and persistence

Key module:

- `repository.py`

### API layer

Location:

- `api/main.py`

Responsibilities:

- expose session, trace, analysis, and replay endpoints
- expose real-time event streaming
- initialize application wiring

Important:

- the live transport currently implemented is SSE, not WebSocket
- auth helpers exist in `auth/` and tenant enforcement is in the repository

### Visualization layer

Location:

- `frontend/src/`

Responsibilities:

- load sessions and traces
- render replay and analysis controls
- render tree, timeline, and event detail views
- inspect tool, LLM, and provenance data

Current state:

- the debugger shell is working
- the UI still needs deeper workflows and product hardening

## Data Flow

The live path today is:

`agent code -> TraceContext/decorators/adapters -> EventBuffer -> SSE endpoint -> frontend`

The durable path today is:

`agent code -> TraceContext persistence hooks -> repository/database -> query endpoints -> frontend`

Those two paths meet at `TraceContext`, which publishes live events and persists the same session data.

## Architectural Strengths

- The event schema is strong enough to support multiple debugger views.
- The core SDK is cleanly separated from framework-specific adapters.
- The live streaming model is simple and easy to reason about.
- The repository layer is the durable source of truth for session history.
- Replay and analysis are shared helpers rather than frontend-only logic.
