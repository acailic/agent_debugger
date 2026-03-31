import type { DriftResponse } from '../types'

interface DriftAlertsPanelProps {
  agentName: string | null
  driftData: DriftResponse | null
  loading: boolean
}

export function DriftAlertsPanel({ agentName, driftData, loading }: DriftAlertsPanelProps) {
  if (!agentName) return null

  if (loading) {
    return (
      <section className="panel drift-panel">
        <p className="eyebrow">Behavior Drift</p>
        <h2>Loading baseline...</h2>
      </section>
    )
  }

  if (!driftData) {
    return (
      <section className="panel drift-panel">
        <p className="eyebrow">Behavior Drift</p>
        <h2>No baseline data</h2>
        <p>Build up session history to enable drift detection.</p>
      </section>
    )
  }

  const { baseline, current, alerts, message, error } = driftData

  if (error) {
    return (
      <section className="panel drift-panel">
        <p className="eyebrow">Behavior Drift</p>
        <h2>{agentName}</h2>
        <p className="drift-error">{error}</p>
      </section>
    )
  }

  return (
    <section className="panel drift-panel">
      <div className="panel-head">
        <p className="eyebrow" title="Detected deviation from established execution patterns over recent sessions">Behavior Drift</p>
        <h2>{agentName}</h2>
      </div>

      {message && <p className="drift-message">{message}</p>}

      {baseline && (
        <div className="baseline-summary">
          <span>Sessions: {baseline.session_count}</span>
          <span>Window: {baseline.time_window_days}d</span>
          <span>Confidence: {baseline.avg_decision_confidence.toFixed(2)}</span>
        </div>
      )}

      {current && (
        <div className="baseline-summary current-summary">
          <span>Current Sessions: {driftData.recent_session_count ?? 'N/A'}</span>
          <span>Confidence: {current.avg_decision_confidence.toFixed(2)}</span>
        </div>
      )}

      {alerts.length > 0 && (
        <div className="drift-alerts">
          <h3>Alerts ({alerts.length})</h3>
          {alerts.map((alert, index) => (
            <div key={`${alert.metric}-${index}`} className={`drift-alert ${alert.severity}`}>
              <div className="alert-header">
                <span className="alert-label">{alert.metric_label}</span>
                <span className={`alert-badge ${alert.severity}`}>
                  {alert.severity}
                </span>
              </div>
              <p className="alert-description">{alert.description}</p>
              <p className="alert-guidance">
                <small>Drift direction: {alert.change_percent > 0 ? 'Increased' : 'Decreased'}</small>
              </p>
              <div className="alert-values">
                <span>Baseline: {formatMetricValue(alert.baseline_value)}</span>
                <span>Current: {formatMetricValue(alert.current_value)}</span>
                <span>Change: {formatChange(alert.change_percent)}</span>
              </div>
              {alert.likely_cause && (
                <p className="alert-cause">Likely cause: {alert.likely_cause}</p>
              )}
              <p className="alert-suggested-action">
                <small>Consider anchoring your prompt or reviewing recent prompt changes</small>
              </p>
            </div>
          ))}
        </div>
      )}

      {alerts.length === 0 && baseline && (
        <p className="no-drift">No significant drift detected.</p>
      )}
    </section>
  )
}

function formatMetricValue(value: number): string {
  if (value < 0.01 && value > -0.01 && value !== 0) {
    return value.toExponential(2)
  }
  return value.toFixed(3)
}

function formatChange(percent: number): string {
  const sign = percent >= 0 ? '+' : ''
  return `${sign}${percent.toFixed(1)}%`
}
