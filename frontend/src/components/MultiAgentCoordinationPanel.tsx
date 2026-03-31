import type { TraceBundle } from '../types'

interface CoordinationSummary {
  turnCount: number
  policyCount: number
  speakerCount: number
  speakers: string[]
  speakerTurns: Array<{ speaker: string; turnCount: number }>
  policyTemplates: string[]
  stanceShiftCount: number
  escalationCount: number
  evidenceLinkedDecisionCount: number
  totalDecisionCount: number
  turns: Array<{
    speaker: string
    turnIndex: number
    isEscalation: boolean
    hasPolicyShift: boolean
  }>
}

interface MultiAgentCoordinationPanelProps {
  bundle: TraceBundle | null
}

function containsEscalationSignal(value: string): boolean {
  const normalized = value.toLowerCase()
  return ['escalate', 'handoff', 'review', 'supervisor', 'critic'].some((token) =>
    normalized.includes(token)
  )
}

function summarizeCoordination(bundle: TraceBundle): CoordinationSummary | null {
  if (!bundle.events.length) return null

  const turns = bundle.events.filter((event) => event.event_type === 'agent_turn')
  const policies = bundle.events.filter((event) => event.event_type === 'prompt_policy')
  const decisions = bundle.events.filter((event) => event.event_type === 'decision')

  const speakers = Array.from(
    new Set(turns.map((event) => event.speaker ?? event.agent_id ?? '').filter(Boolean))
  )

  // Count turns per speaker
  const speakerTurnMap = new Map<string, number>()
  for (const turn of turns) {
    const speaker = turn.speaker ?? turn.agent_id ?? 'Unknown'
    speakerTurnMap.set(speaker, (speakerTurnMap.get(speaker) ?? 0) + 1)
  }

  const speakerTurns = Array.from(speakerTurnMap.entries())
    .map(([speaker, turnCount]) => ({ speaker, turnCount }))
    .sort((a, b) => b.turnCount - a.turnCount)

  const policyTemplates = Array.from(
    new Set(policies.map((event) => event.template_id ?? event.name).filter(Boolean))
  )

  // Track stance shifts (policy template changes)
  let stanceShiftCount = 0
  let previousTemplate: string | null = null
  const policyShiftTurns = new Set<number>()

  for (const event of policies) {
    const currentTemplate = event.template_id ?? event.name
    if (previousTemplate && currentTemplate && previousTemplate !== currentTemplate) {
      stanceShiftCount += 1
      // Mark the turn as having a policy shift
      const turnIndex = event.turn_index
      if (turnIndex !== undefined) {
        policyShiftTurns.add(turnIndex)
      }
    }
    previousTemplate = currentTemplate
  }

  // Identify escalations
  const escalationTurns = new Set<number>()
  for (const event of turns) {
    if (containsEscalationSignal(`${event.goal ?? ''} ${event.content ?? ''}`)) {
      const turnIndex = event.turn_index
      if (turnIndex !== undefined) {
        escalationTurns.add(turnIndex)
      }
    }
  }

  const escalationCount = escalationTurns.size
  const evidenceLinkedDecisionCount = decisions.filter(
    (event) => (event.evidence_event_ids?.length ?? 0) > 0
  ).length

  // Build turn timeline
  const turnTimeline = turns.map((turn) => ({
    speaker: turn.speaker ?? turn.agent_id ?? 'Unknown',
    turnIndex: turn.turn_index ?? 0,
    isEscalation: escalationTurns.has(turn.turn_index ?? 0),
    hasPolicyShift: policyShiftTurns.has(turn.turn_index ?? 0),
  }))

  return {
    turnCount: turns.length,
    policyCount: policies.length,
    speakerCount: speakers.length,
    speakers,
    speakerTurns,
    policyTemplates,
    stanceShiftCount,
    escalationCount,
    evidenceLinkedDecisionCount,
    totalDecisionCount: decisions.length,
    turns: turnTimeline,
  }
}

function TurnTimelineStrip({ turns }: { turns: CoordinationSummary['turns'] }) {
  if (!turns.length) return null

  const maxTurns = Math.min(turns.length, 50) // Limit for visual clarity
  const displayTurns = turns.slice(0, maxTurns)

  // Generate a color for each speaker
  const speakerColors = new Map<string, string>()
  const colors = [
    'var(--node-session)',
    'var(--node-llm)',
    'var(--node-tool)',
    'var(--node-decision)',
    'var(--node-checkpoint)',
    'var(--accent)',
  ]
  let colorIndex = 0

  for (const turn of turns) {
    if (!speakerColors.has(turn.speaker)) {
      speakerColors.set(turn.speaker, colors[colorIndex % colors.length])
      colorIndex++
    }
  }

  return (
    <div className="turn-timeline">
      <span className="metric-label">Turn sequence</span>
      <div className="turn-strip">
        {displayTurns.map((turn, idx) => {
          const backgroundColor = speakerColors.get(turn.speaker) ?? 'var(--node-default)'
          const hasIndicator = turn.isEscalation || turn.hasPolicyShift

          return (
            <div
              key={idx}
              className={`turn-cell ${turn.isEscalation ? 'escalation' : ''} ${turn.hasPolicyShift ? 'policy-shift' : ''}`}
              style={{ backgroundColor }}
              title={`${turn.speaker} - turn ${turn.turnIndex}${turn.isEscalation ? ' (escalation)' : ''}${turn.hasPolicyShift ? ' (policy shift)' : ''}`}
            >
              {hasIndicator && (
                <span className="turn-indicator">
                  {turn.isEscalation ? '⚠' : turn.hasPolicyShift ? '⚡' : ''}
                </span>
              )}
            </div>
          )
        })}
        {turns.length > maxTurns && (
          <div className="turn-cell turn-ellipsis">+{turns.length - maxTurns}</div>
        )}
      </div>
      <div className="turn-legend">
        {Array.from(speakerColors.entries()).map(([speaker, color]) => (
          <div key={speaker} className="legend-item">
            <div className="legend-dot" style={{ backgroundColor: color }} />
            <small>{speaker}</small>
          </div>
        ))}
        {turns.some((t) => t.isEscalation) && (
          <div className="legend-item">
            <span className="legend-indicator">⚠</span>
            <small>Escalation</small>
          </div>
        )}
        {turns.some((t) => t.hasPolicyShift) && (
          <div className="legend-item">
            <span className="legend-indicator">⚡</span>
            <small>Policy shift</small>
          </div>
        )}
      </div>
    </div>
  )
}

function SpeakerTopology({ speakerTurns }: { speakerTurns: CoordinationSummary['speakerTurns'] }) {
  if (!speakerTurns.length) return null

  const maxTurns = Math.max(...speakerTurns.map((s) => s.turnCount))

  return (
    <div className="speaker-topology">
      <span className="metric-label">Speaker topology</span>
      <div className="speaker-bars">
        {speakerTurns.map(({ speaker, turnCount }) => (
          <div key={speaker} className="speaker-bar-row">
            <small className="speaker-name">{speaker}</small>
            <div className="speaker-bar-container">
              <div
                className="speaker-bar"
                style={{
                  width: `${(turnCount / maxTurns) * 100}%`,
                }}
              />
              <span className="speaker-turn-count">{turnCount}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function CoordinationMetrics({ summary }: { summary: CoordinationSummary }) {
  const evidencePercentage = summary.totalDecisionCount > 0
    ? (summary.evidenceLinkedDecisionCount / summary.totalDecisionCount) * 100
    : 0

  return (
    <div className="coordination-metrics">
      <div className="coordination-metric">
        <span className="metric-label">Total turns</span>
        <strong>{summary.turnCount}</strong>
      </div>
      <div className="coordination-metric">
        <span className="metric-label">Speakers</span>
        <strong>{summary.speakerCount}</strong>
      </div>
      <div className="coordination-metric">
        <span className="metric-label">Policies</span>
        <strong>{summary.policyCount}</strong>
      </div>
      <div className="coordination-metric">
        <span className="metric-label">Stance shifts</span>
        <strong>{summary.stanceShiftCount}</strong>
      </div>
      <div className="coordination-metric">
        <span className="metric-label">Escalations</span>
        <strong style={{ color: summary.escalationCount > 0 ? 'var(--danger)' : undefined }}>
          {summary.escalationCount}
        </strong>
      </div>
      <div className="coordination-metric">
        <span className="metric-label">Evidence grounding</span>
        <strong style={{
          color: evidencePercentage >= 50 ? 'var(--olive)' : evidencePercentage >= 25 ? 'var(--warning)' : 'var(--danger)'
        }}>
          {evidencePercentage.toFixed(0)}%
        </strong>
        <small>({summary.evidenceLinkedDecisionCount}/{summary.totalDecisionCount})</small>
      </div>
    </div>
  )
}

export function MultiAgentCoordinationPanel({ bundle }: MultiAgentCoordinationPanelProps) {
  const summary = bundle ? summarizeCoordination(bundle) : null

  if (!bundle) {
    return (
      <section className="panel coordination-panel">
        <div className="panel-head">
          <p className="eyebrow">Multi-Agent Coordination</p>
          <h2>Speaker patterns</h2>
        </div>
        <p className="empty-message">No session data available.</p>
      </section>
    )
  }

  if (!summary) {
    return (
      <section className="panel coordination-panel">
        <div className="panel-head">
          <p className="eyebrow">Multi-Agent Coordination</p>
          <h2>Speaker patterns</h2>
        </div>
        <p className="empty-message">No coordination data available for this session.</p>
      </section>
    )
  }

  return (
    <section className="panel coordination-panel">
      <div className="panel-head">
        <p className="eyebrow">Multi-Agent Coordination</p>
        <h2>Speaker patterns</h2>
      </div>

      <CoordinationMetrics summary={summary} />

      {summary.speakerTurns.length > 0 && <SpeakerTopology speakerTurns={summary.speakerTurns} />}

      {summary.turns.length > 0 && <TurnTimelineStrip turns={summary.turns} />}

      {summary.policyTemplates.length > 0 && (
        <div className="coordination-policies">
          <span className="metric-label">Policy templates</span>
          <div className="policy-pills">
            {summary.policyTemplates.map((template) => (
              <span key={template} className="policy-pill">
                {template}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
