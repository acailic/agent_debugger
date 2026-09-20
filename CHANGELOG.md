# Changelog

All notable changes to Peaky Peek will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]

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
