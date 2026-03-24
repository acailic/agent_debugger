# Refactor: Two-Phase Code Improvement

Target: $ARGUMENTS

If the target is empty, ask the user which file or module to refactor and wait.

First determine whether the target is:

- Python/backend: `agent_debugger_sdk/`, `api/`, `collector/`, `storage/`, `auth/`, `redaction/`, `tests/`
- Frontend: `frontend/`

## Phase 1 — Automated Cleanup

### For Python targets

Run:

1. `ruff check --fix $ARGUMENTS`
2. `ruff format $ARGUMENTS`
3. `git diff --stat -- $ARGUMENTS`

### For frontend targets

Run:

1. derive the path relative to `frontend/`, then run `cd frontend && npx eslint --fix <relative-path>` if ESLint is available
2. `cd frontend && npm run build`
3. `git diff --stat -- $ARGUMENTS`

If the eslint step is unavailable or fails because the tool is not installed, note it and continue instead of stopping.

Report what changed in Phase 1.

## Phase 2 — Repo-Aware Refactor Review

Read the target in full plus the closest related tests and callers. Then analyze the following.

### 1. Dead Code and Unused Paths

- unused functions, helpers, imports, props, or branches
- stale event types or fields that no longer match API/frontend contracts

### 2. Complexity Hotspots

- functions or components that are too large
- deep nesting
- duplicated event-shape branching
- logic that should be moved out of routes, components, or render blocks

### 3. Naming and Consistency

- Python: snake_case functions/modules, PascalCase classes
- React: PascalCase components, prop/type naming consistency
- match existing repo conventions before proposing renames

### 4. Coupling and Boundary Issues

- API routes doing service/domain work
- frontend components re-deriving server logic
- SDK internals leaking directly into API or UI boundaries
- event/schema changes that should be centralized in `api/schemas.py` and `frontend/src/types/index.ts`

### 5. Refactor Candidates

Propose concrete steps such as:

- extract helper/service/module
- tighten a boundary
- split a component
- replace ad hoc dict shapes with typed structures
- add or move tests

## Output Format

Group findings by category. For each finding:

- file and symbol
- what is wrong
- why it matters
- concrete refactor proposal

Do not apply Phase 2 changes automatically. Ask the user which proposed refactors to implement.
