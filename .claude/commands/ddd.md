# Domain-Driven Design Assistant

Arguments: $ARGUMENTS

## Determine Mode

Decide the mode from the arguments above:

- If the argument is empty, or looks like a file/module path such as `agent_debugger_sdk/...`, `api/...`, `frontend/...`, or `tests/...`, use **Review Mode**.
- If the argument looks like a domain concept such as `session replay ranking`, `policy violation provenance`, or `checkpoint restore value`, use **Model Mode**.

## Review Mode

Analyze the project, or the target path, through a DDD lens. Ground the review in the real repo structure rather than generic DDD advice.

### 1. Map Bounded Contexts

Use these repo-specific contexts:

- **Tracing Core**: `agent_debugger_sdk/core/`, `agent_debugger_sdk/checkpoints/`, `agent_debugger_sdk/config.py`, `agent_debugger_sdk/transport.py`, `agent_debugger_sdk/pricing.py`
- **Instrumentation Edge**: `agent_debugger_sdk/adapters/`, `agent_debugger_sdk/auto_patch/`
- **Server / Delivery**: `api/`, plus `collector/`, `storage/`, `auth/`, and `redaction/` when they participate in the target flow
- **Presentation / Inspection UI**: `frontend/src/`
- **Contract Boundary**: `api/schemas.py`, `frontend/src/types/index.ts`, `frontend/src/api/client.ts`

If the target touches one context, still note the adjacent contexts it depends on.

### 2. Entities, Value Objects, and Aggregates

For the contexts you inspect:

- Identify likely entities such as sessions, traces, checkpoints, alerts, or replay analyses.
- Identify likely value objects such as rankings, summaries, policy parameters, or tool call payloads.
- Identify aggregate roots and consistency boundaries.
- Flag places where persistence shape, transport shape, and domain shape are being conflated.

### 3. Domain Logic Leakage

Look for:

- Business rules in FastAPI routes instead of services or SDK/core modules
- Server or storage details bleeding into tracing core
- Frontend components re-implementing backend/domain decisions instead of consuming a clear contract
- Serialization or API schemas owning rules that should live in domain logic

### 4. Boundary Health

Check whether dependencies flow cleanly:

- core/checkpoints should stay independent of API and frontend
- adapters/auto-patch may depend on core, but should isolate framework-specific models
- API should expose contracts rather than force the frontend to know SDK internals
- frontend should depend on serialized shapes, not backend implementation details

Also check whether changes to event shapes require synchronized edits across:

- `api/schemas.py`
- `frontend/src/types/index.ts`
- `frontend/src/api/client.ts`
- matching tests in `tests/`

### 5. Recommendations

Return a prioritized list of concrete improvements. For each one:

- state the current boundary problem
- identify the exact file(s) involved
- propose a concrete refactor
- rate impact as high, medium, or low

## Model Mode

Help the user model the domain concept in the context of this repo.

### 1. Place the Concept

- Restate the concept in Peaky Peek terms.
- Identify whether it belongs mainly to tracing core, instrumentation edge, server delivery, or frontend inspection.
- If the concept is ambiguous, ask a clarifying question and wait.

### 2. Tactical DDD Design

For the concept, propose:

- **Entity**: identity and lifecycle
- **Value Object**: immutable structured data
- **Aggregate**: consistency boundary and root
- **Domain Event**: emitted or consumed events
- **Repository / Storage Boundary**: how it is saved or queried
- **Service**: behavior that does not fit cleanly on an entity

### 3. Integration Points

Call out how the concept affects:

- SDK event capture
- API schemas/routes/services
- frontend contract types and UI panels
- tests that should be added or updated

### 4. Proposed File Layout

Output a concrete file tree that matches this repo's conventions. Prefer existing directories such as:

```text
agent_debugger_sdk/core/
agent_debugger_sdk/checkpoints/
agent_debugger_sdk/adapters/
agent_debugger_sdk/auto_patch/
api/
frontend/src/
tests/
tests/auto_patch/
```

Reference existing files that are close analogs when possible.
