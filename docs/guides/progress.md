# Progress

This page records actual repo progress so the documentation does not drift behind the code.

Snapshot date: `2026-03-24`

## Current Status

| Area | Status | Notes |
|------|--------|-------|
| Core trace event model | Implemented | Typed events, provenance fields, checkpoints, and serialization are in place. |
| Trace capture runtime | Implemented | `TraceContext`, decorators, async context management, and framework adapters are working. |
| Local live debugger path | Implemented | Event buffer, persistence hooks, FastAPI query routes, SSE, replay helpers, and frontend views work together. |
| Research-grade analysis features | Implemented | Ranking, replay slicing, failure clustering, loop-style alerts, safety/policy event types, and seeded demo sessions are present. |
| SDK initialization/config | Implemented | `init()` supports env-driven local/cloud configuration and prompt redaction flags. |
| API key primitives | Implemented | Key generation, bcrypt hashing, auth ORM models, and FastAPI auth helpers are in place and wired into API routes. |
| Redaction pipeline | Implemented | Prompt, tool-payload, and regex PII scrubbing are implemented, tested, and wired into the event persistence path. |
| Multi-tenant enforcement | Implemented | `tenant_id` is on all trace models and enforced by `TraceRepository` on all queries. |
| SDK cloud transport | Implemented | SDK config detects cloud mode, uses HTTP transport with API key auth for remote event delivery. |
| Cloud-ready infrastructure | Implemented | PostgreSQL migrations, Redis buffer, and retention logic exist. |
| CLI | Implemented | `peaky-peek` command with `--host`, `--port`, `--open`, `--version` flags via `cli.py`. |
| Pricing module | Implemented | `agent_debugger_sdk/pricing.py` with model cost table; `LLMResponseEvent` auto-calculates cost on creation. |
| Bundled UI | Implemented | Frontend built to `frontend/dist/`, served at `/ui/` by FastAPI when present. |
| JSON export | Implemented | `GET /api/sessions/{id}/export` returns portable session bundle (session + events + checkpoints). |
| Examples | Implemented | 8 annotated examples in `examples/` covering hello world, research agent, LangChain, PydanticAI, checkpoint replay, safety audit, loop detection, and live streaming. |
| Getting started guide | Implemented | `docs/getting-started.md` covers install, start, first trace, UI tour, and export in 5 minutes. |
| Replay depth L1 | Implemented | Typed checkpoint schemas: `BaseCheckpointState`, `LangChainCheckpointState`, `CustomCheckpointState` with validation and serialization helpers. |
| Replay depth L2 | Implemented | `TraceContext.restore()` classmethod fetches checkpoint from server and creates a new context with restored state. REST endpoints: `GET /api/checkpoints/{id}` and `POST /api/checkpoints/{id}/restore`. |

## What Shipped

### Core debugger (complete)

- Local trace capture through SDK context, decorators, and adapters
- Database-backed session/event/checkpoint persistence
- FastAPI query surface for sessions, traces, search, analysis, replay, and SSE
- Frontend debugger views for sessions, timeline/tree inspection, replay, and analysis
- Benchmark/demo seeding and targeted tests around contracts, adapters, auth helpers, redaction, and config

### Cloud-hardening layer (complete)

- SDK cloud configuration and API key awareness with HTTP transport
- API key auth lookup helpers and supporting auth models, wired into API routes
- Redaction pipeline wired into the persistence path
- Buffer abstraction with Redis-backed implementation for cloud event fan-out
- Repository-enforced tenant isolation on sessions, events, and checkpoints
- API routes that consistently resolve tenant identity from auth
- Alembic migrations for PostgreSQL schema management

### Quick wins (complete)

- `peaky-peek` CLI command (install and run in one step)
- Model pricing table with auto-cost calculation on LLM response events
- Bundled frontend served directly from the pip package
- JSON export endpoint for portable session bundles
- 8 examples covering all major SDK features
- 5-minute getting started guide

### Replay depth (complete)

- Standardized checkpoint schemas (`agent_debugger_sdk/checkpoints/`)
- `validate_checkpoint_state()` and `serialize_checkpoint_state()` helpers
- `TraceContext.restore(checkpoint_id)` for manual execution restoration
- `create_checkpoint()` now accepts and validates typed dataclass state
- REST endpoints for checkpoint fetch and restore

## What Is Next

### Replay depth L3+ (not started)

Planned in `docs/improvement-roadmap.md`:

- Deterministic restore hooks per framework adapter (LangChain, PydanticAI)
- State-drift markers when replay diverges from the original run
- Expose replay provenance and restore boundaries in the UI

### Phase 2: Auth + Teams + Landing Page (not started)

Planned in `docs/decisions/ADR-011-build-sequence.md`:

- Clerk integration (signup, login, OAuth)
- API key management UI (create, list, rotate, revoke)
- Stripe integration (billing tiers)
- Team creation and shared session access
- Public landing page (positioning, demo GIF, pricing, CTA)
- Documentation site

### Phase 3: Beta Launch (not started)

Planned in `docs/decisions/ADR-011-build-sequence.md`:

- Private beta invite (20-50 developers)
- CrewAI adapter
- Feedback collection
- Session comparison (side-by-side debugging)

### Intelligence improvements (not started)

Planned in `docs/improvement-roadmap.md`:

- Cross-session failure clustering
- Richer ranking signals (retry churn, latency spikes, policy escalation)
- Representative trace surfacing per cluster

## Decision Progress

The ADR set in [`docs/decisions/`](./decisions/README.md) is visible in code:

- ADR-006 is visible through `init()` and env-based configuration.
- ADR-008 is visible through API key helpers, auth models, and the redaction pipeline, with tenant isolation enforced in the repository.
- ADR-011 Phase 1 is complete: cloud-hardening, SDK polish, CLI, pricing, bundled UI, and examples are all shipped. Phase 2 (auth/teams/landing) has not started.

## Validation

Current local verification on `2026-03-24`:

- `frontend`: `npm run build` passes
- `python tests`: `pytest tests/ -v` passes — 365 passed, 1 skipped, 1 pre-existing failure (`test_version_exists` — package metadata not installed in dev env)
- Redis tests are skipped automatically if redis package is not installed
- All cloud-readiness tests for tenant isolation and engine factory pass
