# Release Check Skill Design

**Date**: 2026-03-24
**Status**: Draft
**Author**: Claude

## Summary

A Claude Code skill (`/release-check`) that validates codebase readiness for release by running a comprehensive suite of checks in sequence, failing fast on any error.

## Scope

| Check | Command | Purpose |
|-------|---------|---------|
| Lint | `ruff check .` | Python linting |
| Security | `bandit -r agent_debugger_sdk api collector storage auth redaction` | Security vulnerability scan |
| Tests | `pytest -q` | All Python tests (unit, integration, e2e) |
| Frontend | `cd frontend && npm run build` | TypeScript compilation + Vite build |

## Execution Order

Sequential, fail-fast:

1. **Lint** — Fastest, catches syntax and style issues
2. **Security** — Static analysis, no runtime dependencies
3. **Tests** — All pytest tests (unit + integration + e2e)
4. **Frontend** — Build verification

Each step runs only if the previous step passed.

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
- Display the full error output
- Suggest remediation steps
- Exit with non-zero status

### Missing Dependencies

If `bandit` is not installed:
```
⚠ bandit not found. Install with: pip install bandit
```

If frontend dependencies are missing:
```
⚠ Frontend dependencies missing. Run: cd frontend && npm install
```

## Skill Location

```
.claude/skills/release-check/SKILL.md
```

## Why This Approach

- **Sequential order**: Lint first (fastest feedback), then security (fast), then tests (slower), then build (requires clean code)
- **Fail-fast**: Catches issues quickly without wasting time on later steps
- **No parallelization**: Simpler implementation, clearer output, still fast enough for pre-release use
- **Bandit over pip-audit**: Catches code-level security issues, not just dependency vulnerabilities

## Future Considerations

- Optional `--full` flag to add type checking (pyright) and dependency auditing (pip-audit)
- Configurable timeout per step
- Integration with CI/CD for automated release gates
