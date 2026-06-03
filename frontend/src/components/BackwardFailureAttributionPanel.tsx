import type { TraceEvent, FailureExplanation } from '../types'
import { memo, useState } from 'react'

interface BackwardFailureAttributionPanelProps {
  events: TraceEvent[]
  failureExplanations: FailureExplanation[]
  selectedEventId: string | null
  onEventSelect: (eventId: string) => void
}

interface CausalChain {
  failure_event_id: string
  failure_headline: string
  failure_mode: string
  causal_candidates: CausalCandidate[]
  confidence: number
}

interface CausalCandidate {
  event_id: string
  event_type: string
  headline: string
  score: number
  causal_depth: number
  relation: string
  relation_label: string
  is_explicit: boolean
  reasoning: string
  supporting_event_ids: string[]
}

interface BackwardTrace {
  event_id: string
  event_type: string
  timestamp: string
  name: string
  is_failure: boolean
  failure_type: string | null
  distance_from_failure: number
  causal_strength: number
}

/**
 * Build causal chains from failure explanations
 * This implements the Backward Failure Attribution logic from ErrorProbe
 */
function buildCausalChains(
  explanations: FailureExplanation[],
  events: TraceEvent[]
): CausalChain[] {
  const eventMap = new Map(events.map(e => [e.id, e]))

  return explanations.map(explanation => {
    const failureEvent = eventMap.get(explanation.failure_event_id)
    const failureHeadline = failureEvent?.error || failureEvent?.name || explanation.failure_headline

    return {
      failure_event_id: explanation.failure_event_id,
      failure_headline: failureHeadline,
      failure_mode: explanation.failure_mode,
      causal_candidates: explanation.candidates.map(candidate => ({
        event_id: candidate.event_id,
        event_type: candidate.event_type,
        headline: candidate.headline,
        score: candidate.score,
        causal_depth: candidate.causal_depth,
        relation: candidate.relation,
        relation_label: candidate.relation_label,
        is_explicit: candidate.explicit,
        reasoning: candidate.rationale,
        supporting_event_ids: candidate.supporting_event_ids,
      })),
      confidence: explanation.confidence,
    }
  })
}

/**
 * Build backward trace from failure to potential causes
 */
function buildBackwardTrace(
  failureEventId: string,
  events: TraceEvent[]
): BackwardTrace[] {
  const eventMap = new Map(events.map(e => [e.id, e]))
  const failureEvent = eventMap.get(failureEventId)
  if (!failureEvent) return []

  const trace: BackwardTrace[] = []
  const visited = new Set<string>()

  function traceBackward(eventId: string, depth: number = 0): void {
    if (visited.has(eventId) || depth > 10) return

    const event = eventMap.get(eventId)
    if (!event) return

    visited.add(eventId)

    // Add to trace
    trace.push({
      event_id: event.id,
      event_type: event.event_type,
      timestamp: event.timestamp,
      name: event.name,
      is_failure: event.event_type === 'error' || event.event_type === 'refusal',
      failure_type: event.error_type || null,
      distance_from_failure: depth,
      causal_strength: 1.0 - (depth * 0.1), // Simple decay model
    })

    // Trace parent dependencies
    if (event.parent_id) {
      traceBackward(event.parent_id, depth + 1)
    }

    // Trace upstream dependencies
    if (event.upstream_event_ids) {
      for (const upstreamId of event.upstream_event_ids) {
        traceBackward(upstreamId, depth + 1)
      }
    }
  }

  // Start tracing from failure event
  traceBackward(failureEventId)

  return trace.sort((a, b) => a.distance_from_failure - b.distance_from_failure)
}

function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.8) return 'var(--olive)'
  if (confidence >= 0.5) return 'var(--warning)'
  return 'var(--danger)'
}

function getRelationLabelColor(relationLabel: string): string {
  if (relationLabel.toLowerCase().includes('direct')) return 'var(--olive)'
  if (relationLabel.toLowerCase().includes('indirect')) return 'var(--warning)'
  return 'var(--muted)'
}

function CausalChainCard({
  chain,
  selectedEventId,
  onEventSelect,
  events
}: {
  chain: CausalChain
  selectedEventId: string | null
  onEventSelect: (eventId: string) => void
  events: TraceEvent[]
}) {
  const [showDetails, setShowDetails] = useState(false)
  const backwardTrace = buildBackwardTrace(chain.failure_event_id, events)
  const confidenceColor = getConfidenceColor(chain.confidence)

  return (
    <div className="causal-chain-card">
      <div className="chain-header">
        <h4>Failure: {chain.failure_headline}</h4>
        <div className="chain-meta">
          <span className="failure-mode">{chain.failure_mode}</span>
          <span
            className="confidence-score"
            style={{ color: confidenceColor }}
          >
            {Math.round(chain.confidence * 100)}% confidence
          </span>
        </div>
      </div>

      <button
        type="button"
        className={`show-details-btn ${showDetails ? 'active' : ''}`}
        onClick={() => setShowDetails(!showDetails)}
        aria-label="Show causal chain details"
      >
        {showDetails ? '▼' : '▶'} Show {chain.causal_candidates.length} causal candidates
      </button>

      {showDetails && (
        <div className="causal-candidates">
          {chain.causal_candidates.map(candidate => (
            <div
              key={candidate.event_id}
              className={`causal-candidate ${selectedEventId === candidate.event_id ? 'selected' : ''}`}
            >
              <div className="candidate-header">
                <button
                  type="button"
                  className="candidate-select-btn"
                  onClick={() => onEventSelect(candidate.event_id)}
                  aria-label={`Select causal candidate: ${candidate.headline}`}
                >
                  {candidate.relation_label === 'Direct' ? '⚡' : '→'}
                </button>
                <div className="candidate-info">
                  <span className="candidate-headline">{candidate.headline}</span>
                  <span className="candidate-event-type">{candidate.event_type}</span>
                </div>
                <div className="candidate-metrics">
                  <span
                    className="candidate-score"
                    style={{ color: getConfidenceColor(candidate.score) }}
                  >
                    {candidate.score.toFixed(2)}
                  </span>
                  <span className="candidate-depth">Depth: {candidate.causal_depth}</span>
                  <span
                    className="candidate-relation"
                    style={{ color: getRelationLabelColor(candidate.relation_label) }}
                  >
                    {candidate.relation_label}
                  </span>
                  {candidate.is_explicit && (
                    <span className="explicit-badge">Explicit</span>
                  )}
                </div>
              </div>

              {candidate.reasoning && (
                <p className="candidate-reasoning">
                  <small>Reasoning: {candidate.reasoning}</small>
                </p>
              )}

              {candidate.supporting_event_ids.length > 0 && (
                <div className="supporting-events">
                  <small>Supporting evidence: {candidate.supporting_event_ids.length} events</small>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {showDetails && backwardTrace.length > 0 && (
        <div className="backward-trace">
          <h5>Backward Execution Trace</h5>
          <div className="trace-timeline">
            {backwardTrace.map((traceEvent) => (
              <div
                key={traceEvent.event_id}
                className={`trace-event ${traceEvent.is_failure ? 'failure' : ''} ${selectedEventId === traceEvent.event_id ? 'selected' : ''}`}
              >
                <button
                  type="button"
                  className="trace-event-btn"
                  onClick={() => onEventSelect(traceEvent.event_id)}
                  aria-label={`Select trace event: ${traceEvent.name}`}
                >
                  <span className="trace-distance">← {traceEvent.distance_from_failure}</span>
                  <span className="trace-type">{traceEvent.event_type}</span>
                  <span className="trace-name">{traceEvent.name}</span>
                  <span className="trace-strength">
                    {Math.round(traceEvent.causal_strength * 100)}%
                  </span>
                  {traceEvent.is_failure && (
                    <span className="failure-badge">FAIL</span>
                  )}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export function BackwardFailureAttributionPanel({
  events,
  failureExplanations,
  selectedEventId,
  onEventSelect,
}: BackwardFailureAttributionPanelProps) {
  const causalChains = buildCausalChains(failureExplanations, events)

  if (causalChains.length === 0) {
    return (
      <section className="panel backward-failure-panel">
        <div className="panel-head">
          <p className="eyebrow">Error Analysis</p>
          <h2>Backward Failure Attribution</h2>
        </div>
        <div className="empty-state">
          <div className="empty-state-icon">🔍</div>
          <h3>No failure attributions available</h3>
          <p>Backward failure attribution identifies root causes by tracing backwards from failures through their causal dependencies.</p>
          <small>Failure attributions will appear here when errors occur in traced sessions</small>
        </div>
      </section>
    )
  }

  // Sort by confidence (highest first)
  const sortedChains = [...causalChains].sort((a, b) => b.confidence - a.confidence)

  return (
    <section className="panel backward-failure-panel">
      <div className="panel-head">
        <p className="eyebrow">Error Analysis</p>
        <h2>Backward Failure Attribution ({sortedChains.length})</h2>
      </div>

      <div className="causal-chains-container">
        {sortedChains.map(chain => (
          <CausalChainCard
            key={chain.failure_event_id}
            chain={chain}
            selectedEventId={selectedEventId}
            onEventSelect={onEventSelect}
            events={events}
          />
        ))}
      </div>

      <div className="attribution-summary">
        <h3>Summary</h3>
        <div className="summary-stats">
          <div className="stat-item">
            <span className="stat-label">Total Failures</span>
            <strong>{sortedChains.length}</strong>
          </div>
          <div className="stat-item">
            <span className="stat-label">High Confidence</span>
            <strong>{sortedChains.filter(c => c.confidence >= 0.8).length}</strong>
          </div>
          <div className="stat-item">
            <span className="stat-label">Direct Causes Found</span>
            <strong>
              {sortedChains.reduce((sum, c) =>
                sum + c.causal_candidates.filter(cand => cand.relation_label === 'Direct').length, 0
              )}
            </strong>
          </div>
        </div>
      </div>
    </section>
  )
}

// Custom comparison for BackwardFailureAttributionPanel
function arePropsEqual(
  prevProps: Readonly<BackwardFailureAttributionPanelProps>,
  nextProps: Readonly<BackwardFailureAttributionPanelProps>
): boolean {
  return (
    prevProps.events === nextProps.events &&
    prevProps.failureExplanations === nextProps.failureExplanations &&
    prevProps.selectedEventId === nextProps.selectedEventId
  )
}

export const BackwardFailureAttributionPanelMemo = memo(BackwardFailureAttributionPanel, arePropsEqual)