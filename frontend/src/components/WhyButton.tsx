import { useState } from 'react'
import { getAnalysis } from '../api/client'
import type { FailureCauseCandidate, FailureExplanation } from '../types'

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

function formatFailureMode(failureMode: string): string {
  return failureMode.replace(/_/g, ' ')
}

function CandidateButton({
  candidate,
  onSelectEvent,
}: {
  candidate: FailureCauseCandidate
  onSelectEvent: (eventId: string) => void
}) {
  return (
    <li>
      <button type="button" className="diagnosis-link" onClick={() => onSelectEvent(candidate.event_id)}>
        {candidate.headline}
      </button>
    </li>
  )
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
        setExplanation(null)
        setNoFailures(true)
        setStatus('loaded')
        return
      }
      setNoFailures(false)
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

  const confidencePercent = explanation ? Math.round(explanation.confidence * 100) : 0
  const topCandidate = explanation?.candidates[0] ?? null

  return (
    <div>
      <button
        type="button"
        className={`why-btn${status === 'loaded' ? ' active' : ''}`}
        disabled={status === 'loading'}
        onClick={status === 'idle' || status === 'error' ? handleFetch : undefined}
      >
        {status === 'loading' ? <span className="spinner" /> : 'Why Did It Fail?'}
      </button>

      {status === 'error' && errorInfo && (
        <div className="error-banner">
          {errorInfo.message}
          {errorInfo.isNetwork && (
            <button type="button" className="retry-link" onClick={handleFetch}>
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
            <strong>{explanation.failure_headline}</strong>
            <span>{confidencePercent}% confidence</span>
          </div>
          <p>{formatFailureMode(explanation.failure_mode)}</p>
          <p>{explanation.narrative}</p>
          <p>
            <strong>Likely cause:</strong> {explanation.likely_cause}
          </p>
          {explanation.candidates.length > 0 && (
            <ul className="diagnosis-list">
              {explanation.candidates.map((candidate) => (
                <CandidateButton key={candidate.event_id} candidate={candidate} onSelectEvent={onSelectEvent} />
              ))}
            </ul>
          )}
          <div className="diagnosis-actions">
            {explanation.likely_cause_event_id && (
              <button
                type="button"
                onClick={() => {
                  onSelectEvent(explanation.likely_cause_event_id!)
                  onFocusReplay(explanation.likely_cause_event_id!)
                }}
              >
                Inspect likely cause
              </button>
            )}
            <button type="button" onClick={() => onFocusReplay(explanation.next_inspection_event_id)}>
              Focus replay
            </button>
          </div>
          {topCandidate && (
            <div className="diagnosis-actions">
              <button type="button" onClick={() => onSelectEvent(topCandidate.event_id)}>
                Inspect top candidate
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
