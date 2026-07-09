import { useState, useEffect, useMemo } from 'react'
import { logger } from '../utils/logger'
import {
  getDivergenceAnalysis,
  getStructuralDivergence,
  getTemporalDivergence,
  getBehavioralDivergence,
  getBaselineDivergence
} from '../api/client'
import type {
  Session,
  DivergencePoint,
  DivergenceSeverity,
  DivergenceType,
  DivergenceAnalysisResponse,
  StructuralDivergenceResponse,
  TemporalDivergenceResponse,
  BehavioralDivergenceResponse,
  BaselineDivergenceResponse
} from '../types'

interface DivergenceAnalysisPanelProps {
  primarySessionId: string | null
  secondarySessionId: string | null
  sessions: Session[]
  onSelectSecondarySession: (sessionId: string | null) => void
}

type AnalysisTab = 'overview' | 'structural' | 'temporal' | 'behavioral' | 'baseline'

function getSeverityColor(severity: DivergenceSeverity): string {
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

function getDivergenceTypeColor(type: DivergenceType): string {
  switch (type) {
    case 'structural':
      return '#8b5cf6' // violet-500
    case 'temporal':
      return '#06b6d4' // cyan-500
    case 'behavioral':
      return '#ec4899' // pink-500
    case 'state':
      return '#f59e0b' // amber-500
    case 'error':
      return '#ef4444' // red-500
    case 'performance':
      return '#10b981' // emerald-500
    default:
      return '#6b7280' // gray-500
  }
}

function getSeverityLabel(severity: DivergenceSeverity): string {
  return severity.charAt(0).toUpperCase() + severity.slice(1)
}

function getDivergenceTypeLabel(type: DivergenceType): string {
  return type.split('_').map(word =>
    word.charAt(0).toUpperCase() + word.slice(1)
  ).join(' ')
}

export function DivergenceAnalysisPanel({
  primarySessionId,
  secondarySessionId,
  sessions,
  onSelectSecondarySession
}: DivergenceAnalysisPanelProps) {
  const [activeTab, setActiveTab] = useState<AnalysisTab>('overview')
  const [divergenceAnalysis, setDivergenceAnalysis] = useState<DivergenceAnalysisResponse | null>(null)
  const [structuralAnalysis, setStructuralAnalysis] = useState<StructuralDivergenceResponse | null>(null)
  const [temporalAnalysis, setTemporalAnalysis] = useState<TemporalDivergenceResponse | null>(null)
  const [behavioralAnalysis, setBehavioralAnalysis] = useState<BehavioralDivergenceResponse | null>(null)
  const [baselineAnalysis, setBaselineAnalysis] = useState<BaselineDivergenceResponse | null>(null)
  const [prevPrimaryForBaseline, setPrevPrimaryForBaseline] = useState(primarySessionId)
  const [prevSecondaryForBaseline, setPrevSecondaryForBaseline] = useState(secondarySessionId)
  const [prevPrimaryForAnalysis, setPrevPrimaryForAnalysis] = useState(primarySessionId)
  const [prevSecondaryForAnalysis, setPrevSecondaryForAnalysis] = useState(secondarySessionId)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Filter out primary session from secondary options
  const secondaryOptions = useMemo(() => {
    if (!primarySessionId) return []
    return sessions.filter(session => session.id !== primarySessionId)
  }, [sessions, primarySessionId])

  // Clear stale divergence analysis when a session is removed.
  // setState-during-render replaces the previous synchronous setState-in-effect reset.
  if (primarySessionId !== prevPrimaryForAnalysis || secondarySessionId !== prevSecondaryForAnalysis) {
    setPrevPrimaryForAnalysis(primarySessionId)
    setPrevSecondaryForAnalysis(secondarySessionId)
    if (!primarySessionId || !secondarySessionId) {
      setDivergenceAnalysis(null)
      setError(null)
    }
  }

  // Load divergence analysis when both sessions are selected
  useEffect(() => {
    if (!primarySessionId || !secondarySessionId) return

    const loadAnalysis = async () => {
      setLoading(true)
      setError(null)
      try {
        const analysis = await getDivergenceAnalysis(primarySessionId, secondarySessionId)
        setDivergenceAnalysis(analysis)
      } catch (err) {
        logger.error('Failed to load divergence analysis:', {component: 'DivergenceAnalysisPanel'}, err)
        setError(err instanceof Error ? err.message : 'Failed to load divergence analysis')
        setDivergenceAnalysis(null)
      } finally {
        setLoading(false)
      }
    }

    loadAnalysis()
  }, [primarySessionId, secondarySessionId])

  // Load specific analysis types based on active tab
  useEffect(() => {
    if (!primarySessionId || !secondarySessionId) return

    const loadSpecificAnalysis = async () => {
      try {
        switch (activeTab) {
          case 'structural': {
            const structural = await getStructuralDivergence(primarySessionId, secondarySessionId)
            setStructuralAnalysis(structural)
            break
          }
          case 'temporal': {
            const temporal = await getTemporalDivergence(primarySessionId, secondarySessionId)
            setTemporalAnalysis(temporal)
            break
          }
          case 'behavioral': {
            const behavioral = await getBehavioralDivergence(primarySessionId, secondarySessionId)
            setBehavioralAnalysis(behavioral)
            break
          }
          default:
            break
        }
      } catch (err) {
        logger.error(`Failed to load ${activeTab} analysis:`, {component: 'DivergenceAnalysisPanel'}, err)
      }
    }

    loadSpecificAnalysis()
  }, [activeTab, primarySessionId, secondarySessionId])

  // Clear stale baseline analysis when the baseline-loading condition no longer holds.
  // setState-during-render replaces the previous synchronous setState-in-effect reset.
  if (primarySessionId !== prevPrimaryForBaseline || secondarySessionId !== prevSecondaryForBaseline) {
    setPrevPrimaryForBaseline(primarySessionId)
    setPrevSecondaryForBaseline(secondarySessionId)
    if (!primarySessionId || secondarySessionId) {
      setBaselineAnalysis(null)
    }
  }

  // Load baseline analysis when only primary session is selected
  useEffect(() => {
    if (!primarySessionId || secondarySessionId) return

    const loadBaseline = async () => {
      try {
        const baseline = await getBaselineDivergence(primarySessionId)
        setBaselineAnalysis(baseline)
      } catch (err) {
        logger.error('Failed to load baseline analysis:', {component: 'DivergenceAnalysisPanel'}, err)
      }
    }

    loadBaseline()
  }, [primarySessionId, secondarySessionId])

  const currentAnalysis = divergenceAnalysis?.divergence_analysis
  const divergencePoints = useMemo(
    () => currentAnalysis?.divergence_points || [],
    [currentAnalysis]
  )
  const overallScore = currentAnalysis?.overall_divergence_score || 0

  // Group divergences by type and severity
  const groupedDivergences = useMemo(() => {
    const groups: Record<DivergenceType, DivergencePoint[]> = {
      structural: [],
      temporal: [],
      behavioral: [],
      state: [],
      error: [],
      performance: []
    }

    divergencePoints.forEach(point => {
      if (point.divergence_type in groups) {
        groups[point.divergence_type as DivergenceType].push(point)
      }
    })

    return groups
  }, [divergencePoints])

  const severityCounts = useMemo(() => {
    const counts: Record<DivergenceSeverity, number> = {
      critical: 0,
      high: 0,
      medium: 0,
      low: 0
    }

    divergencePoints.forEach(point => {
      counts[point.severity]++
    })

    return counts
  }, [divergencePoints])

  if (!primarySessionId) {
    return (
      <div className="divergence-panel empty-panel">
        <p>Select a primary session to analyze divergences.</p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="divergence-panel loading-panel">
        <p>Loading divergence analysis...</p>
      </div>
    )
  }

  if (error && !divergenceAnalysis) {
    return (
      <div className="divergence-panel error-panel">
        <p className="error-message">Error: {error}</p>
      </div>
    )
  }

  return (
    <div className="divergence-panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Divergence Analysis</p>
          <h2>Session Comparison</h2>
        </div>
        <select
          className="compare-select"
          value={secondarySessionId || ''}
          onChange={(e) => onSelectSecondarySession(e.target.value || null)}
        >
          <option value="">Select comparison session</option>
          {secondaryOptions.map((session: Session) => (
            <option key={session.id} value={session.id}>
              {session.agent_name} · {session.started_at}
            </option>
          ))}
        </select>
      </div>

      {!secondarySessionId ? (
        <div className="empty-panel">
          <p>Select a secondary session to compare and analyze divergences.</p>
          {baselineAnalysis && baselineAnalysis.baseline_session_id && (
            <div className="baseline-info">
              <h3>Baseline Comparison Available</h3>
              <p>Baseline session: {baselineAnalysis.baseline_session?.agent_name}</p>
              {baselineAnalysis.divergence_analysis && (
                <div className="baseline-metrics">
                  <div className="metric">
                    <span className="label">Divergence Score:</span>
                    <strong>{baselineAnalysis.divergence_analysis.overall_divergence_score.toFixed(2)}</strong>
                  </div>
                  <div className="metric">
                    <span className="label">Similarity:</span>
                    <strong>{(baselineAnalysis.divergence_analysis.structural_similarity * 100).toFixed(1)}%</strong>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        <>
          {/* Analysis Tabs */}
          <div className="analysis-tabs">
            <button
              className={`tab-button ${activeTab === 'overview' ? 'active' : ''}`}
              onClick={() => setActiveTab('overview')}
            >
              Overview
            </button>
            <button
              className={`tab-button ${activeTab === 'structural' ? 'active' : ''}`}
              onClick={() => setActiveTab('structural')}
            >
              Structural
            </button>
            <button
              className={`tab-button ${activeTab === 'temporal' ? 'active' : ''}`}
              onClick={() => setActiveTab('temporal')}
            >
              Temporal
            </button>
            <button
              className={`tab-button ${activeTab === 'behavioral' ? 'active' : ''}`}
              onClick={() => setActiveTab('behavioral')}
            >
              Behavioral
            </button>
          </div>

          {/* Overview Tab */}
          {activeTab === 'overview' && currentAnalysis && (
            <div className="overview-content">
              {/* Overall Divergence Score */}
              <div className="overall-score-section">
                <h3>Overall Divergence Score</h3>
                <div className="score-display">
                  <div
                    className="score-bar"
                    style={{ width: `${overallScore * 100}%`, backgroundColor: getSeverityColor(overallScore > 0.7 ? 'critical' : overallScore > 0.4 ? 'high' : 'medium') }}
                  />
                  <span className="score-value">{(overallScore * 100).toFixed(1)}%</span>
                </div>
              </div>

              {/* Similarity Scores */}
              <div className="similarity-scores">
                <h3>Similarity Scores</h3>
                <div className="score-grid">
                  <div className="score-item">
                    <span className="label">Structural:</span>
                    <div className="score-bar-container">
                      <div
                        className="score-bar"
                        style={{ width: `${currentAnalysis.structural_similarity * 100}%` }}
                      />
                      <span>{(currentAnalysis.structural_similarity * 100).toFixed(1)}%</span>
                    </div>
                  </div>
                  <div className="score-item">
                    <span className="label">Temporal:</span>
                    <div className="score-bar-container">
                      <div
                        className="score-bar"
                        style={{ width: `${currentAnalysis.temporal_similarity * 100}%` }}
                      />
                      <span>{(currentAnalysis.temporal_similarity * 100).toFixed(1)}%</span>
                    </div>
                  </div>
                  <div className="score-item">
                    <span className="label">Behavioral:</span>
                    <div className="score-bar-container">
                      <div
                        className="score-bar"
                        style={{ width: `${currentAnalysis.behavioral_similarity * 100}%` }}
                      />
                      <span>{(currentAnalysis.behavioral_similarity * 100).toFixed(1)}%</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Severity Summary */}
              <div className="severity-summary">
                <h3>Divergence Severity</h3>
                <div className="severity-grid">
                  {Object.entries(severityCounts).map(([severity, count]) => (
                    <div key={severity} className="severity-item">
                      <span
                        className="severity-badge"
                        style={{ backgroundColor: getSeverityColor(severity as DivergenceSeverity) }}
                      >
                        {getSeverityLabel(severity as DivergenceSeverity)}
                      </span>
                      <strong>{count}</strong>
                    </div>
                  ))}
                </div>
              </div>

              {/* Divergence by Type */}
              <div className="divergence-by-type">
                <h3>Divergences by Type</h3>
                {Object.entries(groupedDivergences).map(([type, points]) => (
                  <div key={type} className="type-section">
                    <div className="type-header">
                      <span
                        className="type-badge"
                        style={{ backgroundColor: getDivergenceTypeColor(type as DivergenceType) }}
                      >
                        {getDivergenceTypeLabel(type as DivergenceType)}
                      </span>
                      <strong>{points.length} divergences</strong>
                    </div>
                    {points.length > 0 && (
                      <div className="divergence-list">
                        {points.slice(0, 5).map(point => (
                          <div key={point.divergence_type + point.primary_event_id} className="divergence-item">
                            <div className="divergence-header">
                              <span
                                className="severity-indicator"
                                style={{ backgroundColor: getSeverityColor(point.severity) }}
                              />
                              <span className="description">{point.description}</span>
                            </div>
                            <div className="divergence-details">
                              <small>Score: {point.divergence_score.toFixed(2)}</small>
                              {point.primary_event_id && <small>Event: {point.primary_event_id}</small>}
                            </div>
                          </div>
                        ))}
                        {points.length > 5 && (
                          <p className="more-items">+{points.length - 5} more</p>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Structural Analysis Tab */}
          {activeTab === 'structural' && structuralAnalysis && (
            <div className="structural-content">
              <h3>Structural Comparison</h3>
              <div className="structural-metrics">
                <div className="metric-pair">
                  <div className="metric primary">
                    <span className="label">Tree Depth (Primary):</span>
                    <strong>{structuralAnalysis.structural_comparison.primary_depth}</strong>
                  </div>
                  <div className="metric secondary">
                    <span className="label">Tree Depth (Secondary):</span>
                    <strong>{structuralAnalysis.structural_comparison.secondary_depth}</strong>
                  </div>
                </div>
                <div className="metric-pair">
                  <div className="metric primary">
                    <span className="label">Branching Factor (Primary):</span>
                    <strong>{structuralAnalysis.structural_comparison.primary_branching_factor.toFixed(2)}</strong>
                  </div>
                  <div className="metric secondary">
                    <span className="label">Branching Factor (Secondary):</span>
                    <strong>{structuralAnalysis.structural_comparison.secondary_branching_factor.toFixed(2)}</strong>
                  </div>
                </div>
                <div className="metric">
                  <span className="label">Structural Similarity:</span>
                  <strong>{(structuralAnalysis.structural_comparison.structural_similarity * 100).toFixed(1)}%</strong>
                </div>
              </div>
            </div>
          )}

          {/* Temporal Analysis Tab */}
          {activeTab === 'temporal' && temporalAnalysis && (
            <div className="temporal-content">
              <h3>Temporal Analysis</h3>
              <div className="temporal-metrics">
                <div className="metric-pair">
                  <div className="metric primary">
                    <span className="label">Duration (Primary):</span>
                    <strong>{temporalAnalysis.temporal_analysis.primary_duration_seconds.toFixed(2)}s</strong>
                  </div>
                  <div className="metric secondary">
                    <span className="label">Duration (Secondary):</span>
                    <strong>{temporalAnalysis.temporal_analysis.secondary_duration_seconds.toFixed(2)}s</strong>
                  </div>
                </div>
                <div className="metric">
                  <span className="label">Duration Difference:</span>
                  <strong>{temporalAnalysis.temporal_analysis.duration_difference_seconds.toFixed(2)}s</strong>
                </div>
                <div className="metric">
                  <span className="label">Temporal Divergence Score:</span>
                  <strong>{(temporalAnalysis.temporal_analysis.temporal_divergence_score * 100).toFixed(1)}%</strong>
                </div>
              </div>

              {temporalAnalysis.temporal_analysis.timing_differences.length > 0 && (
                <div className="timing-differences">
                  <h4>Timing Differences</h4>
                  {temporalAnalysis.temporal_analysis.timing_differences.map((diff, index) => (
                    <div key={index} className="timing-item">
                      <span className="type">{diff.type}</span>
                      <span className="difference">{diff.time_difference_seconds.toFixed(2)}s</span>
                      <span className="description">{diff.description}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Behavioral Analysis Tab */}
          {activeTab === 'behavioral' && behavioralAnalysis && (
            <div className="behavioral-content">
              <h3>Behavioral Analysis</h3>
              <div className="behavioral-metrics">
                <div className="metric-pair">
                  <div className="metric primary">
                    <span className="label">Decisions (Primary):</span>
                    <strong>{behavioralAnalysis.behavioral_analysis.primary_decision_count}</strong>
                  </div>
                  <div className="metric secondary">
                    <span className="label">Decisions (Secondary):</span>
                    <strong>{behavioralAnalysis.behavioral_analysis.secondary_decision_count}</strong>
                  </div>
                </div>
                <div className="metric-pair">
                  <div className="metric primary">
                    <span className="label">Tool Calls (Primary):</span>
                    <strong>{behavioralAnalysis.behavioral_analysis.primary_tool_call_count}</strong>
                  </div>
                  <div className="metric secondary">
                    <span className="label">Tool Calls (Secondary):</span>
                    <strong>{behavioralAnalysis.behavioral_analysis.secondary_tool_call_count}</strong>
                  </div>
                </div>
                <div className="metric">
                  <span className="label">Behavioral Divergence Score:</span>
                  <strong>{(behavioralAnalysis.behavioral_analysis.behavioral_divergence_score * 100).toFixed(1)}%</strong>
                </div>
              </div>

              {behavioralAnalysis.behavioral_analysis.decision_divergences.length > 0 && (
                <div className="decision-divergences">
                  <h4>Decision Divergences</h4>
                  {behavioralAnalysis.behavioral_analysis.decision_divergences.map((diff, index) => (
                    <div key={index} className="decision-item">
                      <span className="index">Decision {diff.index}</span>
                      <span className="confidence-diff">
                        Confidence difference: {diff.confidence_difference.toFixed(2)}
                      </span>
                      <span className="description">{diff.description}</span>
                    </div>
                  ))}
                </div>
              )}

              {behavioralAnalysis.behavioral_analysis.tool_divergences.length > 0 && (
                <div className="tool-divergences">
                  <h4>Tool Usage Divergences</h4>
                  {behavioralAnalysis.behavioral_analysis.tool_divergences.map((diff, index) => (
                    <div key={index} className="tool-item">
                      <span className="tool-name">{diff.tool_name}</span>
                      <span className="description">{diff.description}</span>
                      {diff.tool_only_in_one && <span className="exclusive">Only in one session</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}