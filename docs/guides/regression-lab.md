# Regression Lab: incident → regression case → baseline/candidate comparison

An incident you captured with Peaky Peek is already the hard part of a
regression test: the exact events, the failure, and the audit verdict. The
regression laboratory turns it into a pinned test case you can commit and
re-run — no model calls, no re-execution of the agent, everything local and
deterministic.

This is the first slice of the incident-to-regression workflow
(roadmap W05 / queue item Q14):

```
incident (captured session)
   └─ export   → sanitized, content-hashed incident bundle (JSON)
        └─ review → a human reads the sanitized bundle, adjusts assertions if needed
             └─ commit → the bundle becomes an immutable test fixture
                  └─ run     → replay through the CURRENT audit engine, evaluate assertions
                       └─ compare → candidate vs baseline, name the regressed assertions
```

## The incident bundle

`collector/regression/bundles.py` exports one stored session (read-only use
of the repository layer — no HTTP routes involved) into a single JSON file:

| Field | Contents |
|-------|----------|
| `schema_version` | `1` today; loaders reject any other value loudly |
| `bundle_kind` | `"agent_debugger.incident_bundle"` discriminator |
| `session` | id, agent name, framework, status, started/ended, tags, config |
| `sanitized` | `true` when the redaction policy was applied |
| `redaction` | the applied policy summary (or `null` for a raw export) |
| `events` | all events, ordered by `(timestamp, id)` |
| `checkpoints` | all checkpoints, ordered by `(timestamp, sequence, id)` |
| `audit_report` | the report `SessionAuditEngine` produced at export time |
| `expected_assertions` | the pinned contract derived from that report |
| `engine` | `audit_engine_version` of the evaluator semantics used |
| `event_count` / `checkpoint_count` | convenience counts |
| `content_hash` | sha256 over canonical JSON of everything above (minus the hash field itself) |

Two properties matter more than any individual field:

- **Determinism.** There is no wall-clock value inside a bundle. Exporting
  the same stored session twice produces byte-identical files — the content
  hash proves it. A bundle committed as a fixture pins its own expectations.
- **Immutability.** The runner verifies the content hash before evaluating
  anything. A bundle edited after export (tampering) is rejected; an
  assertion set a human deliberately edited must be re-signed with
  `content_hash()` so the edit is an explicit, visible act.

### Sanitization

By default the export routes every event, the session config, and the
checkpoint state/memory through the same configured `RedactionPipeline` the
persistence path uses (`RedactionPipeline.from_config()`, the policy behind
`collector.server._persist_event_if_configured`). The bundle records
`sanitized: true` plus the policy summary, so a recipient can see exactly
which scrubbing produced what they are reading. Use `sanitized=False` (the
CLI's `--raw`) only for local debugging — the raw bundle keeps stored
payloads verbatim and must not be shared.

The export-time audit report is computed from the *sanitized* events — the
exact objects the runner later rebuilds from the bundle — so the stored
assertions are reproducible by construction, not by luck.

## Expected assertions

`derive_expected_assertions(report)` pins the audit verdict on the incident.
Each assertion is a `(kind, path, expected)` triple evaluated independently,
so a regression names exactly the behaviour that changed:

| Kind | Path | Pins |
|------|------|------|
| `trust_band` | `trust.band` | the trust band (`low` / `medium` / `high`) |
| `trust_score` | `trust.score` | the explainable trust score |
| `claim_verification_status` | `claims.<event_id>.verification_status` | one row per decision: `verified`, `partially_verified`, `contradicted`, `unsupported`, `unverified`, `stale` |
| `failure_event_ids` | `failures.event_ids` | which findings (localized failures) are present |
| `failure_narrative_mechanism` | `failure_narrative.symptom.mechanism_category` | the normalized failure mechanism (e.g. `tool_invocation_failed`) |
| `summary_verdict` | `summary.verdict` | the deterministic verdict (`pass` / `review` / `fail`) |

## The runner

`collector/regression/runner.py` loads a bundle, rebuilds the events and
checkpoints, and feeds them to the **current** `SessionAuditEngine` — never
the report stored in the bundle. The stored assertions are then evaluated
against that fresh report, each with its actual vs expected value:

- same bundle + same engine semantics → same verdict, always;
- analysis only — no agent, tool, or model is executed;
- the bundle's schema version and content hash are verified first, so an
  unknown future format or a tampered file fails loudly instead of
  evaluating to "pass".

Run results carry the bundle hash and the evaluator version
(`engine.audit_engine_version`) alongside the verdict and per-assertion rows.

## Baseline / candidate comparison

`compare_run_results(baseline, candidate)` takes two run results. Per the
W05 gate — *candidate and baseline share data/evaluator versions* — the two
runs must come from the **same bundle** (identical content hash); comparing
runs from different incidents raises instead of producing a meaningless
diff. Mismatched evaluator versions are surfaced (`engine_versions_match`)
rather than silently ignored.

Per-assertion statuses:

| Status | Meaning |
|--------|---------|
| `regressed` | passed at baseline, fails on the candidate |
| `improved` | failed at baseline, passes on the candidate |
| `changed` | same pass state, different actual value |
| `unchanged` | identical expected/actual |
| `added` / `removed` | the assertion exists on only one side |

The typical use is an engine-tuning change: commit the bundle as a fixture,
record the baseline run (`run --out`), apply your change, run again, compare.
Only the pinned behaviours your change moved show up.

## CLI

```
# 1. Export incident session <id> as a sanitized bundle (default) — shareable
.venv-ci/bin/python scripts/regression_cli.py export \
    --session-id <id> --out incidents/my-incident.json [--db-url URL] [--tenant ID]

# Local-only raw copy (no redaction — do not share)
.venv-ci/bin/python scripts/regression_cli.py export \
    --session-id <id> --out local.json --raw

# 2. Replay a bundle through the current engine; exit 1 on any failed assertion
.venv-ci/bin/python scripts/regression_cli.py run --bundle incidents/my-incident.json
.venv-ci/bin/python scripts/regression_cli.py run --bundle incidents/my-incident.json --json
.venv-ci/bin/python scripts/regression_cli.py run --bundle incidents/my-incident.json --out baseline-run.json

# 3. Compare candidate vs baseline; exit 1 when anything regressed
.venv-ci/bin/python scripts/regression_cli.py compare \
    --baseline baseline-run.json --candidate candidate-run.json [--json]

# 4. Run every committed bundle (the regression suite); exit 1 when any bundle fails
.venv-ci/bin/python scripts/regression_cli.py run-suite --dir benchmarks/regression/ [--json]
```

Exit codes: `0` = pass / nothing regressed, `1` = failed assertions or a
regression, `2` = operational error (missing session, tampered bundle,
mismatched bundles, empty suite directory, ...).

### Python API

```python
from collector.regression import (
    export_session_bundle, save_bundle, load_bundle,
    run_bundle, compare_run_results, content_hash,
)

bundle = await export_session_bundle(repo, session_id)          # sanitized by default
save_bundle(bundle, "incidents/my-incident.json")               # deterministic bytes

result = run_bundle(load_bundle("incidents/my-incident.json"))  # verdict + rows
comparison = compare_run_results(baseline_result, candidate_result)
```

`run_bundle` also accepts an injected `engine` (anything exposing
`audit(events, checkpoints, session=...)`) — the seam a candidate comparison
exercises — and an `engine_version` label to record for that run.

## Workflow narrative: incident to committed fixture

1. **Incident.** An agent run goes wrong; the session is already captured.
2. **Export.** `export --session-id ... --out ...` produces the sanitized,
   content-hashed bundle.
3. **Review.** A human reads the bundle — the sanitized events, the audit
   report, the derived assertions. If an expectation should differ (a
   finding that is actually acceptable, a band that should be stricter),
   edit the assertion and re-sign with `content_hash()`; the edit is then
   visible in the diff of the fixture.
4. **Commit.** The reviewed bundle is committed like any other test
   fixture. Because the export is deterministic and hashed, the file never
   churns and cannot drift silently.
5. **Run.** Locally, in code review, and in CI: the committed suite under
   `benchmarks/regression/` is replayed by the ordinary pytest gate (and by
   `run-suite`), reporting exactly which pinned assertions moved.
6. **Compare.** For an engine or analysis change, record the baseline run
   before the change and compare the candidate run after — the regressed
   cases are the review checklist for the change.

## CI gate: the committed regression suite

The lab's second hypothesis — *a saved failure is useful as a regression* —
is wired into the normal test suite. `benchmarks/regression/` holds
committed incident bundles, and `tests/test_regression_baseline.py` replays
every `*.json` bundle in that directory through the current audit engine
**in-process** (it imports `collector.regression.runner` directly — no
subprocess, no database) and fails on any assertion drift. Because it is an
ordinary pytest file, it runs wherever the suite already runs — locally and
in CI's existing matrix — with zero new CI configuration.

The gate today:

- `benchmarks/regression/baseline_session.json` — a sanitized, synthetic
  error-chain incident (session `regbase-session-0001`) whose 7 assertions
  cover all six assertion kinds: a `verified` claim (decision citing a
  successful search), an `unsupported` claim (decision with no evidence),
  two failure findings (failing `deploy` tool result + chained `error`
  event), the `runtime_error` narrative mechanism, trust band/score, and
  the `fail` verdict.
- A drifted engine fails `test_committed_regression_bundle_passes_*` with
  the per-assertion diff — expected vs actual for each pinned path that
  moved (e.g. `[trust_band] trust.band: expected 'medium', got 'low'`).
  A fixture edited after export fails as *tampering* first, because the
  gate loads bundles through the content-hash check.

`run-suite` gives the same multi-bundle verdict from the CLI:

```
.venv-ci/bin/python scripts/regression_cli.py run-suite --dir benchmarks/regression/
# baseline_session.json: PASS — 7/7 assertions passed (0 failed)
# Suite verdict PASS: 1/1 bundles passed, 7/7 assertions passed
```

It exits `1` when any bundle fails (printing each failed assertion) and
`2` when the directory holds no bundles at all — an empty suite is an
operational error, not a silent pass.

### Adding more baselines

1. **Export** the incident (captured session) as a sanitized bundle:
   `regression_cli.py export --session-id <id> --out benchmarks/regression/<name>.json`.
   For the synthetic baseline specifically, `scripts/seed_regression_baseline.py`
   regenerates it end-to-end (see below).
2. **Review** the bundle — the sanitized events, the audit report, the
   derived assertions. Deliberately adjust an expectation and re-sign with
   `content_hash()` if needed; the edit is then visible in the fixture diff.
3. **Commit** the file. The parametrized gate test picks up every
   `*.json` in `benchmarks/regression/` automatically, and `run-suite`
   includes it in the combined verdict. No test or CI changes required.

`benchmarks/regression/` is deliberately *not* gitignored (unlike the
runtime `benchmarks/corpora/`): committed bundles are the fixture.

### Regenerating the synthetic baseline (determinism)

The committed baseline is reproducible byte-for-byte — fixed ids, fixed
timestamps, no wall-clock, and the redaction-policy environment pinned to
the repo defaults:

```
.venv-ci/bin/python scripts/seed_regression_baseline.py
# Baseline bundle ready: benchmarks/regression/baseline_session.json
#   session: regbase-session-0001  content_hash: fe99b689ecf07b006f366f25fa22e95044490a33ec5a7831ae541a01dc8093d9
#   events: 8  checkpoints: 1  assertions: 7
```

Re-running the script must print the same `content_hash` (the lab's
determinism tests pin this property; the regeneration is the manual
re-check). If the hash changes after an *engine* change, that is the gate
telling you the baseline needs a deliberate, reviewed re-export.

### Limit of the committed data

The committed baseline is **synthetic**: a hand-built session seeded by
`scripts/seed_regression_baseline.py` (obviously synthetic ids/payloads —
`regbase-*`, `regbase@example.com`) with no real incident data, user
content, or secrets. It is sanitized (`sanitized: true` with the policy
recorded) like every shareable bundle, but sanitization here is belt and
braces — there was nothing real to sanitize. Real captured incidents enter
the suite only through the export → review → commit path above, where a
human reads exactly what is being committed.

## Current limits (this slice)

- **Analysis only.** The runner re-audits captured events; it never
  re-executes tools, agents, or models. Re-execution divergence is W04
  (restore/continuation) territory.
- **Single-session scope per bundle.** One bundle = one session; the
  committed suite (`run-suite` + the parametrized gate test) aggregates a
  directory of them into one verdict, but there is no cross-session
  scenario assertion yet.
- **CI coverage = the committed suite.** The gate runs whatever bundles are
  committed under `benchmarks/regression/` in the normal pytest matrix; a
  dedicated nightly job over larger corpora is future work.
- **Assertion kinds are report-level.** They pin the audit verdict's
  headline fields, not every number in the report. Scenario-family
  assertions (retry loops, stale evidence, restore divergence, ...) follow
  the W05 scenario-family work.
- **Evaluator versioning is a constant.** `AUDIT_ENGINE_VERSION` is bumped
  by hand when audit semantics change; there is no automatic fingerprint of
  the engine code yet.
- **The committed baseline is synthetic.** It pins engine behaviour on a
  hand-built error chain, not on real incident data (see "Limit of the
  committed data" above).
