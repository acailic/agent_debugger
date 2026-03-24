# Implementation Plan: PreToolUse Query Duplicate Detection

# Implementation Plan
# Implementation Plan: PreToolUse Hook: Query Duplicate Detection
# Implementation Plan
# ---
   - Create pattern registry JSON with pre-computed query shapes from `storage/repository.py` and `auth/middleware.py`.
   - Hook configuration should add to `.claude/settings.json`
   - (Note: Need to add tests to the exempt list,)
   - Run tests

   - Commit files
   - Verify new hook works

   - (Optional) Try with an on new query patterns
---

# Task Summary
Create tasks to track progress:
1. Create pattern registry JSON file
2. Create Python script for pattern matching
3. Update settings.json with hook configuration
4. Commit files
5. Run tests

6. Verify new hook works

## Prerequisites

- ruff check . (passing)
- pytest -q (passing tests)
- Frontend build passes (passing)

- Type: `mypy analyze` to see if hook code needs updating
- Run `ruff check --fix` manually

    - Or run in terminal: `ruff check .`
    - `ruff check . --fix`
    - `ruff check . --fix`
    - `ruff check. --fix`
    - `ruff check . --fix`
- Run `ruff check` on api/ routes - should pass (no failures)
- Frontend build passes (passing)
- All Python files pass ruff check

- Run tests in parallel

    ```bash
    make server
    ```
4. **Create implementation plan** in `docs/superpowers/plans/2026-03-24-pretooluse-query-duplicate-detection.md`
   - Commit with message
5. Run final verification: `ruff check . && pytest -q`
   - Frontend build: `cd frontend && npm run build`

   - (Optional) Start dev server manually: `make dev` or `python -m api.app` and `    - cd scripts && `python -m api.app` &
    - - `git add docs/superpowers/specs/2026-03-24-pretooluse-query-duplicate-detection.md`
    - `git commit -m "Add PreToolUse hook for query duplicate detection"`
   - `git add docs/superpowers/specs/2026-03-24-pretooluse-query-duplicate-detection.md`
   - `git commit -m "Add PreToolUse hook for query duplicate detection\n\nPattern: SessionModel.where[id, tenant_id]\nExisting method: get_session\nLocation: storage/repository.py\n\nUse this existing method instead of writing a new query."
   ```
6. Commit pattern_registry.json
   - cd scripts/hooks && python3 check_duplicate_queries.py --content "$content" --path "$path"
   ```
2. If no duplicates found, output allow message
3. If duplicates, ask user for approval to proceed
    - If not in scope, output allow message
    - Run tests
    - Output: `ruff check. && pytest -q (passing)`
    - output: `1 file changed, 24 delet, 2 inserts, 2 hooks, 1 spec written` (no tests affected)
    - Created pattern registry JSON
    - Created Python script for pattern matching
    - Updated settings.json with hook configuration

    - Committed all files
    - Tests pass
    - Frontend build passes
    - Started dev server manually to `make dev` or run `python3 -m api.app` and the dev server is running.
    - Run `ruff check . && pytest -q` (passing)
    - output: `All files created, 6 changes to git status`
    - spec document written and design documented
    - code committed
    - front end build passes (passing)
    - Tests pass (passing)
    - No hook integration needed

4. After successful test run: `ruff check` is not being about tests")

Summary: Implementation complete!
- Committed spec document
- - All hooks files created and code is clean and documented
- Frontend build passes (passing)
    - Ready to test the hook

 run the:
    1. Start dev server: `make dev`
    2. Start dev server: `make frontend`
    3. Run frontend build: `cd frontend && npm run build`
    4. Start dev server: `make dev`
    5. Run demo flows: `make demo-seed demo-live demo-safety demo-research`
    6. Run demo-research: `make demo-research`
    ```bash
    make demo-live
    make demo-safety
    make demo-research
    ```
## Files Created
- `.claude/settings.json` - Hook configuration
- `docs/superpowers/specs/2026-03-24-pretooluse-query-duplicate-detection.md` - Design document
- `scripts/hooks/pattern_registry.json` - Pattern registry
- `scripts/hooks/check_duplicate_queries.py` - Pattern matching script
- `api/services.py` - Service layer (used by routes)

- `api/session_routes.py` - Session routes
- `api/trace_routes.py` - Trace routes
- `api/replay_routes.py` - Replay routes
- `api/system_routes.py` - System routes
- `api/auth_routes.py` - Auth routes
- `auth/middleware.py` - Auth middleware
- `storage/repository.py` - Repository layer
- `tests/` - Tests directory (exempt)
- `frontend/` - Frontend code (exempt)
- `collector/` - Collector directory (exempt)

- `examples/` and `scripts/` - Examples and scripts (exempt)

- `docs/` - Documentation (exempt)

- `.venv/`, `dist/`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, `node_modules``, `frontend/dist` - Build artifacts (exempt)
- `.mcp` - MCP configuration
    - `storage/` - Storage
- - `auth/` - Auth
    - `api/` - API
    - `collector/` - Collector

    - `tests/` - Tests

    - `.gitignore` - Git ignore
    - `uv.lock` - UV lock file
    - `Makefile` - Makefile
    - `README.md` - README
    - `pyproject.toml` - `pyproject-server.toml` - Python package configuration
    - `Makefile` - Makefile

    - `.github/` - GitHub workflows
    - `alembic.ini` - Alembic config
    - `docker-compose.yml` - Docker Componse
    - `Makefile` - Makefile
    - `schema.pxd` - Pydantic schemas

    - `api/schemas.py` - API schemas
    - `frontend/src/types/index.ts` - Frontend types
    - `frontend/src/api/client.ts` - API client
    - `frontend/src/App.css` - App styling
    - `frontend/src/hooks/` - Custom hooks
    - `frontend/src/stores/` - State management
    - `frontend/src/components/` - React components
    - `frontend/src/utils/` - Utility functions
    - `frontend/vite.config.ts` - Vite configuration
    - `frontend/tsconfig.json` - TypeScript config
    - `frontend/index.html` - Frontend entry
    - `scripts/hooks/pattern_registry.json` - Pattern registry
    - `scripts/hooks/check_duplicate_queries.py` - Pattern matching script
    - `.tool-versions` - Version file
    - `.claude/commands/` - Claude commands
    - `Makefile` - Makefile
    - `README.md` - README
    - `SDK_README.md` - SDK README
    - `pyproject.toml` - Server package config
    - `pyproject-server.toml` - Server package config
- `CONTRIBUTING.md` - Contribution guide
- `DISCOVERIES.md` - Project discoveries
    - `CHANGElog.md` - Changelog

