import type { TraceEvent } from '../types'
import { memo } from 'react'

interface ConformalPredictionScoringPanelProps {
  events: TraceEvent[]
  selectedEventId: string | null
  onEventSelect: (eventId: string) => void
}

interface PredictionInterval {
  event_id: string
  timestamp: string
  decision_type: string
  prediction: string
  lower_bound: number
  upper_bound: number
  confidence_level: number
  actual_outcome: number | null
  coverage_status: 'covered' | 'missed' | 'pending'
  interval_width: number
  calibration_error: number
}

interface CalibrationMetrics {
  total_predictions: number
  coverage_rate: number
  target_coverage: number
  calibration_error: number
  avg_interval_width: number
  well_calibrated: boolean
  prediction_types: Record<string, number>
  coverage_by_type: Record<string, number>
}

interface RiskRegion {
  region_type: 'high_uncertainty' | 'systematic_bias' | 'calibration_drift'
  description: string
  affected_events: string[]
  severity: 'low' | 'medium' | 'high' | 'critical'
  recommendation: string
}

/**
 * Extract prediction intervals from events
 * This implements the Conformal Prediction logic from CROP
 */
function extractPredictionIntervals(events: TraceEvent[]): PredictionInterval[] {
  const intervals: PredictionInterval[] = []

  for (const event of events) {
    // Check if this event contains conformal prediction data
    const conformalData = event.data?.conformal_prediction as
      | { prediction: number; lower_bound: number; upper_bound: number; confidence_level: number }
      | undefined

    if (!conformalData) continue

    const actualOutcome = event.data?.actual_outcome as number | undefined

    intervals.push({
      event_id: event.id,
      timestamp: event.timestamp,
      decision_type: event.event_type,
      prediction: event.name,
      lower_bound: conformalData.lower_bound,
      upper_bound: conformalData.upper_bound,
      confidence_level: conformalData.confidence_level,
      actual_outcome: actualOutcome ?? null,
      coverage_status: actualOutcome !== undefined
        ? (actualOutcome >= conformalData.lower_bound && actualOutcome <= conformalData.upper_bound)
          ? 'covered'
          : 'missed'
        : 'pending',
      interval_width: conformalData.upper_bound - conformalData.lower_bound,
      calibration_error: 0, // Will be computed
    })
  }

  return intervals
}

/**
 * Calculate calibration metrics for conformal predictions
 */
function calculateCalibrationMetrics(
  intervals: PredictionInterval[]
): CalibrationMetrics {
  const completedPredictions = intervals.filter(p => p.coverage_status !== 'pending')
  const coveredPredictions = completedPredictions.filter(p => p.coverage_status === 'covered')

  const coverageRate = completedPredictions.length > 0
    ? coveredPredictions.length / completedPredictions.length
    : 0

  const targetCoverage = 0.9 // Default 90% coverage target
  const calibrationError = Math.abs(coverageRate - targetCoverage)

  const avgIntervalWidth = intervals.length > 0
    ? intervals.reduce((sum, p) => sum + p.interval_width, 0) / intervals.length
    : 0

  // Group by decision type
  const predictionTypes: Record<string, number> = {}
  const coverageByType: Record<string, number> = {}

  for (const interval of intervals) {
    predictionTypes[interval.decision_type] = (predictionTypes[interval.decision_type] || 0) + 1

    if (interval.coverage_status === 'covered') {
      coverageByType[interval.decision_type] = (coverageByType[interval.decision_type] || 0) + 1
    }
  }

  // Calculate coverage rates by type
  for (const type in coverageByType) {
    coverageByType[type] = coverageByType[type] / predictionTypes[type]
  }

  return {
    total_predictions: intervals.length,
    coverage_rate: coverageRate,
    target_coverage: targetCoverage,
    calibration_error: calibrationError,
    avg_interval_width: avgIntervalWidth,
    well_calibrated: calibrationError < 0.1, // Within 10% tolerance
    prediction_types: predictionTypes,
    coverage_by_type: coverageByType,
  }
}

/**
 * Identify risk regions in prediction quality
 */
function identifyRiskRegions(
  intervals: PredictionInterval[],
  metrics: CalibrationMetrics
): RiskRegion[] {
  const risks: RiskRegion[] = []

  // High uncertainty detection
  const highUncertaintyEvents = intervals
    .filter(p => p.interval_width > metrics.avg_interval_width * 2)
    .map(p => p.event_id)

  if (highUncertaintyEvents.length > 0) {
    risks.push({
      region_type: 'high_uncertainty',
      description: `${highUncertaintyEvents.length} predictions with unusually wide intervals`,
      affected_events: highUncertaintyEvents,
      severity: highUncertaintyEvents.length > 5 ? 'high' : 'medium',
      recommendation: 'Review model calibration for high-uncertainty predictions',
    })
  }

  // Systematic bias detection
  const missedPredictions = intervals.filter(p => p.coverage_status === 'missed')
  if (missedPredictions.length > intervals.length * 0.2) {
    risks.push({
      region_type: 'systematic_bias',
      description: `Coverage rate ${(metrics.coverage_rate * 100).toFixed(1)}% below target ${(metrics.target_coverage * 100)}%`,
      affected_events: missedPredictions.map(p => p.event_id),
      severity: metrics.coverage_rate < 0.7 ? 'critical' : 'high',
      recommendation: 'Recalibrate prediction intervals or adjust coverage target',
    })
  }

  // Calibration drift detection
  const recentIntervals = intervals.slice(-10)
  const recentCoverage = recentIntervals.filter(p => p.coverage_status === 'covered').length /
    recentIntervals.filter(p => p.coverage_status !== 'pending').length

  if (recentCoverage < metrics.coverage_rate - 0.1 && recentIntervals.length >= 5) {
    risks.push({
      region_type: 'calibration_drift',
      description: `Recent coverage ${(recentCoverage * 100).toFixed(1)}% significantly lower than overall ${(metrics.coverage_rate * 100).toFixed(1)}%`,
      affected_events: recentIntervals.map(p => p.event_id),
      severity: 'medium',
      recommendation: 'Investigate temporal calibration drift in recent predictions',
    })
  }

  return risks
}

function getCoverageStatusColor(status: 'covered' | 'missed' | 'pending'): string {
  if (status === 'covered') return 'var(--olive)'
  if (status === 'missed') return 'var(--danger)'
  return 'var(--muted)'
}

function getSeverityColor(severity: 'low' | 'medium' | 'high' | 'critical'): string {
  if (severity === 'critical') return 'var(--danger)'
  if (severity === 'high') return 'var(--warning)'
  if (severity === 'medium') return 'var(--muted-foreground)'
  return 'var(--olive)'
}

function PredictionIntervalCard({
  interval,
  selectedEventId,
  onEventSelect
}: {
  interval: PredictionInterval
  selectedEventId: string | null
  onEventSelect: (eventId: string) => void
}) {
  const statusColor = getCoverageStatusColor(interval.coverage_status)

  return (
    <button
      type="button"
      className={`prediction-interval-card ${selectedEventId === interval.event_id ? 'selected' : ''} ${interval.coverage_status}`}
      onClick={() => onEventSelect(interval.event_id)}
      aria-label={`Prediction interval for ${interval.prediction}, range: [${interval.lower_bound}, ${interval.upper_bound}], coverage: ${interval.coverage_status}`}
    >
      <div className="interval-header">
        <span className="interval-type">{interval.decision_type}</span>
        <span className="interval-prediction">{interval.prediction}</span>
        <span
          className="interval-status"
          style={{ color: statusColor }}
        >
          {interval.coverage_status === 'covered' && '✓ Covered'}
          {interval.coverage_status === 'missed' && '✗ Missed'}
          {interval.coverage_status === 'pending' && '⏳ Pending'}
        </span>
      </div>

      <div className="interval-values">
        <div className="interval-range">
          <span className="range-label">Interval:</span>
          <span className="range-bounds">
            [{interval.lower_bound.toFixed(2)}, {interval.upper_bound.toFixed(2)}]
          </span>
          <span className="range-width">
            Width: {interval.interval_width.toFixed(2)}
          </span>
        </div>

        <div className="interval-confidence">
          <span className="confidence-label">Confidence:</span>
          <span className="confidence-level">
            {(interval.confidence_level * 100).toFixed(0)}%
          </span>
        </div>

        {interval.actual_outcome !== null && (
          <div className="interval-outcome">
            <span className="outcome-label">Actual:</span>
            <span className="outcome-value">
              {interval.actual_outcome.toFixed(2)}
            </span>
            <span className="outcome-status">
              {interval.coverage_status === 'covered' ? '✓' : '✗'}
            </span>
          </div>
        )}
      </div>
    </button>
  )
}

function CalibrationMetricsCard({ metrics }: { metrics: CalibrationMetrics }) {
  return (
    <div className="calibration-metrics-card">
      <h4>Calibration Metrics</h4>
      <div className="metrics-grid">
        <div className="metric-item">
          <span className="metric-label">Total Predictions</span>
          <strong>{metrics.total_predictions}</strong>
        </div>
        <div className="metric-item">
          <span className="metric-label">Coverage Rate</span>
          <strong
            className={metrics.well_calibrated ? 'good' : 'poor'}
            style={{ color: metrics.well_calibrated ? 'var(--olive)' : 'var(--danger)' }}
          >
            {(metrics.coverage_rate * 100).toFixed(1)}%
          </strong>
        </div>
        <div className="metric-item">
          <span className="metric-label">Target Coverage</span>
          <strong>{(metrics.target_coverage * 100).toFixed(0)}%</strong>
        </div>
        <div className="metric-item">
          <span className="metric-label">Calibration Error</span>
          <strong
            className={metrics.calibration_error < 0.1 ? 'good' : 'poor'}
            style={{ color: metrics.calibration_error < 0.1 ? 'var(--olive)' : 'var(--danger)' }}
          >
            {(metrics.calibration_error * 100).toFixed(1)}%
          </strong>
        </div>
        <div className="metric-item">
          <span className="metric-label">Avg Interval Width</span>
          <strong>{metrics.avg_interval_width.toFixed(2)}</strong>
        </div>
        <div className="metric-item">
          <span className="metric-label">Calibration Status</span>
          <strong style={{ color: metrics.well_calibrated ? 'var(--olive)' : 'var(--warning)' }}>
            {metrics.well_calibrated ? 'Well Calibrated' : 'Poorly Calibrated'}
          </strong>
        </div>
      </div>

      <div className="coverage-by-type">
        <h5>Coverage by Type</h5>
        <div className="type-coverage-grid">
          {Object.entries(metrics.coverage_by_type).map(([type, coverage]) => (
            <div key={type} className="type-coverage-item">
              <span className="type-name">{type}</span>
              <strong>{(coverage * 100).toFixed(1)}%</strong>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function RiskRegionCard({ risk }: { risk: RiskRegion }) {
  const severityColor = getSeverityColor(risk.severity)

  return (
    <div className="risk-region-card">
      <div className="risk-header">
        <span className="risk-type">{risk.region_type}</span>
        <span
          className="risk-severity"
          style={{ color: severityColor }}
        >
          {risk.severity.toUpperCase()}
        </span>
      </div>
      <p className="risk-description">{risk.description}</p>
      <div className="risk-metrics">
        <span className="affected-count">{risk.affected_events.length} events affected</span>
      </div>
      <p className="risk-recommendation">
        <small>Recommendation: {risk.recommendation}</small>
      </p>
    </div>
  )
}

export function ConformalPredictionScoringPanel({
  events,
  selectedEventId,
  onEventSelect,
}: ConformalPredictionScoringPanelProps) {
  const predictionIntervals = extractPredictionIntervals(events)
  const calibrationMetrics = calculateCalibrationMetrics(predictionIntervals)
  const riskRegions = identifyRiskRegions(predictionIntervals, calibrationMetrics)

  if (predictionIntervals.length === 0) {
    return (
      <section className="panel conformal-prediction-panel">
        <div className="panel-head">
          <p className="eyebrow">Uncertainty Quantification</p>
          <h2>Conformal Prediction Scoring</h2>
        </div>
        <div className="empty-state">
          <div className="empty-state-icon">📊</div>
          <h3>No prediction intervals available</h3>
          <p>Conformal prediction scoring provides rigorous uncertainty quantification with calibrated confidence intervals.</p>
          <small>Prediction intervals will appear here when conformal predictions are made</small>
        </div>
      </section>
    )
  }

  return (
    <section className="panel conformal-prediction-panel">
      <div className="panel-head">
        <p className="eyebrow">Uncertainty Quantification</p>
        <h2>Conformal Prediction Scoring ({predictionIntervals.length})</h2>
      </div>

      <div className="conformal-prediction-content">
        <CalibrationMetricsCard metrics={calibrationMetrics} />

        {riskRegions.length > 0 && (
          <div className="risk-regions">
            <h3>Risk Regions</h3>
            <div className="risk-regions-list">
              {riskRegions.map((risk, idx) => (
                <RiskRegionCard key={idx} risk={risk} />
              ))}
            </div>
          </div>
        )}

        <div className="prediction-intervals">
          <h3>Prediction Intervals</h3>
          <div className="intervals-list">
            {predictionIntervals.map(interval => (
              <PredictionIntervalCard
                key={interval.event_id}
                interval={interval}
                selectedEventId={selectedEventId}
                onEventSelect={onEventSelect}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

// Custom comparison for ConformalPredictionScoringPanel
function arePropsEqual(
  prevProps: Readonly<ConformalPredictionScoringPanelProps>,
  nextProps: Readonly<ConformalPredictionScoringPanelProps>
): boolean {
  return (
    prevProps.events === nextProps.events &&
    prevProps.selectedEventId === nextProps.selectedEventId
  )
}

export const ConformalPredictionScoringPanelMemo = memo(ConformalPredictionScoringPanel, arePropsEqual)