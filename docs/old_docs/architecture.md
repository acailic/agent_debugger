# Architecture

This page describes the system shape without pretending the whole thing is finished. It covers both the design and the parts that are already real in code.

## High-Level Layers

The project falls into five layers:

1. SDK layer
2. collection layer
3. storage layer
4. API layer
5. visualization layer

Two cross-cutting modules now also matter:

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
- expose environment-driven initialization through `agent_debugger.init()`

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
- auth helpers exist in `auth/`, but API-wide tenant enforcement is not finished yet

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

Those two paths now meet at `TraceContext`, which publishes live events and persists the same session data.

The partial cloud/security path looks like this:

`agent_debugger.init() -> API key config + auth helpers + redaction pipeline -> future tenant-aware persistence and remote transport`

That path is directionally correct, but it is not complete end to end in the current repo state.

## Architectural Strengths

- The event schema is strong enough to support multiple debugger views.
- The core SDK is cleanly separated from framework-specific adapters.
- The live streaming model is simple and easy to reason about.
- The repository layer is the durable source of truth for session history.
- Replay and analysis are shared helpers rather than frontend-only logic.

## Architectural Gaps

- Checkpoints are useful but not yet full execution restoration points.
- Cross-session analysis and search are still shallow.
- Live streaming depends on local memory rather than durable fan-out infrastructure.
- Auth exists as helpers and models, but repository-enforced tenant isolation is still missing.
- Redaction exists as a module and tests, but it is not yet inserted into the live ingestion path.
- Cloud configuration exists in the SDK, but remote transport and cloud persistence semantics are not complete.

## Design Direction

The clearest direction from here is:

1. keep the repository as the source of truth for sessions and history
2. keep the in-memory buffer as a live fan-out layer, not the main record
3. deepen checkpoints into restoreable execution boundaries
4. expand ranking and clustering across benchmark corpora and real runs
5. harden the current local debugger into a multi-user product
