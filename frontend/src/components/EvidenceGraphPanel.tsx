import type {
  AuditVerificationStatus,
  EvidenceGraph,
  EvidenceGraphNode,
} from '../types'
import './AuditPanel.css'
import './EvidenceGraphPanel.css'

interface EvidenceGraphPanelProps {
  graph: EvidenceGraph | null
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

const SOURCE_LABELS: Record<string, string> = {
  tool_backed: 'Tool-backed',
  user_provided: 'User-provided',
  other: 'Other',
}

/**
 * Evidence-provenance surface: shows how every claim connects to the facts
 * available to the agent. This is the structural answer to "what data was
 * used?" — including facts that existed but were never cited (a missing-
 * evidence smell the /audit signals flag abstractly, made inspectable here).
 */
export function EvidenceGraphPanel({
  graph,
  loading,
  error,
  selectedEventId,
  onSelectEvent,
}: EvidenceGraphPanelProps) {
  if (loading) {
    return (
      <section className="panel evidence-graph-panel">
        <p className="eyebrow">Evidence provenance</p>
        <h2>Building evidence graph…</h2>
        <p className="audit-muted">Resolving claims, facts, and evidence edges.</p>
      </section>
    )
  }

  if (error) {
    return (
      <section className="panel evidence-graph-panel">
        <p className="eyebrow">Evidence provenance</p>
        <h2>Evidence graph unavailable</h2>
        <p className="audit-error">{error}</p>
      </section>
    )
  }

  if (!graph || graph.nodes.length === 0) return null

  const nodesById = new Map<string, EvidenceGraphNode>()
  for (const node of graph.nodes) nodesById.set(node.event_id, node)

  // Evidence edge: source = claim, target = fact.
  const evidenceTargets = new Set<string>()
  const citedByClaim = new Map<string, { factId: string; sourceClass: string | null }[]>()
  for (const edge of graph.edges) {
    if (edge.edge_type !== 'evidence') continue
    evidenceTargets.add(edge.target_id)
    const bucket = citedByClaim.get(edge.source_id) ?? []
    bucket.push({ factId: edge.target_id, sourceClass: edge.source_class })
    citedByClaim.set(edge.source_id, bucket)
  }

  const claims = graph.nodes.filter((n) => n.role === 'claim')
  const facts = graph.nodes.filter((n) => n.role === 'tool_fact' || n.role === 'user_fact')
  const otherNodes = graph.nodes.filter((n) => n.role === 'other')
  const uncitedFacts = facts.filter((n) => !evidenceTargets.has(n.event_id))

  const verificationEntries = Object.entries(graph.stats.verification_counts)
  const orderedStatuses: AuditVerificationStatus[] = [
    'verified',
    'partially_verified',
    'contradicted',
    'unsupported',
    'unverified',
    'stale',
  ]

  return (
    <section className="panel evidence-graph-panel">
      <div className="panel-head">
        <p className="eyebrow" title="Provenance graph of claims and the facts they cite">
          Evidence provenance — what data was used
        </p>
        <h2>{claims.length} claims · {facts.length} facts</h2>
      </div>

      <div className="evidence-graph-stats">
        <EvidenceStat label="Claims" value={graph.stats.claim_count} />
        <EvidenceStat label="Facts" value={graph.stats.fact_count} />
        <EvidenceStat label="Evidence edges" value={graph.stats.evidence_edges} />
        <EvidenceStat label="Causal edges" value={graph.stats.causal_edges} />
        <EvidenceStat
          label="Unresolved refs"
          value={graph.stats.unresolved_evidence_refs}
          tone={graph.stats.unresolved_evidence_refs > 0 ? 'bad' : undefined}
        />
        <EvidenceStat
          label="Evidence coverage"
          value={`${Math.round(graph.stats.evidence_coverage * 100)}%`}
        />
      </div>

      {verificationEntries.length > 0 && (
        <div className="audit-tags evidence-graph-verification">
          {orderedStatuses
            .filter((status) => graph.stats.verification_counts[status] > 0)
            .map((status) => (
              <span
                key={status}
                className={`audit-verification-badge audit-verification-badge--${status}`}
              >
                {VERIFICATION_LABELS[status]}: {graph.stats.verification_counts[status]}
              </span>
            ))}
        </div>
      )}

      {uncitedFacts.length > 0 && (
        <div className="evidence-graph-ignored" data-failed="true">
          <p className="evidence-graph-ignored-title">
            {uncitedFacts.length} available fact{uncitedFacts.length === 1 ? '' : 's'} never cited
          </p>
          <p className="audit-muted">
            Evidence the agent had but did not reference in any decision — a missing-evidence smell.
          </p>
          <div className="audit-tags">
            {uncitedFacts.map((node) => (
              <button
                key={node.event_id}
                className="audit-tag audit-tag--link unresolved"
                type="button"
                onClick={() => onSelectEvent(node.event_id)}
                title={node.label}
              >
                {SOURCE_LABELS[node.role] ?? node.role}: {node.event_id.slice(0, 8)}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="evidence-graph-section">
        <p className="evidence-graph-section-title">Claims and their evidence</p>
        {claims.length === 0 ? (
          <p className="audit-muted">No decision claims in this session.</p>
        ) : (
          <ul className="evidence-graph-claims">
            {claims.map((claim) => {
              const status = (claim.verification_status ?? 'unverified') as AuditVerificationStatus
              const cited = citedByClaim.get(claim.event_id) ?? []
              const isSelected = claim.event_id === selectedEventId
              return (
                <li
                  key={claim.event_id}
                  className={`evidence-graph-claim${isSelected ? ' selected' : ''}`}
                  data-verification={status}
                >
                  <div className="evidence-graph-claim-head">
                    <span className={`audit-verification-badge audit-verification-badge--${status}`}>
                      {VERIFICATION_LABELS[status] ?? status}
                    </span>
                    {claim.confidence != null && (
                      <span className="audit-confidence" title="Stated confidence">
                        {Math.round(claim.confidence * 100)}%
                      </span>
                    )}
                    {claim.is_failure && (
                      <span className="audit-verification-badge audit-verification-badge--contradicted">
                        failure
                      </span>
                    )}
                    <button
                      className="audit-link"
                      type="button"
                      onClick={() => onSelectEvent(claim.event_id)}
                      title={claim.label}
                    >
                      {claim.label}
                    </button>
                  </div>
                  {cited.length === 0 ? (
                    <p className="audit-muted">No evidence cited for this claim.</p>
                  ) : (
                    <div className="audit-tags">
                      {cited.map((ref, idx) => (
                        <button
                          key={`${ref.factId}-${idx}`}
                          className="audit-tag audit-tag--link"
                          type="button"
                          onClick={() => onSelectEvent(ref.factId)}
                          title={nodesById.get(ref.factId)?.label ?? ref.factId}
                        >
                          {SOURCE_LABELS[ref.sourceClass ?? 'other'] ?? ref.sourceClass}: {ref.factId.slice(0, 8)}
                        </button>
                      ))}
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {facts.length > 0 && (
        <div className="evidence-graph-section">
          <p className="evidence-graph-section-title">Available facts</p>
          <div className="audit-tags">
            {facts.map((node) => {
              const cited = evidenceTargets.has(node.event_id)
              return (
                <button
                  key={node.event_id}
                  className={`audit-tag audit-tag--link${cited ? '' : ' unresolved'}`}
                  type="button"
                  onClick={() => onSelectEvent(node.event_id)}
                  title={node.label}
                >
                  {SOURCE_LABELS[node.role] ?? node.role}: {node.event_id.slice(0, 8)}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {otherNodes.length > 0 && (
        <div className="evidence-graph-section">
          <p className="evidence-graph-section-title">Other referenced events</p>
          <div className="audit-tags">
            {otherNodes.map((node) => (
              <button
                key={node.event_id}
                className="audit-tag audit-tag--link"
                type="button"
                onClick={() => onSelectEvent(node.event_id)}
                title={node.label}
              >
                {node.event_type}: {node.event_id.slice(0, 8)}
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

function EvidenceStat({
  label,
  value,
  tone,
}: {
  label: string
  value: number | string
  tone?: 'bad' | 'warn'
}) {
  return (
    <div className={`evidence-graph-stat${tone ? ` evidence-graph-stat--${tone}` : ''}`}>
      <strong>{value}</strong>
      <small>{label}</small>
    </div>
  )
}
