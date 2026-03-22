# Improvement Roadmap

This page is about the shortest path from promising prototype to useful debugger.

## Core Principle

Do not chase more features first. Make the core path work cleanly from trace capture to persistence to UI.

## Highest-Leverage Improvements

### 1. Unify the runtime path

The best next steps are:

1. create sessions in the database, not only in memory
2. persist emitted events as they arrive
3. persist checkpoints alongside events
4. make list/query endpoints read from the same source that live tracing writes to

This is the biggest structural fix in the whole project.

### 2. Make session state authoritative

Choose one source of truth for session lifecycle.

For this project, that should be the database-backed repository. Any in-memory session manager should be a helper, not the truth.

### 3. Align frontend and backend contracts

The frontend should consume the exact response shapes the backend actually returns.

That means:

- verify session list responses
- verify trace list responses
- verify tree response shapes
- verify SSE event payloads

### 4. Build one complete debugger slice

The best near-term UI milestone is:

1. session list
2. timeline
3. event detail panel
4. decision tree

That is enough to make the product useful before replay is fully built.

### 5. Improve event richness

Add more debugging value to each event:

- consistent token accounting
- cost tracking
- model/provider metadata
- retry metadata
- latency breakdowns
- safe serialization for tool inputs and outputs

### 6. Make replay real

Replay only becomes real when checkpoints are treated as a first-class part of execution, not just metadata.

Needed steps:

1. define what state must be serializable
2. checkpoint at meaningful execution boundaries
3. restore from checkpoint plus event suffix
4. expose replay controls in the UI

## Suggested Delivery Phases

### Phase 1: reliability

- unify session persistence
- unify event persistence
- align frontend/backend contracts
- add end-to-end tests for trace capture, storage, and streaming

### Phase 2: usability

- build the session list
- build the timeline view
- build event detail inspection
- build event filtering

### Phase 3: power features

- checkpoint-driven replay
- run comparison
- search over traces
- anomaly highlighting

### Phase 4: production hardening

- auth and tenant separation
- retention policies
- redaction/privacy controls
- PostgreSQL support and migrations
- backpressure handling for high-volume streams

## Best Next Implementation Task

If only one engineering task is chosen next, it should be this:

- make a traced agent run appear in both live SSE and persisted history using one coherent session lifecycle

If that works, the rest of the product gets much easier.
