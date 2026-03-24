import type { FailureExplanation } from '../types'

interface FailureExplanationModalProps {
  isOpen: boolean
  onClose: () => void
  explanation: FailureExplanation | null
  onInspectCause: (eventId: string) => void
  onSeeAllFailures: () => void
  totalFailures: number
}

export function FailureExplanationModal({
  isOpen,
  onClose,
  explanation,
  onInspectCause,
  onSeeAllFailures,
  totalFailures,
}: FailureExplanationModalProps) {
  if (!isOpen || !explanation) return null

  const confidencePercent = Math.round(explanation.confidence * 100)

  return (
    <div className="failure-modal-overlay" onClick={onClose}>
      <div className="failure-modal" onClick={(e) => e.stopPropagation()}>
        <div className="failure-modal-header">
          <p className="eyebrow">Failure Analysis</p>
          <h2>{explanation.failure_headline}</h2>
          <span className="failure-mode-badge">{explanation.failure_mode.replaceAll('_', ' ')}</span>
        </div>

        <div className="failure-content">
          <div className="failure-section">
            <h3>What went wrong</h3>
            <p className="failure-symptom">{explanation.symptom}</p>
          </div>

          <div className="failure-section">
            <h3>Likely cause</h3>
            <p className="failure-cause">{explanation.likely_cause}</p>
            <div className="failure-confidence">
              <span className="metric-label">Confidence</span>
              <div className="failure-confidence-bar-container">
                <div
                  className="failure-confidence-bar"
                  style={{ width: `${confidencePercent}%` }}
                />
              </div>
              <span className="failure-confidence-value">{confidencePercent}%</span>
            </div>
          </div>

          {explanation.narrative && (
            <div className="failure-section failure-narrative">
              <h3>Full diagnosis</h3>
              <p>{explanation.narrative}</p>
            </div>
          )}
        </div>

        <div className="failure-modal-actions">
          {explanation.likely_cause_event_id && (
            <button
              type="button"
              className="failure-action-primary"
              onClick={() => {
                onInspectCause(explanation.likely_cause_event_id!)
                onClose()
              }}
            >
              <span className="failure-action-icon">&#x2192;</span>
              Inspect Cause
            </button>
          )}
          {totalFailures > 1 && (
            <button
              type="button"
              className="failure-action-secondary"
              onClick={() => {
                onSeeAllFailures()
                onClose()
              }}
            >
              See All Failures ({totalFailures})
            </button>
          )}
          <button type="button" className="failure-action-close" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
