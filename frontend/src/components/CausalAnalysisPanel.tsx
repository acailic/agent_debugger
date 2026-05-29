import type { CausalAnalysisResponse, CriticalPathAnalysis } from '../types'

interface CausalAnalysisPanelProps {
  sessionId: string | null
  causalData: CausalAnalysisResponse | null
  loading: boolean
}

export function CausalAnalysisPanel({ sessionId, causalData, loading }: CausalAnalysisPanelProps) {
  if (!sessionId) return null

  if (loading) {
    return (
      <section className="panel causal-panel">
        <p className="eyebrow">Causal Root Cause Analysis</p>
        <h2>Analyzing execution trace...</h2>
      </section>
    )
  }

  if (!causalData) {
    return (
      <section className="panel causal-panel">
        <p className="eyebrow">Causal Root Cause Analysis</p>
        <h2>No causal data available</h2>
        <p>Session events could not be analyzed for causal relationships.</p>
      </section>
    )
  }

  const { causal_graph, critical_paths, root_causes } = causalData
  const { statistics } = causal_graph

  const failureCount = statistics.failure_count
  const hasFailures = failureCount > 0

  return (
    <section className="panel causal-panel">
      <div className="panel-head">
        <p className="eyebrow" title="Root cause analysis based on AgentTrace methodology (arXiv:2603.14688)">
          Causal Root Cause Analysis
        </p>
        <h2>Session {sessionId.slice(0, 8)}</h2>
      </div>

      {/* Statistics Summary */}
      <div className="causal-stats">
        <div className="stat-item">
          <span className="stat-label">Events Analyzed:</span>
          <span className="stat-value">{statistics.total_nodes}</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">Causal Relationships:</span>
          <span className="stat-value">{statistics.total_edges}</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">Failures Detected:</span>
          <span className={`stat-value ${hasFailures ? 'failure-count' : ''}`}>
            {failureCount}
          </span>
        </div>
        <div className="stat-item">
          <span className="stat-label">Max Causal Depth:</span>
          <span className="stat-value">{statistics.max_depth}</span>
        </div>
      </div>

      {/* Root Causes Section */}
      {root_causes.length > 0 && (
        <div className="causal-section">
          <h3>Root Causes Identified</h3>
          <div className="root-causes-list">
            {root_causes.map((root) => (
              <div key={root.id} className="root-cause-item">
                <div className="root-cause-header">
                  <span className="event-type">{root.event_type}</span>
                  <span className="event-time">{formatTimestamp(root.timestamp)}</span>
                </div>
                <div className="root-cause-details">
                  <p className="root-cause-name">{root.name || 'Unnamed Event'}</p>
                  {root.failure_type && (
                    <span className="failure-type-badge">{root.failure_type}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Critical Paths for Failures */}
      {Object.keys(critical_paths).length > 0 && (
        <div className="causal-section">
          <h3>Failure Critical Paths</h3>
          <div className="critical-paths-list">
            {Object.values(critical_paths).map((path) => (
              <CriticalPathCard key={path.failure_node_id} path={path} />
            ))}
          </div>
        </div>
      )}

      {/* No Failures State */}
      {!hasFailures && (
        <div className="causal-no-failures">
          <p className="success-message">✓ No failures detected in this session</p>
          <p className="info-text">The causal graph shows {statistics.total_nodes} events with {statistics.total_edges} causal relationships.</p>
        </div>
      )}
    </section>
  )
}

interface CriticalPathCardProps {
  path: CriticalPathAnalysis
}

function CriticalPathCard({ path }: CriticalPathCardProps) {
  if (!path.root_cause_found) {
    return (
      <div className="critical-path-card">
        <p className="path-error">Could not trace critical path for failure</p>
      </div>
    )
  }

  return (
    <div className="critical-path-card">
      <div className="path-header">
        <h4>Critical Path to Failure</h4>
        <span className="path-length">{path.chain_length} events</span>
        <span className="path-duration">{path.total_duration_seconds.toFixed(2)}s</span>
      </div>

      {/* Weak Points */}
      {path.weak_points.length > 0 && (
        <div className="weak-points-section">
          <h5>Weak Points Identified</h5>
          <div className="weak-points-list">
            {path.weak_points.map((weakPoint) => (
              <div key={weakPoint.event_id} className="weak-point-item">
                <span className="weak-point-type">{weakPoint.weakness_type}</span>
                <span className="weak-point-desc">{weakPoint.description}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Critical Events Chain */}
      <div className="critical-events-chain">
        <h5>Causal Chain</h5>
        <div className="events-chain">
          {path.critical_events.map((event, index) => (
            <div key={event.event_id} className={`chain-event ${event.is_failure ? 'failure-event' : ''}`}>
              <div className="event-connector">
                {index < path.critical_events.length - 1 && <div className="connector-line" />}
              </div>
              <div className="event-content">
                <span className="event-sequence">{index + 1}</span>
                <span className="event-type-badge">{event.event_type}</span>
                <span className="event-name">{event.name}</span>
                {event.is_failure && (
                  <span className="failure-badge">FAILURE</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// Utility functions
function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSecs = Math.floor(diffMs / 1000)
  const diffMins = Math.floor(diffSecs / 60)
  const diffHours = Math.floor(diffMins / 60)

  if (diffSecs < 60) return `${diffSecs}s ago`
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  return date.toLocaleDateString()
}