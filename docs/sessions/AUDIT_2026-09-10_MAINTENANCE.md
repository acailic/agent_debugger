# 🔧 Maintenance Session — Autonomous Investigation & Fixes

**Date:** 2026-09-10
**Duration:** 1 extended autonomous session
**Scope:** Find best places to fix / improve / reorganize without changing product ideas; verify everything functions.
**Baseline before changes:** ruff clean · 3153 Python tests passing · 366 frontend tests passing · frontend build green.

---

## 🐛 Real bugs found and fixed

### 1. Every SDK session update was rejected with 422 (HIGH)

**Symptom:** After each recorded event, the SDK sends `PUT /api/sessions/{id}` to persist
counters/status/`ended_at`. Every one of these returned `422 Unprocessable Entity` — the SDK
logged "Permanent error" warnings and moved on. Result: sessions stuck at `status="running"`,
`ended_at` never set, token/cost/tool-call/error counters never updated (23 such rows in the
local demo DB).

**Root cause chain:**
1. `TraceContext` class defaults were `agent_name=""` and `framework=""` (empty strings).
2. The collector's create schema (`collector/server.py::SessionCreate`) accepts empty strings.
3. `api/schemas_core.py::SessionUpdateRequest` demanded `min_length=1` for the same fields —
   so the create succeeded and every subsequent update failed. Validation asymmetry between
   two endpoints of the same resource.

**Fixes:**
- `api/schemas_core.py`: dropped `min_length=1` on `agent_name`/`framework` in
  `SessionUpdateRequest` (PUT now accepts exactly what POST accepts).
- `agent_debugger_sdk/core/context/trace_context.py`: class defaults changed to
  `agent_name="agent"`, `framework="custom"` — matching `simple.trace_session`'s own
  defaults, so no new convention was introduced.

**Verification:** fresh server + `examples/01_hello.py` → session lands as
`status=completed`, `ended_at` set, `tool_calls=1`, **zero** 422s in the server log
(previously 6+ per run).

### 2. Frontend called a nonexistent endpoint (MEDIUM)

`getCausalAnalysis()` in `frontend/src/api/client.ts` called `GET /api/sessions/{id}/causal`,
which does not exist. The backend serves the identical payload at
`GET /api/sessions/{id}/failures/causes` (`api/research_routes.py`). The function is
currently dead code in the UI (see findings below), but shipped broken. Path corrected to
`/failures/causes`.

### 3. Frontend `EventType` union missing `'drift'` (LOW)

The SDK enum (`agent_debugger_sdk/core/events/base.py`) includes `DRIFT = "drift"`;
`frontend/src/types/index.ts` did not. Added. The unions now match exactly
(`trace_root` remains frontend-only — it is synthesized by `collector/replay.py`).

### 4. Example 01 quick-start was false (MEDIUM)

`examples/01_hello.py` claimed `init()` "connects to http://localhost:8000 by default".
In reality, without an `api_key` the SDK wires no HTTP transport and persists nothing
anywhere — a user following the quick start saw an empty UI. Aligned the example with the
pattern used by all other examples (`init(api_key="local-dev", endpoint=...)`) and fixed the
wrong script filename in the docstring (`hello_agent.py` → `01_hello.py`). Verified
end-to-end against a live server.

### 5. Migration ↔ model schema drift (LOW)

Fresh DBs created via Alembic (the production path) marked 40+ columns nullable while
`storage/models.py` declares them NOT NULL (SQLAlchemy infers from non-Optional `Mapped[]`).
All affected columns carry defaults, so there was no data-loss risk — but the two
schema-creation paths disagreed. Added `nullable=False` to the affected columns in
migrations `001` and `003` (005/006/007 were already correct). A programmatic
migrations-vs-`Base.metadata.create_all` comparison now reports **exact parity** on tables,
columns, types, and nullability. Existing DBs are unaffected; fresh DBs get the intended
constraints. Full e2e suite (46 tests, real uvicorn + real SQLite via migrations) passes.

### 6. Orphaned changelog entry (LOW)

`CHANGELOG_ENTRY.md` was a leftover v0.1.4 release entry referenced by nothing, whose
content was absent from `CHANGELOG.md`. The 0.1.4 section was folded into `CHANGELOG.md`
(chronological order preserved) and the stray file deleted.

---

## ✅ Verified functioning (no changes needed)

- **Environments:** `.venv-ci` editable install resolves to the working tree
  (`/home/nistrator/Documents/github` is a symlink to the same storage — same inodes).
- **Full test suites:** 3153 Python tests (incl. 46 full-stack e2e), 366 frontend tests,
  ruff, tsc, eslint, frontend build, `scripts/check_api_contract.py`, vulture dead-code gate.
- **Live server smoke:** health, sessions list/detail/trace/analysis/audit/safety/live/
  swimlane/replay/evidence-graph/divergence, analytics, cost, alerts, alert-policies,
  violations (dashboard/sparse), clusters, entities, auth keys, compare, search — all 200.
- **SDK→API ingestion roundtrip** with events round-tripping correctly.
- **Packaged UI** served from `/ui/` with current asset hashes.
- **Migrations** apply cleanly head-to-head on a fresh DB.
- **Repo hygiene:** no tracked build artifacts; `.coverage`/`dist`/venvs properly ignored.
- CI workflows (`ci.yml`, `publish.yml`) match the documented commands and tag scheme.

---

## 📋 Documented, deliberately NOT changed (product decisions)

1. **Seven never-mounted frontend panels:** `CausalAnalysisPanel`, `ReasoningEditorPanel`,
   `RedundancyPanel`, `SafetyPanel`, `StepperPanel`, `SwimlanePanel`, `ViolationPanel` —
   built, typed, tested at the client layer, but never imported by any view in any commit.
   The matching backend endpoints and client functions all exist. Wiring them into the UI
   (or removing them) is a product-surface decision.
2. **17 of 72 exported client functions unused** (`searchSessions`, alert-policy CRUD,
   scenario/branch/stepper/swimlane/coordination helpers, …). Same category as above.
3. **46 backend routes not called by the UI** — most are legitimately SDK/CLI-facing
   (ingestion, auth, checkpoints, entities, research frames). Listed in the session notes.
4. **`scripts/check_api_contract.py`** compares schema fields but not the `EventType` enum
   union nor route existence — both of this session's contract bugs would have slipped past
   it. Extending it is worthwhile future work.

## 🧹 Cleanup

- Removed untracked `liveportrait-server/` (contained only stale `__pycache__`).
- Local demo DB restored to its pre-session seeded state after smoke testing.

## 📁 Files changed

| File | Change |
|---|---|
| `api/schemas_core.py` | `SessionUpdateRequest`: drop `min_length=1` on agent_name/framework |
| `agent_debugger_sdk/core/context/trace_context.py` | Non-empty `agent_name`/`framework` defaults |
| `frontend/src/api/client.ts` | `getCausalAnalysis` → `/sessions/{id}/failures/causes` |
| `frontend/src/types/index.ts` | `EventType` += `'drift'` |
| `examples/01_hello.py` | Working init pattern + correct filename in quick-start |
| `storage/migrations/versions/001_initial_schema.py` | `nullable=False` alignment (26 columns) |
| `storage/migrations/versions/003_add_research_features.py` | `nullable=False` alignment (14 columns) |
| `CHANGELOG.md` / `CHANGELOG_ENTRY.md` | Fold v0.1.4 entry in; delete stray file |

**Post-change validation:** ruff clean · 3153 + 366 tests passing · frontend build green ·
live end-to-end run with zero error responses.
