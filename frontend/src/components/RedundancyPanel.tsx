import { getRedundancyAnalysis } from '../api/client'
import type { RedundancyAnalysisResponse } from '../types'
import { useState, useEffect } from 'react'
import './RedundancyPanel.css'

interface RedundancyPanelProps {
  sessionId: string
}

export function RedundancyPanel({ sessionId }: RedundancyPanelProps) {
  const [data, setData] = useState<RedundancyAnalysisResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function loadRedundancyData() {
      try {
        setLoading(true)
        setError(null)
        const response = await getRedundancyAnalysis(sessionId)
        setData(response)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load redundancy analysis')
        console.error('Error loading redundancy analysis:', err)
      } finally {
        setLoading(false)
      }
    }

    loadRedundancyData()
  }, [sessionId])

  if (loading) {
    return (
      <div className="redundancy-panel panel panel--secondary">
        <div className="panel-header">
          <h3>Step Redundancy Analysis</h3>
        </div>
        <div className="panel-body">
          <div className="loading-skeleton">Loading redundancy analysis...</div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="redundancy-panel panel panel--secondary">
        <div className="panel-header">
          <h3>Step Redundancy Analysis</h3>
        </div>
        <div className="panel-body">
          <div className="error-message">{error}</div>
        </div>
      </div>
    )
  }

  if (!data) {
    return null
  }

  const { scores, summary } = data

  // Group scores by contribution type
  const redundantSteps = scores.filter(s => s.contribution === 'redundant')
  const harmfulSteps = scores.filter(s => s.contribution === 'harmful')

  return (
    <div className="redundancy-panel panel panel--secondary">
      <div className="panel-header">
        <h3>Step Redundancy Analysis</h3>
      </div>
      <div className="panel-body">
        {/* Summary Statistics */}
        <div className="redundancy-summary">
          <div className="summary-card">
            <span className="summary-label">Total Steps</span>
            <strong className="summary-value">{summary.total_steps}</strong>
          </div>
          <div className="summary-card essential">
            <span className="summary-label">Essential</span>
            <strong className="summary-value">{summary.essential_count}</strong>
          </div>
          <div className="summary-card redundant">
            <span className="summary-label">Redundant</span>
            <strong className="summary-value">{summary.redundant_count}</strong>
          </div>
          <div className="summary-card harmful">
            <span className="summary-label">Harmful</span>
            <strong className="summary-value">{summary.harmful_count}</strong>
          </div>
          <div className="summary-card unknown">
            <span className="summary-label">Unknown</span>
            <strong className="summary-value">{summary.unknown_count}</strong>
          </div>
          <div className="summary-card">
            <span className="summary-label">Redundancy Rate</span>
            <strong className="summary-value">{(summary.redundancy_rate * 100).toFixed(1)}%</strong>
          </div>
          <div className="summary-card">
            <span className="summary-label">Avg Score</span>
            <strong className="summary-value">{summary.avg_score.toFixed(2)}</strong>
          </div>
        </div>

        {/* Detailed Scores Table */}
        <div className="redundancy-scores">
          <h4>Step-by-Step Analysis</h4>
          {scores.length === 0 ? (
            <p className="empty-state">No steps to analyze</p>
          ) : (
            <table className="scores-table">
              <thead>
                <tr>
                  <th>Step ID</th>
                  <th>Score</th>
                  <th>Contribution</th>
                  <th>Reasoning</th>
                </tr>
              </thead>
              <tbody>
                {scores.map((score) => (
                  <tr key={score.step_id} className={`score-row score-row--${score.contribution}`}>
                    <td className="step-id">{score.step_id.slice(0, 8)}...</td>
                    <td className="score-value">{score.score.toFixed(2)}</td>
                    <td className="contribution-badge">
                      <span className={`badge badge--${score.contribution}`}>
                        {score.contribution}
                      </span>
                    </td>
                    <td className="reasoning">{score.reasoning}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Key Insights */}
        {redundantSteps.length > 0 && (
          <div className="redundancy-insights">
            <h4>Redundancy Insights</h4>
            <ul>
              <li>{redundantSteps.length} steps identified as redundant ({(redundantSteps.length / summary.total_steps * 100).toFixed(1)}%)</li>
              <li>Potential cost savings from removing redundant steps</li>
              <li>Consider optimizing agent workflow to eliminate redundant operations</li>
            </ul>
          </div>
        )}

        {harmfulSteps.length > 0 && (
          <div className="redundancy-alerts">
            <h4>Harmful Steps Detected</h4>
            <ul>
              {harmfulSteps.map((step) => (
                <li key={step.step_id}>
                  <strong>Step {step.step_id.slice(0, 8)}...</strong>: {step.reasoning}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}