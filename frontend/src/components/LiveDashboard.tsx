import type { Checkpoint, LiveSummary, RollingSummary, Session, TraceEvent } from '../types'
import { computeCheckpointDelta, formatEventHeadline, formatMetricLabel, latestOf } from '../utils/formatting'

interface LiveDashboardProps {
  session: Session | null
  events: TraceEvent[]
  checkpoints: Checkpoint[]
  liveSummary: LiveSummary | null
  rollingSummaryData?: RollingSummary | null
  isConnected: boolean
  liveEventCount: number
  onSelectEvent: (eventId: string) => void
}

interface StabilityIndicatorProps {
  alertCount: number
  hasOscillation: boolean
}

function StabilityIndicator({ alertCount, hasOscillation }: StabilityIndicatorProps) {
  let status: 'stable' | 'oscillating' | 'problematic' = 'stable'
  let label = 'Stable'
  let colorVar = '--olive'

  if (hasOscillation || alertCount >= 4) {
    status = 'problematic'
    label = 'Problematic'
    colorVar = '--danger'
  } else if (alertCount >= 2) {
    status = 'oscillating'
    label = 'Oscillating'
    colorVar = '--warning'
  }

  return (
    <div className={`stability-indicator stability-${status}`}>
      <span className="stability-dot" style={{ backgroundColor: `var(${colorVar})` }} />
      <strong>{label}</strong>
      <small className="stability-count">{alertCount} alert{alertCount !== 1 ? 's' : ''}</small>
    </div>
  )
}

export function LiveDashboard({
  session,
  events,
  checkpoints,
  liveSummary,
  rollingSummaryData,
  isConnected,
  liveEventCount,
  onSelectEvent,
}: LiveDashboardProps) {
  const latestDecision = latestOf(events, ['decision'])
  const latestTool = latestOf(events, ['tool_call', 'tool_result'])
  const latestError = latestOf(events, ['error'])
  const latestTurn = latestOf(events, ['agent_turn'])
  const latestPolicy = latestOf(events, ['prompt_policy'])
  const latestCheckpoint = checkpoints.at(-1) ?? null
  const previousCheckpoint = checkpoints.length > 1 ? checkpoints.at(-2) : null

  // Get behavior alerts from live summary
  const behaviorAlerts = liveSummary?.recent_alerts ?? []
  const hasOscillation = behaviorAlerts.some(alert => alert.alert_type === 'oscillation')

  const rollingSummary = rollingSummaryData?.text
    ?? liveSummary?.rolling_summary
    ?? latestTurn?.state_summary
    ?? latestPolicy?.state_summary
    ?? latestDecision?.reasoning
    ?? 'Awaiting richer live summaries'

  const metrics = rollingSummaryData?.metrics ?? {}
  const metricEntries = Object.entries(metrics)

  const checkpointDelta = computeCheckpointDelta(latestCheckpoint, previousCheckpoint)

  return (
    <div className="live-dashboard">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Live Monitoring</p>
          <h2>Session dashboard</h2>
        </div>
        <StabilityIndicator alertCount={behaviorAlerts.length} hasOscillation={hasOscillation} />
      </div>

      <div className="analysis-strip">
        <span>Status {session?.status ?? 'unknown'}</span>
        <span>Live events {liveEventCount}</span>
        <span>Checkpoints {liveSummary?.checkpoint_count ?? checkpoints.length}</span>
        <span>Recent alerts {behaviorAlerts.length}</span>
      </div>

      <div className="dashboard-grid">
        {/* Latest decision */}
        <button
          type="button"
          className="dashboard-card"
          disabled={!latestDecision}
          onClick={() => {
            if (latestDecision) onSelectEvent(latestDecision.id)
          }}
        >
          <span className="metric-label">Latest decision</span>
          <strong>{formatEventHeadline(latestDecision, 'None yet')}</strong>
          {latestDecision?.confidence && (
            <small className="dashboard-meta">Confidence: {(latestDecision.confidence * 100).toFixed(0)}%</small>
          )}
        </button>

        {/* Latest tool activity */}
        <button
          type="button"
          className="dashboard-card"
          disabled={!latestTool}
          onClick={() => {
            if (latestTool) onSelectEvent(latestTool.id)
          }}
        >
          <span className="metric-label">Latest tool activity</span>
          <strong>{formatEventHeadline(latestTool, 'None yet')}</strong>
          {latestTool?.tool_name && (
            <small className="dashboard-meta">{latestTool.event_type === 'tool_call' ? 'Call' : 'Result'}</small>
          )}
        </button>

        {/* Current error state */}
        <button
          type="button"
          className={`dashboard-card ${latestError ? 'dashboard-card--error' : ''}`}
          disabled={!latestError}
          onClick={() => {
            if (latestError) onSelectEvent(latestError.id)
          }}
        >
          <span className="metric-label">Current error state</span>
          <strong>{latestError ? formatEventHeadline(latestError) : 'No errors'}</strong>
          {latestError?.error_type && (
            <small className="dashboard-meta dashboard-meta--error">{latestError.error_type}</small>
          )}
        </button>

        {/* Latest checkpoint */}
        <div className="dashboard-card dashboard-card--static">
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

      {/* Behavior alerts section */}
      <div className="dashboard-alerts">
        <h3>Behavior alerts</h3>
        <div className="dashboard-alert-list">
          {behaviorAlerts.length ? (
            behaviorAlerts.map((alert) => (
              <button
                key={`${alert.source}-${alert.alert_type}-${alert.event_id}`}
                type="button"
                className={`dashboard-alert-row ${alert.severity} ${alert.source === 'derived' ? 'alert-derived' : ''}`}
                onClick={() => onSelectEvent(alert.event_id)}
              >
                <span className="dashboard-alert-head">
                  <strong>{alert.alert_type.replaceAll('_', ' ')}</strong>
                  <small>{alert.source}</small>
                </span>
                <span className="dashboard-alert-signal">{alert.signal}</span>
              </button>
            ))
          ) : (
            <p className="dashboard-alert-empty">No behavior alerts detected.</p>
          )}
        </div>
      </div>

      {/* Rolling summary */}
      <div className="dashboard-rolling">
        <h3>Rolling summary</h3>
        <p>{rollingSummary}</p>
        {rollingSummaryData && (
          <small className="rolling-window-info">
            Window: {rollingSummaryData.window_size} {rollingSummaryData.window_type}
          </small>
        )}
      </div>

      {/* Session metrics */}
      {metricEntries.length > 0 && (
        <div className="dashboard-metrics">
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

      {/* Connection status */}
      <div className={`live-badge ${isConnected ? 'connected' : 'offline'}`}>
        <span className={`live-dot ${isConnected ? 'pulsing' : ''}`} />
        <strong>{isConnected ? 'Connected' : 'Offline'}</strong>
      </div>
    </div>
  )
}
