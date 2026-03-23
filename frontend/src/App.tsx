import { useEffect, useMemo, useState } from 'react'
import './App.css'
import { getReplay, getSessions, getTraceBundle } from './api/client'
import { DecisionTree } from './components/DecisionTree'
import { LLMViewer } from './components/LLMViewer'
import { SessionReplay } from './components/SessionReplay'
import { ToolInspector } from './components/ToolInspector'
import { TraceTimeline } from './components/TraceTimeline'
import type { ReplayResponse, Session, TraceBundle, TraceEvent } from './types'

type ReplayMode = 'full' | 'focus' | 'failure'

function formatNumber(value: number, digits = 0): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(value)
}

function formatEventHeadline(event: TraceEvent | null): string {
  if (!event) return 'Select an event'
  switch (event.event_type) {
    case 'decision':
      return event.chosen_action ?? event.name
    case 'tool_call':
    case 'tool_result':
      return event.tool_name ?? event.name
    case 'refusal':
      return event.reason ?? event.name
    case 'safety_check':
      return `${event.policy_name ?? 'Safety'} · ${event.outcome ?? 'pass'}`
    case 'policy_violation':
      return event.violation_type ?? event.name
    case 'behavior_alert':
      return event.alert_type ?? event.name
    case 'agent_turn':
      return `${event.speaker ?? event.agent_id ?? 'Agent'} turn`
    default:
      return event.name
  }
}

function EventDetail({ event, ranking }: { event: TraceEvent | null; ranking?: TraceBundle['analysis']['event_rankings'][number] }) {
  if (!event) {
    return (
      <section className="event-detail panel empty-panel">
        <p>Choose a trace node to inspect provenance, guardrails, and replay value.</p>
      </section>
    )
  }

  return (
    <section className="event-detail panel">
      <div className="detail-header">
        <div>
          <p className="eyebrow">Event Detail</p>
          <h2>{formatEventHeadline(event)}</h2>
        </div>
        <span className={`event-chip ${event.event_type}`}>{event.event_type.replaceAll('_', ' ')}</span>
      </div>

      <div className="detail-grid">
        <div>
          <span className="metric-label">Importance</span>
          <strong>{event.importance.toFixed(2)}</strong>
        </div>
        <div>
          <span className="metric-label">Timestamp</span>
          <strong>{new Date(event.timestamp).toLocaleTimeString()}</strong>
        </div>
        <div>
          <span className="metric-label">Parent</span>
          <strong>{event.parent_id ? event.parent_id.slice(0, 8) : 'root'}</strong>
        </div>
        <div>
          <span className="metric-label">Upstream</span>
          <strong>{event.upstream_event_ids.length}</strong>
        </div>
      </div>

      {ranking && (
        <div className="analysis-strip">
          <span>Severity {ranking.severity.toFixed(2)}</span>
          <span>Novelty {ranking.novelty.toFixed(2)}</span>
          <span>Recurrence {ranking.recurrence.toFixed(2)}</span>
          <span>Replay {ranking.replay_value.toFixed(2)}</span>
          <span>Composite {ranking.composite.toFixed(2)}</span>
        </div>
      )}

      <div className="detail-sections">
        {event.reasoning && (
          <div>
            <h3>Reasoning</h3>
            <p>{event.reasoning}</p>
          </div>
        )}
        {event.evidence?.length ? (
          <div>
            <h3>Evidence</h3>
            <pre>{JSON.stringify(event.evidence, null, 2)}</pre>
          </div>
        ) : null}
        {event.evidence_event_ids?.length ? (
          <div>
            <h3>Evidence Provenance</h3>
            <p>{event.evidence_event_ids.join(', ')}</p>
          </div>
        ) : null}
        {event.rationale && (
          <div>
            <h3>Guardrail Rationale</h3>
            <p>{event.rationale}</p>
          </div>
        )}
        {event.signal && (
          <div>
            <h3>Behavior Signal</h3>
            <p>{event.signal}</p>
          </div>
        )}
        <div>
          <h3>Payload</h3>
          <pre>{JSON.stringify(event, null, 2)}</pre>
        </div>
      </div>
    </section>
  )
}

function App() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [bundle, setBundle] = useState<TraceBundle | null>(null)
  const [replay, setReplay] = useState<ReplayResponse | null>(null)
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [replayMode, setReplayMode] = useState<ReplayMode>('full')
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [speed, setSpeed] = useState(1)
  const [breakpointEventTypes, setBreakpointEventTypes] = useState('error,refusal,policy_violation')
  const [breakpointToolNames, setBreakpointToolNames] = useState('')
  const [breakpointConfidenceBelow, setBreakpointConfidenceBelow] = useState('0.45')
  const [breakpointSafetyOutcomes, setBreakpointSafetyOutcomes] = useState('warn,block')

  useEffect(() => {
    let ignore = false
    async function loadSessions() {
      setLoading(true)
      setError(null)
      try {
        const response = await getSessions()
        if (ignore) return
        setSessions(response.sessions)
        setSelectedSessionId((current) => current ?? response.sessions[0]?.id ?? null)
      } catch (err) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to load sessions')
        }
      } finally {
        if (!ignore) setLoading(false)
      }
    }
    void loadSessions()
    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    if (!selectedSessionId) return
    const sessionId = selectedSessionId
    let ignore = false
    async function loadBundle() {
      setLoading(true)
      setError(null)
      try {
        const response = await getTraceBundle(sessionId)
        if (ignore) return
        setBundle(response)
        setSelectedEventId((current) => current ?? response.events[0]?.id ?? null)
      } catch (err) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to load trace bundle')
        }
      } finally {
        if (!ignore) setLoading(false)
      }
    }
    void loadBundle()
    return () => {
      ignore = true
    }
  }, [selectedSessionId])

  useEffect(() => {
    if (!selectedSessionId || !bundle) return
    const sessionId = selectedSessionId
    let ignore = false
    async function loadReplay() {
      try {
        const response = await getReplay(sessionId, {
          mode: replayMode,
          focusEventId: replayMode === 'focus' ? selectedEventId : null,
          breakpointEventTypes: breakpointEventTypes.split(',').map((item) => item.trim()).filter(Boolean),
          breakpointToolNames: breakpointToolNames.split(',').map((item) => item.trim()).filter(Boolean),
          breakpointConfidenceBelow: breakpointConfidenceBelow ? Number(breakpointConfidenceBelow) : null,
          breakpointSafetyOutcomes: breakpointSafetyOutcomes.split(',').map((item) => item.trim()).filter(Boolean),
        })
        if (ignore) return
        setReplay(response)
        setCurrentIndex(0)
        setIsPlaying(false)
      } catch (err) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to load replay')
        }
      }
    }
    void loadReplay()
    return () => {
      ignore = true
    }
  }, [
    selectedSessionId,
    bundle,
    replayMode,
    selectedEventId,
    breakpointEventTypes,
    breakpointToolNames,
    breakpointConfidenceBelow,
    breakpointSafetyOutcomes,
  ])

  const activeEvents = replay?.events ?? bundle?.events ?? []
  const selectedEvent = useMemo(
    () => activeEvents.find((event) => event.id === selectedEventId) ?? bundle?.events.find((event) => event.id === selectedEventId) ?? null,
    [activeEvents, bundle?.events, selectedEventId],
  )

  const currentReplayEvent = activeEvents[currentIndex] ?? null
  const activeEventForInspectors = currentReplayEvent ?? selectedEvent

  const llmRequest = useMemo(() => {
    if (!activeEventForInspectors) return null
    if (activeEventForInspectors.event_type === 'llm_request') return activeEventForInspectors
    if (activeEventForInspectors.event_type === 'llm_response') {
      return bundle?.events.find((event) => event.id === activeEventForInspectors.parent_id) ?? null
    }
    return null
  }, [activeEventForInspectors, bundle?.events])

  const llmResponse = useMemo(() => {
    if (!activeEventForInspectors) return null
    if (activeEventForInspectors.event_type === 'llm_response') return activeEventForInspectors
    if (activeEventForInspectors.event_type === 'llm_request') {
      return bundle?.events.find((event) => event.parent_id === activeEventForInspectors.id && event.event_type === 'llm_response') ?? null
    }
    return null
  }, [activeEventForInspectors, bundle?.events])

  const toolEvent = useMemo(() => {
    if (!activeEventForInspectors) return null
    if (activeEventForInspectors.event_type === 'tool_call' || activeEventForInspectors.event_type === 'tool_result') {
      return activeEventForInspectors
    }
    return null
  }, [activeEventForInspectors])

  const selectedRanking = useMemo(
    () => bundle?.analysis.event_rankings.find((ranking) => ranking.event_id === (activeEventForInspectors?.id ?? selectedEventId ?? '')),
    [bundle?.analysis.event_rankings, activeEventForInspectors?.id, selectedEventId],
  )

  const currentSession = sessions.find((session) => session.id === selectedSessionId) ?? bundle?.session ?? null

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Research-grade agent debugging</p>
          <h1>Edge Trace Console</h1>
          <p className="hero-copy">
            One coherent surface for safety-aware traces, provenance, adaptive replay, and failure clustering.
          </p>
        </div>
        <div className="hero-metrics">
          <div>
            <span className="metric-label">Sessions</span>
            <strong>{formatNumber(sessions.length)}</strong>
          </div>
          <div>
            <span className="metric-label">Failures Clustered</span>
            <strong>{formatNumber(bundle?.analysis.failure_clusters.length ?? 0)}</strong>
          </div>
          <div>
            <span className="metric-label">Replay Start</span>
            <strong>{formatNumber(replay?.start_index ?? 0)}</strong>
          </div>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <main className="workspace">
        <aside className="session-rail panel">
          <div className="rail-head">
            <p className="eyebrow">Sessions</p>
            <h2>Captured Runs</h2>
          </div>
          {loading && !sessions.length ? <p>Loading sessions…</p> : null}
          <div className="session-list">
            {sessions.map((session) => (
              <button
                key={session.id}
                type="button"
                className={`session-card ${selectedSessionId === session.id ? 'active' : ''}`}
                onClick={() => {
                  setSelectedSessionId(session.id)
                  setReplayMode('full')
                  setSelectedEventId(null)
                }}
              >
                <span className="session-name">{session.agent_name}</span>
                <span className="session-framework">{session.framework}</span>
                <span className="session-status">{session.status}</span>
              </button>
            ))}
          </div>

          {currentSession && (
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
            </div>
          )}
        </aside>

        <section className="main-stage">
          <section className="control-bar panel">
            <div className="control-copy">
              <p className="eyebrow">Replay</p>
              <h2>Checkpoint-aware playback</h2>
            </div>
            <div className="mode-switches">
              {(['full', 'focus', 'failure'] as ReplayMode[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className={replayMode === mode ? 'active' : ''}
                  onClick={() => setReplayMode(mode)}
                >
                  {mode}
                </button>
              ))}
            </div>
            <div className="breakpoint-grid">
              <label>
                Event breakpoints
                <input value={breakpointEventTypes} onChange={(event) => setBreakpointEventTypes(event.target.value)} />
              </label>
              <label>
                Tool breakpoints
                <input value={breakpointToolNames} onChange={(event) => setBreakpointToolNames(event.target.value)} />
              </label>
              <label>
                Confidence floor
                <input value={breakpointConfidenceBelow} onChange={(event) => setBreakpointConfidenceBelow(event.target.value)} />
              </label>
              <label>
                Safety outcomes
                <input value={breakpointSafetyOutcomes} onChange={(event) => setBreakpointSafetyOutcomes(event.target.value)} />
              </label>
            </div>
          </section>

          <section className="analysis-ribbon panel">
            <div>
              <p className="eyebrow">Adaptive Intelligence</p>
              <h2>Representative failures</h2>
            </div>
            <div className="cluster-list">
              {bundle?.analysis.failure_clusters.slice(0, 3).map((cluster) => (
                <button
                  key={cluster.fingerprint}
                  type="button"
                  className="cluster-pill"
                  onClick={() => {
                    setSelectedEventId(cluster.representative_event_id)
                    setReplayMode('focus')
                  }}
                >
                  <span>{cluster.fingerprint}</span>
                  <strong>{cluster.count}x</strong>
                </button>
              )) ?? <p>No clustered failures yet.</p>}
            </div>
          </section>

          <div className="trace-layout">
            <div className="panel timeline-panel">
              <TraceTimeline
                events={activeEvents}
                selectedEventId={selectedEventId}
                onSelectEvent={(eventId) => {
                  setSelectedEventId(eventId)
                  setCurrentIndex(Math.max(activeEvents.findIndex((event) => event.id === eventId), 0))
                }}
              />
            </div>
            <div className="panel tree-panel">
              <DecisionTree tree={bundle?.tree ?? null} selectedEventId={selectedEventId} onSelectEvent={setSelectedEventId} />
            </div>
          </div>

          <div className="replay-layout">
            <section className="panel replay-panel">
              <div className="panel-head">
                <p className="eyebrow">Replay Controls</p>
                <h2>Nearest checkpoint plus suffix</h2>
              </div>
              <SessionReplay
                events={activeEvents}
                currentIndex={currentIndex}
                isPlaying={isPlaying}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                onStepForward={() => setCurrentIndex((value) => Math.min(value + 1, Math.max(activeEvents.length - 1, 0)))}
                onStepBackward={() => setCurrentIndex((value) => Math.max(value - 1, 0))}
                onSeek={setCurrentIndex}
                speed={speed}
                onSpeedChange={setSpeed}
              />
              <div className="replay-summary">
                <span>Nearest checkpoint: {replay?.nearest_checkpoint?.sequence ?? 'none'}</span>
                <span>Breakpoints hit: {replay?.breakpoints.length ?? 0}</span>
                <span>Failures: {replay?.failure_event_ids.length ?? 0}</span>
              </div>
            </section>

            <section className="panel inspectors">
              <div className="inspectors-grid">
                <ToolInspector event={toolEvent} />
                <LLMViewer request={llmRequest} response={llmResponse} />
              </div>
            </section>
          </div>
        </section>

        <aside className="detail-rail">
          <EventDetail event={activeEventForInspectors} ranking={selectedRanking} />
          <section className="panel alerts-panel">
            <p className="eyebrow">Behavior Alerts</p>
            <h2>Live heuristics</h2>
            <div className="alert-list">
              {bundle?.analysis.behavior_alerts.length ? (
                bundle.analysis.behavior_alerts.map((alert) => (
                  <button
                    key={`${alert.alert_type}-${alert.event_id}`}
                    type="button"
                    className="alert-row"
                    onClick={() => setSelectedEventId(alert.event_id)}
                  >
                    <span>{alert.alert_type}</span>
                    <strong>{alert.severity}</strong>
                    <small>{alert.signal}</small>
                  </button>
                ))
              ) : (
                <p>No oscillation or loop alerts detected.</p>
              )}
            </div>
          </section>
        </aside>
      </main>
    </div>
  )
}

export default App
