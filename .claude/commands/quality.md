# Quality Gate: Pre-Merge Readiness Check

Run the repo-aware merge gate and produce a final pass/warn/fail summary.

Start by collecting changed files from both staged and unstaged diffs:

- `git diff --name-only`
- `git diff --cached --name-only`

Split the changes into backend, frontend, and docs/other buckets before deciding what to inspect more deeply.

## 1. Baseline Checks

Always run:

- `ruff check .`
- `python3 -m pytest -q`

If any files under `frontend/` changed, also run:

- `cd frontend && npm run build`

Report pass/fail and key failure details.

## 2. Changed-File Review

Read the changed source files and review them with repo context:

- backend and SDK files under `agent_debugger_sdk/`, `api/`, `collector/`, `storage/`, `auth/`, `redaction/`
- frontend files under `frontend/src/`

Look for:

- broken contracts
- missing edge-case handling
- type mismatches or weak typing
- overly large functions or components
- suspicious TODO/FIXME/HACK comments

Verdict rules:

- **PASS**: no meaningful issues found
- **WARN**: minor maintainability or typing issues
- **FAIL**: likely bug, regression, broken contract, or missing guardrail

## 3. Contract Boundary Review

If any of these files changed, inspect them together:

- `api/schemas.py`
- `frontend/src/types/index.ts`
- `frontend/src/api/client.ts`
- any route file in `api/`
- event definitions or serializers in `agent_debugger_sdk/`

Flag mismatches in shape, naming, nullability, or event coverage.

## 4. Coverage Gaps on Changed Code

For changed Python modules:

- identify public functions/classes
- search `tests/` and `tests/auto_patch/` for matching references
- flag likely missing tests

For changed frontend modules:

- note whether the behavior is exercised only indirectly
- flag risky UI logic changes that lack any obvious verification path

## 5. Recent Hot Spots

Use `git log --oneline -20` and recent changed paths to identify hot areas. Read the top 3 most-active relevant files and call out code smells or risky patterns.

## Final Summary

Output:

```text
| Check              | Verdict | Details                          |
|--------------------|---------|----------------------------------|
| Baseline Checks    | PASS    | ruff, pytest, frontend build     |
| Changed-File Review| WARN    | minor issues in X and Y          |
| Contract Boundary  | PASS    | API and frontend types aligned   |
| Coverage Gaps      | FAIL    | missing tests for public API Z   |
| Hot Spot Review    | PASS    | no major concerns                |
|--------------------|---------|----------------------------------|
| OVERALL            | WARN    | add tests before merging         |
```

`OVERALL` is:

- `PASS` only if every check is `PASS`
- `WARN` if at least one check is `WARN` and none are `FAIL`
- `FAIL` if any check is `FAIL`

After the table, add **Actionable Items** ordered by priority.
