import type { ReactNode } from 'react'
import type {
  AuditClaim,
  AuditFailure,
  AuditReviewPoint,
  AuditSignal,
  AuditVerificationStatus,
  SessionAuditReport,
} from '../types'
import './AuditPanel.css'

interface AuditPanelProps {
  report: SessionAuditReport | null
  loading: boolean
  error: string | null
  selectedEventId: string | null
  onSelectEvent: (eventId: string) => void
}

const VERIFICATION_LABELS: Record<AuditVerificationStatus, string> = {
  verified: 'Verified',
  partially_verified: 'Partial',
  contradicted: 'Contradicted',
  unsupported: 'Unsupported',
  unverified: 'Unverified',
  stale: 'Stale',
}

const TRUST_BAND_LABEL: Record<string, string> = {
  low: 'Low trust',
  medium: 'Medium trust',
  high: 'High trust',
}

export function AuditPanel({
  report,
  loading,
  error,
  selectedEventId,
  onSelectEvent,
}: AuditPanelProps) {
  if (loading) {
    return (
      <section className="panel audit-panel">
        <p className="eyebrow">Agent Audit</p>
        <h2>Computing audit report…</h2>
        <p className="audit-muted">Classifying claims, evidence, and failure provenance.</p>
      </section>
    )
  }

  if (error) {
    return (
      <section className="panel audit-panel">
        <p className="eyebrow">Agent Audit</p>
        <h2>Audit unavailable</h2>
        <p className="audit-error">{error}</p>
      </section>
    )
  }

  if (!report) return null

  const { questions, trust } = report
  const trustPct = Math.round(trust.score * 100)

  return (
    <section className="panel audit-panel" data-trust-band={trust.band}>
      <div className="panel-head">
        <p className="eyebrow" title="Evidence-backed audit answering what / why / evidence / outcome / where-failed">
          Agent Audit — Black Box Recorder
        </p>
        <h2>Trust &amp; verification</h2>
      </div>

      <div className="audit-trust-header">
        <div className={`audit-score audit-score--${trust.band}`}>
          <span className="audit-score-value">{trustPct}</span>
          <span className="audit-score-unit">/100</span>
          <span className="audit-score-band">{TRUST_BAND_LABEL[trust.band] ?? trust.band}</span>
        </div>
        <div className="audit-trust-components">
          <TrustComponent label="Evidence coverage" value={trust.components.evidence_coverage} />
          <TrustComponent label="Verification rate" value={trust.components.verification_rate} />
          <TrustComponent label="Policy compliance" value={trust.components.policy_compliance} />
          <TrustComponent label="Recovery rate" value={trust.components.recovery_rate} />
          <TrustComponent label="Failure severity" value={trust.components.failure_severity} inverted />
          <TrustComponent label="Contradiction rate" value={trust.components.contradiction_rate} inverted />
        </div>
        <p className="audit-trust-explanation">{trust.explanation}</p>
      </div>

      {report.objective && (
        <div className="audit-block">
          <p className="audit-block-label">Objective</p>
          <p className="audit-objective">{report.objective}</p>
          <p className="audit-outcome">Outcome: {report.final_outcome}</p>
        </div>
      )}

      <div className="audit-questions-grid">
        <QuestionCard title="What happened" className="audit-q--what">
          <p>{questions.what_happened.summary}</p>
          <div className="audit-stats">
            <Stat label="Events" value={questions.what_happened.event_count} />
            <Stat label="Tools" value={questions.what_happened.tool_calls} />
            <Stat label="Model calls" value={questions.what_happened.llm_calls} />
            <Stat label="Decisions" value={questions.what_happened.decisions} />
            <Stat label="Retries" value={questions.what_happened.retries} />
          </div>
        </QuestionCard>

        <QuestionCard title="Evidence used" className="audit-q--evidence">
          <div className="audit-stats">
            <Stat label="Tool-backed" value={questions.evidence.tool_backed_facts} />
            <Stat label="User-provided" value={questions.evidence.user_input_facts} />
            <Stat label="Retrieved" value={questions.evidence.retrieved_facts} />
          </div>
          <p className="audit-muted">
            Coverage of decisions: {Math.round(questions.evidence.coverage_of_decisions * 100)}%
          </p>
          {questions.evidence.evidence_sources.length > 0 && (
            <div className="audit-tags">
              {questions.evidence.evidence_sources.map((src) => (
                <span key={src} className="audit-tag">{src}</span>
              ))}
            </div>
          )}
        </QuestionCard>

        <QuestionCard title="Result / impact" className="audit-q--outcome">
          <div className="audit-stats">
            <Stat label="Successes" value={questions.outcome.success_count} />
            <Stat label="Failures" value={questions.outcome.failure_count} />
            <Stat label="Failed tools" value={questions.outcome.failed_tool_results} />
            <Stat label="State snapshots" value={questions.outcome.state_snapshots} />
          </div>
        </QuestionCard>

        <QuestionCard title="Where it failed" className="audit-q--where">
          {questions.where_it_failed.failures === 0 ? (
            <p className="audit-muted">No localized failures detected.</p>
          ) : (
            <>
              <p className="audit-muted">
                {questions.where_it_failed.failures} failure signal(s).
                {questions.where_it_failed.first_bad_decision && (
                  <> First bad decision: <button className="audit-link" type="button" onClick={() => onSelectEvent(questions.where_it_failed.first_bad_decision!)}>jump</button>.</>
                )}
              </p>
              <ul className="audit-signal-list">
                {questions.where_it_failed.top_signals.map((signal, idx) => (
                  <li key={`${signal.type}-${idx}`} className={`audit-signal audit-signal--${signal.severity}`}>
                    <span className="audit-signal-type">{signal.type}</span>
                    <span className="audit-signal-severity">{signal.severity}</span>
                    <span className="audit-signal-msg">{signal.message}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </QuestionCard>
      </div>

      {report.claims.length > 0 && (
        <div className="audit-block">
          <p className="audit-block-label">Decision claims ({report.claims.length})</p>
          <ul className="audit-claims-list">
            {report.claims.map((claim) => (
              <ClaimRow
                key={claim.event_id}
                claim={claim}
                selected={selectedEventId === claim.event_id}
                onSelectEvent={onSelectEvent}
              />
            ))}
          </ul>
        </div>
      )}

      {report.failures.length > 0 && (
        <div className="audit-block">
          <p className="audit-block-label">Localized failures ({report.failures.length})</p>
          <ul className="audit-failures-list">
            {report.failures.map((failure) => (
              <FailureRow
                key={failure.event_id ?? failure.headline}
                failure={failure}
                selected={selectedEventId === failure.event_id}
                onSelectEvent={onSelectEvent}
              />
            ))}
          </ul>
        </div>
      )}

      {report.review_points.length > 0 && (
        <div className="audit-block">
          <p className="audit-block-label">Recommended human review ({report.review_points.length})</p>
          <ul className="audit-review-list">
            {report.review_points.map((point, idx) => (
              <ReviewRow key={`${point.event_id}-${idx}`} point={point} onSelectEvent={onSelectEvent} />
            ))}
          </ul>
        </div>
      )}

      {report.signals.length > 0 && (
        <div className="audit-block">
          <p className="audit-block-label">Risk signals ({report.signals.length})</p>
          <ul className="audit-signal-list audit-signal-list--flat">
            {report.signals.map((signal, idx) => (
              <SignalRow key={`${signal.event_id}-${signal.type}-${idx}`} signal={signal} onSelectEvent={onSelectEvent} />
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

function TrustComponent({
  label,
  value,
  inverted = false,
}: {
  label: string
  value: number | undefined
  inverted?: boolean
}) {
  if (value === undefined || !Number.isFinite(value)) return null
  const pct = Math.round(value * 100)
  const tone = inverted ? pct : 100 - pct
  const cls = tone >= 67 ? 'good' : tone >= 34 ? 'warn' : 'bad'
  return (
    <div className={`audit-trust-component audit-trust-component--${cls}`}>
      <span className="audit-trust-component-label">{label}</span>
      <span className="audit-trust-component-value">{pct}%</span>
    </div>
  )
}

function QuestionCard({
  title,
  className,
  children,
}: {
  title: string
  className?: string
  children: ReactNode
}) {
  return (
    <div className={`audit-question-card ${className ?? ''}`}>
      <p className="audit-question-title">{title}</p>
      <div className="audit-question-body">{children}</div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="audit-stat">
      <strong>{value}</strong>
      <small>{label}</small>
    </div>
  )
}

function ClaimRow({
  claim,
  selected,
  onSelectEvent,
}: {
  claim: AuditClaim
  selected: boolean
  onSelectEvent: (eventId: string) => void
}) {
  return (
    <li
      className={`audit-claim ${selected ? 'audit-claim--active' : ''}`}
      data-verification={claim.verification_status}
      onClick={() => onSelectEvent(claim.event_id)}
    >
      <div className="audit-claim-head">
        <span className={`audit-verification-badge audit-verification-badge--${claim.verification_status}`}>
          {VERIFICATION_LABELS[claim.verification_status] ?? claim.verification_status}
        </span>
        <span className="audit-claim-headline">{claim.headline}</span>
        <span className="audit-confidence" title="Stated confidence">
          {Math.round(claim.confidence * 100)}%
        </span>
      </div>
      {claim.claim && claim.claim !== claim.headline && (
        <p className="audit-claim-text">{claim.claim}</p>
      )}
      {claim.rationale && (
        <p className="audit-claim-rationale"><span className="audit-inline-label">Why:</span> {claim.rationale}</p>
      )}
      <div className="audit-claim-meta">
        <span className="audit-inline-label">Evidence:</span>
        {claim.evidence_refs.length === 0 && claim.evidence_sources.length === 0 ? (
          <span className="audit-muted"> none</span>
        ) : (
          <>
            {claim.evidence_sources.map((src) => (
              <span key={src} className="audit-tag">{src}</span>
            ))}
            {claim.evidence_refs.map((ref) => (
              <button
                key={ref}
                className="audit-tag audit-tag--link"
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  onSelectEvent(ref)
                }}
              >
                {ref.slice(0, 8)}
              </button>
            ))}
          </>
        )}
        <span className="audit-verification-basis">{claim.verification_basis}</span>
      </div>
    </li>
  )
}

function FailureRow({
  failure,
  selected,
  onSelectEvent,
}: {
  failure: AuditFailure
  selected: boolean
  onSelectEvent: (eventId: string) => void
}) {
  return (
    <li
      className={`audit-failure ${selected ? 'audit-failure--active' : ''}`}
      onClick={() => failure.event_id && onSelectEvent(failure.event_id)}
    >
      <div className="audit-failure-head">
        <span className="audit-failure-mode">{failure.mode}</span>
        <span className="audit-failure-headline">{failure.headline}</span>
        <span className="audit-confidence">{Math.round(failure.confidence * 100)}%</span>
      </div>
      <p className="audit-failure-symptom"><span className="audit-inline-label">Symptom:</span> {failure.symptom}</p>
      <p className="audit-failure-cause">
        <span className="audit-inline-label">Likely cause:</span> {failure.likely_cause}
        {failure.likely_cause_event_id && (
          <button
            className="audit-link"
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onSelectEvent(failure.likely_cause_event_id!)
            }}
          >
            inspect cause
          </button>
        )}
      </p>
    </li>
  )
}

function ReviewRow({
  point,
  onSelectEvent,
}: {
  point: AuditReviewPoint
  onSelectEvent: (eventId: string) => void
}) {
  return (
    <li className={`audit-review audit-review--${point.priority}`} onClick={() => onSelectEvent(point.event_id)}>
      <span className={`audit-review-priority audit-review-priority--${point.priority}`}>{point.priority}</span>
      <span className="audit-review-reason">{point.reason}</span>
    </li>
  )
}

function SignalRow({
  signal,
  onSelectEvent,
}: {
  signal: AuditSignal
  onSelectEvent: (eventId: string) => void
}) {
  return (
    <li
      className={`audit-signal audit-signal--${signal.severity}`}
      onClick={() => onSelectEvent(signal.event_id)}
    >
      <span className="audit-signal-type">{signal.type}</span>
      <span className="audit-signal-severity">{signal.severity}</span>
      <span className="audit-signal-msg">{signal.message}</span>
    </li>
  )
}
