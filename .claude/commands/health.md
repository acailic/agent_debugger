# Project Health Dashboard

Run a repo-aware health check for Peaky Peek and present a concise scorecard. No arguments needed.

Run independent checks in parallel when possible. Ignore generated directories such as `.venv*`, `frontend/node_modules`, `frontend/dist`, `dist`, `.pytest_cache`, `.ruff_cache`, and `traces/`.

## 1. Python Quality

Run from the project root:

```bash
ruff check .
python3 -m pytest -q
```

Report:

- lint pass/fail and total rule violations by category
- test pass/fail and the summary line
- failing test names with a one-line failure summary

## 2. Frontend Build

Run:

```bash
cd frontend && npm run build
```

Report pass/fail. If it fails, capture the first meaningful error.

## 3. Git Hygiene

Check:

- `git status --short`
- `git log @{upstream}..HEAD --oneline 2>/dev/null`
- `git rev-list --left-right --count HEAD...origin/main 2>/dev/null`

Report:

- whether the working tree is clean
- whether there are local commits not pushed
- ahead/behind counts versus `origin/main` when available
- suspicious untracked files that probably should not be committed

## 4. Dependency Drift

Python:

- read direct dependencies from `pyproject.toml` and `pyproject-server.toml`
- run `pip list --outdated --format=columns`
- report only outdated direct dependencies

Frontend:

- run `cd frontend && npm outdated`
- if it errors because dependencies are not installed, say so explicitly
- otherwise report current vs wanted vs latest versions

## 5. Contract Drift Heuristic

Inspect these files together if they exist:

- `api/schemas.py`
- `frontend/src/types/index.ts`
- `frontend/src/api/client.ts`

Flag obvious mismatches in session, event, replay, or live-summary shapes. This is especially important if event types or API fields appear in one side but not the other.

## 6. Coverage Gaps

Do a quick name-based heuristic for public Python interfaces in:

- `agent_debugger_sdk/`
- `api/`

Search `tests/` and `tests/auto_patch/` for references. Group likely-uncovered public symbols by module. Do not run a full coverage tool.

## 7. Security Quick Scan

Scan non-generated files for:

- hardcoded secrets such as `password=`, `secret=`, `api_key=`, `token=`
- debug flags left enabled
- permissive CORS defaults
- tracked `.env` files or similar secrets artifacts

Call out exact files for anything suspicious.

## Output Format

Present results as a table:

| Category | Status | Details |
|----------|--------|---------|

Status values:

- GREEN: clean
- YELLOW: warning or follow-up needed
- RED: failing or risky

After the table, add **Actionable Next Steps** as a numbered list ordered by severity.
