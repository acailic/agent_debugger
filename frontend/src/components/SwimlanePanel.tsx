import { useState, useEffect, useMemo } from 'react'
import {
  getMultiAgentAnalysis
} from '../api/client'
import type {
  CoordinationSeverity,
  EmergentBehaviorType,
  MessageFlowType,
  MultiAgentAnalysisResponse
} from '../types'

interface SwimlanePanelProps {
  sessionId: string | null
}

type AnalysisTab = 'swimlane' | 'messages' | 'coordination' | 'emergent' | 'overview'

// Color helpers for message flows
function getFlowTypeColor(type: MessageFlowType): string {
  switch (type) {
    case 'request':
      return '#3b82f6' // blue-500
    case 'response':
      return '#10b981' // emerald-500
    case 'notification':
      return '#8b5cf6' // violet-500
    case 'synchronization':
      return '#06b6d4' // cyan-500
    case 'broadcast':
      return '#f59e0b' // amber-500
    case 'delegation':
      return '#ec4899' // pink-500
    default:
      return '#6b7280' // gray-500
  }
}

// Color helpers for coordination issues
function getSeverityColor(severity: CoordinationSeverity): string {
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

// Color helpers for emergent behaviors
function getBehaviorTypeColor(type: EmergentBehaviorType): string {
  switch (type) {
    case 'collaborative_problem_solving':
      return '#3b82f6' // blue-500
    case 'emergent_hierarchy':
      return '#8b5cf6' // violet-500
    case 'swarm_intelligence':
      return '#06b6d4' // cyan-500
    case 'adaptive_specialization':
      return '#10b981' // emerald-500
    case 'consensus_building':
      return '#f59e0b' // amber-500
    case 'emergent_workflow':
      return '#ec4899' // pink-500
    case 'self_organization':
      return '#6366f1' // indigo-500
    default:
      return '#6b7280' // gray-500
  }
}

export function SwimlanePanel({ sessionId }: SwimlanePanelProps) {
  const [activeTab, setActiveTab] = useState<AnalysisTab>('overview')
  const [multiAgentAnalysis, setMultiAgentAnalysis] = useState<MultiAgentAnalysisResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Load comprehensive analysis when session is selected
  useEffect(() => {
    if (!sessionId) {
      setMultiAgentAnalysis(null)
      setError(null)
      return
    }

    const loadAnalysis = async () => {
      setLoading(true)
      setError(null)
      try {
        const analysis = await getMultiAgentAnalysis(sessionId)
        setMultiAgentAnalysis(analysis)
      } catch (err) {
        console.error('Failed to load multi-agent analysis:', err)
        setError(err instanceof Error ? err.message : 'Failed to load multi-agent analysis')
        setMultiAgentAnalysis(null)
      } finally {
        setLoading(false)
      }
    }

    loadAnalysis()
  }, [sessionId])

  if (!sessionId) {
    return (
      <div className="swimlane-panel empty-panel">
        <p>Select a session to analyze multi-agent interactions.</p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="swimlane-panel loading-panel">
        <p>Loading multi-agent analysis...</p>
      </div>
    )
  }

  if (error && !multiAgentAnalysis) {
    return (
      <div className="swimlane-panel error-panel">
        <p className="error-message">Error: {error}</p>
      </div>
    )
  }

  const swimlaneData = multiAgentAnalysis?.swimlane_data
  const coordinationIssues = multiAgentAnalysis?.coordination_analysis.issues || []
  const emergentBehaviors = multiAgentAnalysis?.emergent_behavior_analysis.behaviors || []

  // Generate colors for agents
  const agentColors = useMemo(() => {
    const colors = [
      '#3b82f6', // blue-500
      '#10b981', // emerald-500
      '#8b5cf6', // violet-500
      '#f59e0b', // amber-500
      '#ec4899', // pink-500
      '#06b6d4', // cyan-500
      '#ef4444', // red-500
      '#6366f1', // indigo-500
    ]
    const laneMap = new Map<string, string>()
    let colorIndex = 0

    if (swimlaneData) {
      Object.keys(swimlaneData.lanes).forEach(agentId => {
        if (!laneMap.has(agentId)) {
          laneMap.set(agentId, colors[colorIndex % colors.length])
          colorIndex++
        }
      })
    }

    return laneMap
  }, [swimlaneData])

  return (
    <div className="swimlane-panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Multi-Agent Analysis</p>
          <h2>Swimlane Debugger</h2>
        </div>
      </div>

      {/* Analysis Tabs */}
      <div className="analysis-tabs">
        <button
          className={`tab-button ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`tab-button ${activeTab === 'swimlane' ? 'active' : ''}`}
          onClick={() => setActiveTab('swimlane')}
        >
          Swimlanes
        </button>
        <button
          className={`tab-button ${activeTab === 'messages' ? 'active' : ''}`}
          onClick={() => setActiveTab('messages')}
        >
          Messages
        </button>
        <button
          className={`tab-button ${activeTab === 'coordination' ? 'active' : ''}`}
          onClick={() => setActiveTab('coordination')}
        >
          Coordination
        </button>
        <button
          className={`tab-button ${activeTab === 'emergent' ? 'active' : ''}`}
          onClick={() => setActiveTab('emergent')}
        >
          Emergent
        </button>
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && multiAgentAnalysis && (
        <div className="overview-content">
          <h3>Session Overview</h3>
          <div className="session-info">
            <div className="info-item">
              <span className="label">Agent:</span>
              <strong>{multiAgentAnalysis.session_info.agent_name}</strong>
            </div>
            <div className="info-item">
              <span className="label">Framework:</span>
              <strong>{multiAgentAnalysis.session_info.framework}</strong>
            </div>
            <div className="info-item">
              <span className="label">Status:</span>
              <strong>{multiAgentAnalysis.session_info.status}</strong>
            </div>
          </div>

          {swimlaneData && (
            <>
              <h3>Multi-Agent Summary</h3>
              <div className="multi-agent-summary">
                <div className="summary-item">
                  <span className="label">Total Agents:</span>
                  <strong>{swimlaneData.agent_count}</strong>
                </div>
                <div className="summary-item">
                  <span className="label">Total Events:</span>
                  <strong>{swimlaneData.total_event_count}</strong>
                </div>
                <div className="summary-item">
                  <span className="label">Message Flows:</span>
                  <strong>{swimlaneData.message_flows.length}</strong>
                </div>
                <div className="summary-item">
                  <span className="label">Duration:</span>
                  <strong>{swimlaneData.duration_seconds.toFixed(2)}s</strong>
                </div>
              </div>

              <h3>Analysis Results</h3>
              <div className="analysis-results">
                <div className="result-item">
                  <span className="label">Coordination Issues:</span>
                  <strong className={coordinationIssues.length > 0 ? 'has-issues' : 'no-issues'}>
                    {coordinationIssues.length}
                  </strong>
                </div>
                <div className="result-item">
                  <span className="label">Emergent Behaviors:</span>
                  <strong className={emergentBehaviors.length > 0 ? 'has-behaviors' : 'no-behaviors'}>
                    {emergentBehaviors.length}
                  </strong>
                </div>
              </div>

              {coordinationIssues.length > 0 && (
                <div className="critical-issues">
                  <h4>Critical Issues</h4>
                  {coordinationIssues
                    .filter(issue => issue.severity === 'critical')
                    .slice(0, 3)
                    .map(issue => (
                      <div key={issue.issue_id} className="issue-item critical">
                        <span
                          className="severity-indicator"
                          style={{ backgroundColor: getSeverityColor(issue.severity) }}
                        />
                        <span className="description">{issue.description}</span>
                      </div>
                    ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Swimlane Tab */}
      {activeTab === 'swimlane' && swimlaneData && (
        <div className="swimlane-content">
          <h3>Agent Swimlanes</h3>
          <div className="swimlane-container">
            {Object.values(swimlaneData.lanes).map(lane => (
              <div key={lane.agent_id} className="swimlane-lane">
                <div className="lane-header">
                  <div
                    className="lane-color"
                    style={{ backgroundColor: agentColors.get(lane.agent_id) || '#3b82f6' }}
                  />
                  <div className="lane-info">
                    <strong>{lane.agent_name}</strong>
                    <span className="lane-events">{lane.event_count} events</span>
                    <span className="lane-duration">{lane.duration_seconds.toFixed(2)}s</span>
                  </div>
                </div>
                <div className="lane-events-bar">
                  <div
                    className="events-fill"
                    style={{
                      width: `${(lane.event_count / swimlaneData.total_event_count) * 100}%`,
                      backgroundColor: agentColors.get(lane.agent_id) || '#3b82f6'
                    }}
                  />
                </div>
              </div>
            ))}
          </div>

          {swimlaneData.message_flows.length > 0 && (
            <div className="message-flows-summary">
              <h4>Message Flows</h4>
              <p>{swimlaneData.message_flows.length} inter-agent communications detected</p>
            </div>
          )}
        </div>
      )}

      {/* Messages Tab */}
      {activeTab === 'messages' && swimlaneData && (
        <div className="messages-content">
          <h3>Inter-Agent Message Flows</h3>
          {swimlaneData.message_flows.length === 0 ? (
            <p className="empty-message">No message flows detected in this session.</p>
          ) : (
            <div className="message-flows-list">
              {swimlaneData.message_flows.map(flow => (
                <div key={flow.flow_id} className="message-flow-item">
                  <div className="flow-header">
                    <div className="flow-agents">
                      <span
                        className="agent-badge from"
                        style={{ backgroundColor: agentColors.get(flow.from_agent_id) || '#6b7280' }}
                      >
                        {swimlaneData.lanes[flow.from_agent_id]?.agent_name || flow.from_agent_id}
                      </span>
                      <span className="flow-arrow">→</span>
                      <span
                        className="agent-badge to"
                        style={{ backgroundColor: agentColors.get(flow.to_agent_id) || '#6b7280' }}
                      >
                        {swimlaneData.lanes[flow.to_agent_id]?.agent_name || flow.to_agent_id}
                      </span>
                    </div>
                    <span
                      className="flow-type-badge"
                      style={{ backgroundColor: getFlowTypeColor(flow.flow_type) }}
                    >
                      {flow.flow_type}
                    </span>
                  </div>
                  <p className="flow-description">{flow.description}</p>
                  {flow.timestamp && (
                    <small className="flow-timestamp">
                      {new Date(flow.timestamp).toLocaleTimeString()}
                    </small>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Coordination Tab */}
      {activeTab === 'coordination' && (
        <div className="coordination-content">
          <h3>Coordination Analysis</h3>
          {coordinationIssues.length === 0 ? (
            <p className="no-issues-message">No coordination issues detected. All agents are coordinating well.</p>
          ) : (
            <div className="coordination-issues">
              <div className="issues-summary">
                <div className="summary-item">
                  <span className="label">Total Issues:</span>
                  <strong>{coordinationIssues.length}</strong>
                </div>
                <div className="summary-item">
                  <span className="label">Critical:</span>
                  <strong className="critical-count">
                    {coordinationIssues.filter(i => i.severity === 'critical').length}
                  </strong>
                </div>
                <div className="summary-item">
                  <span className="label">High:</span>
                  <strong className="high-count">
                    {coordinationIssues.filter(i => i.severity === 'high').length}
                  </strong>
                </div>
              </div>

              <div className="issues-list">
                {coordinationIssues.map(issue => (
                  <div key={issue.issue_id} className="coordination-issue">
                    <div className="issue-header">
                      <span
                        className="severity-badge"
                        style={{ backgroundColor: getSeverityColor(issue.severity) }}
                      >
                        {issue.severity}
                      </span>
                      <span className="issue-type">{issue.issue_type.replace(/_/g, ' ')}</span>
                    </div>
                    <p className="issue-description">{issue.description}</p>
                    {issue.suggestion && (
                      <div className="issue-suggestion">
                        <strong>Suggestion:</strong> {issue.suggestion}
                      </div>
                    )}
                    <div className="issue-agents">
                      <strong>Involved agents:</strong>
                      <div className="agent-list">
                        {issue.involved_agents.map(agentId => (
                          <span
                            key={agentId}
                            className="agent-chip"
                            style={{ backgroundColor: agentColors.get(agentId) || '#6b7280' }}
                          >
                            {swimlaneData?.lanes[agentId]?.agent_name || agentId}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Emergent Tab */}
      {activeTab === 'emergent' && (
        <div className="emergent-content">
          <h3>Emergent Behaviors</h3>
          {emergentBehaviors.length === 0 ? (
            <p className="no-behaviors-message">No emergent behaviors detected. Agents are acting as designed.</p>
          ) : (
            <div className="emergent-behaviors">
              <div className="behaviors-summary">
                <div className="summary-item">
                  <span className="label">Total Behaviors:</span>
                  <strong>{emergentBehaviors.length}</strong>
                </div>
                <div className="summary-item">
                  <span className="label">High Confidence:</span>
                  <strong className="high-confidence-count">
                    {emergentBehaviors.filter(b => b.confidence >= 0.7).length}
                  </strong>
                </div>
                <div className="summary-item">
                  <span className="label">Avg Confidence:</span>
                  <strong>
                    {(emergentBehaviors.reduce((sum, b) => sum + b.confidence, 0) / emergentBehaviors.length).toFixed(2)}
                  </strong>
                </div>
              </div>

              <div className="behaviors-list">
                {emergentBehaviors.map(behavior => (
                  <div key={behavior.behavior_id} className="emergent-behavior">
                    <div className="behavior-header">
                      <span
                        className="behavior-type-badge"
                        style={{ backgroundColor: getBehaviorTypeColor(behavior.behavior_type) }}
                      >
                        {behavior.behavior_type.replace(/_/g, ' ')}
                      </span>
                      <span className="behavior-confidence">
                        {(behavior.confidence * 100).toFixed(0)}% confidence
                      </span>
                    </div>
                    <p className="behavior-description">{behavior.description}</p>
                    {behavior.pattern_description && (
                      <div className="behavior-pattern">
                        <strong>Pattern:</strong> {behavior.pattern_description}
                      </div>
                    )}
                    <div className="behavior-agents">
                      <strong>Involved agents:</strong>
                      <div className="agent-list">
                        {behavior.involved_agents.map(agentId => (
                          <span
                            key={agentId}
                            className="agent-chip"
                            style={{ backgroundColor: agentColors.get(agentId) || '#6b7280' }}
                          >
                            {swimlaneData?.lanes[agentId]?.agent_name || agentId}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}