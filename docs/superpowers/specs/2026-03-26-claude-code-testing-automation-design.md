# Claude Code Testing Automation

**Date**: 2026-03-26
**Status**: Approved

## Context

The repo has solid CI (ruff, pytest, pip-audit, gitleaks) and good Claude Code tooling (hooks for make-check, /quality command, /pre-release command), but lacks:

- A fast way to run *only* the tests relevant to what changed
- A unified local security testing command
- Any frontend testing framework or tests

This spec adds three Claude Code automation primitives: a `/test` command for targeted test runs, a `/test-security` command for security validation, and Vitest setup with smoke tests for the frontend.

## Design

### 1. `/test` Slash Command

**File**: `.claude/commands/test.md`

A targeted test runner that maps changed files to their test files and runs only those.

**Behavior**:
1. Collect changed files via `git diff --name-only` and `git diff --cached --name-only`
2. For each changed `.py` file, find the corresponding test:
   - `agent_debugger_sdk/core/foo.py` → `tests/test_foo.py`
   - `api/routes/bar.py` → `tests/test_bar.py`
   - Fallback: run tests from the same subdirectory under `tests/`
3. Run `python3 -m pytest -q <identified-tests>`
4. If no tests found for changed files, run the full suite
5. Support optional args: `--full` (entire suite), `--integration` (include integration tests)

### 2. `/test-security` Slash Command

**File**: `.claude/commands/test-security.md`

Runs all security-focused checks in one command.

**Checks** (run in parallel where possible):
1. `bandit -r agent_debugger_sdk api storage auth redaction collector -f screen` — Python security lint
2. `python3 -m pytest tests/test_redaction_security.py -q` — Redaction edge cases
3. `python3 -m pytest tests/ -k "auth" -q` — Auth tests
4. `pip-audit -r pyproject.toml --desc` — Dependency vulnerability check

**Output**: Table with PASS/FAIL per check and actionable items for failures.

### 3. Frontend Testing with Vitest

**Setup**:
1. Install: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`
2. Add `frontend/vitest.config.ts` with jsdom environment and path aliases matching Vite config
3. Add `npm run test` and `npm run test:watch` scripts to `frontend/package.json`
4. Create `frontend/src/__tests__/` with initial smoke tests

**Initial smoke tests**:
- `App.test.tsx` — App renders without crashing
- `api-client.test.ts` — API client exports expected functions
- `types.test.ts` — Type exports match expected surface

**`/test-frontend` slash command**: `.claude/commands/test-frontend.md`
- Runs `cd frontend && npm run test -- --reporter=verbose`
- Reports pass/fail summary

### New Dependencies

**Python**: `bandit` (dev dependency)
**Frontend**: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`

## Files to Create/Modify

| File | Action |
|------|--------|
| `.claude/commands/test.md` | Create |
| `.claude/commands/test-security.md` | Create |
| `.claude/commands/test-frontend.md` | Create |
| `frontend/vitest.config.ts` | Create |
| `frontend/src/__tests__/App.test.tsx` | Create |
| `frontend/src/__tests__/api-client.test.ts` | Create |
| `frontend/src/__tests__/types.test.ts` | Create |
| `frontend/package.json` | Modify (add deps + scripts) |
| `pyproject.toml` | Modify (add bandit dev dep) |

## Verification

1. `/test` — make a small Python edit, run `/test`, confirm only relevant tests run
2. `/test-security` — run command, confirm all 4 checks execute with PASS/FAIL output
3. `/test-frontend` — run command, confirm vitest executes smoke tests
4. Full validation: run `/quality` to confirm nothing is broken
