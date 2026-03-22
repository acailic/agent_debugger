# Architecture

This document describes the intended system shape and the most important current implementation details.

## High-Level Layers

The system is organized into five layers:

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

Important note:

- the live transport currently implemented is SSE, not WebSocket

### Visualization layer

Location:

- `frontend/src/`

Responsibilities:

- load sessions and traces
- subscribe to live updates
- render tree, timeline, and event detail views

Current state:

- conceptually scaffolded
- not yet assembled into a finished debugger UI

## Data Flow

The current live flow is:

`agent code -> TraceContext/decorators/adapters -> EventBuffer -> SSE endpoint -> frontend`

The intended persistent flow is:

`agent code -> repository/database -> query endpoints -> frontend`

Right now, those two flows are not fully unified.

## Architectural Strengths

- strong event schema
- clear separation between generic SDK and framework-specific adapters
- simple live streaming model
- repository abstraction ready for more durable usage

## Architectural Gaps

- session lifecycle is split between memory and persistence
- event persistence is not the single source of truth yet
- replay is modeled but not closed end to end
- frontend is not fully aligned with backend contracts yet

## Design Direction

The best architectural direction for this repo is:

1. make the repository the source of truth for sessions and history
2. keep the in-memory buffer as a live fan-out layer, not the main record
3. build the UI directly from the event schema instead of inventing extra backend abstractions
4. treat checkpoints as a real replay primitive, not just metadata
