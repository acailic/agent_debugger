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
  - `hosted auth gate` = `api/dependencies.py:72` `require_hosted_auth`
    (valid Bearer key required in cloud mode; no-op in local mode — used by
    routes whose backing store has no tenant dimension).
  - `collector resolver` = `collector/server.py:161` `_get_tenant_id` (local
    mode requires a localhost client; otherwise
    `auth/middleware.py:41` `get_tenant_from_api_key`, which rejects a
    missing header with 401).
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
| GET /api/analytics | api/analytics_routes.py:113 | `hosted auth gate` (:117) — closed since (see below) | **no — local-only store** (api/analytics_db.py:10-13), documented open limitation | none (reads analytics.db) |
| POST /api/analytics/events | api/analytics_routes.py:177 | `hosted auth gate` (:180) — closed since (see below) | **no** | analytics.db (api/analytics_db.py:73-96) |
| GET /api/analytics/patterns | api/analytics_routes.py:255 | `tenant repo` (:263) | yes — PatternRepository(repo.session, repo.tenant_id) (:273); repo contract storage/repositories/pattern_repo.py:18-21 | none |
| GET /api/analytics/patterns/{pattern_id} | api/analytics_routes.py:318 | `tenant repo` (:321) | yes (:329) | none |
| GET /api/analytics/health-report | api/analytics_routes.py:357 | `tenant repo` (:361) | yes (:376) | none |

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
| GET /api/sessions/{session_id}/stream | api/session_routes.py:195 | none (SSE fan-out from event buffer — redacted since Q08, see "Closed since") |
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

45, 101, 130, 158, 183, 219, 252, 294, 319, 354, 383, 410. All signatures use
`Depends(get_repository)`. CUSTOM_CONDITION predicates are validated at
creation time and rejected with 422 pre-mutation (api/stepper_routes.py:88-99
→ agent_debugger_sdk/core/stepper.py `AgentStepper.set_breakpoint`).

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

## Closed since: one redaction policy across sinks (W10 / Q08)

The redaction gap recorded below as "SSE fan-out is not redacted" is closed,
along with its siblings:

1. **Buffer/SSE fan-out now publishes the redacted event.** The collector
   publishes the exact object `_persist_event_if_configured` returned after
   applying the pipeline (collector/server.py, `_ingest_trace`), so storage
   and stream can no longer diverge. The in-process path
   (`api/services/ingestion.py:persist_event`) copies the redacted state
   back onto the caller's event before its first await, so the SDK emitter's
   concurrent `buffer.publish` streams the same redacted representation.
2. **Session config and checkpoint state/memory pass through the same
   policy** via `RedactionPipeline.scrub_payload` (a carrier event through
   `apply()` — no second policy format): collector session-create and
   checkpoint ingest (collector/server.py) and the in-process persisters
   (api/services/ingestion.py).
3. **Event metadata joined the scrub path**: `_build_event_payload` now
   includes `metadata` alongside `data` and typed fields; structural base
   fields (id, session_id, parent linkage, timestamps) stay excluded so
   trace linkage survives redaction (redaction/pipeline.py).
4. **`from_config` wiring** maps `redact_pii` /
   `redact_tool_payloads` from the SDK config when present, else from
   `AGENT_DEBUGGER_REDACT_PII` / `AGENT_DEBUGGER_REDACT_TOOL_PAYLOADS`
   (defaults off; `redact_prompts`/`max_payload_kb` as before). With
   `redact_pii` on, the scrub now also applies the secret patterns
   (`SECRET_PATTERNS`) that were defined but never wired in.

Documented exception: original in-memory objects the caller keeps outside
the persist/stream path (e.g. a running agent's live `Session.config`, or
the SDK's pre-redaction in-memory event store) may remain unredacted; every
persisted or streamed copy is scrubbed. Regression gate:
`tests/test_redaction_boundary.py`. Manual audit artifact:
`scripts/scan_redaction_sinks.py SESSION_ID MARKER...` scans the sessions/
events/checkpoints rows (config, data, event_metadata, state, memory) plus
a captured SSE stream and exits nonzero if a marker survives.

## Closed since: hosted auth hardening (W10 / Q06 remainder, second slice)

The two security gaps recorded below as "missing-key behavior in hosted
mode" and "unauthenticated analytics reads" are closed:

1. **Absent API key no longer falls back to the `local` tenant in cloud
   mode.** `auth/middleware.py:61-70` `get_tenant_from_api_key` now raises
   401 ("Authorization header required") when the Authorization header is
   absent, instead of returning `"local"`. The helper is only reached in
   cloud mode — both callers (`api/dependencies.py:24` `get_tenant_id` and
   `collector/server.py:161` `_get_tenant_id`) resolve keyless local traffic
   to the `local` tenant themselves when `config.mode == "local"`, so
   loopback single-user mode stays keyless. Regression gates:
   `tests/test_hosted_tenant_matrix.py::test_hosted_invalid_and_absent_key_behavior`
   (401 on reads, session creation and trace ingestion without a key) and
   `tests/test_auth_middleware_unit.py::test_get_tenant_from_api_key_rejects_missing_header`.
2. **Analytics route exposure is authenticated in hosted mode.**
   `GET /api/analytics` and `POST /api/analytics/events` take the new
   mode-conditional gate `api/dependencies.py:72` `require_hosted_auth` — a
   valid Bearer key is required in cloud mode (401 on missing/invalid
   keys), while local mode remains fully open keyless. Route paths and
   response shapes are unchanged. Regression gates:
   `tests/test_hosted_tenant_matrix.py::test_hosted_analytics_routes_require_a_key`
   and `tests/test_hosted_tenant_matrix.py::test_local_mode_analytics_stay_fully_open`.

Related hardening in the same slice (Q07 remainder): CUSTOM_CONDITION
breakpoint predicates are validated pre-mutation at every materialization
boundary (`AgentStepper.set_breakpoint` / `import_state`,
agent_debugger_sdk/core/stepper.py) and the API returns 422 naming the
unsupported construct; the predicate interpreter's runtime bounds (AST
nodes, exponents, symmetric sequence-repetition and concatenation length
caps) are documented in `validate_custom_condition` and pinned by
`tests/test_breakpoint_safety.py::TestBoundedEvaluation` /
`TestPreMutationValidation` plus route-level
`tests/test_stepper_route_conditions.py`.

## Known-open gaps (documented, intentionally not fixed here)

1. **Analytics store is local-only and not tenant-isolated.** Route
   *exposure* is now authenticated in hosted mode (see "Closed since"
   above), but the store itself remains a separate SQLite file with no
   `tenant_id` dimension (api/analytics_db.py:10-13,
   storage/repositories/analytics_repo.py), so authenticated tenants share
   one local analytics dataset, and tenant-authenticated routes still write
   usage counters into it (e.g. replay_started, api/replay_routes.py:64).
   Pinned by
   `tests/test_hosted_tenant_matrix.py::test_hosted_analytics_routes_require_a_key`
   (valid keys share the same store).
2. **Redaction policy remains opt-in per deployment.** The boundary is now
   uniform (see "Closed since" above), but the pipeline only scrubs when the
   deployment enables it (`AGENT_DEBUGGER_REDACT_PROMPTS` /
   `AGENT_DEBUGGER_REDACT_PII` / `AGENT_DEBUGGER_REDACT_TOOL_PAYLOADS`, or
   the corresponding SDK config fields); a deployment that configures no
   policy still stores and streams raw payloads. Additionally, the SDK
   `Config` object does not yet carry `redact_pii`/`redact_tool_payloads`
   fields — those are environment-only until the SDK grows them (SDK changes
   out of scope for Q08).
3. **The e2e suite never runs the server in cloud mode.**
   tests/e2e/conftest.py starts uvicorn without any mode/key environment, so
   the server resolves every caller as tenant `local` and the suite proves
   transport, not auth enforcement. The in-process hosted fixture in
   `tests/test_hosted_tenant_matrix.py` covers the gap at the ASGI layer; a
   real-process hosted e2e (uvicorn subprocess in cloud mode) remains open.
4. **Checkpoint event/session consistency.** `POST /api/checkpoints`
   verifies the parent session is visible to the caller's tenant, but
   `storage/repositories/checkpoint_repo.py` still copies the supplied event
   ID without checking that the event belongs to the checkpoint's session.
