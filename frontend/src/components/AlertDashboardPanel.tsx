import { useState } from 'react'
import { useAlerts } from '../hooks/useAlerts'
import { useAlertSummary } from '../hooks/useAlertSummary'
import type { AlertStatus } from '../types'
import { severityLabel } from '../types'

interface AlertDashboardPanelProps {
  agentName: string | null
}

export function AlertDashboardPanel({ agentName }: AlertDashboardPanelProps) {
  const { alerts, loading, error, filters, setFilter, clearAllFilters, updateStatus, bulkUpdate } =
    useAlerts(agentName ? { agent_name: agentName } : {})
  const { summary, trending, loading: summaryLoading } = useAlertSummary(7)
  const [expandedAlertId, setExpandedAlertId] = useState<string | null>(null)
  const [resolutionNote, setResolutionNote] = useState('')
  const [resolvingAlertId, setResolvingAlertId] = useState<string | null>(null)

  const handleStatusChange = async (alertId: string, status: AlertStatus, note?: string) => {
    try {
      await updateStatus(alertId, status, note)
      if (status === 'resolved' || status === 'dismissed') {
        setExpandedAlertId(null)
        setResolutionNote('')
      }
    } catch (err) {
      console.error('Failed to update alert status:', err)
    }
  }

  const handleBulkAcknowledge = async () => {
    const activeAlerts = alerts.filter((a) => a.status === 'active').map((a) => a.id)
    if (activeAlerts.length === 0) return
    try {
      await bulkUpdate(activeAlerts, 'acknowledged')
    } catch (err) {
      console.error('Failed to bulk acknowledge:', err)
    }
  }

  const handleResolve = async (alertId: string) => {
    setResolvingAlertId(alertId)
    try {
      await handleStatusChange(alertId, 'resolved', resolutionNote || undefined)
    } finally {
      setResolvingAlertId(null)
    }
  }

  const getSeverityColor = (severity: number): string => {
    const label = severityLabel(severity)
    switch (label) {
      case 'critical':
        return 'var(--danger)'
      case 'high':
        return 'oklch(0.58 0.22 25)'
      case 'medium':
        return 'var(--warning)'
      case 'low':
        return 'var(--olive)'
      default:
        return 'var(--muted)'
    }
  }

  const getStatusVariant = (status: AlertStatus): string => {
    switch (status) {
      case 'active':
        return 'alert-row--active'
      case 'acknowledged':
        return 'alert-row--acknowledged'
      case 'resolved':
        return 'alert-row--resolved'
      case 'dismissed':
        return 'alert-row--dismissed'
      default:
        return ''
    }
  }

  if (summaryLoading && !summary) {
    return (
      <section className="panel alert-dashboard">
        <div className="panel-head">
          <p className="eyebrow">Alerts</p>
          <h2>Alert Dashboard</h2>
        </div>
        <div className="loading-state">Loading alert data...</div>
      </section>
    )
  }

  return (
    <section className="panel alert-dashboard">
      <div className="panel-head">
        <p className="eyebrow">Alert Management</p>
        <h2>
          Alert Dashboard
          {summary && summary.total > 0 && <span className="alert-badge">{summary.total}</span>}
        </h2>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {/* Summary Cards */}
      {summary && (
        <div className="alert-summary-cards">
          <div className="alert-card alert-card--critical">
            <span className="metric-label">Total Alerts</span>
            <strong>{summary.total}</strong>
          </div>
          <div className="alert-card alert-card--critical">
            <span className="metric-label">Critical</span>
            <strong>{summary.by_severity.critical || 0}</strong>
          </div>
          <div className="alert-card alert-card--warning">
            <span className="metric-label">Warning</span>
            <strong>{summary.by_severity.high || 0}</strong>
          </div>
          <div className="alert-card alert-card--info">
            <span className="metric-label">Active</span>
            <strong>{summary.by_status.active || 0}</strong>
          </div>
        </div>
      )}

      {/* Filter Bar */}
      <div className="alert-filter-bar">
        <select
          value={filters.severity || ''}
          onChange={(e) => setFilter('severity', e.target.value)}
          className="filter-select"
        >
          <option value="">All Severities</option>
          <option value="0.8">Critical</option>
          <option value="0.5">High</option>
          <option value="0.3">Medium</option>
          <option value="0">Low</option>
        </select>
        <select
          value={filters.status || ''}
          onChange={(e) => setFilter('status', e.target.value)}
          className="filter-select"
        >
          <option value="">All Statuses</option>
          <option value="active">Active</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="resolved">Resolved</option>
          <option value="dismissed">Dismissed</option>
        </select>
        <select
          value={filters.alert_type || ''}
          onChange={(e) => setFilter('alert_type', e.target.value)}
          className="filter-select"
        >
          <option value="">All Types</option>
          <option value="oscillation">Oscillation</option>
          <option value="looping">Looping</option>
          <option value="confidence_drop">Confidence Drop</option>
          <option value="policy_violation">Policy Violation</option>
          <option value="safety_check">Safety Check</option>
        </select>
        {(filters.severity || filters.status || filters.alert_type) && (
          <button type="button" onClick={clearAllFilters} className="clear-filters-btn">
            Clear Filters
          </button>
        )}
        {alerts.some((a) => a.status === 'active') && (
          <button
            type="button"
            onClick={handleBulkAcknowledge}
            className="bulk-acknowledge-btn"
          >
            Acknowledge All
          </button>
        )}
      </div>

      {/* Alert List */}
      <div className="alert-list">
        {loading ? (
          <div className="loading-state">Loading alerts...</div>
        ) : alerts.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">🔔</div>
            <h3>No alerts</h3>
            <p>No alerts match the current filters.</p>
            <small>Alerts will appear here when behavior patterns need attention</small>
          </div>
        ) : (
          alerts.map((alert) => (
            <div
              key={alert.id}
              className={`alert-row ${getStatusVariant(alert.status)}`}
              role="button"
              tabIndex={0}
              aria-expanded={expandedAlertId === alert.id}
              onClick={() => setExpandedAlertId(expandedAlertId === alert.id ? null : alert.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  setExpandedAlertId(expandedAlertId === alert.id ? null : alert.id)
                }
              }}
            >
              <div className="alert-row-header">
                <div className="alert-row-meta">
                  <span
                    className="alert-severity-dot"
                    style={{ backgroundColor: getSeverityColor(alert.severity) }}
                  />
                  <span className="alert-type">{alert.alert_type}</span>
                  <span className="alert-severity">{severityLabel(alert.severity)}</span>
                  <span className="alert-status">{alert.status}</span>
                </div>
                <span className="alert-time">
                  {new Date(alert.created_at).toLocaleString()}
                </span>
              </div>
              <p className="alert-signal">{alert.signal}</p>

              {expandedAlertId === alert.id && (
                <div className="alert-details" onClick={(e) => e.stopPropagation()}>
                  <div className="alert-detail-row">
                    <span className="alert-detail-label">Session ID:</span>
                    <span className="alert-detail-value">{alert.session_id}</span>
                  </div>
                  <div className="alert-detail-row">
                    <span className="alert-detail-label">Detection Source:</span>
                    <span className="alert-detail-value">{alert.detection_source}</span>
                  </div>
                  <div className="alert-detail-row">
                    <span className="alert-detail-label">Events:</span>
                    <span className="alert-detail-value">{alert.event_ids.length} linked</span>
                  </div>
                  {alert.resolution_note && (
                    <div className="alert-detail-row">
                      <span className="alert-detail-label">Resolution Note:</span>
                      <span className="alert-detail-value">{alert.resolution_note}</span>
                    </div>
                  )}

                  {/* Resolution note input for active/acknowledged alerts */}
                  {(alert.status === 'active' || alert.status === 'acknowledged') && (
                    <div className="alert-resolution">
                      <label htmlFor={`resolution-${alert.id}`} className="alert-detail-label">
                        Resolution Note:
                      </label>
                      <input
                        id={`resolution-${alert.id}`}
                        type="text"
                        value={resolutionNote}
                        onChange={(e) => setResolutionNote(e.target.value)}
                        placeholder="Add resolution note..."
                        className="resolution-input"
                      />
                      <div className="alert-actions">
                        {alert.status === 'active' && (
                          <button
                            type="button"
                            onClick={() => handleStatusChange(alert.id, 'acknowledged')}
                            className="alert-action-btn alert-action-btn--acknowledge"
                          >
                            Acknowledge
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => handleResolve(alert.id)}
                          disabled={resolvingAlertId === alert.id || !resolutionNote}
                          className="alert-action-btn alert-action-btn--resolve"
                        >
                          {resolvingAlertId === alert.id ? 'Resolving...' : 'Resolve'}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleStatusChange(alert.id, 'dismissed')}
                          className="alert-action-btn alert-action-btn--dismiss"
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Trending Section */}
      {trending && trending.length > 0 && (
        <div className="trending-section">
          <h3>Alert Volume (Last 7 Days)</h3>
          <div className="trending-bars">
            {trending.map((point) => {
              const maxCount = Math.max(...trending.map((p) => p.count))
              const heightPercent = maxCount > 0 ? (point.count / maxCount) * 100 : 0
              return (
                <div key={point.date} className="trending-bar-container">
                  <div
                    className="trending-bar"
                    style={{ height: `${heightPercent}%` }}
                    title={`${point.date}: ${point.count} alerts`}
                  />
                  <span className="trending-label">{new Date(point.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </section>
  )
}
