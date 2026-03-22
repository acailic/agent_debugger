# Architecture

This page describes the system shape without pretending the whole thing is finished. It covers both the design and the parts that are already real in code.

## High-Level Layers

The project falls into five layers:

1. SDK layer
2. collection layer
3. storage layer
4. API layer
5. visualization layer

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

Key modules:

- `server.py`
- `buffer.py`
- `scorer.py`

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

- expose session and trace endpoints
- expose real-time event streaming
- initialize application wiring

Important:

- the live transport currently implemented is SSE, not WebSocket

### Visualization layer

Location:

- `frontend/src/`

Responsibilities:

- load sessions and traces
- subscribe to live updates
- render tree, timeline, and event detail views

Current state:

- the pieces are scaffolded
- the full debugger UI is not assembled yet

## Data Flow

The live path today is:

`agent code -> TraceContext/decorators/adapters -> EventBuffer -> SSE endpoint -> frontend`

The intended durable path is:

`agent code -> repository/database -> query endpoints -> frontend`

Those two paths do not fully meet yet, which is one of the main architectural problems in the project.

## Architectural Strengths

- The event schema is strong enough to support multiple debugger views.
- The core SDK is cleanly separated from framework-specific adapters.
- The live streaming model is simple and easy to reason about.
- The repository layer is ready to become the long-term source of truth.

## Architectural Gaps

- Session lifecycle is split between memory and persistence.
- Event persistence is not the single source of truth yet.
- Replay is represented in the model, but not finished end to end.
- Frontend contracts still need to line up with backend responses.

## Design Direction

The clearest direction from here is:

1. make the repository the source of truth for sessions and history
2. keep the in-memory buffer as a live fan-out layer, not the main record
3. build the UI directly from the event schema instead of inventing extra backend abstractions
4. treat checkpoints as a real replay primitive, not just metadata
