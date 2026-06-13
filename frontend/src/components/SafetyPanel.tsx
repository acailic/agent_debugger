import { useEffect, useState } from 'react'
import { getSafetyAnalysis } from '../api/client'
import type { SafetyAnalysisResponse, SafetyDimension } from '../types'
import { logger } from '../utils/logger'

interface SafetyPanelProps {
  sessionId: string
}

export function SafetyPanel({ sessionId }: SafetyPanelProps) {
  const [safetyData, setSafetyData] = useState<SafetyAnalysisResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function loadSafetyData() {
      try {
        setLoading(true)
        setError(null)
        const data = await getSafetyAnalysis(sessionId)
        setSafetyData(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load safety analysis')
        logger.error('Failed to load safety analysis:', {component: 'SafetyPanel'}, err)
      } finally {
        setLoading(false)
      }
    }

    loadSafetyData()
  }, [sessionId])

  const getScoreColor = (score: number): string => {
    if (score >= 0.8) return 'var(--olive)'
    if (score >= 0.6) return 'oklch(0.58 0.22 25)'
    if (score >= 0.4) return 'var(--warning)'
    return 'var(--danger)'
  }

  const getSeverityColor = (severity: string): string => {
    switch (severity) {
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

  const getDimensionLabel = (dimension: SafetyDimension): string => {
    switch (dimension) {
      case 'goal_alignment':
        return 'Goal Alignment'
      case 'constraint_adherence':
        return 'Constraint Adherence'
      case 'reasoning_coherence':
        return 'Reasoning Coherence'
      default:
        return dimension
    }
  }

  if (loading) {
    return (
      <section className="panel safety-panel">
        <div className="panel-head">
          <p className="eyebrow">Safety</p>
          <h2>Safety Analysis</h2>
        </div>
        <div className="loading-state">Loading safety analysis...</div>
      </section>
    )
  }

  if (error) {
    return (
      <section className="panel safety-panel">
        <div className="panel-head">
          <p className="eyebrow">Safety</p>
          <h2>Safety Analysis</h2>
        </div>
        <div className="error-banner">{error}</div>
      </section>
    )
  }

  if (!safetyData) {
    return null
  }

  const { safety_report } = safetyData

  return (
    <section className="panel safety-panel">
      <div className="panel-head">
        <p className="eyebrow">Safety</p>
        <h2>Safety Analysis</h2>
      </div>

      {/* Overall Safety Score */}
      <div className="safety-overview">
        <div className="safety-gauge-container">
          <div
            className="safety-gauge"
            style={{
              background: `conic-gradient(${getScoreColor(safety_report.overall_score)} ${safety_report.overall_score * 360}deg, var(--muted) 0deg)`,
            }}
          >
            <div className="safety-gauge-inner">
              <span className="safety-score">{(safety_report.overall_score * 100).toFixed(0)}%</span>
            </div>
          </div>
          <div className="safety-status">
            <strong>{safety_report.is_safe ? 'Safe' : 'Unsafe'}</strong>
            <small>{safety_report.unsafe_steps} of {safety_report.total_steps} steps unsafe</small>
          </div>
        </div>
      </div>

      {/* Dimension Scores */}
      <div className="safety-dimensions">
        <h3>Safety Dimensions</h3>
        {Object.entries(safety_report.per_dimension_scores).map(([dim, score]) => (
          <div key={dim} className="dimension-row">
            <span className="dimension-label">{getDimensionLabel(dim as SafetyDimension)}</span>
            <div className="dimension-bar-container">
              <div
                className="dimension-bar"
                style={{
                  width: `${score * 100}%`,
                  backgroundColor: getScoreColor(score),
                }}
              />
            </div>
            <span className="dimension-score">{(score * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>

      {/* High Risk Dimensions */}
      {safety_report.high_risk_dimensions.length > 0 && (
        <div className="high-risk-dimensions">
          <h3>High Risk Dimensions</h3>
          <div className="risk-dimensions-list">
            {safety_report.high_risk_dimensions.map((dim) => (
              <div key={dim} className="risk-dimension-tag" style={{ backgroundColor: getSeverityColor('high') }}>
                {getDimensionLabel(dim)}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Safety Alerts */}
      {safety_report.alerts.length > 0 && (
        <div className="safety-alerts">
          <h3>Safety Alerts ({safety_report.alerts.length})</h3>
          {safety_report.alerts.map((alert, index) => (
            <div key={index} className="safety-alert">
              <div className="alert-header">
                <span className="alert-dimension">{getDimensionLabel(alert.dimension)}</span>
                <span
                  className="alert-severity"
                  style={{ backgroundColor: getSeverityColor(alert.severity) }}
                >
                  {alert.severity}
                </span>
              </div>
              <p className="alert-message">{alert.message}</p>
              <div className="alert-details">
                <small>Score: {alert.score.toFixed(2)} / Threshold: {alert.threshold.toFixed(2)}</small>
                {alert.mitigation_suggestion && (
                  <div className="alert-mitigation">
                    <strong>Mitigation:</strong> {alert.mitigation_suggestion}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* No Alerts State */}
      {safety_report.alerts.length === 0 && safety_report.is_safe && (
        <div className="no-alerts-state">
          <div className="success-indicator">✓</div>
          <h3>No Safety Issues Detected</h3>
          <p>This session passes all safety checks across all dimensions.</p>
        </div>
      )}

      {/* Per-Step Scores (expandable) */}
      {safety_report.per_step_scores.length > 0 && (
        <details className="step-scores-details">
          <summary>View Per-Step Safety Scores</summary>
          <div className="step-scores-list">
            {safety_report.per_step_scores.map((score, index) => (
              <div
                key={index}
                className={`step-score ${!score.is_safe ? 'step-score--unsafe' : ''}`}
              >
                <div className="step-score-header">
                  <span className="step-index">Step {score.step_index}</span>
                  <span className="step-dimension">{getDimensionLabel(score.dimension)}</span>
                  <span
                    className="step-score-value"
                    style={{ color: getScoreColor(score.score) }}
                  >
                    {(score.score * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="step-score-details">{score.details}</p>
                {!score.is_safe && (
                  <div className="step-warning">⚠️ Unsafe step detected</div>
                )}
              </div>
            ))}
          </div>
        </details>
      )}
    </section>
  )
}