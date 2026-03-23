# Improvement Roadmap

This page is about the shortest path from working debugger core to research-grade product.

## Core Principle

Do not re-open solved contract problems. Build on the now-coherent core path from trace capture to persistence to UI.

## Highest-Leverage Improvements

### 1. Deepen replay from trace playback to execution restoration

The current replay path can start from the nearest checkpoint and expose useful slices of a run. The next step is to restore meaningful agent state, not just replay stored events.

Best next steps:

1. standardize what checkpoint state must contain for each adapter
2. support deterministic restore hooks per framework
3. record state-drift markers when replay diverges from the original run
4. expose replay provenance and restore boundaries in the UI

### 2. Strengthen adaptive trace intelligence

The current ranking model is useful, but still local and heuristic.

Best next steps:

1. cluster failures across sessions, not only within one run
2. add recurrence windows for repeated loops and flaky tool behavior
3. score traces using richer signals such as retry churn, latency spikes, and policy escalation
4. surface one-click representative traces for each cluster

### 3. Expand research benchmarks into a reusable corpus

The repo now has benchmark-style tests, but it needs a larger, reusable corpus for regression testing and demos.

Best next steps:

1. add benchmark seeds for prompt injection, evidence-grounded tool use, prompt-policy shifts, multi-agent debate, loop detection, and replay determinism
2. persist demo sessions into the local database for UI smoke testing
3. track expected rankings, clusters, and breakpoint hits as regression assertions
4. add fixtures that mimic both safe and unsafe tool-use paths

### 4. Finish the cloud and security path that has already started

Best next steps:

1. wire API key auth into the actual API dependency chain
2. add `tenant_id` to trace models and enforce it in `TraceRepository`
3. apply redaction before persistence so privacy settings affect stored traces
4. implement the SDK's remote/cloud transport path
5. add PostgreSQL support, migrations, and backpressure handling for high-volume streams

### 5. Expand the product surface around the current core

The current UI is coherent, but still narrow.

Best next steps:

1. side-by-side run comparison
2. search over traces, clusters, and safety outcomes
3. saved debugger views and pinned failures
4. richer drill-down for provenance chains and evidence links

## Suggested Delivery Phases

### Phase 1: replay depth

- standardize checkpoint contents
- add restore semantics per adapter
- detect replay divergence
- test focused and failure replay paths end to end

### Phase 2: intelligence

- expand ranking signals
- add cross-session failure clustering
- strengthen loop and anomaly detection
- add representative trace surfacing

### Phase 3: benchmark corpus

- add reusable benchmark fixtures
- add seeded demo sessions
- run benchmark assertions in CI
- add benchmark docs for expected debugger behavior

### Phase 4: production hardening

- repository-enforced tenant isolation
- redaction wired into persistence
- SDK cloud transport
- retention policies
- PostgreSQL support and migrations
- backpressure handling for high-volume streams

## Best Next Implementation Task

If only one engineering task is chosen next, it should be this:

- finish the end-to-end cloud ingestion path from `agent_debugger.init()` through authenticated ingestion, tenant-aware persistence, and redaction on write

That work turns several partial features into one coherent product capability.
