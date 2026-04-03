import { useState } from 'react'
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

function WhyButtonInner({
  sessionId,
  onSelectEvent,
  onFocusReplay,
}: Omit<WhyButtonProps, 'hasFailures'>) {
  const [status, setStatus] = useState<Status>('idle')
  const [explanation, setExplanation] = useState<FailureExplanation | null>(null)
  const [noFailures, setNoFailures] = useState(false)
  const [errorInfo, setErrorInfo] = useState<ErrorInfo | null>(null)

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
      let message = 'Analysis unavailable.'
      let isNetwork = false

      if (err instanceof TypeError && err.message.includes('fetch')) {
        message = 'Network error. Check your connection and try again.'
        isNetwork = true
      } else if (err instanceof Error) {
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
          <div className="diagnosis-card__header">
            <strong>{explanation.label}</strong>
            <span>{confidencePercent}% confidence</span>
          </div>
          <p>{explanation.summary}</p>
          {explanation.likely_causes.length > 0 && (
            <ul className="diagnosis-list">
              {explanation.likely_causes.map((cause) => (
                <li key={cause}>{cause}</li>
              ))}
            </ul>
          )}
          {explanation.event_id && (
            <div className="diagnosis-actions">
              <button type="button" onClick={() => onSelectEvent(explanation.event_id!)}>
                Inspect event
              </button>
              <button type="button" onClick={() => onFocusReplay(explanation.event_id!)}>
                Focus replay
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function WhyButton({ hasFailures = true, ...props }: WhyButtonProps) {
  if (!hasFailures) return null
  return <WhyButtonInner key={props.sessionId} {...props} />
}
