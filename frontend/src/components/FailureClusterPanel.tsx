import type { FailureCluster } from '../types'

interface FailureClusterPanelProps {
  clusters: FailureCluster[]
  onSelectSession: (sessionId: string) => void
  selectedSessionId: string | null
}

export function FailureClusterPanel({ clusters, onSelectSession, selectedSessionId }: FailureClusterPanelProps) {
  if (clusters.length === 0) {
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

  return (
    <section className="panel failure-cluster-panel">
      <div className="panel-head">
        <p className="eyebrow">Failure Clusters</p>
        <h2>Cross-session patterns ({clusters.length})</h2>
      </div>

      <div className="cluster-list-detailed">
        {clusters.map((cluster) => (
          <button
            key={cluster.id}
            type="button"
            className={`cluster-card ${selectedSessionId === cluster.representative_session_id ? 'active' : ''}`}
            onClick={() => onSelectSession(cluster.representative_session_id)}
            aria-label={`Failure cluster: ${cluster.fingerprint}, ${cluster.session_count} sessions, average severity ${cluster.avg_severity.toFixed(2)}`}
          >
            <div className="cluster-header">
              <span className="cluster-fingerprint">{cluster.fingerprint}</span>
              <span className="cluster-severity">Avg severity: {cluster.avg_severity.toFixed(2)}</span>
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
            </div>
            {cluster.sample_symptom && (
              <p className="cluster-symptom">{cluster.sample_symptom}</p>
            )}
            <span className="cluster-link">View representative session</span>
          </button>
        ))}
      </div>
    </section>
  )
}
