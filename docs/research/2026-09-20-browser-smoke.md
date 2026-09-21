# Browser smoke journey: finding → evidence → restore boundary (Q11 / W08 first slice)

**Verified:** 2026-09-21, local checkout. **Deliverable:** `scripts/browser_smoke.mjs`.
This is the first REAL-browser acceptance for the roadmap Q11 slice: a headless
chromium drives the bundled React UI end to end — from the session list, through
an audit finding's evidence link, past a deliberately delayed API response, to
the semantic-restore provenance marker. It is a browser journey, not API tests.

## Run command

```bash
node scripts/browser_smoke.mjs        # from the repo root
```

Prerequisites on this machine (all verified present):

- `frontend/dist/` exists (`cd frontend && npm run build` after the one-line
  timeline change below). The script fails fast with a clear message if missing.
- `.venv-ci/bin/python` with `uvicorn` importable (falls back to `python3`).
- Playwright **not** in `package.json**: the script resolves it from
  `NODE_PATH` first, then `npm root -g`
  (`/home/nistrator/.nvm/versions/node/v22.23.2/lib/node_modules`), which hosts
  playwright 1.58.2; chromium comes from the shared `~/.cache/ms-playwright`
  cache (chromium-1208). Zero new npm dependencies.

The script is hermetic: ephemeral TCP port, `mkdtemp` data dir with its own
`AGENT_DEBUGGER_DB_URL` sqlite file, server `cwd` inside the temp dir (keeps the
cwd-relative `analytics.db` out of the repo; `/ui/` serving is cwd-independent
because `api/ui_routes.DIST_PATH` is derived from the package location), server
killed and temp dir removed on exit — success or failure.

## What the journey covers

1. **Server boot** — `uvicorn api.main:app` (real lifespan: migrations, buffer,
   storage wiring), polled until `GET /api/health` returns 200.
2. **HTTP seeding (local mode, keyless loopback)** — one session
   (`deploy_agent_smoke`), six events POSTed to `/api/traces` in the SDK
   `to_dict()` shape (typed fields as top-level extras), one checkpoint POSTed
   to `/api/checkpoints` anchored on the CI tool result:
   - `agent_turn` (user goal: ship 2.3) →
   - `tool_result ci_status_check` (success — the tool-backed fact) →
   - `decision deploy_version_2_3` (confidence 0.9, `evidence_event_ids=[ci]`) →
   - `tool_call deploy` →
   - `tool_result deploy` **with `error`** (upstream of the decision) →
   - `decision declare_incident_resolved` (0.8, no evidence → *unsupported*).
   The audit engine classifies the first decision **contradicted** (confident
   claim whose causal subtree contains the failing deploy) with a clickable
   evidence ref to the CI event; the script prechecks both server-side via
   `GET /api/sessions/{id}/audit` before opening the browser.
3. **Semantic restore over HTTP** — `POST /api/checkpoints/{id}/restore`
   (`{session_id, label: restored_deploy_smoke}`) creates the second session:
   2 prefix events copied with fresh ids plus the leading `session_restored`
   marker (`AGENT_START` type, strictly-earliest timestamp, data carrying
   `restore_token`, `source_checkpoint_id`, `source_session_id`,
   `copied_event_count`). Prechecked via the trace bundle before the browser.
4. **Browser journey** (assertions in order):
   - `/ui/` loads; the session rail renders ≥ 2 captured runs.
   - Clicking the seeded session renders the timeline incl. `deploy_version_2_3`.
   - Inspect tab → Agent Audit panel ("Trust & verification") renders the
     `data-verification="contradicted"` claim row with its badge.
   - Clicking the claim's evidence-ref link selects the linked event: back on
     the Trace tab the `.selected` timeline row and the event-detail heading
     are `ci_status_check`, and the detail payload contains the seeded event id.
   - **Delayed response:** `page.route` stalls the restored session's audit
     call for 1.5 s (once). While stalled the UI shows its "Computing audit
     report…" loading state without crashing, then renders the report.
   - Restore boundary: in the restored session the FIRST timeline event is
     `[data-event-name="session_restored"]`; clicking it shows the event-detail
     payload with `session_restored`, the restore token, and the source
     checkpoint id.
   - Zero error-level console messages across the whole journey (see filters).

## Selector strategy

Role/text/aria first, stable CSS classes second, exactly one new attribute:

| Target | Selector |
|---|---|
| Session cards | `button.session-card` filtered by agent-name text |
| Tabs | `getByRole('button', { name: 'Inspect' \| 'Trace', exact: true })` |
| Audit panel | `.audit-panel` + heading "Trust & verification" |
| Contradicted finding | `.audit-claim[data-verification="contradicted"]` |
| Evidence link | `.audit-tag--link` scoped inside the claim row |
| Selected timeline row | `.timeline-event.selected` |
| Event detail | `.event-detail` (heading + payload `pre`) |
| Restore marker | `.timeline-event[data-event-name="session_restored"]` |

### Frontend change shipped (one line)

`frontend/src/components/TraceTimeline.tsx` — the timeline event row now also
renders `data-event-name={event.name}`. This is the stable hook that makes the
restore boundary addressable in the DOM (the marker's name is
`session_restored`; headline rendering collapses it to "Agent Start"). No other
component was touched; `frontend/dist` was rebuilt; the 35 TraceTimeline
vitest cases still pass.

## Console-error policy

The journey fails on any error-level console message (and `pageerror`), except
two documented benign patterns:

- favicon 404s (the dist ships favicons; purely defensive), and
- the decision-justification panel's designed probe: selecting a non-decision
  event triggers `GET /api/sessions/{sid}/decisions/{eid}/justification` → 404,
  which `useDecisionJustification` explicitly treats as a silent no-op. The
  filter matches the 404's request URL via `msg.location()`, not the message
  text, so unrelated 404s still fail the run.

## Findings / known limits

- **Pre-existing UI bug (not fixed, out of slice scope):** on the Inspect tab,
  `DecisionTree`'s `ResizeObserver` feedback loop grows the page continuously
  (the SVG is sized from the container, then resizes the container; ~4 kpx per
  400 ms with zero network traffic). It makes Playwright's actionability check
  ("element is stable") unable to click anything on that tab, and would
  eventually exhaust memory on a long-lived tab. The smoke works around it with
  a DOM-level `el.click()` for the evidence link; the real fix belongs in
  `DecisionTree.tsx` (break the observer loop, e.g. observe a fixed-height
  parent).
- **`content-visibility: auto`** on `.trace-timeline` means off-screen rows
  have empty `innerText`; assertions use `textContent`. Anything that queries
  rendered text off-screen will see the same effect.
- CI wiring deferred: the script is developer-run, not wired into a workflow;
  single browser (chromium headless) and single journey — no multi-session
  comparison, replay-mode, or analytics-tab coverage yet.
- The smoke targets local mode only (keyless loopback ingestion + queries);
  hosted/tenant auth paths remain covered by the pytest e2e suite.

## Verification log (2026-09-21)

- `node scripts/browser_smoke.mjs` — run 1: PASSED (exit 0, 15 steps logged);
  run 2: PASSED (exit 0). Both against a freshly built `frontend/dist`.
- `.venv-ci/bin/python -m pytest -q -o addopts='' tests/e2e` — 53 passed,
  server-side surface unchanged (suite files owned by another agent; this
  slice adds no server code).
- `npx vitest run src/__tests__/TraceTimeline.test.tsx` — 35/35 pass after the
  one-line timeline attribute addition.
