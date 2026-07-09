import { useState, useEffect } from 'react'
import { logger } from '../utils/logger'
import {
  getViolationDashboard,
  searchViolations,
  clusterSessions,
  detectSparseFailures,
  findSimilarSessions,
} from '../api/client'
import type {
  ViolationReport,
  TraceCluster,
  SparseFailurePattern,
  ViolationDashboardSummary,
  SimilarSession,
} from '../types'

interface ViolationPanelProps {
  selectedSessionId: string | null
}

export function ViolationPanel({ selectedSessionId }: ViolationPanelProps) {
  const [activeTab, setActiveTab] = useState<'dashboard' | 'search' | 'clusters' | 'sparse'>('dashboard')
  const [dashboardData, setDashboardData] = useState<ViolationDashboardSummary | null>(null)
  const [searchResults, setSearchResults] = useState<ViolationReport[] | null>(null)
  const [clusters, setClusters] = useState<TraceCluster[] | null>(null)
  const [sparseFailures, setSparseFailures] = useState<SparseFailurePattern[] | null>(null)
  const [similarSessions, setSimilarSessions] = useState<SimilarSession[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  // Load dashboard data on mount
  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const data = await getViolationDashboard({ days: 7 })
        if (!cancelled) {
          setDashboardData(data)
        }
      } catch (err) {
        if (!cancelled) {
          logger.error('Failed to load violation dashboard:', {component: 'ViolationPanel'}, err)
          setError(err instanceof Error ? err.message : 'Failed to load dashboard')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    void load()
    return () => { cancelled = true }
  }, [])

  // Load similar sessions when session is selected
  useEffect(() => {
    if (!selectedSessionId) return
    let cancelled = false
    async function load(sessionId: string) {
      try {
        const data = await findSimilarSessions({ sessionId, limit: 5 })
        if (!cancelled) {
          setSimilarSessions(data.similar_sessions)
        }
      } catch (err) {
        if (!cancelled) {
          logger.error('Failed to load similar sessions:', {component: 'ViolationPanel'}, err)
        }
      }
    }
    void load(selectedSessionId)
    return () => { cancelled = true }
  }, [selectedSessionId])

  const handleSearch = async () => {
    if (!searchQuery.trim()) return

    setLoading(true)
    setError(null)
    try {
      const data = await searchViolations({
        nlQuery: searchQuery,
        maxResults: 20
      })
      setSearchResults(data.violations)
      setActiveTab('search')
    } catch (err) {
      logger.error('Failed to search violations:', {component: 'ViolationPanel'}, err)
      setError(err instanceof Error ? err.message : 'Failed to search violations')
    } finally {
      setLoading(false)
    }
  }

  const handleClusterSessions = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await clusterSessions({
        similarityThreshold: 0.7,
        minClusterSize: 2
      })
      setClusters(data.clusters)
      setActiveTab('clusters')
    } catch (err) {
      logger.error('Failed to cluster sessions:', {component: 'ViolationPanel'}, err)
      setError(err instanceof Error ? err.message : 'Failed to cluster sessions')
    } finally {
      setLoading(false)
    }
  }

  const handleDetectSparseFailures = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await detectSparseFailures({
        minOccurrences: 2
      })
      setSparseFailures(data.sparse_failures)
      setActiveTab('sparse')
    } catch (err) {
      logger.error('Failed to detect sparse failures:', {component: 'ViolationPanel'}, err)
      setError(err instanceof Error ? err.message : 'Failed to detect sparse failures')
    } finally {
      setLoading(false)
    }
  }

  function getSeverityColor(severity: string): string {
    switch (severity) {
      case 'critical':
        return '#dc2626' // red-600
      case 'high':
        return '#ea580c' // orange-600
      case 'medium':
        return '#ca8a04' // yellow-600
      case 'low':
        return '#65a30d' // lime-600
      default:
        return '#6b7280' // gray-500
    }
  }

  function getViolationTypeColor(violationType: string): string {
    switch (violationType) {
      case 'outlier_behavior':
        return '#8b5cf6' // violet-500
      case 'sparse_failure':
        return '#ef4444' // red-500
      case 'pattern_deviation':
        return '#3b82f6' // blue-500
      case 'temporal_anomaly':
        return '#06b6d4' // cyan-500
      case 'resource_anomaly':
        return '#10b981' // emerald-500
      case 'safety_violation':
        return '#f59e0b' // amber-500
      default:
        return '#6b7280' // gray-500
    }
  }

  if (loading && !dashboardData) {
    return (
      <div className="violation-panel loading-panel">
        <p>Loading violation detection...</p>
      </div>
    )
  }

  if (error && !dashboardData) {
    return (
      <div className="violation-panel error-panel">
        <p className="error-message">Error: {error}</p>
      </div>
    )
  }

  return (
    <div className="violation-panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Cross-Trace Violations</p>
          <h2>Meerkat Detection</h2>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="analysis-tabs">
        <button
          className={`tab-button ${activeTab === 'dashboard' ? 'active' : ''}`}
          onClick={() => setActiveTab('dashboard')}
        >
          Dashboard
        </button>
        <button
          className={`tab-button ${activeTab === 'search' ? 'active' : ''}`}
          onClick={() => setActiveTab('search')}
        >
          NL Search
        </button>
        <button
          className={`tab-button ${activeTab === 'clusters' ? 'active' : ''}`}
          onClick={() => setActiveTab('clusters')}
        >
          Clusters
        </button>
        <button
          className={`tab-button ${activeTab === 'sparse' ? 'active' : ''}`}
          onClick={() => setActiveTab('sparse')}
        >
          Sparse Failures
        </button>
      </div>

      {/* Dashboard Tab */}
      {activeTab === 'dashboard' && dashboardData && (
        <div className="dashboard-content">
          <div className="summary-cards">
            <div className="summary-card">
              <h3>Total Violations</h3>
              <strong>{dashboardData.violation_summary.total_violations}</strong>
            </div>
            <div className="summary-card">
              <h3>Total Clusters</h3>
              <strong>{dashboardData.cluster_summary.total_clusters}</strong>
            </div>
            <div className="summary-card">
              <h3>Outliers</h3>
              <strong>{dashboardData.cluster_summary.total_outliers}</strong>
            </div>
            <div className="summary-card">
              <h3>Sparse Patterns</h3>
              <strong>{dashboardData.sparse_failure_summary.total_patterns}</strong>
            </div>
          </div>

          {/* Violations by Type */}
          <div className="violation-by-type">
            <h3>Violations by Type</h3>
            {Object.entries(dashboardData.violation_summary.by_type).map(([type, count]) => (
              <div key={type} className="type-item">
                <span
                  className="type-badge"
                  style={{ backgroundColor: getViolationTypeColor(type) }}
                >
                  {type.replace('_', ' ')}
                </span>
                <strong>{count as number}</strong>
              </div>
            ))}
          </div>

          {/* Violations by Severity */}
          <div className="violation-by-severity">
            <h3>Violations by Severity</h3>
            {Object.entries(dashboardData.violation_summary.by_severity).map(([severity, count]) => (
              <div key={severity} className="severity-item">
                <span
                  className="severity-badge"
                  style={{ backgroundColor: getSeverityColor(severity) }}
                >
                  {severity}
                </span>
                <strong>{count as number}</strong>
              </div>
            ))}
          </div>

          {/* Common Failure Types */}
          {dashboardData.sparse_failure_summary.most_common_failure_types.length > 0 && (
            <div className="common-failures">
              <h3>Most Common Failure Types</h3>
              {dashboardData.sparse_failure_summary.most_common_failure_types.map((failure: { failure_type: string; occurrence_count: number }) => (
                <div key={failure.failure_type} className="failure-item">
                  <span className="failure-type">{failure.failure_type}</span>
                  <span className="failure-count">{failure.occurrence_count} occurrences</span>
                </div>
              ))}
            </div>
          )}

          {/* Similar Sessions */}
          {selectedSessionId && similarSessions && similarSessions.length > 0 && (
            <div className="similar-sessions">
              <h3>Sessions Similar to Current</h3>
              {similarSessions.map((similar) => (
                <div key={similar.session_id} className="similar-item">
                  <span className="session-name">{similar.agent_name}</span>
                  <span className="similarity-score">
                    {(similar.similarity_score * 100).toFixed(1)}% similar
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Search Tab */}
      {activeTab === 'search' && (
        <div className="search-content">
          <div className="search-bar">
            <input
              type="text"
              placeholder="Describe violation to search (e.g., 'unsafe data handling')"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            />
            <button onClick={handleSearch} disabled={loading || !searchQuery.trim()}>
              Search
            </button>
          </div>

          {searchResults && searchResults.length > 0 ? (
            <div className="search-results">
              <h3>Found {searchResults.length} Violations</h3>
              {searchResults.map((violation) => (
                <div key={violation.violation_id} className="violation-card">
                  <div className="violation-header">
                    <span
                      className="violation-type-badge"
                      style={{ backgroundColor: getViolationTypeColor(violation.violation_type) }}
                    >
                      {violation.violation_type.replace('_', ' ')}
                    </span>
                    <span
                      className="severity-badge"
                      style={{ backgroundColor: getSeverityColor(violation.severity) }}
                    >
                      {violation.severity}
                    </span>
                  </div>
                  <h4>{violation.title}</h4>
                  <p>{violation.description}</p>
                  <div className="evidence-section">
                    <h5>Evidence ({violation.evidence.length} items)</h5>
                    {violation.evidence.slice(0, 3).map((evidence: { session_id: string; description: string }, idx: number) => (
                      <div key={idx} className="evidence-item">
                        <small>Session: {evidence.session_id}</small>
                        <p>{evidence.description}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : searchResults && searchResults.length === 0 ? (
            <div className="empty-state">
              <p>No violations found matching your search.</p>
            </div>
          ) : (
            <div className="empty-state">
              <p>Enter a natural language description to search for violations.</p>
            </div>
          )}
        </div>
      )}

      {/* Clusters Tab */}
      {activeTab === 'clusters' && (
        <div className="clusters-content">
          <button onClick={handleClusterSessions} disabled={loading}>
            Analyze Clusters
          </button>

          {clusters && clusters.length > 0 ? (
            <div className="clusters-list">
              <h3>Found {clusters.length} Clusters</h3>
              {clusters.map((cluster) => (
                <div key={cluster.cluster_id} className="cluster-card">
                  <h4>{cluster.cluster_id}</h4>
                  <p>{cluster.session_ids.length} sessions in cluster</p>
                  {cluster.outlier_session_ids.length > 0 && (
                    <div className="outliers">
                      <h5>Outliers:</h5>
                      {cluster.outlier_session_ids.map((id: string) => (
                        <span key={id} className="outlier-id">{id}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : clusters && clusters.length === 0 ? (
            <div className="empty-state">
              <p>No clusters found with current settings.</p>
            </div>
          ) : (
            <div className="empty-state">
              <p>Click "Analyze Clusters" to group similar sessions.</p>
            </div>
          )}
        </div>
      )}

      {/* Sparse Failures Tab */}
      {activeTab === 'sparse' && (
        <div className="sparse-content">
          <button onClick={handleDetectSparseFailures} disabled={loading}>
            Detect Sparse Failures
          </button>

          {sparseFailures && sparseFailures.length > 0 ? (
            <div className="sparse-list">
              <h3>Found {sparseFailures.length} Sparse Failure Patterns</h3>
              {sparseFailures.map((pattern) => (
                <div key={pattern.pattern_id} className="sparse-card">
                  <h4>{pattern.failure_type}</h4>
                  <p>{pattern.description}</p>
                  <div className="pattern-details">
                    <small>Required sessions: {pattern.required_sessions}</small>
                    <small>Found in {pattern.session_ids.length} sessions</small>
                    <small>Confidence: {(pattern.confidence * 100).toFixed(1)}%</small>
                  </div>
                </div>
              ))}
            </div>
          ) : sparseFailures && sparseFailures.length === 0 ? (
            <div className="empty-state">
              <p>No sparse failure patterns detected.</p>
            </div>
          ) : (
            <div className="empty-state">
              <p>Click "Detect Sparse Failures" to find cross-trace failure patterns.</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}