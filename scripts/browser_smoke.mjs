#!/usr/bin/env node
/**
 * Browser smoke journey (roadmap Q11 / W08 first slice).
 *
 * A REAL headless-chromium journey through the bundled React UI served by the
 * FastAPI server — not API tests:
 *
 *   1. start uvicorn (api.main:app) on an ephemeral port with a temp sqlite db
 *   2. seed, over plain HTTP (local mode = keyless loopback):
 *        - a "contradicted deploy" session: a confident decision citing a
 *          successful CI tool result, followed by a failing deploy in its
 *          causal subtree -> audit finding (contradiction) with evidence links
 *        - a checkpoint anchored mid-session, restored through
 *          POST /api/checkpoints/{id}/restore -> a second session whose first
 *          event is the session_restored provenance marker
 *   3. drive the UI: session list -> session -> Inspect tab -> audit panel ->
 *      click the contradicted finding's evidence link -> the linked event is
 *      selected in the timeline + event detail
 *   4. delayed-response coverage: page.route delays the restored session's
 *      audit API call by 1.5s once; assert the loading state shows, no crash,
 *      content renders afterwards
 *   5. navigate to the restored session; assert the restore boundary is
 *      visible (first timeline event is the session_restored marker; its
 *      provenance payload shows the restore token + source checkpoint)
 *   6. assert zero error-level console messages across the whole journey
 *
 * Exit 0 on success; on the first failed assertion it saves a screenshot to
 * /tmp/browser_smoke_fail.png before exiting 1.
 *
 * Run (from the repo root):
 *   node scripts/browser_smoke.mjs
 *
 * Playwright is resolved from NODE_PATH or the global npm root (npx-installed
 * 1.58.x with cached chromium); nothing is added to package.json.
 */

import { execFileSync, spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { existsSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const FAIL_SHOT = '/tmp/browser_smoke_fail.png'
const AUDIT_DELAY_MS = 1500

// ---------------------------------------------------------------------------
// Playwright resolution: NODE_PATH first, then the global npm root.
// ---------------------------------------------------------------------------

function resolvePlaywright() {
  const candidates = []
  if (process.env.NODE_PATH) candidates.push(...process.env.NODE_PATH.split(':'))
  try {
    candidates.push(execFileSync('npm', ['root', '-g'], { encoding: 'utf8' }).trim())
  } catch {
    /* npm not on PATH — rely on NODE_PATH */
  }
  for (const root of candidates) {
    if (!root || !existsSync(join(root, 'playwright'))) continue
    const req = createRequire(join(root, 'noop.cjs'))
    try {
      return req('playwright')
    } catch {
      /* try next candidate */
    }
  }
  throw new Error(
    'playwright not resolvable: run with NODE_PATH=<dir containing playwright> ' +
      'or install playwright globally (npm i -g playwright && npx playwright install chromium)',
  )
}

const { chromium } = resolvePlaywright()
const net = createRequire(import.meta.url)('node:net')

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

const steps = []
function logStep(message) {
  const line = `[step] ${message}`
  steps.push(message)
  console.log(line)
}

function freePort() {
  return new Promise((res, rej) => {
    const srv = net.createServer()
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address()
      srv.close(() => res(port))
    })
    srv.on('error', rej)
  })
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function apiFetch(base, path, options = {}) {
  const response = await fetch(`${base}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  })
  const text = await response.text()
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} on ${path}: ${text.slice(0, 400)}`)
  }
  return text ? JSON.parse(text) : null
}

// ---------------------------------------------------------------------------
// Server lifecycle
// ---------------------------------------------------------------------------

const PYTHON = existsSync(join(REPO_ROOT, '.venv-ci', 'bin', 'python'))
  ? join(REPO_ROOT, '.venv-ci', 'bin', 'python')
  : 'python3'

async function startServer(tmpDir, port) {
  const dbUrl = `sqlite+aiosqlite:///${tmpDir}/smoke.db`
  const child = spawn(
    PYTHON,
    [
      '-m', 'uvicorn', 'api.main:app',
      '--host', '127.0.0.1',
      '--port', String(port),
      '--log-level', 'warning',
    ],
    {
      cwd: tmpDir, // keep cwd-relative side effects (analytics.db) inside tmp
      env: {
        ...process.env,
        AGENT_DEBUGGER_DB_URL: dbUrl,
        PYTHONPATH: `${REPO_ROOT}${process.env.PYTHONPATH ? ':' + process.env.PYTHONPATH : ''}`,
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  )
  let output = ''
  child.stdout.on('data', (d) => (output += d.toString()))
  child.stderr.on('data', (d) => (output += d.toString()))

  const base = `http://127.0.0.1:${port}`
  const deadline = Date.now() + 60_000
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`server died during startup:\n${output.slice(-3000)}`)
    }
    try {
      const r = await fetch(`${base}/api/health`)
      if (r.ok) {
        logStep(`server up on ${base} (temp db: ${dbUrl})`)
        return { child, base }
      }
    } catch {
      /* not up yet */
    }
    await sleep(300)
  }
  child.kill('SIGKILL')
  throw new Error('server never became healthy')
}

async function stopServer(child) {
  child.kill('SIGTERM')
  const exited = await Promise.race([
    new Promise((r) => child.on('exit', () => r(true))),
    sleep(5000).then(() => false),
  ])
  if (!exited) child.kill('SIGKILL')
}

// ---------------------------------------------------------------------------
// Seed data — contradicted deploy + mid-session checkpoint, over HTTP
// ---------------------------------------------------------------------------

const RUN_TAG = Math.random().toString(36).slice(2, 10)
const SID_A = `smoke-contradicted-${RUN_TAG}`
const SID_B = `smoke-restored-${RUN_TAG}`
const ID = {
  turn: `ev-${RUN_TAG}-turn`,
  ci: `ev-${RUN_TAG}-ci`,
  decision: `ev-${RUN_TAG}-decision`,
  deployCall: `ev-${RUN_TAG}-deploy-call`,
  deployFail: `ev-${RUN_TAG}-deploy-fail`,
  unsupported: `ev-${RUN_TAG}-unsupported`,
}
const CP_ID = `cp-${RUN_TAG}-1`

const ts = (i) => `2026-09-20T10:00:${String(i).padStart(2, '0')}+00:00`

function traceEvent(eventType, id, timestamp, extra = {}) {
  // POST /api/traces accepts the SDK to_dict() shape: typed event fields sent
  // as top-level extras are folded into the stored payload by the collector.
  return { session_id: SID_A, id, event_type: eventType, timestamp, name: '', ...extra }
}

async function seed(base) {
  logStep(`seeding session ${SID_A} (contradicted deploy + checkpoint) over HTTP`)
  await apiFetch(base, '/api/sessions', {
    method: 'POST',
    body: JSON.stringify({
      id: SID_A,
      agent_name: 'deploy_agent_smoke',
      framework: 'custom',
      tags: ['browser-smoke', 'contradiction'],
      config: { goal: 'Ship version 2.3 to production and confirm the health check' },
    }),
  })

  const events = [
    traceEvent('agent_turn', ID.turn, ts(0), {
      agent_id: 'deploy_agent_smoke',
      speaker: 'user',
      turn_index: 0,
      content: 'Ship version 2.3 to production and confirm the health check.',
      goal: 'Ship version 2.3 to production and confirm the health check',
    }),
    traceEvent('tool_result', ID.ci, ts(1), {
      tool_name: 'ci_status_check',
      result: { status: 'passed', build: '2.3', gate: 'green' },
      duration_ms: 120,
      upstream_event_ids: [ID.turn],
    }),
    traceEvent('decision', ID.decision, ts(2), {
      reasoning: 'CI check passed for build 2.3, safe to deploy now',
      confidence: 0.9,
      chosen_action: 'deploy_version_2_3',
      evidence_event_ids: [ID.ci],
      evidence: [{ source: 'tool_result', content: 'ci gate green for build 2.3' }],
      alternatives: [{ action: 'wait_for_fresh_ci_run', chosen: false }],
      upstream_event_ids: [ID.turn],
    }),
    traceEvent('tool_call', ID.deployCall, ts(3), {
      tool_name: 'deploy',
      arguments: { version: '2.3', environment: 'production' },
      upstream_event_ids: [ID.decision],
    }),
    traceEvent('tool_result', ID.deployFail, ts(4), {
      tool_name: 'deploy',
      result: null,
      error: 'health check failed: 3 replicas crashed after rollout',
      duration_ms: 8300,
      upstream_event_ids: [ID.decision],
    }),
    traceEvent('decision', ID.unsupported, ts(5), {
      reasoning: '',
      confidence: 0.8,
      chosen_action: 'declare_incident_resolved',
      upstream_event_ids: [ID.deployFail],
    }),
  ]
  for (const event of events) {
    await apiFetch(base, '/api/traces', { method: 'POST', body: JSON.stringify(event) })
  }

  // Mid-session checkpoint anchored on the CI result (the evidence event).
  await apiFetch(base, '/api/checkpoints', {
    method: 'POST',
    body: JSON.stringify({
      session_id: SID_A,
      id: CP_ID,
      event_id: ID.ci,
      sequence: 1,
      state: { stage: 'ci_verified', version: '2.3', framework: 'custom' },
      memory: { last_gate: 'green' },
      timestamp: ts(2),
      importance: 0.7,
    }),
  })

  // Server-side precheck: the audit must already contain the finding the
  // browser will hunt down.
  const audit = await apiFetch(base, `/api/sessions/${SID_A}/audit`)
  const claims = audit.audit.claims || []
  const contradicted = claims.find((c) => c.event_id === ID.decision)
  if (!contradicted || contradicted.verification_status !== 'contradicted') {
    throw new Error(
      `seed precheck: decision is not contradicted (claims: ` +
        `${JSON.stringify(claims.map((c) => [c.event_id, c.verification_status]))})`,
    )
  }
  if (!Array.isArray(contradicted.evidence_refs) || contradicted.evidence_refs[0] !== ID.ci) {
    throw new Error(`seed precheck: contradicted claim missing evidence ref to ${ID.ci}`)
  }
  logStep(`audit finding confirmed server-side: decision CONTRADICTED, evidence ref -> ${ID.ci}`)

  // Semantic restore -> second session led by the session_restored marker.
  const restore = await apiFetch(base, `/api/checkpoints/${CP_ID}/restore`, {
    method: 'POST',
    body: JSON.stringify({ session_id: SID_B, label: 'restored_deploy_smoke' }),
  })
  const traceB = await apiFetch(base, `/api/sessions/${SID_B}/trace`)
  const first = traceB.events[0]
  if (!first || first.name !== 'session_restored') {
    throw new Error(
      `restore precheck: first event of ${SID_B} is not the session_restored marker (` +
        `${first && first.name})`,
    )
  }
  logStep(
    `restored session ${SID_B}: ${restore.copied_event_count} events copied, ` +
      `restore marker leads (token ${restore.restore_token.slice(0, 8)}…)`,
  )
  return { restoreToken: restore.restore_token }
}

// ---------------------------------------------------------------------------
// Browser journey
// ---------------------------------------------------------------------------

async function runJourney(base, { restoreToken }) {
  const consoleErrors = []
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage()

  page.on('console', (msg) => {
    if (msg.type() !== 'error') return
    const text = msg.text()
    const url = msg.location()?.url || ''
    // Benign, known noise:
    //  - favicon 404s (dist ships favicons, but be forgiving)
    //  - the decision-justification panel's designed "404 = not a decision"
    //    probe (useDecisionJustification treats it as a silent no-op)
    if (/favicon/i.test(text) || /\/decisions\/[^/]+\/justification/.test(url)) return
    consoleErrors.push(text)
  })
  page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`))

  const assert = (condition, message) => {
    if (!condition) throw new Error(`assertion failed: ${message}`)
  }

  try {
    // Delayed-response coverage: intercept the restored session's audit call
    // once and stall it for 1.5s. The UI must show its loading state, not
    // crash, and render the report afterwards.
    let delayed = false
    await page.route(`**/api/sessions/${SID_B}/audit`, async (route) => {
      if (delayed) {
        await route.continue()
        return
      }
      delayed = true
      await sleep(AUDIT_DELAY_MS)
      await route.continue()
    })

    // -- 1. open the UI, wait for the session list ------------------------------
    logStep(`opening ${base}/ui/ and waiting for the session list`)
    await page.goto(`${base}/ui/`, { waitUntil: 'domcontentloaded' })
    await page.locator('.session-card').first().waitFor({ state: 'visible', timeout: 20_000 })
    const cardCount = await page.locator('.session-card').count()
    assert(cardCount >= 2, `expected >=2 session cards, saw ${cardCount}`)
    logStep(`session list rendered (${cardCount} captured runs)`)

    // -- 2. select the seeded contradicted session -------------------------------
    const cardA = page.locator('.session-card', { hasText: 'deploy_agent_smoke' }).first()
    await cardA.click()
    await page
      .locator('.timeline-event', { hasText: 'deploy_version_2_3' })
      .first()
      .waitFor({ state: 'visible', timeout: 20_000 })
    logStep('session selected; timeline shows the seeded decision event')

    // -- 3. open the audit panel and follow the finding's evidence link ----------
    await page.getByRole('button', { name: 'Inspect', exact: true }).click()
    const auditPanel = page.locator('.audit-panel')
    await auditPanel
      .getByRole('heading', { name: 'Trust & verification' })
      .waitFor({ timeout: 20_000 })

    const contradictedClaim = auditPanel.locator('.audit-claim[data-verification="contradicted"]')
    await contradictedClaim.first().waitFor({ timeout: 10_000 })
    // textContent (not innerText): the timeline CSS uses content-visibility,
    // so off-screen rows render with empty innerText.
    const claimText = await contradictedClaim.first().textContent() || ''
    assert(
      /contradicted/i.test(claimText),
      `contradicted claim row did not render its verification badge: ${claimText}`,
    )
    logStep('audit panel shows the CONTRADICTED finding')

    const evidenceLink = contradictedClaim.first().locator('.audit-tag--link')
    const evidenceLinkCount = await evidenceLink.count()
    assert(evidenceLinkCount >= 1, 'contradicted finding has no clickable evidence link')
    // DOM-level click: the Inspect tab's d3 decision tree has a ResizeObserver
    // feedback loop that grows the page continuously, so Playwright's
    // actionability "element is stable" check never passes here (see the
    // findings doc). The React onClick handler fires normally on el.click().
    await evidenceLink.first().evaluate((el) => el.click())
    logStep(`clicked the finding's evidence link (${evidenceLinkCount} ref(s) listed)`)

    // -- 4. the linked event is selected in timeline + event detail --------------
    await page.getByRole('button', { name: 'Trace', exact: true }).click()
    const selectedRow = page.locator('.timeline-event.selected')
    await selectedRow.waitFor({ timeout: 10_000 })
    const selectedText = await selectedRow.first().textContent() || ''
    assert(
      selectedText.includes('ci_status_check'),
      `selected timeline row is not the linked evidence event (ci_status_check): ${selectedText}`,
    )
    const detail = page.locator('.event-detail')
    await detail.waitFor({ timeout: 10_000 })
    const detailHeading = (await detail.locator('h2').first().textContent()) || ''
    assert(
      detailHeading.trim() === 'ci_status_check',
      `event detail heading expected "ci_status_check", saw "${detailHeading.trim()}"`,
    )
    const payloadText = (await detail.textContent()) || ''
    assert(payloadText.includes(ID.ci), 'event detail payload does not contain the linked event id')
    logStep('evidence link navigated to the correct event (timeline + event detail)')

    // -- 5. switch to the restored session with a delayed audit response ---------
    logStep('selecting the restored session; its audit API call is delayed 1.5s once')
    const cardB = page.locator('.session-card', { hasText: 'restored_deploy_smoke' }).first()
    await cardB.click()

    await page.getByRole('button', { name: 'Inspect', exact: true }).click()
    await page
      .getByText('Computing audit report', { exact: false })
      .waitFor({ state: 'visible', timeout: 5_000 })
    assert(delayed, 'audit route interception never fired')
    logStep('delayed audit response: UI shows its loading state, no crash')

    await page
      .locator('.audit-panel')
      .getByRole('heading', { name: 'Trust & verification' })
      .waitFor({ timeout: 20_000 })
    logStep('delayed audit response completed; report rendered')

    // -- 6. the restore boundary is visible --------------------------------------
    await page.getByRole('button', { name: 'Trace', exact: true }).click()
    const markerRow = page.locator('.timeline-event[data-event-name="session_restored"]')
    await markerRow.first().waitFor({ state: 'visible', timeout: 20_000 })
    const markerIsFirst = await markerRow
      .first()
      .evaluate((node) => node.parentElement.firstElementChild === node)
    assert(markerIsFirst, 'session_restored marker is not the first timeline event (restore boundary)')
    await markerRow.first().click()

    const restoredDetail = page.locator('.event-detail')
    await restoredDetail.waitFor({ timeout: 10_000 })
    const restoredPayload = (await restoredDetail.textContent()) || ''
    assert(restoredPayload.includes('session_restored'), 'marker payload does not name session_restored')
    assert(restoredPayload.includes(restoreToken), 'marker payload does not show the restore token')
    assert(restoredPayload.includes(CP_ID), 'marker payload does not show the source checkpoint id')
    logStep('restore boundary visible: first event is the session_restored provenance marker')

    // -- 7. zero console errors ---------------------------------------------------
    if (consoleErrors.length > 0) {
      throw new Error(`console errors during journey:\n  ${consoleErrors.join('\n  ')}`)
    }
    logStep('zero error-level console messages across the journey')
  } catch (err) {
    await page
      .screenshot({ path: FAIL_SHOT, fullPage: true })
      .then(() => console.error(`[FAIL] screenshot saved to ${FAIL_SHOT}`))
      .catch(() => console.error(`[FAIL] screenshot could not be saved to ${FAIL_SHOT}`))
    throw err
  } finally {
    await browser.close().catch(() => {})
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  if (!existsSync(join(REPO_ROOT, 'frontend', 'dist', 'index.html'))) {
    throw new Error('frontend/dist is missing — run `cd frontend && npm run build` first')
  }

  const tmpDir = mkdtempSync(join(tmpdir(), 'browser-smoke-'))
  const port = await freePort()
  const { child, base } = await startServer(tmpDir, port)

  try {
    const seedInfo = await seed(base)
    await runJourney(base, seedInfo)
    console.log('\nbrowser smoke journey PASSED')
    for (const step of steps) console.log(`  [step] ${step}`)
  } finally {
    await stopServer(child)
    rmSync(tmpDir, { recursive: true, force: true })
  }
}

main().catch((err) => {
  console.error(`\n[FAIL] ${err && err.message ? err.message : err}`)
  process.exit(1)
})
