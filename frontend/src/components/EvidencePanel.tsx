import { useEffect, useState } from 'react'
import type {
  EvidenceEntry,
  EvidenceIntegrity,
  EvidencePackageDetail,
  EvidencePackageSummary,
} from '../types'
import { getEvidencePackage, getEvidencePackages } from '../api/client'
import './AuditPanel.css'

interface EvidencePanelProps {
  /**
   * Peaky Peek event id currently selected in the audit view. Evidence rows
   * whose MCP call_id matches are highlighted — the lightweight per-event
   * alignment until executions carry an explicit session linkage.
   */
  highlightCallId: string | null
}

const INTEGRITY_LABEL: Record<EvidenceIntegrity, string> = {
  verified: 'Verified',
  unverified: 'Unverified',
  failed: 'Failed',
}

const INTEGRITY_BADGE: Record<EvidenceIntegrity, string> = {
  verified: 'audit-verification-badge--verified',
  unverified: 'audit-verification-badge--unverified',
  failed: 'audit-verification-badge--unsupported',
}

const EVENT_TYPE_LABEL: Record<string, string> = {
  'execution.started': 'Execution started',
  'decision.recorded': 'Gateway decision',
  'outcome.recorded': 'Observed outcome',
}

/**
 * Agent Evidence Box panel: exported, offline-verifiable evidence packages
 * mapped onto the investigation timeline.
 *
 * The integrity/coverage badges carry ONLY the cryptographic verifier's
 * verdict; they are a separate field from the behavioral audit assessment
 * (trust score, claim verification) shown elsewhere in the AuditPanel.
 */
export function EvidencePanel({ highlightCallId }: EvidencePanelProps) {
  const [open, setOpen] = useState(false)
  const [packages, setPackages] = useState<EvidencePackageSummary[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<EvidencePackageDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)

  // Load the package list lazily, the first time the section is opened.
  useEffect(() => {
    if (!open || packages !== null) return
    let cancelled = false
    async function loadPackages() {
      setLoading(true)
      setError(null)
      try {
        const result = await getEvidencePackages()
        if (!cancelled) setPackages(result)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load evidence packages')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void loadPackages()
    return () => {
      cancelled = true
    }
  }, [open, packages])

  // Load the detail whenever a package is expanded.
  useEffect(() => {
    if (!expandedId) return
    const executionId = expandedId
    let cancelled = false
    async function loadDetail() {
      setDetail(null)
      setDetailError(null)
      setDetailLoading(true)
      try {
        const result = await getEvidencePackage(executionId)
        if (!cancelled) setDetail(result)
      } catch (err) {
        if (!cancelled) {
          setDetailError(err instanceof Error ? err.message : 'Failed to load evidence package')
        }
      } finally {
        if (!cancelled) setDetailLoading(false)
      }
    }
    void loadDetail()
    return () => {
      cancelled = true
    }
  }, [expandedId])

  return (
    <div className="audit-block evidence-box">
      <div className="audit-narrative-head">
        <p className="audit-block-label">Evidence Box — signed MCP evidence</p>
        <button type="button" className="audit-link" onClick={() => setOpen((prev) => !prev)}>
          {open ? 'hide' : 'show'} packages
        </button>
      </div>
      <p className="audit-muted">
        Gateway-signed evidence packages with an offline cryptographic verdict. Integrity is a
        separate field from the behavioral trust assessment above.
      </p>

      {open && (
        <>
          {loading && <p className="audit-muted">Loading evidence packages…</p>}
          {error && <p className="audit-error">{error}</p>}
          {!loading && !error && packages !== null && packages.length === 0 && (
            <p className="audit-muted">
              No evidence packages exported yet. Run the evidence gateway and export a package
              (see docs/evidence-box.md).
            </p>
          )}

          {packages !== null && packages.length > 0 && (
            <ul className="audit-claims-list">
              {packages.map((pkg) => (
                <PackageRow
                  key={pkg.execution_id}
                  pkg={pkg}
                  expanded={expandedId === pkg.execution_id}
                  onToggle={() =>
                    setExpandedId((prev) => (prev === pkg.execution_id ? null : pkg.execution_id))
                  }
                  detail={expandedId === pkg.execution_id ? detail : null}
                  detailLoading={expandedId === pkg.execution_id && detailLoading}
                  detailError={expandedId === pkg.execution_id ? detailError : null}
                  highlightCallId={highlightCallId}
                />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

function PackageRow({
  pkg,
  expanded,
  onToggle,
  detail,
  detailLoading,
  detailError,
  highlightCallId,
}: {
  pkg: EvidencePackageSummary
  expanded: boolean
  onToggle: () => void
  detail: EvidencePackageDetail | null
  detailLoading: boolean
  detailError: string | null
  highlightCallId: string | null
}) {
  return (
    <li className={`audit-claim ${expanded ? 'audit-claim--active' : ''}`}>
      <div className="audit-claim-head" onClick={onToggle}>
        <span
          className={`audit-verification-badge ${INTEGRITY_BADGE[pkg.integrity]}`}
          title="Offline cryptographic verification verdict"
        >
          {INTEGRITY_LABEL[pkg.integrity]}
        </span>
        <span className="audit-claim-headline">{pkg.execution_id}</span>
        <span className="audit-confidence" title="Coverage established by the verifier">
          {pkg.coverage}
        </span>
      </div>

      <div className="audit-claim-meta">
        <div className="audit-stats">
          <Stat label="Events" value={pkg.event_count} />
          <Stat label="Outcomes known" value={pkg.outcomes_known} />
          <Stat label="Outcomes unknown" value={pkg.outcomes_unknown} />
        </div>
        <div className="audit-tags">
          {pkg.run_ids.map((runId) => (
            <span key={runId} className="audit-tag" title="Correlating SDK run id">
              run {runId}
            </span>
          ))}
          {pkg.gateway_id && (
            <span className="audit-tag" title="Evidence gateway identity">
              gateway {pkg.gateway_id}
            </span>
          )}
          {pkg.key_id && (
            <span className="audit-tag" title="Signing key id">
              key {pkg.key_id}
            </span>
          )}
        </div>
        {pkg.error && <p className="audit-error">{pkg.error}</p>}
      </div>

      {expanded && (
        <div className="audit-question-body">
          {detailLoading && <p className="audit-muted">Loading signed events…</p>}
          {detailError && <p className="audit-error">{detailError}</p>}
          {detail && detail.verification && (
            <p className="audit-claim-rationale">
              <span className="audit-inline-label">Verifier:</span>{' '}
              {detail.verification.ok ? 'package verified' : 'verification not passed'} ·{' '}
              {detail.verification.integrity.verified_events} chain-intact event(s) ·{' '}
              {detail.verification.integrity.findings.length} finding(s)
              {detail.verification.coverage.detail ? ` · ${detail.verification.coverage.detail}` : ''}
            </p>
          )}
          {detail && detail.entries.length > 0 && (
            <ul className="audit-claims-list">
              {detail.entries.map((entry) => (
                <EntryRow key={entry.seq} entry={entry} highlight={entry.call_id === highlightCallId} />
              ))}
            </ul>
          )}
          {detail && detail.entries.length === 0 && !detailLoading && (
            <p className="audit-muted">No intact event records in this package.</p>
          )}
        </div>
      )}
    </li>
  )
}

const OUTCOME_BADGE: Record<string, string> = {
  success: 'audit-verification-badge--verified',
  error: 'audit-verification-badge--unsupported',
  unknown: 'audit-verification-badge--unverified',
}

function EntryRow({ entry, highlight }: { entry: EvidenceEntry; highlight: boolean }) {
  const typeLabel = EVENT_TYPE_LABEL[entry.event_type] ?? entry.event_type
  return (
    <li
      className={`audit-claim ${highlight ? 'audit-claim--active' : ''}`}
      data-integrity={entry.integrity}
    >
      <div className="audit-claim-head">
        <span
          className={`audit-verification-badge ${INTEGRITY_BADGE[entry.integrity]}`}
          title="Cryptographic verification of this event — separate from the behavioral audit"
        >
          {INTEGRITY_LABEL[entry.integrity]}
        </span>
        <span className="audit-claim-headline">
          #{entry.seq} {typeLabel}
        </span>
        {entry.decision && (
          <span
            className={`audit-verification-badge ${
              entry.decision === 'allow'
                ? 'audit-verification-badge--verified'
                : 'audit-verification-badge--contradicted'
            }`}
          >
            {entry.decision}
          </span>
        )}
        {entry.outcome_status && (
          <span
            className={`audit-verification-badge ${OUTCOME_BADGE[entry.outcome_status]}`}
            title="Gateway-observed outcome"
          >
            {entry.outcome_status}
            {entry.outcome_code ? ` (${entry.outcome_code})` : ''}
          </span>
        )}
      </div>

      {entry.reason && (
        <p className="audit-claim-rationale">
          <span className="audit-inline-label">Why:</span> {entry.reason}
        </p>
      )}

      <div className="audit-claim-meta">
        <span className="audit-inline-label">Evidence:</span>
        <span className="audit-verification-basis" title="Verified source and original record reference">
          {entry.verified_source} · {entry.original_ref}
        </span>
        <div className="audit-tags">
          {entry.run_id && <span className="audit-tag">run {entry.run_id}</span>}
          {entry.call_id && <span className="audit-tag">call {entry.call_id}</span>}
          {entry.tool_name && <span className="audit-tag">{entry.tool_name}</span>}
          {entry.principal && <span className="audit-tag">{entry.principal}</span>}
        </div>
      </div>
    </li>
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
