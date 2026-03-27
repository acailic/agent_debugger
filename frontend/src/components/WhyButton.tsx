import { useState, useEffect } from 'react'
import { getAnalysis } from '../api/client'
import type { FailureExplanation } from '../types'

interface WhyButtonProps {
  sessionId: string
  onSelectEvent: (eventId: string) => void
  onFocusReplay: (eventId: string) => void
  hasFailures?: boolean
}

type Status = 'idle' | 'loading' | 'loaded' | 'error'

interface ErrorInfo {
  message: string
  isNetwork: boolean
}

export default function WhyButton({
  sessionId,
  onSelectEvent,
  onFocusReplay,
  hasFailures = true,
}: WhyButtonProps) {
  const [status, setStatus] = useState<Status>('idle')
  const [explanation, setExplanation] = useState<FailureExplanation | null>(null)
  const [noFailures, setNoFailures] = useState(false)
  const [errorInfo, setErrorInfo] = useState<ErrorInfo | null>(null)

  // Reset state when session changes
  useEffect(() => {
    setStatus('idle')
    setExplanation(null)
    setNoFailures(false)
    setErrorInfo(null)
  }, [sessionId])

  if (!hasFailures) return null

  const handleFetch = async () => {
    setStatus('loading')
    setErrorInfo(null)
    try {
      const result = await getAnalysis(sessionId)
      const explanations = result?.analysis?.failure_explanations ?? []
      if (explanations.length === 0) {
        setNoFailures(true)
        setStatus('loaded')
        return
      }
      setExplanation(explanations[0])
      setStatus('loaded')
    } catch (err) {
      // Extract meaningful error info
      let message = 'Analysis unavailable.'
      let isNetwork = false

      if (err instanceof TypeError && err.message.includes('fetch')) {
        message = 'Network error. Check your connection and try again.'
        isNetwork = true
      } else if (err instanceof Error) {
        // Try to extract status or message from API error
        const errStr = err.message.toLowerCase()
        if (errStr.includes('404') || errStr.includes('not found')) {
          message = 'Session not found or analysis not available.'
        } else if (errStr.includes('500') || errStr.includes('internal')) {
          message = 'Server error. The analysis service may be temporarily unavailable.'
        } else if (errStr.includes('timeout')) {
          message = 'Request timed out. Try again.'
          isNetwork = true
        } else {
          message = `Analysis failed: ${err.message}`
        }
      }

      setErrorInfo({ message, isNetwork })
      setStatus('error')
    }
  }

  const confidencePercent = explanation
    ? Math.round(explanation.confidence * 100)
    : 0

  return (
    <div>
      <button
        type="button"
        className={`why-btn${status === 'loaded' ? ' active' : ''}`}
        disabled={status === 'loading'}
        onClick={status === 'idle' || status === 'error' ? handleFetch : undefined}
      >
        {status === 'loading' ? (
          <span className="spinner" />
        ) : (
          'Why Did It Fail?'
        )}
      </button>

      {status === 'error' && errorInfo && (
        <div className="error-banner">
          {errorInfo.message}
          {errorInfo.isNetwork && (
            <button
              type="button"
              className="retry-link"
              onClick={handleFetch}
            >
              Retry
            </button>
          )}
        </div>
      )}

      {status === 'loaded' && noFailures && (
        <div className="diagnosis-card">
          <p>No failure patterns detected</p>
        </div>
      )}

      {status === 'loaded' && explanation && (
        <div className="diagnosis-card">
          {/* Failure mode + confidence */}
          <div className="candidate-head">
            <span className="failure-mode-badge">
              {explanation.failure_mode.replaceAll('_', ' ')}
            </span>
            <span className="diagnosis-badge">
              {confidencePercent}%
            </span>
          </div>

          {/* Symptom */}
          <h3>{explanation.failure_headline}</h3>
          <p>{explanation.symptom}</p>

          {/* Likely cause */}
          {explanation.likely_cause && (
            <p className="likely-cause">{explanation.likely_cause}</p>
          )}

          {/* Narrative */}
          {explanation.narrative && (
            <div className="failure-narrative">
              <p>{explanation.narrative}</p>
            </div>
          )}

          {/* Candidates */}
          {explanation.candidates.length > 0 && (
            <div className="candidate-list">
              {explanation.candidates.map((candidate) => (
                <button
                  key={candidate.event_id}
                  type="button"
                  className="candidate-card"
                  onClick={() => onSelectEvent(candidate.event_id)}
                >
                  <div className="candidate-head">
                    <span>{candidate.event_type.replaceAll('_', ' ')}</span>
                    <span className="diagnosis-badge">
                      {Math.round(candidate.score * 100)}%
                    </span>
                  </div>
                  <h4>{candidate.headline}</h4>
                  <p>{candidate.rationale}</p>
                </button>
              ))}
            </div>
          )}

          {/* Supporting event chain */}
          {explanation.supporting_event_ids.length > 0 && (
            <div className="analysis-strip">
              {explanation.supporting_event_ids.map((eventId) => (
                <button
                  key={eventId}
                  type="button"
                  className="reference-chip"
                  onClick={() => onSelectEvent(eventId)}
                >
                  <span>supporting event</span>
                  <strong>{eventId.slice(0, 8)}</strong>
                </button>
              ))}
            </div>
          )}

          {/* Inspect likely cause */}
          {explanation.likely_cause_event_id && (
            <div className="analysis-strip">
              <button
                type="button"
                className="reference-chip"
                onClick={() => {
                  onSelectEvent(explanation.likely_cause_event_id!)
                  onFocusReplay(explanation.likely_cause_event_id!)
                }}
              >
                <span>inspect likely cause</span>
                <strong>{explanation.likely_cause_event_id.slice(0, 8)}</strong>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
