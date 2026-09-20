# Hosted-mode route inventory (auth, tenant scoping, sinks)

Complete inventory of every HTTP route mounted by `api/main.py:create_app()`
(collector router included), produced for roadmap **W10 — enforced data
boundaries and safe remote operation** (first slice). Evidence is given as
`file:line` against the working tree of this slice.

Related artifacts:

- Two-tenant regression matrix: `tests/test_hosted_tenant_matrix.py`
- Closed in this slice: the `/api/clusters` hard-coded local tenant and the
  unverified checkpoint parent-session ownership (see "Closed in this slice").

## How to read the table

- **Auth**: the dependency chain that resolves the caller.
  - `tenant repo` = `api/dependencies.py:54` `get_repository` (→ `get_db_session`
    `api/dependencies.py:18` + `get_tenant_id` `api/dependencies.py:24`).
  - `tenant entity repo` = `api/dependencies.py:62` `get_entity_repository`.
  - `tenant policy repo` = `api/policy_routes.py:18` (uses `get_tenant_id`).
  - `collector resolver` = `collector/server.py:161` `_get_tenant_id` (local
    mode requires a localhost client; otherwise
    `auth/middleware.py:41` `get_tenant_from_api_key`).
  - `none` = no authentication or tenant resolution at all.
- **Tenant store**: whether every underlying query/mutation is scoped to the
  resolved tenant. All `TraceRepository` sub-repositories filter on
  `tenant_id` (`storage/repository.py:48-68`; e.g. sessions
  `storage/repositories/session_repo.py:71-76`, checkpoints
  `storage/repositories/checkpoint_repo.py:63-72`).
- **Sinks**: databases/stores the route can write. `analytics.db` is the
  separate local-only SQLite file (`api/analytics_db.py:39-50`). The event
  buffer is the in-process/Redis fan-out used by SSE.

## Ingestion (collector/server.py, router prefix /api)

| Route | Evidence | Auth | Tenant store | Sinks |
|---|---|---|---|---|
| POST /api/traces | collector/server.py:303 | collector resolver (:293) | yes — ownership check `get_session` before write, collector/server.py:207-212 | events table; session.error counters (storage/repository.py:199-217); event buffer publish (collector/server.py:298) |
| POST /api/sessions | collector/server.py:354 | collector resolver (:327) | yes — repo scoped to resolved tenant (:328); explicit ids rejected in hosted mode (:178-188) | sessions table |
| POST /api/checkpoints | collector/server.py:375 | collector resolver (:400) | yes — parent-session ownership check (:405-409, added this slice) | checkpoints table |
| GET /api/health | collector/server.py:415 | none | n/a | none |

## System / UI

| Route | Evidence | Auth | Tenant store | Sinks |
|---|---|---|---|---|
| GET /health | api/system_routes.py:16 | none | n/a | none (read-only `SELECT 1` connectivity probe) |
| GET / | api/ui_routes.py:15 | none | n/a | none (static UI) |
| GET /api/version | api/main.py:165 | none | n/a | none |

## Auth (prefix /api/auth)

| Route | Evidence | Auth | Tenant store | Sinks |
|---|---|---|---|---|
| POST /api/auth/keys | api/auth_routes.py:36 | `get_tenant_id` | yes — key bound to caller tenant (auth/service.py:19-46) | api_keys table |
| GET /api/auth/keys | api/auth_routes.py:61 | `get_tenant_id` | yes — filtered `tenant_id == caller` (auth/service.py:49-68) | none |
| DELETE /api/auth/keys/{key_id} | api/auth_routes.py:81 | `get_tenant_id` | yes — lookup constrained to caller tenant (auth/service.py:71-95) | api_keys table (deactivate) |

## Analytics

| Route | Evidence | Auth | Tenant store | Sinks |
|---|---|---|---|---|
| GET /api/analytics | api/analytics_routes.py:113 | **none (open gap)** | **no — local-only store** (api/analytics_db.py:10-13) | none (reads analytics.db) |
| POST /api/analytics/events | api/analytics_routes.py:174 | **none (open gap)** | **no** | analytics.db (api/analytics_db.py:73-96) |
| GET /api/analytics/patterns | api/analytics_routes.py:246 | `tenant repo` (:254) | yes — PatternRepository(repo.session, repo.tenant_id) (:264); repo contract storage/repositories/pattern_repo.py:18-21 | none |
| GET /api/analytics/patterns/{pattern_id} | api/analytics_routes.py:309 | `tenant repo` (:312) | yes (:320) | none |
| GET /api/analytics/health-report | api/analytics_routes.py:348 | `tenant repo` (:352) | yes (:367) | none |

## Sessions (api/session_routes.py)

All routes below use `Depends(get_repository)` (tenant repo) and gate
per-session access through `require_session`
(api/services/sessions.py:54-58 → tenant-scoped `get_session`,
storage/repositories/session_repo.py:71-76), which yields 404 for another
tenant's session id.

| Route | Evidence | Sinks |
|---|---|---|
| GET /api/sessions | api/session_routes.py:79 | none |
| GET /api/sessions/{session_id} | api/session_routes.py:98 | none |
| PUT /api/sessions/{session_id} | api/session_routes.py:107 | sessions table (:116-120) |
| DELETE /api/sessions/{session_id} | api/session_routes.py:124 | sessions + cascade tables (:129-131) |
| GET /api/sessions/{session_id}/traces | api/session_routes.py:135 | none |
| GET /api/sessions/{session_id}/tree | api/session_routes.py:150 | none |
| GET /api/sessions/{session_id}/checkpoints | api/session_routes.py:163 | none |
| GET /api/sessions/{session_id}/checkpoints/deltas | api/session_routes.py:176 | none |
| GET /api/sessions/{session_id}/stream | api/session_routes.py:195 | none (SSE fan-out from event buffer — see open gaps) |
| GET /api/sessions/{session_id}/export | api/session_routes.py:212 | none |
| POST /api/sessions/{session_id}/fix-note | api/session_routes.py:236 | sessions table (:243-245) |
| GET /api/sessions/{session_id}/similar-failures | api/session_routes.py:249 | none |
| GET /api/sessions/{session_id}/workflow-graph | api/session_routes.py:272 | none |
| GET /api/sessions/{session_id}/redundancy | api/session_routes.py:290 | none |

## Traces, analysis and alerts (api/trace_routes.py)

| Route | Evidence | Sinks |
|---|---|---|
| GET /api/sessions/{session_id}/trace | api/trace_routes.py:71 | sessions table (replay_value, :79-83) |
| GET /api/sessions/{session_id}/analysis | api/trace_routes.py:98 | sessions table (replay_value, :102-106) |
| GET /api/sessions/{session_id}/safety | api/trace_routes.py:115 | none |
| GET /api/sessions/{session_id}/live | api/trace_routes.py:143 | none |
| GET /api/traces/search | api/trace_routes.py:155 | none |
| GET /api/agents/{agent_name}/baseline | api/trace_routes.py:234 | none |
| GET /api/agents/{agent_name}/drift | api/trace_routes.py:249 | none |
| GET /api/sessions/{session_id}/alerts | api/trace_routes.py:325 | none |
| GET /api/alerts/summary | api/trace_routes.py:374 | none |
| GET /api/alerts/trending | api/trace_routes.py:396 | none |
| POST /api/alerts/bulk-status | api/trace_routes.py:418 | anomaly alerts (:435-438) |
| GET /api/alerts | api/trace_routes.py:449 | none |
| GET /api/alerts/{alert_id} | api/trace_routes.py:520 | none |
| PUT /api/alerts/{alert_id}/status | api/trace_routes.py:559 | anomaly alerts (:579-584) |

All of the above resolve `Depends(get_repository)` at the cited line's
function signature (tenant repo; alerts sub-repository is tenant-scoped,
storage/repository.py:67).

## Replay and checkpoints (api/replay_routes.py)

| Route | Evidence | Auth | Sinks |
|---|---|---|---|
| GET /api/sessions/{session_id}/replay | api/replay_routes.py:36 | `tenant repo` (:47) | analytics.db (replay_started / replay_highlights_used, :64, :100) |
| GET /api/checkpoints/{checkpoint_id} | api/replay_routes.py:136 | `tenant repo` (:139) | none — tenant join in storage/repositories/checkpoint_repo.py:63-72 |
| POST /api/checkpoints/{checkpoint_id}/restore | api/replay_routes.py:241 | `tenant repo` (:245) | sessions + events + checkpoints (all via tenant repo, :283-300) |

## Cross-session clustering (api/cross_session_routes.py)

| Route | Evidence | Auth | Sinks |
|---|---|---|---|
| GET /api/clusters | api/cross_session_routes.py:22 | `tenant repo` (:26) — **fixed in this slice** (previously a local `get_repository` hard-coding `tenant_id="local"`) | none |
| GET /api/clusters/{fingerprint}/sessions | api/cross_session_routes.py:97 | `tenant repo` (:100) | none |

## Comparison (api/comparison_routes.py) — all `tenant repo`, read-only

56 (compare), 310, 353, 389, 425 (divergence variants), 461 (baseline
divergence), 520 (divergence summary). Each signature uses
`Depends(get_repository)`.

## Cost (api/cost_routes.py) — all `tenant repo`, read-only

75 (summary), 106 (top-sessions), 126 (session cost).

## Search (api/search_routes.py) — all `tenant repo`, read-only

79 (GET /api/search), 119 (POST /api/search natural language).

## Entities (api/entity_routes.py) — all `tenant entity repo`, read-only

54 (entities), 83 (tools), 105 (errors), 127 (models), 148 (summary).
Tenant scoping via `EntityRepository(session, tenant_id)`
(api/dependencies.py:62-69; storage/repositories/entity_repo.py:25-34).

## Alert policies (api/policy_routes.py) — `tenant policy repo`

| Route | Evidence | Sinks |
|---|---|---|
| GET /api/alert-policies | api/policy_routes.py:26 | none |
| POST /api/alert-policies | api/policy_routes.py:63 | alert_policies (tenant-stamped, storage/repositories/policy_repo.py:21-32) |
| GET /api/alert-policies/{policy_id} | api/policy_routes.py:100 | none |
| PUT /api/alert-policies/{policy_id} | api/policy_routes.py:133 | alert_policies |
| DELETE /api/alert-policies/{policy_id} | api/policy_routes.py:180 | alert_policies |

## Reasoning editor (api/reasoning_routes.py) — `tenant repo` reads, no persistence

107 (edit), 160 (branch), 232 (replay), 280 (hierarchical), 321 (scenarios),
356 (scenario), 390 (compare), 427 (export), 462 (import). Each request
builds an ephemeral `ReasoningEditor` over tenant-scoped events
(api/reasoning_routes.py:132 et al.); edits/branches are request-scoped and
never persisted.

## Swimlanes (api/swimlane_routes.py) — `tenant repo`, read-only

32 (swimlane), 63 (messages), 98 (coordination-analysis), 135
(emergent-behaviors), 172 (multi-agent-analysis).

## Research (api/research_routes.py) — `tenant repo`, read-only

35 (frames), 56 (frames/tree), 82 (failure causes), 116 (similar failures),
157 (uncertainty), 180 (prediction intervals), 204 (risk assessment).

## Violations (api/violation_routes.py) — `tenant repo`, read-only

47 (cluster), 126 (search), 196 (sparse), 265 (detail), 287 (dashboard), 411
(session embedding), 436 (session similar).

## Stepper (api/stepper_routes.py) — `tenant repo` (module owned by another team)

45, 91, 120, 148, 173, 209, 242, 284, 309, 344, 373, 400. All signatures use
`Depends(get_repository)`.

## Closed in this slice

1. **`/api/clusters` hard-coded local tenant** — the module defined its own
   `get_repository()` returning `TraceRepository(session, tenant_id="local")`
   and also leaked the opened session (never closed). It now uses the shared
   `api.dependencies.get_repository` (api/cross_session_routes.py:13), so
   cluster queries are tenant-scoped; route paths and response shapes are
   unchanged. Regression gate:
   `tests/test_hosted_tenant_matrix.py::test_hosted_cross_session_clustering_isolated`.
2. **Checkpoint ingestion without parent-session ownership check** —
   `POST /api/checkpoints` now verifies the parent session is visible to the
   caller's tenant before writing (collector/server.py:405-409), mirroring
   the event path (collector/server.py:207-212). Legitimate callers are
   unaffected (the SDK always creates the session before checkpoints).
   Regression gate:
   `tests/test_hosted_tenant_matrix.py::test_hosted_checkpoint_write_and_read_isolated_no_mutation`.

## Known-open gaps (documented, intentionally not fixed here)

1. **Analytics store is local-only and unauthenticated.**
   `GET /api/analytics` and `POST /api/analytics/events`
   (api/analytics_routes.py:113, :174) carry no auth dependency, and the
   analytics store is a separate SQLite file with no `tenant_id` dimension
   (api/analytics_db.py:10-13, storage/repositories/analytics_repo.py).
   Additionally, tenant-authenticated routes write usage counters into this
   shared local store (e.g. replay_started, api/replay_routes.py:64). Pinned
   by `tests/test_hosted_tenant_matrix.py::test_hosted_analytics_route_is_local_only_open_gap`.
2. **Absent API key falls back to the `local` tenant in cloud mode.**
   `auth/middleware.py:61-62` returns `"local"` when the Authorization header
   is missing, so a hosted deployment admits unauthenticated callers as the
   `local` tenant instead of rejecting them. Pinned by
   `tests/test_hosted_tenant_matrix.py::test_hosted_invalid_and_absent_key_behavior`.
   Fixing this is owned by W10 ("missing-key behavior in hosted mode") and
   must not regress local single-user mode.
3. **SSE fan-out is not redacted.** The ingest path applies the redaction
   pipeline only to the persisted copy (`_persist_event_if_configured`,
   collector/server.py:202-203; `RedactionPipeline.apply` returns a deep
   copy, redaction/pipeline.py:54-58), while `buffer.publish` fans out the
   original event object (collector/server.py:298) and
   `GET /api/sessions/{id}/stream` serializes it verbatim
   (api/services/ingestion.py:117-171). In hosted mode a subscriber to a
   session they own can receive un-redacted payloads.
4. **The e2e suite never runs the server in cloud mode.**
   tests/e2e/conftest.py starts uvicorn without any mode/key environment, so
   the server resolves every caller as tenant `local` and the suite proves
   transport, not auth enforcement. The in-process hosted fixture in
   `tests/test_hosted_tenant_matrix.py` covers the gap at the ASGI layer; a
   real-process hosted e2e remains open.
