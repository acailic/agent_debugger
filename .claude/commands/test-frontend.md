# Frontend Test Runner

Run the Vitest frontend test suite.

## Args

- `$ARGUMENTS` — optional: `--watch` for watch mode, `--coverage` for coverage report

## Steps

### 1. Check if Vitest is installed

```bash
cd frontend && npx vitest --version 2>/dev/null
```

If not installed, run:

```bash
cd frontend && npm install
```

### 2. Run tests

If `$ARGUMENTS` contains `--watch`:

```bash
cd frontend && npx vitest --reporter=verbose
```

If `$ARGUMENTS` contains `--coverage`:

```bash
cd frontend && npx vitest run --reporter=verbose --coverage
```

Otherwise:

```bash
cd frontend && npx vitest run --reporter=verbose
```

### 3. Report results

Print pass/fail summary with file-level breakdown.
