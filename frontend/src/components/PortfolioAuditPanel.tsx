import type {
  AuditVerificationStatus,
  PortfolioAuditResponse,
  PortfolioSessionRow,
} from '../types'
import { useSessionStore } from '../stores/sessionStore'
import './AuditPanel.css'
import './PortfolioAuditPanel.css'

interface PortfolioAuditPanelProps {
  report: PortfolioAuditResponse | null
  loading: boolean
  error: string | null
}

const TRUST_BAND_LABEL: Record<string, string> = {
  low: 'Low trust',
  medium: 'Medium trust',
  high: 'High trust',
}

/** Map a 0..1 mean trust score to a low/medium/high band (mirrors engine bands). */
function bandForScore(score: number): 'low' | 'medium' | 'high' {
  if (score < 0.45) return 'low'
  if (score < 0.7) return 'medium'
  return 'high'
}

const MEAN_COMPONENTS: Array<{ key: string; label: string; inverted?: boolean }> = [
  { key: 'evidence_coverage', label: 'Evidence coverage' },
  { key: 'verification_rate', label: 'Verification rate' },
  { key: 'policy_compliance', label: 'Policy compliance' },
  { key: 'recovery_rate', label: 'Recovery rate' },
  { key: 'failure_severity', label: 'Failure severity', inverted: true },
]

const VERIFICATION_ORDER: AuditVerificationStatus[] = [
  'verified',
  'partially_verified',
  'contradicted',
  'unsupported',
  'unverified',
]

function pct(value: number): string {
  return `${Math.round((value ?? 0) * 100)}%`
}

function componentTone(value: number, inverted?: boolean): string {
  const v = value ?? 0
  const score = inverted ? 1 - v : v
  if (score >= 0.66) return 'good'
  if (score >= 0.33) return 'warn'
  return 'bad'
}

function MeanComponent({ label, value, inverted }: { label: string; value: number; inverted?: boolean }) {
  return (
    <div className={`audit-trust-component audit-trust-component--${componentTone(value, inverted)}`}>
      <span className="audit-trust-component-label">{label}</span>
      <span className="audit-trust-component-value">{pct(value)}</span>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="audit-stat">
      <strong>{value}</strong>
      <small>{label}</small>
    </div>
  )
}

function SessionRow({ row }: { row: PortfolioSessionRow }) {
  const setSelectedSessionId = useSessionStore((state) => state.setSelectedSessionId)
  const setActiveTab = useSessionStore((state) => state.setActiveTab)

  const handleClick = () => {
    setSelectedSessionId(row.session_id)
    setActiveTab('inspect')
  }

  return (
    <li>
      <button type="button" className="portfolio-row" onClick={handleClick} data-band={row.band}>
        <div className="portfolio-row-head">
          <span className={`portfolio-row-score audit-score--${row.band}`}>
            {pct(row.trust_score)}
          </span>
          <span className="portfolio-row-name">{row.agent_name ?? row.session_id}</span>
          <span className="portfolio-row-band">{TRUST_BAND_LABEL[row.band] ?? row.band}</span>
        </div>
        <div className="portfolio-row-stats">
          <Stat label="Decisions" value={row.decision_count} />
          <Stat label="Unsupported" value={row.unsupported_count} />
          <Stat label="Contradictions" value={row.contradiction_count} />
          <Stat label="Failures" value={row.failure_count} />
          <Stat label="Signals" value={row.signal_count} />
        </div>
        {(row.objective || row.final_outcome) && (
          <p className="portfolio-row-outcome audit-muted">
            {row.objective ? `${row.objective}` : ''}
            {row.final_outcome ? ` → ${row.final_outcome}` : ''}
          </p>
        )}
      </button>
    </li>
  )
}

export function PortfolioAuditPanel({ report, loading, error }: PortfolioAuditPanelProps) {
  if (loading) {
    return (
      <section className="panel audit-panel">
        <p className="eyebrow">Fleet Audit Portfolio</p>
        <h2>Aggregating trust across runs…</h2>
        <p className="audit-muted">Auditing each recent session and reducing to fleet reliability.</p>
      </section>
    )
  }

  if (error) {
    return (
      <section className="panel audit-panel">
        <p className="eyebrow">Fleet Audit Portfolio</p>
        <h2>Portfolio unavailable</h2>
        <p className="audit-error">{error}</p>
      </section>
    )
  }

  if (!report) return null

  const { summary } = report
  if (summary.total_sessions === 0) {
    return (
      <section className="panel audit-panel">
        <div className="panel-head">
          <p className="eyebrow" title="Cross-session trust / verification / failure aggregate">Fleet Audit Portfolio</p>
          <h2>Reliability at a glance</h2>
        </div>
        <p className="audit-muted">No audited sessions yet. Capture a run to populate the fleet portfolio.</p>
      </section>
    )
  }

  const band = bandForScore(summary.trust.mean_score)

  return (
    <section className="panel audit-panel">
      <div className="panel-head">
        <p className="eyebrow" title="Cross-session trust / verification / failure aggregate">
          Fleet Audit Portfolio — {summary.total_sessions} session(s)
        </p>
        <h2>Reliability at a glance</h2>
      </div>

      <div className="audit-trust-header" data-trust-band={band}>
        <div className={`audit-score audit-score--${band}`}>
          <span className="audit-score-value">{Math.round(summary.trust.mean_score * 100)}</span>
          <span className="audit-score-unit">/100</span>
          <span className="audit-score-band">{TRUST_BAND_LABEL[band]}</span>
        </div>
        <div className="audit-trust-components">
          {MEAN_COMPONENTS.map((c) => (
            <MeanComponent
              key={c.key}
              label={c.label}
              value={(summary.means[c.key] as number) ?? 0}
              inverted={c.inverted}
            />
          ))}
        </div>
        <p className="audit-trust-explanation">
          Fleet mean trust across {summary.total_sessions} audited run(s). Lower-trust runs are
          listed below — open one to inspect its five-question audit.
        </p>
      </div>

      <div className="portfolio-meta-grid">
        <div className="audit-block">
          <p className="audit-block-label">Trust band distribution</p>
          <div className="audit-stats">
            <Stat label="High" value={summary.trust.band_distribution.high ?? 0} />
            <Stat label="Medium" value={summary.trust.band_distribution.medium ?? 0} />
            <Stat label="Low" value={summary.trust.band_distribution.low ?? 0} />
          </div>
        </div>

        <div className="audit-block">
          <p className="audit-block-label">Claim verification (fleet)</p>
          <div className="audit-tags">
            {VERIFICATION_ORDER.filter((status) => (summary.verification_totals[status] ?? 0) > 0).map((status) => (
              <span key={status} className={`audit-tag audit-verification-badge audit-verification-badge--${status}`}>
                {status.replace('_', ' ')}: {summary.verification_totals[status] ?? 0}
              </span>
            ))}
          </div>
        </div>

        <div className="audit-block">
          <p className="audit-block-label">Fleet totals</p>
          <div className="audit-stats">
            <Stat label="Decisions" value={summary.totals.decisions ?? 0} />
            <Stat label="Failures" value={summary.totals.failures ?? 0} />
            <Stat label="Unsupported" value={summary.totals.unsupported_claims ?? 0} />
            <Stat label="Contradictions" value={summary.totals.contradictions ?? 0} />
            <Stat label="Signals" value={summary.totals.signals ?? 0} />
          </div>
        </div>

        {summary.signal_type_counts.length > 0 && (
          <div className="audit-block">
            <p className="audit-block-label">Recurring signal types</p>
            <div className="audit-tags">
              {summary.signal_type_counts.map((s) => (
                <span key={s.type} className="audit-tag">{s.type}: {s.count}</span>
              ))}
            </div>
          </div>
        )}

        {summary.failure_mode_counts.length > 0 && (
          <div className="audit-block">
            <p className="audit-block-label">Recurring failure modes</p>
            <div className="audit-tags">
              {summary.failure_mode_counts.map((f) => (
                <span key={f.mode} className="audit-tag audit-tag--risk">{f.mode}: {f.count}</span>
              ))}
            </div>
          </div>
        )}
      </div>

      {summary.sessions.length > 0 && (
        <div className="audit-block">
          <p className="audit-block-label">Sessions — worst trust first</p>
          <ul className="portfolio-rows">
            {summary.sessions.map((row) => (
              <SessionRow key={row.session_id} row={row} />
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
