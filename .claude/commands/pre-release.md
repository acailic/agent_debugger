# Pre-Release Validation (Dry Run)

Run a dry-run release readiness check for this repo. Do not create or push tags.

Ground the validation in the actual release flow in `.github/workflows/publish.yml`.

## Run All Checks

Run independent checks in parallel where possible.

### 1. Python Lint

```bash
ruff check .
```

### 2. Python Tests

```bash
python3 -m pytest -q
```

Capture the summary line.

### 3. Frontend Build

```bash
cd frontend && npm run build
```

### 4. SDK Build

```bash
python3 -m build
```

This validates the root `pyproject.toml` packaging path used for `sdk-v*` and `v*` tags.

### 5. Server Release Inputs

Validate that the server release inputs exist and look ready:

- `pyproject-server.toml`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/dist` is not required ahead of time, but the frontend build in step 3 must pass

Do not permanently modify `pyproject.toml` during this dry run.

### 6. Git Working Tree Clean

```bash
git status --porcelain
```

PASS only if empty.

### 7. On Main Branch

```bash
git branch --show-current
```

PASS only if the branch is `main`.

### 8. Up To Date With Remote

```bash
git fetch origin main
git rev-list HEAD..origin/main --count
```

PASS only if the count is `0`.

## Summary Scorecard

Output this exact format:

```text
=== Pre-Release Validation Scorecard ===

  Lint (ruff check)       : PASS or FAIL
  Tests (pytest)          : PASS or FAIL — {summary line}
  Frontend build          : PASS or FAIL
  SDK build               : PASS or FAIL
  Server release inputs   : PASS or FAIL
  Git status clean        : PASS or FAIL
  On main branch          : PASS or FAIL — {branch name}
  Remote up-to-date       : PASS or FAIL

  Overall: READY TO RELEASE  or  NOT READY ({N} check(s) failed)
```

If READY TO RELEASE, say the repo is ready for `/release`.

If NOT READY, list exactly what must be fixed.
