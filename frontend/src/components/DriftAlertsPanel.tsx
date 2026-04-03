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

  const { baseline, current, alerts, message, recent_session_count } = driftData

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
          <span>LLM/session: {formatMetricValue(baseline.avg_llm_calls_per_session)}</span>
          <span>Cost/session: {formatCurrency(baseline.avg_cost_per_session)}</span>
          <span>Tokens/session: {formatMetricValue(baseline.avg_tokens_per_session)}</span>
          <span>Error rate: {formatPercent(baseline.error_rate)}</span>
        </div>
      )}

      {current && (
        <div className="baseline-summary current-summary">
          <span>Current Sessions: {recent_session_count ?? current.session_count}</span>
          <span>Tool/session: {formatMetricValue(current.avg_tool_calls_per_session)}</span>
          <span>Cost/session: {formatCurrency(current.avg_cost_per_session)}</span>
          <span>Duration: {formatDuration(current.avg_duration_seconds)}</span>
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
              <p className="alert-suggested-action">
                <small>Review the recent execution pattern that moved this metric.</small>
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

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function formatCurrency(value: number): string {
  return `$${value.toFixed(3)}`
}

function formatDuration(value: number): string {
  return `${value.toFixed(1)}s`
}
