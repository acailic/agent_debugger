# Changelog

All notable changes to Peaky Peek will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [0.6.0] - 2026-09-21

#### Scientific foundations, verified and wired in
- 17 new paper notes (docs/papers) verified against primary sources
  (arXiv/DOI/publisher records): systems classics (Zeller delta debugging,
  Weiser slicing, Tarantula SBFL, Dapper, rr, ROME), trust and safety
  science (Lee & See, Leveson STAMP, Reason, FreshQA, Liu et al.
  verifiability), and 2025-26 agent-failure research (MAST, TRAIL,
  tau-bench pass^k, AgentRewind, agentic fault taxonomy, Model-or-Harness);
  README Scientific Foundations reorganized into five pillars (32 notes),
  candidates digest with per-work verification in docs/research

#### Deterministic failure typing (STAMP + Model-or-Harness + MAST)
- first_bad_decision_detail on the where-it-failed answer: uca_type
  (omitted/wrong/mistimed/overlong — stale is formally mistimed),
  fault_side (model_produced/tool_returned/harness_recorded/undetermined),
  interaction_edge, and a derivation string naming the rule that fired;
  plus MAST mast_mode/mast_category typed from the paper's Appendix-A
  vocabulary (4 modes derivable from single-agent facts; unmapped is an
  honest value, never a guess)
- Reason active/latent split in the failure narrative:
  mechanism.latent_conditions from the completeness pass (missing events,
  orphaned parents, truncation, non-monotonic timestamps) plus
  stale-evidence/unsupported-claim/goal-drift conditions, with the active
  failure excluded; empty stays silent ("none found", never "none existed")
- Liu et al. verifiability measurement: claim_status_fractions on the
  audit report (all six statuses, counts + fractions + total) with a
  headline "Claim verification:" line in the summary markdown

#### Program slices (Weiser) over the evidence graph
- collector/audit/slices.py: backward_slice ("what fed this"), forward_slice
  ("what it fed"), damage_radius (forward slice from the first bad
  decision) — exact dynamic slices of one recorded execution ("what DID
  influence, in this run"), traversal only, edges never re-derived
- New API routes GET /api/sessions/{id}/slices?node_id=&direction= and
  GET /api/sessions/{id}/damage-radius (route inventory updated); the
  unavailable radius says so explicitly instead of reading as "no damage"

#### Regression-lab spectrum and reliability (Tarantula, tau-bench)
- Bundle reports gain spectrum.top_suspects — Ochiai suspiciousness per
  decision node across a bundle's passed/failed runs (deterministic
  arithmetic; ranks, never convicts, never feeds the trust score) — and
  reliability {k, passes, pass_hat_k} worst-of-k gating; per-run
  decision_nodes identity (event id within a bundle, normalized
  type:headline across bundles)

#### Regression gate in CI (Q14 follow-up)
- A committed synthetic baseline bundle (sanitized, deterministic,
  content-hashed) now runs through the current engine as part of the
  normal test suite — engine and analysis changes fail CI with a
  per-assertion diff on drift; new baselines auto-join the gate, and
  regression_cli.py gains run-suite

#### Session completeness and delivery diagnostics (W02)
- GET /api/sessions/{id}/completeness reports expected vs received
  counts, sequence gaps, missing parents, duplicate ids, truncation and
  redaction markers, and a single verdict; the SDK exposes
  delivery_summary() counters (accepted/failed per kind, last error,
  explicit zero in inert mode)

#### Onboarding contract repaired (W12)
- Every quickstart snippet now inits with an explicit endpoint (bare
  init() is inert since the no-key change — users saw no trace);
  PEAKY_PEEK_AUTO_PATCH value, router/panel/test-count claims, Docker
  volume path and UI links corrected; one canonical install path
  (pip install peaky-peek-server && peaky-peek --open) and three
  operator workflows documented with their proving artifacts
## [0.5.0] - 2026-09-21

The enforced-boundaries and regression-lab release: hosted-mode auth and
reference consistency, one redaction policy across every sink, no-key
local delivery, SDK semantic restore with provenance, the
incident-to-regression laboratory, real-framework adapter capability
proof, SSE reconnect recovery — and CI gates that exercise real
browsers, real Redis and real framework packages on every push.

### Fixed

#### Hosted-boundary slice (Q06)
- `/api/clusters` no longer resolves its repository through a module-local
  helper that hard-coded `tenant_id="local"` (and leaked its DB session);
  both cluster routes use the shared tenant-scoped repository dependency
- Checkpoint ingestion verifies the parent session is visible to the
  caller's tenant before writing (404, zero mutation on cross-tenant
  attach), mirroring the event path
- New two-tenant hosted-mode regression matrix (sessions, events,
  checkpoints, replay, SSE, clusters, analytics) plus
  `docs/hosted-route-inventory.md` — every mounted route with auth,
  tenant-scoping evidence and sinks, and the known-open gaps pinned

#### Custom breakpoint predicates are no longer eval'd (Q07)
- `Breakpoint.should_trigger` evaluated CUSTOM_CONDITION strings with
  Python `eval` in the server process. Conditions are now parsed and
  validated against a strict AST allowlist and evaluated by a recursive
  interpreter — no calls, no dunder access, no comprehensions/f-strings,
  length and node caps, explicit unsupported-construct errors. Wire
  contract unchanged

#### No-key local SDK delivers traces (Q09)
- Destination selection is separate from authentication: an endpoint
  without an API key now installs unauthenticated HTTP delivery to a
  local collector (the documented quickstart path); no endpoint or
  disabled tracing stays fully inert. `Config.endpoint` now defaults to
  None so bare `init()` never guesses a localhost port

#### Redis buffer repaired (Q13)
- `RedisEventBuffer()` no longer raises NameError without an injected
  client (lazy import; clear RuntimeError when the package is absent),
  `REDIS_URL` is actually passed to the selected redis backend,
  subscriber queues are bounded with a documented drop-oldest policy,
  the pub/sub listener reconnects after connection loss, and the class
  docstring states the durability limit. Real-service tests activate
  where redis/redis-server exist


#### One redaction policy across every sink (Q08)
- The configured pipeline now covers persisted event rows (data and
  metadata), the live buffer/SSE fan-out (the collector publishes exactly
  the redacted object it stores), checkpoint state/memory, session config,
  and the NDJSON buffer spill — previously only the persisted event copy
  was redacted, so stored and streamed versions could differ and
  session/checkpoint payloads bypassed the policy entirely. `from_config`
  wires redact_pii/redact_tool_payloads (env fallbacks, documented);
  defaults remain off (opt-in per deployment). New sentinel boundary
  tests plus `scripts/scan_redaction_sinks.py` for manual audits

#### Fixed: Python 3.10 SSE streams died on quiet periods
- The stream loop caught the builtin `TimeoutError`, a different class
  from `asyncio.TimeoutError` on Python 3.10 (aliases only from 3.11),
  so any quiet period longer than the queue timeout killed the stream
  with an unhandled timeout; both are now caught and yield keepalives

#### SDK semantic restore with provenance (Q10)
- `SessionManager.restore_from_checkpoint` / `TraceContext.restore` now
  POST the server's semantic restore contract (authenticated; works
  keyless against a local collector), adopt the server-minted session /
  checkpoint / restore-marker ids, and expose a typed
  `RestoreProvenance` (mode, source and new ids, copied_event_count,
  token, timestamp). Servers without the route fall back to the legacy
  authenticated GET reconstruction, marked `legacy-get`. The source
  session is preserved unchanged and no agent/tool execution is started


#### Contract gate: payload fixtures, nullability and type checks (Q04)
- The gate now validates required/nullability compatibility between live
  Pydantic fields and TS properties, structural type kinds, and eight
  real response payload fixtures captured verbatim from the in-process
  app (committed as a static artifact with a regeneration script); 56
  mutation tests including TS-source mutations and CLI exit codes

#### Hosted auth hardened; breakpoint conditions validated at creation (Q06/Q07)
- Absent Authorization header in cloud mode is rejected with 401 instead
  of falling back to the 'local' tenant; analytics routes require a valid
  key in hosted mode and stay open in local mode; custom breakpoint
  conditions are validated when set/imported (422 naming the unsupported
  construct) and the predicate interpreter closes residual unbounded-work
  vectors (repetition/concatenation caps, printf-style formatting
  rejected)

#### Installed-artifact and container repair (Q12 first slice)
- scripts/install_smoke.sh proves the full first-value journey from
  built wheels in a clean venv outside the checkout — server start with
  explicit data dir, keyless local SDK trace, query, restart with the
  trace intact, bundled UI — and the same inside a Docker container.
  Fixed en route: the installed server crashed because wheels don't ship
  alembic.ini (migrations env now guards on existence), and the
  Dockerfile copied pyproject-server.toml under the wrong name and never
  copied the README its metadata references. CI gains a real-service
  Redis buffer job (redis:7-alpine + redis-server binary) so the Redis
  tests run without skips (Q13 acceptance)

#### Tracker reconciliation (Q03)
- #325 landed (AlertDeriver threshold tests, 12 cases, via local review),
  #321/#322/#323/#309 closed with documented rationale, #311 closed;
  dependabot #307/#308/#310/#306 merged on green CI; TypeScript 7 bump
  (#309) blocked by typescript-eslint's peer range (<6.1.0), not by this
  repo


#### Historical secret-scan baseline resolved
- The complete HEAD-history gitleaks scan's 19 older test/documentation
  findings each have a byte-exact commit:file:rule:line fingerprint in
  .gitleaksignore (verified 1:1 against the source-reviewed inventory);
  full-history and push-range scans exit 0, and a disposable-clone
  control with a changed value still reports a finding — exact-value
  suppression, never path- or rule-wide

#### Q06 acceptance complete
- Checkpoint writes verify the event reference belongs to the checkpoint's
  session in the caller's tenant (404/422, zero mutation, both ingest
  paths); a route-inventory sync test now fails on doc drift (and found
  63 undocumented routes — doc completed); the server starts hosted via
  AGENT_DEBUGGER_MODE=cloud with a real-uvicorn e2e proving 401s for
  absent keys and 404 cross-tenant reads while local mode stays keyless

#### Real-browser smoke journey (Q11 first slice)
- scripts/browser_smoke.mjs drives headless chromium through the UI:
  contradicted audit finding → evidence link → correct event, restored
  session showing the session_restored provenance marker, a delayed API
  response survived via its loading state, zero console errors; 15
  asserted steps, verified repeatedly

#### Incident-to-regression laboratory, first slice (Q14)
- Export a session as a deterministic, sanitized, content-hashed incident
  bundle carrying the audit report and derived expected assertions; run it
  back through the current engine with actual-vs-expected rows; compare
  baseline vs candidate with a shared-data gate (mismatched hashes or
  engine versions are refused). CLI: scripts/regression_cli.py
  (export/run/compare). 13 tests including determinism, sentinel
  sanitization, tamper rejection and exact-regression detection

#### Real-framework adapter capability matrix (Q15)
- Sixteen tests run the LangChain and PydanticAI adapters against the
  real installed packages (langchain-core 1.6.3, pydantic-ai 2.46.0),
  skipping cleanly where absent; the LangChain handler gains four
  minimal >=1.0 compatibility fixes; docs/adapters/capability-matrix.md
  publishes per-adapter capability rows with honest VERIFIED / MOCKED /
  NOT SUPPORTED statuses. CI gains framework-adapters and browser-smoke
  jobs (the real-chromium journey now gates every push)

#### SSE reconnect recovery + UI stability
- SSE blocks carry event ids and honor Last-Event-ID: a reconnect replays
  the persisted gap (unknown cursor replays the whole session),
  deduplicated against the live stream — disconnects no longer silently
  skip events. The DecisionTree ResizeObserver feedback loop that grew
  the Inspect page unboundedly is fixed; the browser smoke now uses
  normal Playwright clicks
## [0.4.0] - 2026-09-20

The benchmark-integrity and delivery-recovery release: the Who&When
protocol corrected against the pinned upstream conventions (the previously
published step number was invalid), a contract gate that actually inspects
contracts — with the three client bugs it caught, main CI recovered from
the long-standing xdist instability, and dependency-audit hygiene.

### Fixed

#### Full-suite xdist instability root-caused and fixed (#324 / Q01)
Three stacked, order-dependent root causes; all reproduced locally:
- `test_lifespan_configures_pipeline_for_sqlite` patched the database URL
  to the fixed machine-global path `/tmp/test.db` and executed the real
  app lifespan, which installs a real engine into module-global
  `app_context`; the patch exit restored only the URL function, leaking
  the poisoned engine to every later test in the same process (29–70
  failures per xdist run depending on test distribution). The test now
  uses a `tmp_path` URL, resets `app_context` before entering the
  lifespan, and snapshot/restores (and disposes) everything the lifespan
  installs
- Tests using `from conftest import ...` re-execute `tests/conftest.py`
  under a second module name; the module body ran a second `mkdtemp()`
  and rewrote `AGENT_DEBUGGER_DB_URL` to a schema-less path mid-worker.
  The side effects are now idempotent per process, guarded by a PID check
  so environment inheritance across xdist workers cannot share (and
  early-delete) one temp directory
- `tests/conftest.py` read the nonexistent `PYTEST_XDIST_WORKER_ID`
  (the real variable is `PYTEST_XDIST_WORKER`); the per-worker DB file
  name now actually differs per worker
- Verified: the minimal serial reproducer failed 43 tests before and
  passes after; `-n 1` plus twelve consecutive `-n auto` full-suite runs
  are green

#### Who&When benchmark protocol corrected (Q05/E0)
- **Step indexing follows the pinned upstream convention**: `mistake_step`
  is now read by default as the 0-based index into the whole conversation
  (upstream prompt at commit `b2bae5c` numbers every entry). All 184
  annotations are in range globally; 95/184 are out of range under the
  previous per-agent default, which is retained only as
  `--step-scope agent` for reproducing the superseded 2026-09-15 result
- **Metrics renamed and made explicit**: exact independent agent accuracy,
  exact independent step accuracy, joint agent+step accuracy, and
  abstention rate, each with numerator/denominator; the old "step
  accuracy" silently required a correct agent (it was joint accuracy)
- Corrected full-dataset result (184 records, exact scoring, denominator
  includes abstentions): **26.6% agent / 15.2% step / 15.2% joint / 46.7%
  abstentions**; published versioned artifact with corpus hashes,
  evaluator revision, validation findings, and frozen per-record rows at
  `benchmarks/results/who_when/2026-09-20-global-protocol.json`. The
  previous 5.4% step figure was an artifact of the invalid per-agent
  indexing; the paper's 53.5%/14.2% LLM-judge numbers use substring
  scoring on a different protocol and are not a matched baseline
- `--self-test` repaired (the previous-message heuristic fixture no longer
  contradicts its own annotation) and hardened into a contract check with
  command-level subprocess tests
- `scripts/fetch_who_when.py` now fetches the pinned upstream commit by
  default (was a moving-HEAD shallow clone) and records per-file sha256
  hashes in the MANIFEST; annotation validation gates metric publication
  (nonzero exit on any out-of-range or non-integer annotation)
- Research route descriptions no longer claim "calibrated confidence
  intervals", "guaranteed coverage probability", or "calibrated
  probabilities" — the underlying intervals are deterministic
  confidence-derived heuristics with no held-out calibration fit


## [0.3.0] - 2026-09-15

The operator-decides release: failure narratives, minimal re-execution
sets, semantic checkpoint restore, an externally benchmarked localization
harness — and a fully repaired HTTP/cloud delivery path for the SDK.

### Added

#### Failure narratives (M2.2)
- Every audit report now carries a structured failure narrative — observed
  symptom (with a normalized mechanism category), likely mechanism with a
  clickable root-cause → failure chain, contributing factors (repeated
  failed strategies, contradictions, stale evidence, goal drift),
  trace-anchored evidence links, and the single best next inspection point
  with a suggested action; confidence is honestly capped with an explicit
  weakness note when no cause could be localized
- First-class AuditPanel surface in the UI

#### Minimal re-execution set (M2.1)
- `GET /api/sessions/{id}/decisions/{event_id}/reexecution-set` — the
  smallest sub-graph to re-run to confirm or invalidate a suspect decision's
  claim: the decision, its cited evidence, upstream tool calls, and the
  downstream subtree, each node marked read-only vs required-rerun with a
  why-included reason

#### Semantic checkpoint restore (M2.3)
- `POST /api/checkpoints/{id}/restore` now carries the source session's
  event prefix (fresh ids, remapped internal references), a leading
  `session_restored` provenance marker, and an initial SDK-wrapped state
  checkpoint — restored runs stay auditable; response extended with
  `copied_event_count`, `new_checkpoint_id`, `restore_event_id`

#### Who&When benchmark corpora + measured result (M1.3/M2.4)
- `scripts/fetch_who_when.py` seeds the public 184-record benchmark
  (MANIFEST-pinned); `just who-when` reproduces the run
- Full-dataset result: deterministic attribution measures **26.6% agent /
  5.4% step accuracy** on raw conversation logs vs the paper's best LLM
  judge at 53.5% / 14.2% — methodology and the honest read in
  docs/guides/audit-and-trust.md

#### End-to-end scenario suite
- `tests/e2e/` — 46 full-stack tests: real uvicorn subprocess, real SDK
  HTTP transport, real SQLite, authenticated tenant; 11 deterministic
  scenario agents covering grounded runs, contradictions, stale evidence,
  retry loops, goal drift, policy refusions, recovery, checkpoints,
  multi-agent crews, and cross-session surfaces

### Fixed

#### SDK HTTP/cloud delivery path (found by the e2e suite)
- Collector ingest dropped all typed event fields (reasoning, confidence,
  evidence ids, errors, tool results) and regenerated event ids — every
  evidence/upstream/parent reference from the SDK was orphaned; ingest now
  preserves ids and reconstructs typed events
- Checkpoints were silently lost in transport mode — `HttpTransport` gains
  `send_checkpoint` and the collector a `POST /api/checkpoints` endpoint
- `record_tool_call` accepts `agent_id` for multi-agent attribution

#### Audit engine scoring
- Recovery rate counted enum repair outcomes as failures (0% over HTTP);
  stale-evidence claims now appear in review points; a fully repaired
  failure no longer forces a fail verdict; decisions carrying evidence
  items no longer self-supersede into false staleness

#### Frontend
- UI load crash: zustand v5 object selectors in TraceView/InspectView
  re-rendered infinitely (React #185) — now wrapped in `useShallow`
- TraceTimeline crashed on JSON-null `duration_ms` arriving from the API

### Changed

- Who&When harness: 0-based step indexing (was off by one), speaker
  extraction from `name` OR `role` (with parenthetical normalization),
  attribution switched to the measured-best deterministic heuristic
  (message immediately before the first error signal)
- verdict semantics: recovered failures read as review/pass, unrecovered
  and policy-violating runs still fail

## [0.1.4] - 2026-03-24

### Added

#### Auto-Patching Framework Support
- **Tier 1 Adapters**: OpenAI and Anthropic with zero-code instrumentation
- **Tier 2 Adapters**: LangChain and PydanticAI with auto-patch lifecycle
- **Tier 3 Adapters**: CrewAI, AutoGen, and LlamaIndex (experimental)
- Auto-patch registry with activate/deactivate lifecycle management

#### Replay Depth (Checkpoint L1+L2)
- Standardized checkpoint schemas for LangChain, PydanticAI, and custom agents
- `TraceContext.restore()` for manual execution restoration from checkpoints
- REST endpoints: `GET /api/checkpoints/{id}` and `POST /api/checkpoints/{id}/restore`
- Checkpoint validation helpers with framework-specific state validation

#### Developer Experience Improvements
- `peaky-peek` CLI command with --host, --port, --open, --version flags
- Pricing module with auto-cost-calculation for LLM response events
- Bundled frontend UI served from `/ui/` endpoint
- JSON export endpoint: `GET /api/sessions/{id}/export`
- 8 comprehensive examples covering all major SDK features

#### Intelligence & Analysis
- Decomposed TraceIntelligence into focused components
- Causal analysis module for failure-to-cause reconstruction
- Failure diagnostics with adaptive analysis
- Live monitoring with real-time alerts

### Refactored
- Decomposed TraceIntelligence into focused components (causal_analysis, failure_diagnostics, live_monitor)
- Decoupled API dependencies from main.py for better modularity
- Improved repository pattern with cleaner separation of concerns
- Runtime context and persistence flow improvements

### Fixed
- CI test failures - all tests now passing (523 passed, 1 skipped)
- App context initialization in test fixtures
- Transport mock setup for logging tests
- Import ordering and line length lint issues
- Alembic logger configuration
- Database session management in tests

### Documentation
- Getting started guide (5-minute tutorial)
- Quick wins implementation plan
- Examples folder with 8 working code samples
- Landing page design spec for GitHub Pages
- Comprehensive demo recording guide
- Top 0.1% strategy roadmap

### Examples
- 01_hello.py - Basic agent trace
- 02_research_agent.py - Research agent with tools
- 03_langchain.py - LangChain adapter integration
- 04_pydantic_ai.py - PydanticAI adapter integration
- 05_checkpoint_replay.py - Checkpoint creation and restore
- 06_safety_audit.py - Safety audit trail
- 07_loop_detection.py - Stuck agent loop alert
- 08_live_stream.py - Live SSE streaming

### Migration Notes
- Checkpoint schemas are now typed and validated
- Auto-patch adapters require explicit activate/deactivate calls
- TraceIntelligence API has changed (now decomposed into modules)

### Contributors
Thanks to all contributors who made this release possible!
## [0.2.0] - 2026-08-15

The audit & trust release: every run now answers the five operator questions
(what happened, why, with what evidence, with what result, where it failed)
with deterministic claim verification and an explainable trust score.

### Added

#### Agent audit & trust system
- `SessionAuditEngine` — per-session audit report answering the five operator
  questions, with deterministic claim verification
  (verified · partially_verified · contradicted · unsupported · unverified ·
  stale), risk signals, failure localization, and an explainable trust score;
  exposed via `GET /api/sessions/{id}/audit`
- Timestamp-based staleness detection — decisions built on superseded evidence
  are classified `stale` with a matching `stale_evidence` signal
- Per-decision justification (`GET /api/sessions/{id}/decisions/{event_id}/justification`)
- Evidence-provenance graph (`GET /api/sessions/{id}/evidence-graph`), including
  available facts the agent had but never cited
- Cross-session audit portfolio (`GET /api/audit/portfolio`) — fleet-level
  trust/verification/failure aggregates, worst-trust-first
- Human-auditable session summary (verdict + tldr + trust line + markdown
  narrative) rendered as a verdict card
- Goal-drift score — deterministic per-decision objective-adherence series
  with a conservative drift flag and `goal_drift` risk signal
- Verdict-card stakes line (mutating vs read-only tool calls) and named trust
  bands (act / verify-first / do-not-act)
- Success-flow deviation advisory (`GET /api/sessions/{id}/success-flow`) —
  first-divergence localization against a successful reference run;
  advisory-only, never feeds the trust score
- Who&When benchmark harness (`collector/audit/who_when.py` +
  `scripts/benchmark_who_when.py`) — scores the engine's deterministic failure
  attribution against the public annotated benchmark

#### Frontend
- AuditPanel (trust header, five-questions grid, verification badges,
  localized failures, review points, risk signals, goal-drift block)
- EvidenceGraphPanel, DecisionJustificationPanel, PortfolioAuditPanel
- Inline audit risk markers and an "Audit flags" filter on the trace timeline

#### Documentation
- Living `docs/ROADMAP.md` superseding earlier planning docs; audit-and-trust
  guide with example audited-session and failure-report outputs; 5 new
  research paper notes (provenance survey, goal drift, Who&When, OAT
  success-flow, calibrated trust); README repositioned as an agent
  audit/trust console

### Changed
- `api/services.py` split into a cohesive `api/services/` package
  (sessions / ingestion / similarity / causal / analysis) behind a
  backward-compatible facade — all existing imports keep working
- Research-route computation extracted into pure functions in
  `api/services/research`

### Internal
- API route tests for the research and swimlane endpoints (previously
  untested HTTP layer); unit tests for `agent_debugger_sdk/telemetry`
- Shared `unique_id()` test helper; documented the local coverage
  measurement caveat for ASGI route handlers

## [0.1.19] - 2026-06-13

### Internal
- Deduplicated StrEnum Python 3.10 compatibility shim into `agent_debugger_sdk.core._compat`
- Added composite database indexes for events, sessions, checkpoints
- Replaced module-level `_shared_app` pattern with session-scoped `shared_app` fixture
- Enabled pyright type checking in CI

## [0.1.18] - 2026-06-10

### Fixed
- Corrected stepper test fixture and assertions

### Added
- Agent stepper, swimlane debugger, and violation detection features
- Reasoning editor and divergence detection features

## [0.1.17] - 2026-06-08

### Added
- Research-driven event behavior features
- Frame tracer and divergence detector

### Fixed
- Resolved all ruff lint errors across SDK and test files
- Python 3.10 compatibility for StrEnum in core modules
