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
   - Show error output (truncate >50 lines: first 20, last 20, with count)
   - Show remediation suggestion (see below)
   - Stop immediately
4. On all success: Print summary with timings

## Failure Remediation

| Check | Suggestion |
|-------|------------|
| Lint | "Fix lint errors above. Run `ruff check . --fix` for auto-fixable issues." |
| Security | "Review security findings above. Add `# nosec` comments only if justified." |
| Tests | "Fix failing tests. Run `pytest -v` for verbose output." |
| Frontend | "Fix TypeScript/build errors above. Check `frontend/src/` for issues." |

## Error Output Truncation

- If error output ≤ 50 lines: show full output
- If error output > 50 lines: show first 20 lines, `... N lines omitted ...`, last 20 lines

## Missing Dependencies

If a tool is not installed, show:
- bandit: `⚠ bandit not found. Install with: pip install bandit`
- npm: `⚠ npm not found. Ensure Node.js is installed.`

## Output Format

```
🔍 Running release check...

1/4 Lint (ruff)............ ✓ (0.5s)
2/4 Security (bandit)...... ✓ (1.2s)
3/4 Tests (pytest)........ ✓ (12.3s)
4/4 Frontend build........ ✓ (3.1s)

✓ Release check passed. Ready to ship.
```

## Example Failure Output

```
🔍 Running release check...

1/4 Lint (ruff)............ ✓ (0.5s)
2/4 Security (bandit)...... ✗ (1.2s)

Finding: [MEDIUM] Use of assert detected (security issue)
Location: tests/test_example.py:42

... 15 lines omitted ...

Review security findings above. Add `# nosec` comments only if justified.
```