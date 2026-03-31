import type { FailureCluster, TraceAnalysisCluster, TraceEvent } from '../types'

interface FailureClusterPanelProps {
  clusters: FailureCluster[]
  onSelectSession: (sessionId: string) => void
  selectedSessionId: string | null
  analysisClusters?: TraceAnalysisCluster[]
  events?: TraceEvent[]
}

interface DerivedCluster {
  id: string
  fingerprint: string
  session_count: number
  event_count: number
  avg_severity: number
  representative_session_id: string
  sample_symptom: string | null
  representative_event?: TraceEvent
  max_composite: number
}

function deriveSeverityColor(severity: number): string {
  if (severity >= 0.7) return 'var(--danger)'
  if (severity >= 0.4) return 'var(--warning)'
  return 'var(--olive)'
}

function getSeverityLabel(severity: number): string {
  if (severity >= 0.7) return 'High'
  if (severity >= 0.4) return 'Medium'
  return 'Low'
}

function deriveClustersFromAnalysis(
  analysisClusters: TraceAnalysisCluster[],
  events: TraceEvent[]
): DerivedCluster[] {
  const eventLookup = new Map(events.map((e) => [e.id, e]))

  return analysisClusters.map((cluster, idx) => {
    const representativeEvent = eventLookup.get(cluster.representative_event_id)
    const fingerprintLabel = cluster.fingerprint.length > 60
      ? `${cluster.fingerprint.slice(0, 60)}...`
      : cluster.fingerprint

    return {
      id: `derived-${idx}`,
      fingerprint: fingerprintLabel,
      session_count: 1, // Analysis clusters are per-session
      event_count: cluster.count,
      avg_severity: cluster.max_composite,
      representative_session_id: representativeEvent?.session_id ?? '',
      sample_symptom: representativeEvent?.error ?? representativeEvent?.name ?? null,
      representative_event: representativeEvent,
      max_composite: cluster.max_composite,
    }
  })
}

function ClusterBarChart({ clusters }: { clusters: DerivedCluster[] }) {
  const maxCount = Math.max(...clusters.map((c) => c.event_count), 1)

  return (
    <div className="cluster-bar-chart">
      {clusters.map((cluster) => (
        <div
          key={cluster.id}
          className="cluster-bar"
          style={{
            width: `${(cluster.event_count / maxCount) * 100}%`,
            backgroundColor: deriveSeverityColor(cluster.avg_severity),
          }}
          title={`${cluster.event_count} events`}
        />
      ))}
    </div>
  )
}

export function FailureClusterPanel({
  clusters,
  onSelectSession,
  selectedSessionId,
  analysisClusters = [],
  events = [],
}: FailureClusterPanelProps) {
  // Use provided clusters, or derive from analysis data
  const displayClusters: DerivedCluster[] = clusters.length > 0
    ? clusters.map((c) => ({
        ...c,
        max_composite: c.avg_severity,
      }))
    : deriveClustersFromAnalysis(analysisClusters, events)

  if (displayClusters.length === 0) {
    return (
      <section className="panel failure-cluster-panel">
        <div className="panel-head">
          <p className="eyebrow">Failure Clusters</p>
          <h2>Cross-session patterns</h2>
        </div>
        <p className="empty-message">No failure clusters detected across sessions.</p>
      </section>
    )
  }

  // Sort by severity (highest first)
  const sortedClusters = [...displayClusters].sort((a, b) => b.avg_severity - a.avg_severity)

  return (
    <section className="panel failure-cluster-panel">
      <div className="panel-head">
        <p className="eyebrow">Failure Clusters</p>
        <h2>Cross-session patterns ({sortedClusters.length})</h2>
      </div>

      <ClusterBarChart clusters={sortedClusters} />

      <div className="cluster-list-detailed">
        {sortedClusters.map((cluster) => {
          const severityColor = deriveSeverityColor(cluster.avg_severity)
          const severityLabel = getSeverityLabel(cluster.avg_severity)
          const isActive = selectedSessionId === cluster.representative_session_id

          return (
            <button
              key={cluster.id}
              type="button"
              className={`cluster-card ${isActive ? 'active' : ''}`}
              onClick={() => onSelectSession(cluster.representative_session_id)}
              data-severity={severityLabel.toLowerCase()}
              aria-label={`Failure cluster: ${cluster.fingerprint}, ${cluster.session_count} sessions, average severity ${cluster.avg_severity.toFixed(2)}`}
            >
              <div className="cluster-header">
                <span className="cluster-fingerprint" title={cluster.fingerprint}>
                  {cluster.fingerprint}
                </span>
                <span
                  className="cluster-severity"
                  style={{ color: severityColor }}
                >
                  {severityLabel} severity
                </span>
              </div>

              <div className="cluster-metrics">
                <div className="cluster-metric">
                  <span className="metric-label">Sessions</span>
                  <strong>{cluster.session_count}</strong>
                </div>
                <div className="cluster-metric">
                  <span className="metric-label">Events</span>
                  <strong>{cluster.event_count}</strong>
                </div>
                <div className="cluster-metric">
                  <span className="metric-label">Score</span>
                  <strong>{cluster.avg_severity.toFixed(2)}</strong>
                </div>
              </div>

              {cluster.sample_symptom && (
                <p className="cluster-symptom">{cluster.sample_symptom}</p>
              )}

              {cluster.representative_event && (
                <div className="cluster-event-detail">
                  <span className="metric-label">Representative</span>
                  <small>{cluster.representative_event.event_type.replaceAll('_', ' ')}</small>
                </div>
              )}

              <span className="cluster-link">View representative session</span>
            </button>
          )
        })}
      </div>
    </section>
  )
}
