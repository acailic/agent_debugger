# Repo Map: Fast Architecture Context

Target: $ARGUMENTS

Build a fast, repo-aware map of the Peaky Peek codebase before deeper work. If a target path or concept is provided, bias the map toward that area.

## Read First

Start with these files:

- `CLAUDE.md`
- `README.md`
- `pyproject.toml`
- `pyproject-server.toml`
- `Makefile`
- `api/main.py`
- `frontend/src/App.tsx`
- `frontend/src/api/client.ts`
- `frontend/src/types/index.ts`

If `$ARGUMENTS` points to a file or module, also read that target and its closest related tests.

## Output

Produce a concise map with these sections:

### 1. System Summary

- What the product does
- Main runtime surfaces: SDK, API, frontend
- Whether the target is primarily backend, frontend, or cross-boundary

### 2. Module Map

List the most relevant directories and what each is responsible for. Prioritize:

- `agent_debugger_sdk/`
- `api/`
- `collector/`, `storage/`, `auth/`, `redaction/` when server concerns matter
- `frontend/src/`
- `tests/` and `tests/auto_patch/`

### 3. Contract Boundaries

Call out the exact files where shape mismatches are most likely:

- `api/schemas.py`
- `frontend/src/types/index.ts`
- `frontend/src/api/client.ts`

If the target touches events or sessions, mention these explicitly.

### 4. Fastest Commands

Recommend the smallest set of commands that will answer the next questions for this repo. Prefer concrete commands such as:

- `git status --short`
- `rg --files ...`
- `ruff check .`
- `python3 -m pytest -q`
- `cd frontend && npm run build`
- `make server`
- `make frontend`

### 5. Risk Zones

List the 3-5 files or boundaries most likely to break from changes in the target area, with a one-line reason for each.
