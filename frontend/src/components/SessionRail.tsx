import { useSessionStore } from '../stores/sessionStore'
import { EmptyState } from './EmptyState'
import CostPanel from './CostPanel'
import FixAnnotation from './FixAnnotation'
import { formatNumber } from '../utils/formatting'
import { memo, useMemo } from 'react'
import './SessionRail.css'
import type { Session } from '../types'

// Compute health score based on session metrics
function computeHealthScore(session: Session, bundle?: { analysis: { session_summary: { failure_count: number; behavior_alert_count: number } } }): number {
  const failureCount = session.errors ?? 0
  const alertCount = bundle?.analysis.session_summary.behavior_alert_count ?? session.behavior_alert_count ?? 0
  const replayValue = session.replay_value ?? 0

  // Base score starts at 100
  let score = 100

  // Penalize failures (10 points each)
  score -= failureCount * 10

  // Penalize behavior alerts (5 points each)
  score -= alertCount * 5

  // Bonus for high replay value (up to 10 points)
  score += Math.min(replayValue * 2, 10)

  // Bonus for completed sessions (5 points)
  if (session.status === 'completed') {
    score += 5
  }

  // Penalty for error status (20 points)
  if (session.status === 'error') {
    score -= 20
  }

  return Math.max(0, Math.min(100, score))
}

function getHealthGrade(score: number): { grade: string; color: string; label: string } {
  if (score >= 90) return { grade: 'A', color: '#10b981', label: 'Excellent' }
  if (score >= 80) return { grade: 'B', color: '#22c55e', label: 'Good' }
  if (score >= 70) return { grade: 'C', color: '#f59e0b', label: 'Fair' }
  if (score >= 60) return { grade: 'D', color: '#f97316', label: 'Poor' }
  return { grade: 'F', color: '#ef4444', label: 'Critical' }
}

export function SessionRail() {
  const sessions = useSessionStore((state) => state.sessions)
  const selectedSessionId = useSessionStore((state) => state.selectedSessionId)
  const bundle = useSessionStore((state) => state.bundle)
  const loading = useSessionStore((state) => state.loading)
  const sessionSortMode = useSessionStore((state) => state.sessionSortMode)
  const setSecondarySessionId = useSessionStore((state) => state.setSecondarySessionId)
  const setSelectedSessionId = useSessionStore((state) => state.setSelectedSessionId)
  const setSessionSortMode = useSessionStore((state) => state.setSessionSortMode)
  const setReplayMode = useSessionStore((state) => state.setReplayMode)
  const setSelectedEventId = useSessionStore((state) => state.setSelectedEventId)

  const currentSession = sessions.find((session) => session.id === selectedSessionId) ?? bundle?.session ?? null

  // Memoize health scores for all sessions
  const healthScores = useMemo(() => {
    const scores = new Map<string, number>()
    sessions.forEach((session) => {
      const sessionBundle = session.id === selectedSessionId && bundle ? bundle : undefined
      scores.set(session.id, computeHealthScore(session, sessionBundle))
    })
    return scores
  }, [bundle, sessions, selectedSessionId])

  return (
    <aside className="session-rail panel panel--secondary">
      <div className="rail-head">
        <p className="eyebrow">Sessions</p>
        <h2>Captured Runs</h2>
      </div>
      <div className="mode-switches session-sort-switches">
        {(['replay_value', 'started_at'] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            className={sessionSortMode === mode ? 'active' : ''}
            onClick={() => setSessionSortMode(mode)}
          >
            {mode === 'replay_value' ? 'Top replay' : 'Recent'}
          </button>
        ))}
      </div>
      {loading && !sessions.length ? (
        <div className="session-skeleton" aria-label="Loading sessions">
          <span></span>
          <span></span>
          <span></span>
        </div>
      ) : null}
      {!loading && !sessions.length ? (
        <EmptyState
          icon="&#128269;"
          title="No sessions yet"
          description="Capture your first agent run to start debugging."
          steps={[
            { label: 'Install the SDK', detail: 'pip install peaky-peek' },
            { label: 'Add @trace decorator', detail: 'Wrap your agent function' },
            { label: 'Run your agent', detail: 'Traces appear here automatically' },
          ]}
        />
      ) : null}
      <div className="session-list">
        {sessions.map((session) => {
          const healthScore = healthScores.get(session.id) ?? 100
          const healthGrade = getHealthGrade(healthScore)
          return (
            <button
              key={session.id}
              type="button"
              className={`session-card ${selectedSessionId === session.id ? 'active' : ''}`}
              onClick={() => {
                setSelectedSessionId(session.id)
                const currentSecondaryId = useSessionStore.getState().secondarySessionId
                setSecondarySessionId(currentSecondaryId === session.id ? null : currentSecondaryId)
                setReplayMode('full')
                setSelectedEventId(null)
              }}
            >
              <div className="session-card-header">
                <span className="session-name">{session.agent_name}</span>
                <div className="session-header-badges">
                  <span
                    className="health-grade-badge"
                    style={{ backgroundColor: healthGrade.color }}
                    title={`Health Score: ${healthScore.toFixed(0)}/100 - ${healthGrade.label}`}
                    role="status"
                    aria-label={`Health: ${healthGrade.grade} - ${healthGrade.label}`}
                  >
                    {healthGrade.grade}
                  </span>
                  <span className={`session-status-dot ${session.status === 'error' ? 'error' : session.status === 'completed' ? 'success' : 'pending'}`} />
                </div>
              </div>
              <span className="session-framework">{session.framework}</span>
              <span className="session-status">{session.status}</span>
              <div className="session-card-metrics">
                <span className="replay-value-badge">Replay {(session.replay_value ?? 0).toFixed(2)}</span>
                <span className={`retention-pill ${session.retention_tier ?? 'downsampled'}`}>
                  {session.retention_tier ?? 'downsampled'}
                </span>
                <span className="health-score-badge" title={`Health: ${healthScore.toFixed(0)}/100`}>
                  {healthScore.toFixed(0)}
                </span>
              </div>
            </button>
          )
        })}
      </div>

      {currentSession && (
        <>
          <div className="session-stats">
            <div>
              <span className="metric-label">LLM calls</span>
              <strong>{formatNumber(currentSession.llm_calls)}</strong>
            </div>
            <div>
              <span className="metric-label">Tool calls</span>
              <strong>{formatNumber(currentSession.tool_calls)}</strong>
            </div>
            <div>
              <span className="metric-label">Errors</span>
              <strong>{formatNumber(currentSession.errors)}</strong>
            </div>
            <div>
              <span className="metric-label">Cost</span>
              <strong>${(currentSession.total_cost_usd ?? 0).toFixed(4)}</strong>
            </div>
            <div>
              <span className="metric-label">Retention</span>
              <strong>{bundle?.analysis.retention_tier ?? currentSession.retention_tier ?? 'downsampled'}</strong>
            </div>
            <div>
              <span className="metric-label">Replay value</span>
              <strong>{(bundle?.analysis.session_replay_value ?? currentSession.replay_value ?? 0).toFixed(2)}</strong>
            </div>
          </div>
          <CostPanel sessionId={currentSession.id} />
          <FixAnnotation sessionId={currentSession.id} existingNote={currentSession.fix_note ?? null} />
        </>
      )}
    </aside>
  )
}

// SessionRail already uses granular store selectors internally
// No custom comparison needed - component handles its own subscriptions
export const SessionRailMemo = memo(SessionRail)
