import { useSessionStore } from '../stores/sessionStore'
import { EmptyState } from './EmptyState'
import CostPanel from './CostPanel'
import FixAnnotation from './FixAnnotation'
import { formatNumber } from '../utils/formatting'
import './SessionRail.css'

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
        {sessions.map((session) => (
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
            <span className="session-name">{session.agent_name}</span>
            <span className="session-framework">{session.framework}</span>
            <span className="session-status">{session.status}</span>
            <div className="session-card-metrics">
              <span>Replay {(session.replay_value ?? 0).toFixed(2)}</span>
              <span className={`retention-pill ${session.retention_tier ?? 'downsampled'}`}>
                {session.retention_tier ?? 'downsampled'}
              </span>
            </div>
          </button>
        ))}
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
