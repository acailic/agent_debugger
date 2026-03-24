# CLAUDE.md

## Purpose

This repo is **Peaky Peek**, a local-first AI agent debugger.

The product has three connected surfaces:

- `agent_debugger_sdk/`: Python SDK for capturing sessions, events, decisions, checkpoints, and adapters
- `api/`: FastAPI server for query, replay, streaming, auth, and packaged UI serving
- `frontend/`: React + TypeScript + Vite UI for trace inspection

Primary loop: instrument an agent with the SDK, persist/query it through the API, inspect and replay it in the frontend.

## Repo Map

### SDK and tracing

- `agent_debugger_sdk/core/`: tracing primitives, contexts, emitters, recorders, session/event logic
- `agent_debugger_sdk/checkpoints/`: checkpoint schemas and validation
- `agent_debugger_sdk/adapters/`: framework integrations
- `agent_debugger_sdk/auto_patch/`: auto-instrumentation registry and transport bridge
- `agent_debugger_sdk/config.py`, `transport.py`, `pricing.py`: runtime config, delivery, pricing metadata

### Server and storage

- `api/`: app factory, routes, schemas, services, UI/static hooks
- `collector/`: ingestion and event pipeline integration
- `storage/`: database engine, migrations, repositories
- `auth/`: auth and API key support
- `redaction/`: security/privacy filters
- `pyproject-server.toml`: package definition for `peaky-peek-server`

### Frontend

- `frontend/src/App.tsx`: app composition root
- `frontend/src/components/`: inspection panels and visualizations
- `frontend/src/api/client.ts`: API boundary
- `frontend/src/types/index.ts`: frontend contract mirror
- `frontend/src/hooks/`, `frontend/src/stores/`: data flow and state
- `frontend/src/App.css`: main styling surface

### Tests and demos

- `tests/`: main Python test suite
- `tests/auto_patch/`: auto-instrumentation coverage
- `examples/`, `scripts/`: demo flows and seed scripts

## Agent Rules

- Prefer targeted reads over broad scans.
- Prefer `rg` and `rg --files`.
- Use `python3`, not `python`, for module commands in this environment.
- Do not touch unrelated user changes in the worktree.
- Avoid noisy directories unless directly relevant: `.venv*`, `frontend/node_modules`, `frontend/dist`, `dist`, `.pytest_cache`, `.ruff_cache`, `__pycache__`, `traces/`.
- `traces/` may emit permission noise during naive filesystem scans.

## High-Risk Boundaries

Before changing shared shapes, inspect both sides of the boundary.

### API ↔ frontend contract

Check together:

- `api/schemas.py`
- `frontend/src/types/index.ts`
- `frontend/src/api/client.ts`

If sessions, events, replay payloads, analysis payloads, or live summaries change, update these together.

### SDK ↔ API contract

If event capture or event fields change, inspect:

- `agent_debugger_sdk/core/`
- `agent_debugger_sdk/checkpoints/`
- `api/schemas.py`
- related route/service code in `api/`

### Auto-instrumentation

If changing auto-patching or adapters, inspect:

- `agent_debugger_sdk/auto_patch/`
- `agent_debugger_sdk/adapters/`
- `tests/auto_patch/`

### Frontend behavior

If changing a UI panel, inspect:

- `frontend/src/App.tsx`
- the target component
- any related hooks/store files
- `frontend/src/types/index.ts`
- `frontend/src/api/client.ts` when data shape assumptions are involved

## Default Workflow

### 1. Orient

Start with:

```bash
git status --short
rg --files agent_debugger_sdk api frontend/src tests
```

Then read the smallest set of files that defines the target path and its adjacent boundary.

### 2. Change

Make the narrowest safe edit that solves the problem.

### 3. Validate

Run the smallest meaningful validation for the area you changed.

## Validation Defaults

### Python and server changes

```bash
ruff check .
python3 -m pytest -q
```

Use targeted tests when possible, for example:

```bash
python3 -m pytest -q tests/test_api_contract.py -k sessions
```

### Frontend changes

```bash
cd frontend && npm run build
```

### Dev servers

```bash
make server
make frontend
```

### Demo flows

```bash
make demo-seed
make demo-live
make demo-safety
make demo-research
```

## Change Heuristics

- If you change event types or event payload fields, assume backend schema, frontend types, and tests may all need updates.
- If you change an API route, inspect the route module, `api/services.py`, schema definitions, and frontend callers.
- If you change storage or collector behavior, inspect ingestion flow and any tests covering persistence and replay.
- If you change UI logic, validate with a frontend build even if the change looks type-local.
- If you change packaging or release logic, inspect both `pyproject.toml` and `pyproject-server.toml`.

## CI and Release Facts

- CI in `.github/workflows/ci.yml` runs `ruff check .` and `pytest -q` on Python 3.10, 3.11, and 3.12.
- Frontend build is not part of the main CI job, but it is part of local validation and the server publish flow.
- Publishing is tag-driven in `.github/workflows/publish.yml`:
  - `sdk-vX.Y.Z` publishes `peaky-peek`
  - `server-vX.Y.Z` publishes `peaky-peek-server`
  - `vX.Y.Z` publishes both
- The publish workflow derives package versions from the tag and rewrites package metadata during CI.

## Quick Commands

```bash
git status --short
git diff --stat
ruff check .
python3 -m pytest -q
cd frontend && npm run build
make server
make frontend
```
