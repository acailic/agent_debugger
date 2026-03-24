import type { Checkpoint, LiveSummary, RollingSummary, Session, TraceEvent } from '../types'

interface LiveSummaryPanelProps {
  session: Session | null
  events: TraceEvent[]
  checkpoints: Checkpoint[]
  liveSummary: LiveSummary | null
  rollingSummaryData?: RollingSummary | null
  isConnected: boolean
  liveEventCount: number
  onSelectEvent: (eventId: string) => void
}

function latestOf(events: TraceEvent[], eventTypes: string[]): TraceEvent | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index]
    if (eventTypes.includes(event.event_type)) {
      return event
    }
  }
  return null
}

function summarizeEvent(event: TraceEvent | null): string {
  if (!event) return 'None yet'
  switch (event.event_type) {
    case 'decision':
      return event.chosen_action ?? event.name
    case 'tool_call':
    case 'tool_result':
      return event.tool_name ?? event.name
    case 'safety_check':
      return `${event.policy_name ?? 'Safety'} · ${event.outcome ?? 'pass'}`
    case 'refusal':
      return event.reason ?? event.name
    case 'policy_violation':
      return event.violation_type ?? event.name
    case 'prompt_policy':
      return event.template_id ?? event.name
    case 'agent_turn':
      return `${event.speaker ?? event.agent_id ?? 'Agent'} · ${event.goal ?? event.name}`
    default:
      return event.name
  }
}

function formatMetricLabel(key: string): string {
  return key.replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function LiveSummaryPanel({
  session,
  events,
  checkpoints,
  liveSummary,
  rollingSummaryData,
  isConnected,
  liveEventCount,
  onSelectEvent,
}: LiveSummaryPanelProps) {
  const latestDecision = latestOf(events, ['decision'])
  const latestTool = latestOf(events, ['tool_call', 'tool_result'])
  const latestSafety = latestOf(events, ['safety_check', 'refusal', 'policy_violation'])
  const latestTurn = latestOf(events, ['agent_turn'])
  const latestPolicy = latestOf(events, ['prompt_policy'])
  const latestCheckpoint = checkpoints.at(-1) ?? null
  const previousCheckpoint = checkpoints.length > 1 ? checkpoints.at(-2) : null
  const alertTimeline = liveSummary?.recent_alerts ?? []

  const rollingSummary = rollingSummaryData?.text
    ?? liveSummary?.rolling_summary
    ?? latestTurn?.state_summary
    ?? latestPolicy?.state_summary
    ?? latestDecision?.reasoning
    ?? 'Awaiting richer live summaries'

  const metrics = rollingSummaryData?.metrics ?? {}
  const metricEntries = Object.entries(metrics)

  function computeCheckpointDelta(): { stateDelta: number; memoryDelta: number } | null {
    if (!latestCheckpoint || !previousCheckpoint) return null
    const stateDelta = Object.keys(latestCheckpoint.state).length - Object.keys(previousCheckpoint.state).length
    const memoryDelta = Object.keys(latestCheckpoint.memory).length - Object.keys(previousCheckpoint.memory).length
    return { stateDelta, memoryDelta }
  }

  const checkpointDelta = computeCheckpointDelta()

  return (
    <div className="live-summary-panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Live Monitoring</p>
          <h2>Session pulse</h2>
        </div>
        <div className={`live-badge ${isConnected ? 'connected' : 'offline'}`}>
          <span className="live-dot" />
          <strong>{isConnected ? 'Connected' : 'Offline'}</strong>
        </div>
      </div>

      <div className="analysis-strip">
        <span>Status {session?.status ?? 'unknown'}</span>
        <span>Live events {liveEventCount}</span>
        <span>Checkpoints {liveSummary?.checkpoint_count ?? checkpoints.length}</span>
        <span>Recent alerts {alertTimeline.length}</span>
      </div>

      <div className="live-grid">
        {[latestDecision, latestTool, latestSafety, latestTurn, latestPolicy].map((event, index) => {
          const label = ['Latest decision', 'Latest tool', 'Latest safety', 'Latest turn', 'Latest policy'][index]
          return (
            <button
              key={label}
              type="button"
              className="live-card"
              disabled={!event}
              onClick={() => {
                if (event) onSelectEvent(event.id)
              }}
            >
              <span className="metric-label">{label}</span>
              <strong>{summarizeEvent(event)}</strong>
            </button>
          )
        })}
        <div className="live-card static">
          <span className="metric-label">Latest checkpoint</span>
          <strong>{latestCheckpoint ? `Sequence ${latestCheckpoint.sequence}` : 'None yet'}</strong>
          {checkpointDelta && (
            <div className="checkpoint-delta">
              <span className={checkpointDelta.stateDelta >= 0 ? 'delta-positive' : 'delta-negative'}>
                State: {checkpointDelta.stateDelta >= 0 ? '+' : ''}{checkpointDelta.stateDelta}
              </span>
              <span className={checkpointDelta.memoryDelta >= 0 ? 'delta-positive' : 'delta-negative'}>
                Memory: {checkpointDelta.memoryDelta >= 0 ? '+' : ''}{checkpointDelta.memoryDelta}
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="live-rolling">
        <h3>Rolling summary</h3>
        <p>{rollingSummary}</p>
        {rollingSummaryData && (
          <small className="rolling-window-info">
            Window: {rollingSummaryData.window_size} {rollingSummaryData.window_type}
          </small>
        )}
      </div>

      {metricEntries.length > 0 && (
        <div className="rolling-metrics">
          <h3>Session metrics</h3>
          <div className="metric-badges">
            {metricEntries.map(([key, value]) => (
              <span key={key} className="metric-badge">
                <span className="badge-label">{formatMetricLabel(key)}</span>
                <strong className="badge-value">{typeof value === 'number' ? value.toFixed(2) : String(value)}</strong>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="live-alerts">
        <h3>Live alert timeline</h3>
        <div className="live-alert-list">
          {alertTimeline.length ? (
            alertTimeline.map((alert) => (
              <button
                key={`${alert.source}-${alert.alert_type}-${alert.event_id}`}
                type="button"
                className={`live-alert-row ${alert.severity}`}
                onClick={() => onSelectEvent(alert.event_id)}
              >
                <span className="live-alert-head">
                  <strong>{alert.alert_type.replaceAll('_', ' ')}</strong>
                  <small>{alert.source}</small>
                </span>
                <span>{alert.signal}</span>
              </button>
            ))
          ) : (
            <p className="live-alert-empty">No recent instability signals.</p>
          )}
        </div>
      </div>
    </div>
  )
}
