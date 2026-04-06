import type { Session, TraceBundle, ComparisonResponse } from '../types'
import { containsEscalationSignal } from '../utils/formatting'
import { getComparison } from '../api/client'
import { useState, useEffect } from 'react'

interface CoordinationSummary {
  turnCount: number
  policyCount: number
  speakerCount: number
  speakers: string[]
  policyTemplates: string[]
  stanceShiftCount: number
  escalationCount: number
  evidenceLinkedDecisionCount: number
}

interface SessionComparisonPanelProps {
  primaryBundle: TraceBundle | null
  secondaryBundle: TraceBundle | null
  sessions: Session[]
  selectedSessionId: string | null
  secondarySessionId: string | null
  compareLoading: boolean
  onSelectSecondarySession: (sessionId: string | null) => void
}

interface ComparisonDataState {
  comparison: ComparisonResponse | null
  loading: boolean
  error: string | null
}

function summarizeCoordination(bundle: TraceBundle): CoordinationSummary {
  const turns = bundle.events.filter((event) => event.event_type === 'agent_turn')
  const policies = bundle.events.filter((event) => event.event_type === 'prompt_policy')
  const decisions = bundle.events.filter((event) => event.event_type === 'decision')
  const speakers = Array.from(
    new Set(turns.map((event) => event.speaker ?? event.agent_id ?? '').filter(Boolean)),
  )
  const policyTemplates = Array.from(
    new Set(policies.map((event) => event.template_id ?? event.name).filter(Boolean)),
  )

  let stanceShiftCount = 0
  let previousTemplate: string | null = null
  for (const event of policies) {
    const currentTemplate = event.template_id ?? event.name
    if (previousTemplate && currentTemplate && previousTemplate !== currentTemplate) {
      stanceShiftCount += 1
    }
    previousTemplate = currentTemplate
  }

  const escalationCount = turns.filter((event) => containsEscalationSignal(`${event.goal ?? ''} ${event.content ?? ''}`)).length
  const evidenceLinkedDecisionCount = decisions.filter((event) => (event.evidence_event_ids?.length ?? 0) > 0).length

  return {
    turnCount: turns.length,
    policyCount: policies.length,
    speakerCount: speakers.length,
    speakers,
    policyTemplates,
    stanceShiftCount,
    escalationCount,
    evidenceLinkedDecisionCount,
  }
}

function MetricDelta({
  label,
  primary,
  secondary,
  delta,
}: {
  label: string
  primary: number
  secondary: number
  delta?: number | null
}) {
  const calculatedDelta = delta !== null && delta !== undefined ? delta : primary - secondary
  const prefix = calculatedDelta > 0 ? '+' : ''
  return (
    <div className="compare-metric">
      <span className="metric-label">{label}</span>
      <strong>{primary}</strong>
      <small>{prefix}{calculatedDelta.toFixed(0)} vs compare</small>
    </div>
  )
}

function TokenList({ title, values }: { title: string; values: string[] }) {
  return (
    <div>
      <h3>{title}</h3>
      <div className="speaker-strip">
        {values.length ? values.map((value) => <span key={value} className="speaker-pill">{value}</span>) : <span className="speaker-pill muted">None</span>}
      </div>
    </div>
  )
}

export function SessionComparisonPanel({
  primaryBundle,
  secondaryBundle,
  sessions,
  selectedSessionId,
  secondarySessionId,
  compareLoading,
  onSelectSecondarySession,
}: SessionComparisonPanelProps) {
  const [comparisonData, setComparisonData] = useState<ComparisonDataState>({
    comparison: null,
    loading: false,
    error: null,
  })

  // Fetch comparison data from backend when both sessions are selected
  useEffect(() => {
    if (selectedSessionId && secondarySessionId) {
      setComparisonData((prev) => ({ ...prev, loading: true, error: null }))

      getComparison(selectedSessionId, secondarySessionId)
        .then((data) => {
          setComparisonData({ comparison: data, loading: false, error: null })
        })
        .catch((err) => {
          console.error('Failed to fetch comparison data:', err)
          setComparisonData((prev) => ({
            ...prev,
            loading: false,
            error: err instanceof Error ? err.message : 'Failed to load comparison data'
          }))
        })
    } else {
      setComparisonData({ comparison: null, loading: false, error: null })
    }
  }, [selectedSessionId, secondarySessionId])

  if (!primaryBundle) {
    return (
      <div className="comparison-panel empty-panel">
        <p>Select a session to compare prompt policy and multi-agent behavior.</p>
      </div>
    )
  }

  const primarySummary = summarizeCoordination(primaryBundle)
  const secondarySummary = secondaryBundle ? summarizeCoordination(secondaryBundle) : null
  const secondarySessionOptions = sessions.filter((session) => session.id !== selectedSessionId)

  // Use backend comparison data if available, otherwise fall back to client-side calculation
  const useBackendData = comparisonData.comparison !== null && comparisonData.error === null
  const deltas = useBackendData && comparisonData.comparison ? comparisonData.comparison.comparison_deltas : null

  return (
    <div className="comparison-panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Cross-session comparison</p>
          <h2>Prompt policy deltas</h2>
        </div>
        <select
          className="compare-select"
          value={secondarySessionId ?? ''}
          onChange={(event) => onSelectSecondarySession(event.target.value || null)}
        >
          <option value="">Select comparison session</option>
          {secondarySessionOptions.map((session) => (
            <option key={session.id} value={session.id}>
              {session.agent_name} · {(session.replay_value ?? 0).toFixed(2)}
            </option>
          ))}
        </select>
      </div>

      {compareLoading || comparisonData.loading ? <p className="compare-loading">Loading comparison session…</p> : null}

      {comparisonData.error && (
        <p className="compare-error">Using client-side fallback: {comparisonData.error}</p>
      )}

      {secondaryBundle ? (
        <>
          <div className="compare-header">
            <div className="compare-session-card primary">
              <span className="metric-label">Primary</span>
              <strong>{primaryBundle.session.agent_name}</strong>
              <small>{primaryBundle.analysis.retention_tier} · replay {primaryBundle.analysis.session_replay_value.toFixed(2)}</small>
            </div>
            <div className="compare-session-card secondary">
              <span className="metric-label">Compare</span>
              <strong>{secondaryBundle.session.agent_name}</strong>
              <small>{secondaryBundle.analysis.retention_tier} · replay {secondaryBundle.analysis.session_replay_value.toFixed(2)}</small>
            </div>
          </div>

          <div className="compare-metric-grid">
            <MetricDelta
              label="Turns"
              primary={deltas?.turn_count.primary ?? primarySummary.turnCount}
              secondary={deltas?.turn_count.secondary ?? secondarySummary?.turnCount ?? 0}
              delta={deltas?.turn_count.delta}
            />
            <MetricDelta
              label="Policies"
              primary={deltas?.policy_count.primary ?? primarySummary.policyCount}
              secondary={deltas?.policy_count.secondary ?? secondarySummary?.policyCount ?? 0}
              delta={deltas?.policy_count.delta}
            />
            <MetricDelta
              label="Speakers"
              primary={deltas?.speaker_count.primary ?? primarySummary.speakerCount}
              secondary={deltas?.speaker_count.secondary ?? secondarySummary?.speakerCount ?? 0}
              delta={deltas?.speaker_count.delta}
            />
            <MetricDelta
              label="Stance shifts"
              primary={deltas?.stance_shift_count.primary ?? primarySummary.stanceShiftCount}
              secondary={deltas?.stance_shift_count.secondary ?? secondarySummary?.stanceShiftCount ?? 0}
              delta={deltas?.stance_shift_count.delta}
            />
            <MetricDelta
              label="Escalations"
              primary={deltas?.escalation_count.primary ?? primarySummary.escalationCount}
              secondary={deltas?.escalation_count.secondary ?? secondarySummary?.escalationCount ?? 0}
              delta={deltas?.escalation_count.delta}
            />
            <MetricDelta
              label="Grounded decisions"
              primary={deltas?.grounded_decision_count.primary ?? primarySummary.evidenceLinkedDecisionCount}
              secondary={deltas?.grounded_decision_count.secondary ?? secondarySummary?.evidenceLinkedDecisionCount ?? 0}
              delta={deltas?.grounded_decision_count.delta}
            />
          </div>

          <div className="compare-token-grid">
            <TokenList title={`${primaryBundle.session.agent_name} speakers`} values={primarySummary.speakers} />
            <TokenList title={`${secondaryBundle.session.agent_name} speakers`} values={secondarySummary?.speakers ?? []} />
            <TokenList title={`${primaryBundle.session.agent_name} policies`} values={primarySummary.policyTemplates} />
            <TokenList title={`${secondaryBundle.session.agent_name} policies`} values={secondarySummary?.policyTemplates ?? []} />
          </div>
        </>
      ) : (
        <div className="empty-panel">
          <p>Select a second session to compare prompt policy, speaker topology, and coordination heuristics.</p>
        </div>
      )}
    </div>
  )
}
