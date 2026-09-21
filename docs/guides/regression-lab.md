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
```

Exit codes: `0` = pass / nothing regressed, `1` = failed assertions or a
regression, `2` = operational error (missing session, tampered bundle,
mismatched bundles, ...).

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
5. **Run.** Locally, in code review, and (next slice) in CI: the runner
   replays the bundle against whatever the current engine does and reports
   exactly which pinned assertions moved.
6. **Compare.** For an engine or analysis change, record the baseline run
   before the change and compare the candidate run after — the regressed
   cases are the review checklist for the change.

## Current limits (this slice)

- **Analysis only.** The runner re-audits captured events; it never
  re-executes tools, agents, or models. Re-execution divergence is W04
  (restore/continuation) territory.
- **Single-session scope.** One bundle = one session. Multi-baseline
  suites (a directory of bundles aggregated into one verdict) are the next
  slice.
- **CI wiring is manual.** Run the CLI in CI yourself for now; a dedicated
  job/matrix over committed bundles comes with the suite support above.
- **Assertion kinds are report-level.** They pin the audit verdict's
  headline fields, not every number in the report. Scenario-family
  assertions (retry loops, stale evidence, restore divergence, ...) follow
  the W05 scenario-family work.
- **Evaluator versioning is a constant.** `AUDIT_ENGINE_VERSION` is bumped
  by hand when audit semantics change; there is no automatic fingerprint of
  the engine code yet.
