# Progress

This page records actual repo progress so the documentation does not drift behind the code.

Snapshot date: `2026-03-23`

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

## What Shipped

### Shipped and coherent

- Local trace capture through SDK context, decorators, and adapters
- Database-backed session/event/checkpoint persistence
- FastAPI query surface for sessions, traces, search, analysis, replay, and SSE
- Frontend debugger views for sessions, timeline/tree inspection, replay, and analysis
- Benchmark/demo seeding and targeted tests around contracts, adapters, auth helpers, redaction, and config

### Built and integrated

- SDK cloud configuration and API key awareness with HTTP transport
- API key auth lookup helpers and supporting auth models, wired into API routes
- Redaction pipeline wired into the persistence path
- Buffer abstraction with Redis-backed implementation for cloud event fan-out
- Repository-enforced tenant isolation on sessions, events, and checkpoints
- API routes that consistently resolve tenant identity from auth
- Alembic migrations for PostgreSQL schema management

## Decision Progress

The ADR set in [`docs/decisions/`](./decisions/README.md) is visible in code:

- ADR-006 is visible through `init()` and env-based configuration.
- ADR-008 is visible through API key helpers, auth models, and the redaction pipeline, with tenant isolation enforced in the repository.
- ADR-011 is underway: the local debugger, benchmark seeds, and docs foundation exist, and the cloud-hardening sequence is in progress.

## Validation

Current local verification on `2026-03-23`:

- `frontend`: `npm run build` passes
- `python tests`: `pytest tests/ -v` passes
- Redis tests are skipped automatically if redis package is not installed
- All cloud-readiness tests for tenant isolation and engine factory pass
