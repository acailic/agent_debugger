import { memo, useState, useEffect } from 'react'
import type { SimilarFailure, TraceEvent } from '../types'
import { getSimilarFailures } from '../api/client'

interface SimilarFailuresPanelProps {
  sessionId: string | null
  failureEvent: TraceEvent | null
  onSelectSession: (sessionId: string) => void
  selectedSessionId: string | null
}

function getSimilarityColor(similarity: number): string {
  if (similarity >= 0.7) return 'var(--success)'
  if (similarity >= 0.5) return 'var(--warning)'
  return 'var(--olive)'
}

function getSimilarityLabel(similarity: number): string {
  if (similarity >= 0.7) return 'High'
  if (similarity >= 0.5) return 'Medium'
  return 'Low'
}

function getFailureModeColor(failureMode: string): string {
  if (failureMode.includes('loop') || failureMode.includes('behavior')) return 'var(--warning)'
  if (failureMode.includes('block') || failureMode.includes('violation')) return 'var(--danger)'
  if (failureMode.includes('error')) return 'var(--danger)'
  return 'var(--olive)'
}

export function SimilarFailuresPanel({
  sessionId,
  failureEvent,
  onSelectSession,
  selectedSessionId,
}: SimilarFailuresPanelProps) {
  const [similarFailures, setSimilarFailures] = useState<SimilarFailure[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!sessionId || !failureEvent) {
      setSimilarFailures([])
      setError(null)
      return
    }

    let ignore = false
    async function loadSimilarFailures() {
      setLoading(true)
      setError(null)
      try {
        const response = await getSimilarFailures({
          sessionId: sessionId!, // Non-null assertion: we checked above
          failureEventId: failureEvent!.id, // Non-null assertion: we checked above
          limit: 5,
        })
        if (!ignore) {
          setSimilarFailures(response.similar_failures)
        }
      } catch (err) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to load similar failures')
          setSimilarFailures([])
        }
      } finally {
        if (!ignore) setLoading(false)
      }
    }

    loadSimilarFailures()
    return () => {
      ignore = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, failureEvent?.id])

  // Don't show panel if no session selected or viewing a non-failure event
  if (!sessionId || !failureEvent) {
    return null
  }

  // Check if the current event is actually a failure
  const isFailureEvent = [
    'error',
    'refusal',
    'policy_violation',
    'behavior_alert',
    'safety_check',
  ].includes(failureEvent.event_type)

  if (!isFailureEvent && !failureEvent.error) {
    return null
  }

  return (
    <section className="panel similar-failures-panel">
      <div className="panel-head">
        <p className="eyebrow">Similar Failures</p>
        <h2>Historically similar failures</h2>
      </div>

      {loading && (
        <div className="loading-state">
          <div className="loading-spinner" />
          <p>Searching for similar failures...</p>
        </div>
      )}

      {error && (
        <div className="error-state">
          <p>{error}</p>
        </div>
      )}

      {!loading && !error && similarFailures.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">🔍</div>
          <h3>No similar failures found</h3>
          <p>This type of failure hasn't been seen in previous sessions.</p>
          <small>Similar failures will appear here when patterns are detected</small>
        </div>
      )}

      {!loading && !error && similarFailures.length > 0 && (
        <div className="similar-failures-list">
          {similarFailures.map((failure) => {
            const similarityColor = getSimilarityColor(failure.similarity)
            const similarityLabel = getSimilarityLabel(failure.similarity)
            const failureModeColor = getFailureModeColor(failure.failure_mode)
            const isActive = selectedSessionId === failure.session_id

            return (
              <button
                key={failure.session_id}
                type="button"
                className={`similar-failure-card ${isActive ? 'active' : ''}`}
                onClick={() => onSelectSession(failure.session_id)}
                aria-label={`Similar failure in session ${failure.session_id}, ${failure.agent_name}, similarity ${failure.similarity.toFixed(2)}`}
              >
                <div className="failure-header">
                  <div className="failure-meta">
                    <span className="failure-agent">{failure.agent_name}</span>
                    <span className="failure-framework">{failure.framework}</span>
                  </div>
                  <div
                    className="similarity-badge"
                    style={{ color: similarityColor }}
                  >
                    <span className="similarity-label">{similarityLabel} match</span>
                    <span className="similarity-score">{failure.similarity.toFixed(2)}</span>
                  </div>
                </div>

                <div className="failure-details">
                  <div className="failure-detail-row">
                    <span className="detail-label">Type</span>
                    <span className="detail-value">{failure.failure_type.replaceAll('_', ' ')}</span>
                  </div>
                  <div className="failure-detail-row">
                    <span className="detail-label">Mode</span>
                    <span
                      className="detail-value failure-mode"
                      style={{ color: failureModeColor }}
                    >
                      {failure.failure_mode.replaceAll('_', ' ')}
                    </span>
                  </div>
                  <div className="failure-detail-row">
                    <span className="detail-label">When</span>
                    <span className="detail-value">
                      {new Date(failure.started_at).toLocaleDateString()} {new Date(failure.started_at).toLocaleTimeString()}
                    </span>
                  </div>
                </div>

                <div className="failure-root-cause">
                  <span className="root-cause-label">Root cause</span>
                  <p className="root-cause-text">{failure.root_cause}</p>
                </div>

                {failure.fix_note && (
                  <div className="failure-fix-note">
                    <span className="fix-note-label">Fix note</span>
                    <p className="fix-note-text">{failure.fix_note}</p>
                  </div>
                )}

                <span className="view-session-link">View session</span>
              </button>
            )
          })}
        </div>
      )}

      {!loading && !error && similarFailures.length > 0 && (
        <div className="similar-failures-footer">
          <small>
            Showing {similarFailures.length} most similar failures based on failure type, error patterns, and context
          </small>
        </div>
      )}
    </section>
  )
}

// Custom comparison for SimilarFailuresPanel
function arePropsEqual(
  prevProps: Readonly<SimilarFailuresPanelProps>,
  nextProps: Readonly<SimilarFailuresPanelProps>
): boolean {
  return (
    prevProps.sessionId === nextProps.sessionId &&
    prevProps.failureEvent?.id === nextProps.failureEvent?.id &&
    prevProps.selectedSessionId === nextProps.selectedSessionId
  )
}

export const SimilarFailuresPanelMemo = memo(SimilarFailuresPanel, arePropsEqual)
