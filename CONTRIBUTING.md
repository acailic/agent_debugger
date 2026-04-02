# Contributing to Peaky Peek

## Quick Start

```bash
# Clone and install
git clone https://github.com/acailic/agent_debugger.git
cd agent_debugger
pip install -e ".[dev]"

# Install frontend dependencies
cd frontend && npm install && cd ..

# Run tests
python3 -m pytest -q

# Lint
ruff check .

# Build frontend
cd frontend && npm run build
```

## Project Structure

- `agent_debugger_sdk/` — Python SDK for instrumenting AI agents
- `api/` — FastAPI server (query, replay, streaming, auth)
- `frontend/` — React + TypeScript + Vite UI
- `collector/` — Event ingestion and pipeline
- `storage/` — Database engine, migrations, repositories
- `auth/` — API key authentication
- `redaction/` — Security/privacy filters
- `tests/` — Python test suite

See `CLAUDE.md` for the full repo map and high-risk boundaries.

## Development Workflow

1. **Branch off `main`** for any non-trivial change
2. **Make targeted changes** — read the smallest set of files needed first
3. **Validate** after changes:
   - `ruff check .` for Python changes
   - `python3 -m pytest -q` for backend/SDK changes
   - `cd frontend && npm run build` for frontend changes
4. **Check boundaries** before changing shared shapes:
   - API ↔ frontend: `api/schemas.py`, `frontend/src/types/index.ts`, `frontend/src/api/client.ts`
   - SDK ↔ API: `agent_debugger_sdk/core/`, `api/schemas.py`
   - Auto-instrumentation: `agent_debugger_sdk/auto_patch/`, `agent_debugger_sdk/adapters/`

## Code Style

- Python: Ruff with line length 120, rules E/F/I
- TypeScript: Vite/ESLint defaults
- Prefer targeted reads over broad scans
- Use `python3`, not `python`

## Running Locally

```bash
# Start the backend
make server

# Start the frontend dev server
make frontend

# Seed demo data
make demo-seed
```

## Testing

Tests use `pytest-asyncio` with `asyncio_mode = "auto"`. Integration tests are deselected by default (`-m 'not integration'`).

```bash
# Run all tests
python3 -m pytest -q

# Run specific test file
python3 -m pytest -q tests/test_api_contract.py

# Run with verbose output
python3 -m pytest -v tests/sdk/core/test_session_manager.py
```

## Commit Messages

Use conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`.

## Reporting Issues

Use [GitHub Issues](https://github.com/acailic/agent_debugger/issues) with:
- Minimal reproduction steps
- Expected vs actual behavior
- Relevant logs or error messages
