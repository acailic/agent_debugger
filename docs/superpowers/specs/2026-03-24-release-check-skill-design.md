# Release Check Skill Design

**Date**: 2026-03-24
**Status**: Draft
**Author**: Claude

## Summary

A Claude Code skill (`/release-check`) that validates codebase readiness for release by running a comprehensive suite of checks in sequence, failing fast on any error.

## Prerequisites

- Working directory must be repository root (contains `pyproject.toml`)
- Python environment with `ruff`, `pytest`, `bandit` installed
- Node.js environment with `npm` available

## Scope

| Check | Command | Purpose |
|-------|---------|---------|
| Lint | `ruff check .` | Python linting |
| Security | `bandit -r -ll agent_debugger_sdk api collector storage auth redaction` | Security vulnerability scan (medium severity and above) |
| Tests | `pytest -q` | All Python tests (unit, integration, e2e) |
| Frontend | `cd frontend && npm run build` | TypeScript compilation + Vite build |

**Note**: The `-ll` flag on bandit limits reporting to medium severity and above. Low severity findings are shown but do not fail the check.

## Execution Order

Sequential, fail-fast:

1. **Lint** — Fastest, catches syntax and style issues
2. **Security** — Static analysis, no runtime dependencies
3. **Tests** — All pytest tests (unit + integration + e2e)
4. **Frontend** — Build verification

Each step runs only if the previous step passed.

## Timeouts

| Check | Timeout | Reasoning |
|-------|---------|-----------|
| Lint | 60s | Should complete quickly |
| Security | 120s | Static analysis, bounded |
| Tests | 300s (5 min) | Integration/e2e may be slow |
| Frontend | 180s (3 min) | Build + TypeScript compilation |

If a command exceeds its timeout, the check fails with a timeout message.

## Behavior

### On Success

```
🔍 Running release check...

1/4 Lint (ruff)............ ✓ (0.5s)
2/4 Security (bandit)...... ✓ (1.2s)
3/4 Tests (pytest)........ ✓ (12.3s)
4/4 Frontend build........ ✓ (3.1s)

✓ Release check passed. Ready to ship.
```

### On Failure

- Stop immediately at the failing step
- Display the error output (truncated if > 50 lines: show first 20, last 20, with count)
- Show remediation suggestion
- Exit

### Remediation Suggestions

| Failure Type | Suggestion |
|--------------|------------|
| Lint | "Fix lint errors above. Run `ruff check . --fix` for auto-fixable issues." |
| Security | "Review security findings above. Add `# nosec` comments only if justified." |
| Tests | "Fix failing tests. Run `pytest -v` for verbose output." |
| Frontend | "Fix TypeScript/build errors above. Check `frontend/src/` for issues." |

### Error Output Truncation

- If error output ≤ 50 lines: show full output
- If error output > 50 lines: show first 20 lines, `... N lines omitted ...`, last 20 lines

### Missing Dependencies

If `bandit` is not installed:
```
⚠ bandit not found. Install with: pip install bandit
```

If frontend dependencies are missing:
```
⚠ Frontend dependencies missing. Run: cd frontend && npm install
```

### Frontend Build Artifacts

Running `npm run build` creates artifacts in `frontend/dist/`. This is expected behavior — no cleanup is performed. The artifacts are needed for production deployment.

## Skill Location

```
.claude/skills/release-check/SKILL.md
```

## SKILL.md Content

The skill file should contain the following instructions:

```markdown
---
name: release-check
description: Run full validation suite before release. Sequential lint, security scan, tests, and frontend build with fail-fast behavior.
---

# Release Check

Run pre-release validation checks in sequence.

## Checks

1. **Lint**: `ruff check .` (timeout: 60s)
2. **Security**: `bandit -r -ll agent_debugger_sdk api collector storage auth redaction` (timeout: 120s)
3. **Tests**: `pytest -q` (timeout: 300s)
4. **Frontend**: `cd frontend && npm run build` (timeout: 180s)

## Process

1. Verify working directory contains `pyproject.toml` (repo root)
2. Run each check in order, timing execution
3. On failure:
   - Show error output (truncate >50 lines)
   - Show remediation suggestion
   - Stop
4. On all success: Print summary with timings

## Failure Remediation

- Lint: "Run `ruff check . --fix` for auto-fixable issues."
- Security: "Review findings. Add `# nosec` only if justified."
- Tests: "Run `pytest -v` for verbose output."
- Frontend: "Check `frontend/src/` for TypeScript errors."

## Output Format

```
🔍 Running release check...

1/4 Lint (ruff)............ ✓ (0.5s)
2/4 Security (bandit)...... ✓ (1.2s)
3/4 Tests (pytest)........ ✓ (12.3s)
4/4 Frontend build........ ✓ (3.1s)

✓ Release check passed. Ready to ship.
```
```

## Why This Approach

- **Sequential order**: Lint first (fastest feedback), then security (fast), then tests (slower), then build (requires clean code)
- **Fail-fast**: Catches issues quickly without wasting time on later steps
- **No parallelization**: Simpler implementation, clearer output, still fast enough for pre-release use
- **Bandit with `-ll`**: Only fails on medium+ severity, avoiding noise from low-severity findings
- **Explicit timeouts**: Prevents hung commands from blocking indefinitely

## Future Considerations

- Optional `--skip` flag to skip individual checks (e.g., `--skip frontend`)
- Optional `--full` flag to add type checking (pyright) and dependency auditing (pip-audit)
- Integration with CI/CD for automated release gates
