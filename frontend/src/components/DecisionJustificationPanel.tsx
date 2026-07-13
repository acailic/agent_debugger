import type { ReactNode } from 'react'
import type {
  AuditVerificationStatus,
  DecisionJustification,
} from '../types'
import './AuditPanel.css'
import './DecisionJustificationPanel.css'

interface DecisionJustificationPanelProps {
  justification: DecisionJustification | null
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

/**
 * Per-decision audit surface: the Why / Evidence / Outcome / Where-failed /
 * Policy triad for the currently selected decision event. This is the
 * event-level counterpart to the session-level AuditPanel — it answers the
 * same five operator questions, but scoped to a single node.
 */
export function DecisionJustificationPanel({
  justification,
  loading,
  error,
  onSelectEvent,
}: DecisionJustificationPanelProps) {
  if (loading) {
    return (
      <section className="panel decision-justification-panel">
        <p className="eyebrow">Why this decision</p>
        <h2>Loading justification…</h2>
        <p className="audit-muted">Resolving rationale, evidence, and outcome for this node.</p>
      </section>
    )
  }

  if (error) {
    return (
      <section className="panel decision-justification-panel">
        <p className="eyebrow">Why this decision</p>
        <h2>Justification unavailable</h2>
        <p className="audit-error">{error}</p>
      </section>
    )
  }

  // No justification means the selected event is not a decision — render nothing.
  if (!justification) return null

  const status = justification.evidence.verification_status as AuditVerificationStatus
  const evidence = justification.evidence
  const outcome = justification.outcome
  const where = justification.where_it_failed
  const policy = justification.policy

  return (
    <section
      className="panel decision-justification-panel"
      data-verification={status}
      data-failed={where.contradicted || where.subtree_failures.length > 0 ? 'true' : 'false'}
    >
      <div className="panel-head">
        <p className="eyebrow" title="Per-node why / evidence / outcome / where-failed audit">
          Why this decision — node audit
        </p>
        <h2>{justification.headline}</h2>
      </div>

      <div className="decision-justification-headline">
        <span className={`audit-verification-badge audit-verification-badge--${status}`}>
          {VERIFICATION_LABELS[status] ?? status}
        </span>
        <span className="audit-confidence" title="Stated confidence">
          {Math.round(justification.why.confidence * 100)}%
        </span>
        <span className="decision-justification-action">{justification.what.action}</span>
      </div>

      <div className="decision-justification-grid">
        <JustifyCard title="Why" tone="why">
          <p className="decision-justification-rationale">{justification.why.rationale}</p>
          {justification.why.intent && (
            <p className="audit-muted">
              <span className="audit-inline-label">Intent:</span> {justification.why.intent}
            </p>
          )}
          {justification.why.alternatives.length > 0 && (
            <ul className="decision-justification-alternatives">
              {justification.why.alternatives.map((alt, idx) => (
                <li key={`${alt.action}-${idx}`} className={alt.chosen ? 'chosen' : ''}>
                  {alt.chosen ? '✓ ' : '· '}
                  {alt.action}
                </li>
              ))}
            </ul>
          )}
        </JustifyCard>

        <JustifyCard title="Evidence used" tone="evidence">
          {evidence.refs.length === 0 && evidence.sources.length === 0 ? (
            <p className="audit-muted">No evidence cited for this claim.</p>
          ) : (
            <>
              <div className="audit-tags">
                {evidence.sources.map((src) => (
                  <span key={src} className="audit-tag">{src}</span>
                ))}
              </div>
              <p className="audit-muted">
                <span className="audit-inline-label">Refs:</span>{' '}
                {evidence.refs.length} cited / {evidence.resolved_refs.length} resolved
              </p>
              <div className="audit-tags">
                {evidence.refs.map((ref) => {
                  const resolved = evidence.resolved_refs.includes(ref)
                  return (
                    <button
                      key={ref}
                      className={`audit-tag audit-tag--link${resolved ? '' : ' unresolved'}`}
                      type="button"
                      disabled={!resolved}
                      onClick={() => onSelectEvent(ref)}
                      title={resolved ? 'Inspect evidence' : 'Unresolved reference'}
                    >
                      {ref.slice(0, 8)}
                    </button>
                  )
                })}
              </div>
            </>
          )}
          <p className="decision-justification-basis">
            <span className="audit-inline-label">Basis:</span> {evidence.verification_basis}
          </p>
        </JustifyCard>

        <JustifyCard title="Result / impact" tone="outcome">
          <div className="decision-justification-stats">
            <JustifyStat label="Downstream" value={outcome.downstream_event_count} />
            <JustifyStat label="Successes" value={outcome.downstream_successes} />
            <JustifyStat
              label="Failures"
              value={outcome.downstream_failures}
              tone={outcome.downstream_failures > 0 ? 'bad' : undefined}
            />
            <JustifyStat label="State changes" value={outcome.state_changes} />
          </div>
          {outcome.produced.length > 0 && (
            <ul className="decision-justification-produced">
              {outcome.produced.slice(0, 6).map((prod, idx) => (
                <li key={idx}>{prod}</li>
              ))}
            </ul>
          )}
        </JustifyCard>

        <JustifyCard title="Where it failed" tone="where">
          {!where.contradicted && where.subtree_failures.length === 0 ? (
            <p className="audit-muted">No localized failure in this decision's subtree.</p>
          ) : (
            <>
              {where.contradicted && (
                <p className="decision-justification-flag decision-justification-flag--bad">
                  Claim contradicted by cited evidence.
                </p>
              )}
              {where.subtree_failures.map((failure, idx) => (
                <div key={idx} className="decision-justification-subtree-failure">
                  <span className="audit-signal-type">{failure.mode}</span>
                  <span className="audit-signal-msg">{failure.symptom}</span>
                  {failure.likely_cause_event_id && (
                    <button
                      className="audit-link"
                      type="button"
                      onClick={() => onSelectEvent(failure.likely_cause_event_id!)}
                    >
                      inspect cause
                    </button>
                  )}
                </div>
              ))}
            </>
          )}
          {where.path_to_first_failure.length > 0 && (
            <div className="decision-justification-path">
              <span className="audit-inline-label">Path to first failure:</span>
              <ol>
                {where.path_to_first_failure.map((eventId, idx) => (
                  <li key={`${eventId}-${idx}`}>
                    <button className="audit-link" type="button" onClick={() => onSelectEvent(eventId)}>
                      {eventId.slice(0, 8)}
                    </button>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </JustifyCard>
      </div>

      <div className="decision-justification-policy">
        <span
          className={`decision-justification-policy-badge ${
            policy.compliant ? 'compliant' : 'violated'
          }`}
        >
          {policy.compliant ? 'Policy compliant' : `${policy.violations_in_subtree.length} policy violation(s) in subtree`}
        </span>
        {policy.violations_in_subtree.length > 0 && (
          <div className="audit-tags">
            {policy.violations_in_subtree.map((violation, idx) => (
              <button
                key={`${violation.event_id}-${idx}`}
                className="audit-tag audit-tag--link"
                type="button"
                onClick={() => onSelectEvent(violation.event_id)}
              >
                {violation.type}
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

function JustifyCard({
  title,
  tone,
  children,
}: {
  title: string
  tone: string
  children: ReactNode
}) {
  return (
    <div className={`decision-justification-card decision-justification-card--${tone}`}>
      <p className="decision-justification-card-title">{title}</p>
      <div className="decision-justification-card-body">{children}</div>
    </div>
  )
}

function JustifyStat({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone?: 'bad' | 'warn'
}) {
  return (
    <div className={`decision-justification-stat${tone ? ` decision-justification-stat--${tone}` : ''}`}>
      <strong>{value}</strong>
      <small>{label}</small>
    </div>
  )
}
