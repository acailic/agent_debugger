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
| SDK initialization/config | Implemented | `agent_debugger.init()` supports env-driven local/cloud configuration and prompt redaction flags. |
| API key primitives | Partially implemented | Key generation, bcrypt hashing, auth ORM models, and FastAPI auth helpers exist. |
| Redaction pipeline | Partially implemented | Prompt, tool-payload, and regex PII scrubbing are implemented and tested, but not yet wired into ingestion/persistence. |
| Multi-tenant enforcement | Not implemented end to end | Accepted in ADRs, but `tenant_id` is not yet on trace models or enforced by `TraceRepository`. |
| SDK cloud transport | Not implemented end to end | SDK config can switch to cloud mode, but the tracing runtime is still primarily local-pipeline oriented. |
| Cloud-ready infrastructure | Not implemented end to end | PostgreSQL, migrations, durable fan-out, and retention jobs are still pending. |

## Recent Progress

The most recent repo changes on `2026-03-23` materially moved the project forward:

- `03555fa`: implemented research-grade debugger workflows
- `5d2b961`: added benchmark seeds and API contract tests
- `ea6b4ba`: added ADRs and a concrete cloud evolution plan
- `1adf6c9`: extracted `BufferBase` for pluggable event buffers
- `a6c28b6`: extracted ORM models into `storage/models.py`
- `57206be`: added configurable PII/prompt/tool redaction pipeline
- `c55f8c8`: added `agent_debugger.init()` with local/cloud mode detection
- `71320bf`: added API key generation, hashing, and FastAPI auth middleware helpers

There are also active workspace signals for the next likely implementation step:

- `storage/engine.py` introduces a config-driven database engine factory
- `tests/test_engine_factory.py` describes the intended DB URL and engine behavior
- `tests/test_tenant_isolation.py` describes the intended `tenant_id` model and repository filtering behavior

Those files are useful because they make the next cloud-readiness work concrete, but they should still be treated as in-progress until the storage and repository layers actually satisfy them.

## What Shipped Versus What Is Only Scaffolded

### Shipped and coherent

- Local trace capture through SDK context, decorators, and adapters
- Database-backed session/event/checkpoint persistence
- FastAPI query surface for sessions, traces, search, analysis, replay, and SSE
- Frontend debugger views for sessions, timeline/tree inspection, replay, and analysis
- Benchmark/demo seeding and targeted tests around contracts, adapters, auth helpers, redaction, and config

### Built, but not yet integrated all the way through

- SDK cloud configuration and API key awareness
- API key auth lookup helpers and supporting auth models
- Redaction pipeline and configuration flags
- Buffer abstraction for a future Redis-backed or cloud event fan-out layer

### Still pending

- Repository-enforced tenant isolation on sessions, events, and checkpoints
- API routes that consistently resolve tenant identity from auth
- Remote SDK ingestion transport for cloud mode
- PostgreSQL migrations, retention, and durable high-volume streaming infrastructure

## Decision Progress

The ADR set in [`docs/decisions/`](./decisions/README.md) is no longer just aspirational. Some accepted decisions have landed partially in code:

- ADR-006 is now visible in code through `agent_debugger.init()` and env-based configuration.
- ADR-008 is visible through API key helpers, auth models, and the redaction pipeline, but the most important enforcement step, tenant isolation in the repository, is still missing.
- ADR-011 is partially underway: the local debugger, benchmark seeds, and docs foundation exist, and the repo has started the cloud-hardening sequence without finishing it.

## Learning From The Latest Round Of Work

- Configuration-first was the right way to start cloud support. Adding `init()` created one place to centralize environment behavior before introducing remote transport complexity.
- Security features only count when they sit on the hot path. Auth helpers and redaction code are useful progress, but until every write path passes through them, they are preparation rather than completion.
- Extraction work mattered. Pulling out ORM models and a buffer interface reduced coupling and made the next infrastructure changes easier to reason about.
- The repo is now beyond MVP ambiguity. The main risk is no longer "does the debugger concept work?" but "can the cloud/security path be completed without degrading the strong local flow?"

## Highest-Value Next Steps

1. Finish the end-to-end cloud ingestion path: SDK config -> authenticated API ingestion -> tenant-aware repository queries.
2. Wire redaction into the ingestion/persistence path so privacy settings change stored data, not just test behavior.
3. Add `tenant_id` to trace models and enforce it in `TraceRepository`.
4. Introduce migrations and PostgreSQL support so the accepted architecture can operate outside local SQLite.

## Validation Note

Current local verification on `2026-03-23`:

- `frontend`: `npm run build` passes
- `python tests`: `venv/bin/python -m pytest -q` is mostly green, but still fails on the unfinished cloud-readiness work in `tests/test_engine_factory.py` and `tests/test_tenant_isolation.py`
