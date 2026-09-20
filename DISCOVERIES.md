# Reliability discoveries

## 2026-09-15 — Retrying file writes after cancellation or partial failure

**Issue:** Draining the collector buffer before a failed append can lose events.
Retrying a partial append can duplicate records or leave invalid NDJSON.

**Root cause:** Removing a batch from the buffer is separate from acknowledging
its disk write. Cancelling an await of `asyncio.to_thread` does not stop the
underlying thread.

**Solution:** Retain drained batches until the write succeeds, serialize flushes,
and retain a shielded write task across cancellation. Roll failed appends back to
the original file length before retrying.

**Prevention:** Exercise disk errors, partial writes, concurrent flushes, and
shutdown during a blocked write in `tests/collector/test_persistence_recovery.py`.
This is single-writer recovery within a running process: pending batches remain
in memory, and rollback itself can fail. It is not crash durability.

## 2026-09-15 — Search selection across asynchronous replay loading

**Issue:** Search navigation can select an event but leave replay at another
index, or have a delayed replay response reset the search position.

**Root cause:** Search and replay used different event lists and independently
updated selection and replay position.

**Solution:** Route search clicks through one store action, use the same merged
event ordering as the display, and retain the target until replay loading
completes. Load replay only when its bundle belongs to the selected session.

**Prevention:** Keep App-level tests with deferred bundle/replay responses and
real search/store behavior in `frontend/src/__tests__/SearchNavigation.test.tsx`.

## 2026-09-20 — Who&When benchmark scored under the wrong step-index convention

**Issue:** The published 26.6%/5.4% deterministic-attribution result was
computed by reading `mistake_step` as a per-agent index. The CLI self-test
failed (`Verifier_Expert` truth vs `Computer_terminal` prediction) and
95/184 annotations were out of range under that convention.

**Root cause:** The upstream prompt (pinned commit `b2bae5c`,
`Automated_FA/Lib/utils.py`) numbers every entry of the whole conversation,
so `mistake_step` is the **global 0-based history index**. The local
docstring asserted a per-agent convention that the source never states.
Separately, local "step accuracy" silently required a correct agent — it
was joint accuracy under another name — while the upstream evaluator scores
agent and step independently (by substring membership).

**Solution:** Default `step_scope="global"` (all 184 annotations in range;
6 point at another speaker — upstream noise, reported). Metrics renamed to
exact independent agent/step, joint, and abstention rate, each with an
explicit numerator/denominator. Publication is gated on zero invalid
annotations; the fetch script pins the upstream commit and hashes its
output; results export a versioned manifest with frozen prediction rows
(`benchmarks/results/who_when/2026-09-20-global-protocol.json`).
Corrected numbers: 26.6% agent / 15.2% step / 15.2% joint / 46.7%
abstentions. Paper LLM-judge numbers are substring-scored on a different
protocol — kept as context only, never as a matched baseline.

**Prevention:** A convention claim about an external dataset is verified
against the pinned upstream implementation, not inferred from a docstring;
every published rate names its numerator, denominator, and match rule; the
CLI self-test is a subprocess contract test, so evaluator unit tests can no
longer pass while the entry point is broken.

## 2026-09-20 — Full-suite xdist instability: three stacked root causes (issue #324)

**Issue:** Full-suite pytest-xdist runs failed non-deterministically
(29–70 failures per `-n auto` run, varying counts and tests) with
`sqlite3.OperationalError: no such table: sessions` / `unable to open
database file` / `attempt to write a readonly database`, while the serial
suite passed. Reproduced locally 100% of the time.

**Root causes (all three required to explain the pattern):**

1. **A lifespan unit test leaked a poisoned engine.**
   `test_lifespan_configures_pipeline_for_sqlite` patched
   `storage.engine.get_database_url` to the fixed machine-global
   `/tmp/test.db`, executed the real `api.main.lifespan` — which installs a
   real engine into module-global `app_context` — and exited the patch
   context without restoring it (`init_app_context` never replaces an
   existing engine). Every later test in the same process that used
   `require_session_maker()` then hit a schema-less file shared across
   workers AND runs; whether a run survived depended on which tests the
   distributor assigned after the poison.
2. **A conftest dual-import rewrote the database URL mid-worker.** Tests
   calling `from conftest import iter_app_api_routes` import
   `tests/conftest.py` a second time under the top-level name
   `conftest`, re-executing the module body: a fresh `mkdtemp()` and a
   rewritten `AGENT_DEBUGGER_DB_URL` to a path with no schema. Serial runs
   survived only because `app_context` had already cached an engine bound
   to the old path; fresh xdist workers initialized after the rewrite.
3. **A cross-process temp-dir handoff deleted live databases** (found and
   fixed in the same session, after the first two): making the conftest
   side effects idempotent via a plain environment sentinel was wrong,
   because xdist workers inherit the controller's environment — all
   workers then shared one temp directory and the first worker to finish
   its queue `rmtree`'d it while the others were still running.

A secondary defect: `tests/conftest.py` read the nonexistent
`PYTEST_XDIST_WORKER_ID` (the real variable is `PYTEST_XDIST_WORKER`),
giving every worker's DB file the same suffix — harmless because
`mkdtemp()` differs per process, but it masked the per-worker intent.

**Solution:** The lifespan test now points the patched URL at `tmp_path`,
resets `app_context` before entering the lifespan (so it deterministically
builds an engine against the patched URL), and snapshots/restores all four
`app_context` globals, disposing the engine it created. The conftest
temp-dir/env side effects are idempotent per process, keyed by a PID guard
so inherited environment cannot share a directory across processes.
Verified: the minimal serial reproducer (lifespan test followed by
session/swimlane route tests) failed 43 tests before and passes after;
`-n 1` and twelve consecutive `-n auto` full-suite runs are green.

**Prevention:** A test that executes real startup code with patched
configuration must snapshot and restore every piece of module-global state
that code mutates — `patch()` restores functions, not objects the code
already constructed — and must never point patched configuration at a
fixed path outside its own temporary directory. Conftest module bodies
run more than once per process whenever tests use top-level
`from conftest import ...`; their side effects need per-process idempotence,
and environment variables alone cannot provide it across spawned workers.

## 2026-09-17 — Contract gate silently passed without inspecting contracts

**Issue:** CI reported contract alignment despite undetected frontend/backend drift.

**Root cause:** The checker parsed `api/schemas.py` after it became a re-export
module. Its regular expressions also missed indented fields, and its CLI returned
success even on errors. Route methods and SDK enum members were never compared.

**Solution:** Read live Pydantic fields and parse frontend source with the installed
TypeScript compiler. Check explicit core response pairs, enum values (including
synthetic `trace_root`), and HTTP methods/paths against the app's OpenAPI routes.
Fail on drift or extraction errors. Install frontend dependencies before Python
contract tests in CI.

**Prevention:** Mutation tests remove fields and `drift`, introduce bad routes and
methods, and verify nonzero exit statuses. This checks field names and declared
routes, not full payload compatibility or runtime routing behavior.

The working gate exposed three GET calls to POST endpoints (violation clustering,
violation search, and similar sessions), now corrected. It also exposed unsupported
`TraceEvent.sequence` and `checkpoint_id` fields: checkpoint metadata lives in
`event.data`. The timeline and reasoning labels now read the payload sequence.

## 2026-09-17 — Relative client URLs threw before reaching the API

**Issue:** Reasoning replay/comparison and stepper breakpoint/step/branch calls
constructed `new URL('/api/...')` and threw `TypeError` before calling fetch.

**Root cause:** The URL constructor requires a base when its input is relative;
it does not inherit the document origin automatically like browser fetch does.

**Solution:** Supply `window.location.origin` as the base for those five calls.

**Prevention:** Exercise the exported client functions with mocked fetch and
assert the resulting origin, route, method, and query parameters. Static route
existence checks alone cannot establish that a client function reaches fetch.

## 2026-09-20 — Secret scan flagged a synthetic redaction sentinel

**Issue:** Secret-scan run `35483421310` failed on `f832204` while main CI passed.

**Root cause:** The synthetic AWS-shaped value in
`tests/test_redaction_boundary.py:58`, introduced by `7f95046`, is deliberately
recognizable by the redaction detector. Gitleaks also flags it. Direct job logs
identify the executed scanner as 8.24.3; the SARIF driver label `v8.0.0` is not the
binary version. Version 8.24.3 reports `aws-access-token`, while 8.30.1 reports
the same historical fixture as `generic-api-key`.

**Solution:** Add the two observed commit/path/rule/line fingerprints to
[.gitleaksignore](.gitleaksignore), retaining the fixture and default detector
rules. The failed push range reproduces one finding before the correction and
zero afterward in both versions. In a disposable clone, a different synthetic
value at the same path/line in a new commit still produces a finding in both.
All 43 focused redaction tests pass. The patch is locally verified; a new GitHub
run remains pending. See [commands and evidence](docs/research/2026-09-20-delivery-followup.md#secret-scan-diagnosis-and-local-correction).

**Prevention:** Verify the scanner's actual binary version and exact commit range
before reproducing a CI failure. Use precise historical exceptions only after
confirming fixture provenance, and test a new finding at the same path/line.
Keep complete-history results separate: an 8.24.3 HEAD-history scan still reports
19 older findings outside this failing push range. Historical source review
classifies them as test fixtures/documentation placeholders, with an inventory in
the linked evidence. This correction does not suppress them or establish a clean
historical baseline.
