import { useEffect, useMemo, useState } from 'react'
import './App.css'
import { createEventSource, getLiveSummary, getReplay, getSessions, getTraceBundle, searchTraces } from './api/client'
import { ConversationPanel } from './components/ConversationPanel'
import { DecisionTree } from './components/DecisionTree'
import { LLMViewer } from './components/LLMViewer'
import { LiveSummaryPanel } from './components/LiveSummaryPanel'
import { SessionComparisonPanel } from './components/SessionComparisonPanel'
import { SessionReplay } from './components/SessionReplay'
import { ToolInspector } from './components/ToolInspector'
import { TraceTimeline } from './components/TraceTimeline'
import type { EventType, LiveSummary, ReplayResponse, Session, TraceBundle, TraceEvent, TraceSearchResponse } from './types'

type ReplayMode = 'full' | 'focus' | 'failure'
type SessionSortMode = 'started_at' | 'replay_value'
type SearchScope = 'current' | 'all'

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

const searchableEventTypes: Array<{ value: '' | EventType; label: string }> = [
  { value: '', label: 'All event types' },
  { value: 'decision', label: 'Decisions' },
  { value: 'tool_call', label: 'Tool calls' },
  { value: 'tool_result', label: 'Tool results' },
  { value: 'llm_request', label: 'LLM requests' },
  { value: 'llm_response', label: 'LLM responses' },
  { value: 'safety_check', label: 'Safety checks' },
  { value: 'refusal', label: 'Refusals' },
  { value: 'policy_violation', label: 'Policy violations' },
  { value: 'agent_turn', label: 'Agent turns' },
  { value: 'behavior_alert', label: 'Behavior alerts' },
  { value: 'error', label: 'Errors' },
]

function EventReferenceList({
  title,
  eventIds,
  eventLookup,
  onSelectEvent,
}: {
  title: string
  eventIds: string[]
  eventLookup: Map<string, TraceEvent>
  onSelectEvent: (eventId: string) => void
}) {
  const uniqueIds = [...new Set(eventIds)]
  if (!uniqueIds.length) return null

  return (
    <div>
      <h3>{title}</h3>
      <div className="reference-list">
        {uniqueIds.map((eventId) => {
          const relatedEvent = eventLookup.get(eventId)
          if (!relatedEvent) {
            return (
              <span key={eventId} className="reference-chip missing">
                Missing {eventId.slice(0, 8)}
              </span>
            )
          }

          return (
            <button key={eventId} type="button" className="reference-chip" onClick={() => onSelectEvent(eventId)}>
              <span>{relatedEvent.event_type.replaceAll('_', ' ')}</span>
              <strong>{formatEventHeadline(relatedEvent)}</strong>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function EventDetail({
  event,
  ranking,
  diagnosis,
  eventLookup,
  onSelectEvent,
  onFocusReplay,
  onResetReplay,
}: {
  event: TraceEvent | null
  ranking?: TraceBundle['analysis']['event_rankings'][number]
  diagnosis?: TraceBundle['analysis']['failure_explanations'][number]
  eventLookup: Map<string, TraceEvent>
  onSelectEvent: (eventId: string) => void
  onFocusReplay: (eventId: string) => void
  onResetReplay: () => void
}) {
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

      <div className="detail-actions">
        <button type="button" onClick={() => onFocusReplay(event.id)}>
          Focus replay
        </button>
        <button type="button" onClick={onResetReplay}>
          Full session
        </button>
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
        {diagnosis && (
          <div className="diagnosis-card">
            <div className="diagnosis-head">
              <h3>Failure Diagnosis</h3>
              <span className="diagnosis-badge">{diagnosis.failure_mode.replaceAll('_', ' ')}</span>
            </div>
            <p>{diagnosis.narrative}</p>
            <div className="analysis-strip">
              <span>Confidence {diagnosis.confidence.toFixed(2)}</span>
              <span>Candidates {diagnosis.candidates.length}</span>
              <span>Inspect {diagnosis.next_inspection_event_id.slice(0, 8)}</span>
            </div>
            {diagnosis.likely_cause_event_id ? (
              <div className="detail-actions">
                <button type="button" onClick={() => onSelectEvent(diagnosis.likely_cause_event_id!)}>
                  Inspect likely cause
                </button>
                <button type="button" onClick={() => onFocusReplay(diagnosis.next_inspection_event_id)}>
                  Replay from suspect
                </button>
              </div>
            ) : null}
            <EventReferenceList
              title="Supporting Chain"
              eventIds={diagnosis.supporting_event_ids}
              eventLookup={eventLookup}
              onSelectEvent={onSelectEvent}
            />
            {diagnosis.candidates.length ? (
              <div>
                <h3>Candidate Causes</h3>
                <div className="candidate-list">
                  {diagnosis.candidates.map((candidate) => (
                    <button
                      key={candidate.event_id}
                      type="button"
                      className="candidate-card"
                      onClick={() => onSelectEvent(candidate.event_id)}
                    >
                      <div className="candidate-head">
                        <span>{candidate.event_type.replaceAll('_', ' ')}</span>
                        <strong>{candidate.score.toFixed(2)}</strong>
                      </div>
                      <strong>{candidate.headline}</strong>
                      <p>{candidate.rationale}</p>
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        )}
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
          <EventReferenceList
            title="Evidence Provenance"
            eventIds={event.evidence_event_ids}
            eventLookup={eventLookup}
            onSelectEvent={onSelectEvent}
          />
        ) : null}
        {event.upstream_event_ids.length ? (
          <EventReferenceList
            title="Upstream Context"
            eventIds={event.upstream_event_ids}
            eventLookup={eventLookup}
            onSelectEvent={onSelectEvent}
          />
        ) : null}
        {event.related_event_ids?.length ? (
          <EventReferenceList
            title="Related Events"
            eventIds={event.related_event_ids}
            eventLookup={eventLookup}
            onSelectEvent={onSelectEvent}
          />
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

function FailureExplanationCard({
  explanation,
  onInspect,
  onFocusReplay,
}: {
  explanation: TraceBundle['analysis']['failure_explanations'][number]
  onInspect: (eventId: string) => void
  onFocusReplay: (eventId: string) => void
}) {
  return (
    <button
      type="button"
      className="diagnosis-overview-card"
      onClick={() => {
        onInspect(explanation.failure_event_id)
        onFocusReplay(explanation.next_inspection_event_id)
      }}
    >
      <div className="diagnosis-head">
        <span>{explanation.failure_mode.replaceAll('_', ' ')}</span>
        <strong>{explanation.confidence.toFixed(2)}</strong>
      </div>
      <h3>{explanation.failure_headline}</h3>
      <p>{explanation.symptom}</p>
      <small>{explanation.likely_cause}</small>
    </button>
  )
}

function CheckpointSnapshot({
  title,
  checkpoint,
}: {
  title: string
  checkpoint: TraceBundle['checkpoints'][number]
}) {
  return (
    <div className="checkpoint-preview">
      <div className="checkpoint-copy">
        <p className="eyebrow">{title}</p>
        <h3>Sequence {checkpoint.sequence}</h3>
      </div>
      <div className="checkpoint-grid">
        <div>
          <h4>State</h4>
          <pre>{JSON.stringify(checkpoint.state, null, 2)}</pre>
        </div>
        <div>
          <h4>Memory</h4>
          <pre>{JSON.stringify(checkpoint.memory, null, 2)}</pre>
        </div>
      </div>
    </div>
  )
}

function App() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [bundle, setBundle] = useState<TraceBundle | null>(null)
  const [secondaryBundle, setSecondaryBundle] = useState<TraceBundle | null>(null)
  const [replay, setReplay] = useState<ReplayResponse | null>(null)
  const [liveEvents, setLiveEvents] = useState<TraceEvent[]>([])
  const [liveSummary, setLiveSummary] = useState<LiveSummary | null>(null)
  const [streamConnected, setStreamConnected] = useState(false)
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)
  const [selectedCheckpointId, setSelectedCheckpointId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [compareLoading, setCompareLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sessionSortMode, setSessionSortMode] = useState<SessionSortMode>('replay_value')
  const [secondarySessionId, setSecondarySessionId] = useState<string | null>(null)
  const [replayMode, setReplayMode] = useState<ReplayMode>('full')
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [speed, setSpeed] = useState(1)
  const [breakpointEventTypes, setBreakpointEventTypes] = useState('error,refusal,policy_violation')
  const [breakpointToolNames, setBreakpointToolNames] = useState('')
  const [breakpointConfidenceBelow, setBreakpointConfidenceBelow] = useState('0.45')
  const [breakpointSafetyOutcomes, setBreakpointSafetyOutcomes] = useState('warn,block')
  const [searchQuery, setSearchQuery] = useState('')
  const [searchEventType, setSearchEventType] = useState<'' | EventType>('')
  const [searchScope, setSearchScope] = useState<SearchScope>('current')
  const [searchResponse, setSearchResponse] = useState<TraceSearchResponse | null>(null)
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false
    async function loadSessions() {
      setLoading(true)
      setError(null)
      try {
        const response = await getSessions({ sortBy: sessionSortMode })
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
  }, [sessionSortMode])

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
        setLiveSummary(response.analysis.live_summary)
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
    if (!selectedSessionId) {
      setLiveEvents([])
      setLiveSummary(null)
      setStreamConnected(false)
      return
    }

    setLiveEvents([])
    const source = createEventSource(selectedSessionId)

    source.onopen = () => {
      setStreamConnected(true)
    }

    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as TraceEvent
        setLiveEvents((current) => {
          if (current.some((item) => item.id === event.id)) {
            return current
          }
          return [...current, event]
        })
      } catch {
        setStreamConnected(false)
      }
    }

    source.onerror = () => {
      setStreamConnected(false)
    }

    return () => {
      source.close()
      setStreamConnected(false)
    }
  }, [selectedSessionId])

  useEffect(() => {
    if (!selectedSessionId) return

    let ignore = false
    const timeout = setTimeout(async () => {
      try {
        const response = await getLiveSummary(selectedSessionId)
        if (!ignore) {
          setLiveSummary(response.live_summary)
        }
      } catch (err) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to load live session summary')
        }
      }
    }, liveEvents.length ? 250 : 0)

    return () => {
      ignore = true
      clearTimeout(timeout)
    }
  }, [selectedSessionId, liveEvents.length])

  useEffect(() => {
    if (!secondarySessionId) {
      setSecondaryBundle(null)
      setCompareLoading(false)
      return
    }
    if (secondarySessionId === selectedSessionId) {
      setSecondaryBundle(null)
      setCompareLoading(false)
      return
    }

    let ignore = false
    async function loadSecondaryBundle() {
      const targetSessionId = secondarySessionId
      if (!targetSessionId) return
      setCompareLoading(true)
      try {
        const response = await getTraceBundle(targetSessionId)
        if (ignore) return
        setSecondaryBundle(response)
      } catch (err) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to load comparison session')
        }
      } finally {
        if (!ignore) setCompareLoading(false)
      }
    }

    void loadSecondaryBundle()
    return () => {
      ignore = true
    }
  }, [secondarySessionId, selectedSessionId])

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

  const mergedSessionEvents = useMemo(() => {
    const merged = [...(bundle?.events ?? [])]
    for (const event of liveEvents) {
      if (!merged.some((item) => item.id === event.id)) {
        merged.push(event)
      }
    }
    merged.sort((left, right) => left.timestamp.localeCompare(right.timestamp))
    return merged
  }, [bundle?.events, liveEvents])

  const activeEvents = replayMode === 'full'
    ? mergedSessionEvents
    : replay?.events ?? mergedSessionEvents
  const selectedEvent = useMemo(
    () => activeEvents.find((event) => event.id === selectedEventId) ?? mergedSessionEvents.find((event) => event.id === selectedEventId) ?? null,
    [activeEvents, mergedSessionEvents, selectedEventId],
  )

  const currentReplayEvent = activeEvents[currentIndex] ?? null
  const activeEventForInspectors = selectedEvent ?? currentReplayEvent
  const eventLookup = useMemo(
    () => new Map(mergedSessionEvents.map((event) => [event.id, event])),
    [mergedSessionEvents],
  )
  const checkpointLookup = useMemo(
    () => new Map((bundle?.checkpoints ?? []).map((checkpoint) => [checkpoint.id, checkpoint])),
    [bundle?.checkpoints],
  )
  const checkpointRankingLookup = useMemo(
    () => new Map((bundle?.analysis.checkpoint_rankings ?? []).map((ranking) => [ranking.checkpoint_id, ranking])),
    [bundle?.analysis.checkpoint_rankings],
  )
  const breakpointEventIds = useMemo(
    () => replay?.breakpoints.map((event) => event.id) ?? [],
    [replay?.breakpoints],
  )
  const breakpointEventIdSet = useMemo(
    () => new Set(breakpointEventIds),
    [breakpointEventIds],
  )

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
  const selectedDiagnosis = useMemo(() => {
    const activeEventId = activeEventForInspectors?.id ?? selectedEventId ?? ''
    if (!activeEventId) return undefined
    return bundle?.analysis.failure_explanations.find((explanation) => explanation.failure_event_id === activeEventId)
  }, [activeEventForInspectors?.id, bundle?.analysis.failure_explanations, selectedEventId])

  const currentSession = sessions.find((session) => session.id === selectedSessionId) ?? bundle?.session ?? null
  const fullRetentionCount = useMemo(
    () => sessions.filter((session) => session.retention_tier === 'full').length,
    [sessions],
  )
  const selectedCheckpoint = (
    (selectedCheckpointId ? checkpointLookup.get(selectedCheckpointId) : null)
    ?? (replay?.nearest_checkpoint ? checkpointLookup.get(replay.nearest_checkpoint.id) ?? replay.nearest_checkpoint : null)
    ?? null
  )
  const selectedCheckpointRanking = selectedCheckpoint ? checkpointRankingLookup.get(selectedCheckpoint.id) : null
  const searchSessionLookup = useMemo(
    () => new Map(sessions.map((session) => [session.id, session])),
    [sessions],
  )

  function seekReplayIndex(nextIndex: number) {
    const clampedIndex = Math.min(Math.max(nextIndex, 0), Math.max(activeEvents.length - 1, 0))
    setCurrentIndex(clampedIndex)
    const event = activeEvents[clampedIndex]
    if (event) {
      setSelectedEventId(event.id)
    }
  }

  function inspectEvent(eventId: string) {
    setSelectedEventId(eventId)
    const nextIndex = activeEvents.findIndex((event) => event.id === eventId)
    if (nextIndex >= 0) {
      setCurrentIndex(nextIndex)
    }
  }

  async function runTraceSearch() {
    const trimmedQuery = searchQuery.trim()
    if (!trimmedQuery) {
      setSearchResponse(null)
      setSearchError(null)
      return
    }

    setSearchLoading(true)
    setSearchError(null)
    try {
      const response = await searchTraces({
        query: trimmedQuery,
        sessionId: searchScope === 'current' ? selectedSessionId : null,
        eventType: searchEventType || null,
        limit: 18,
      })
      setSearchResponse(response)
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Failed to search traces')
    } finally {
      setSearchLoading(false)
    }
  }

  function jumpToSearchResult(result: TraceEvent) {
    setReplayMode('full')
    if (result.session_id !== selectedSessionId) {
      setSelectedSessionId(result.session_id)
      setSelectedEventId(result.id)
      return
    }
    inspectEvent(result.id)
  }

  useEffect(() => {
    if (!isPlaying || !currentReplayEvent || currentIndex === 0) return
    if (breakpointEventIdSet.has(currentReplayEvent.id)) {
      setIsPlaying(false)
    }
  }, [breakpointEventIdSet, currentIndex, currentReplayEvent, isPlaying])

  useEffect(() => {
    const defaultCheckpointId = bundle?.analysis.checkpoint_rankings[0]?.checkpoint_id
      ?? replay?.nearest_checkpoint?.id
      ?? bundle?.checkpoints[0]?.id
      ?? null
    setSelectedCheckpointId((current) => {
      if (current && checkpointLookup.has(current)) {
        return current
      }
      return defaultCheckpointId
    })
  }, [bundle?.analysis.checkpoint_rankings, bundle?.checkpoints, checkpointLookup, replay?.nearest_checkpoint?.id])

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
            <span className="metric-label">Full retention</span>
            <strong>{formatNumber(fullRetentionCount)}</strong>
          </div>
          <div>
            <span className="metric-label">Failures Clustered</span>
            <strong>{formatNumber(bundle?.analysis.failure_clusters.length ?? 0)}</strong>
          </div>
          <div>
            <span className="metric-label">Replay value</span>
            <strong>{(bundle?.analysis.session_replay_value ?? currentSession?.replay_value ?? 0).toFixed(2)}</strong>
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
          <div className="mode-switches session-sort-switches">
            {(['replay_value', 'started_at'] as SessionSortMode[]).map((mode) => (
              <button key={mode} type="button" className={sessionSortMode === mode ? 'active' : ''} onClick={() => setSessionSortMode(mode)}>
                {mode === 'replay_value' ? 'Top replay' : 'Recent'}
              </button>
            ))}
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
                  setSecondarySessionId((current) => (current === session.id ? null : current))
                  setReplayMode('full')
                  setSelectedEventId(null)
                }}
              >
                <span className="session-name">{session.agent_name}</span>
                <span className="session-framework">{session.framework}</span>
                <span className="session-status">{session.status}</span>
                <div className="session-card-metrics">
                  <span>Replay {(session.replay_value ?? 0).toFixed(2)}</span>
                  <span className={`retention-pill ${session.retention_tier ?? 'downsampled'}`}>{session.retention_tier ?? 'downsampled'}</span>
                </div>
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
              <div>
                <span className="metric-label">Retention</span>
                <strong>{bundle?.analysis.retention_tier ?? currentSession.retention_tier ?? 'downsampled'}</strong>
              </div>
              <div>
                <span className="metric-label">Replay value</span>
                <strong>{(bundle?.analysis.session_replay_value ?? currentSession.replay_value ?? 0).toFixed(2)}</strong>
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
            <div className="analysis-strip">
              <span>Retention {bundle?.analysis.retention_tier ?? 'downsampled'}</span>
              <span>Checkpoints ranked {bundle?.analysis.checkpoint_rankings.length ?? 0}</span>
              <span>High severity {bundle?.analysis.session_summary.high_severity_count ?? 0}</span>
            </div>
            <div className="diagnosis-overview-grid">
              {bundle?.analysis.failure_explanations.slice(0, 3).map((explanation) => (
                <FailureExplanationCard
                  key={explanation.failure_event_id}
                  explanation={explanation}
                  onInspect={inspectEvent}
                  onFocusReplay={(eventId) => {
                    setReplayMode('focus')
                    setSelectedEventId(eventId)
                  }}
                />
              )) ?? null}
            </div>
          </section>

          <section className="panel coordination-panel">
            <ConversationPanel
              events={mergedSessionEvents}
              selectedEventId={selectedEventId}
              onSelectEvent={inspectEvent}
            />
          </section>

          <section className="panel comparison-shell">
            <SessionComparisonPanel
              primaryBundle={bundle}
              secondaryBundle={secondaryBundle}
              sessions={sessions}
              selectedSessionId={selectedSessionId}
              secondarySessionId={secondarySessionId}
              compareLoading={compareLoading}
              onSelectSecondarySession={setSecondarySessionId}
            />
          </section>

          <section className="panel live-shell">
            <LiveSummaryPanel
              session={currentSession}
              events={mergedSessionEvents}
              checkpoints={bundle?.checkpoints ?? []}
              liveSummary={liveSummary}
              isConnected={streamConnected}
              liveEventCount={liveEvents.length}
              onSelectEvent={inspectEvent}
            />
          </section>

          <div className="trace-layout">
            <div className="panel timeline-panel">
              <TraceTimeline
                events={activeEvents}
                selectedEventId={selectedEventId}
                onSelectEvent={inspectEvent}
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
                breakpointEventIds={breakpointEventIds}
                currentIndex={currentIndex}
                isPlaying={isPlaying}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                onStepForward={() => seekReplayIndex(currentIndex + 1)}
                onStepBackward={() => seekReplayIndex(currentIndex - 1)}
                onSeek={seekReplayIndex}
                speed={speed}
                onSpeedChange={setSpeed}
              />
              <div className="replay-summary">
                <span>Scope events: {activeEvents.length}</span>
                <span>Nearest checkpoint: {replay?.nearest_checkpoint?.sequence ?? 'none'}</span>
                <span>Breakpoints hit: {replay?.breakpoints.length ?? 0}</span>
                <span>Failures: {replay?.failure_event_ids.length ?? 0}</span>
              </div>
            </section>

            <section className="panel checkpoint-panel">
              <div className="panel-head">
                <p className="eyebrow">Checkpoint Ranking</p>
                <h2>Restore candidates</h2>
              </div>
              <div className="checkpoint-list">
                {bundle?.analysis.checkpoint_rankings.slice(0, 5).map((ranking) => {
                  const checkpoint = checkpointLookup.get(ranking.checkpoint_id)
                  if (!checkpoint) return null
                  return (
                    <button
                      key={ranking.checkpoint_id}
                      type="button"
                      className={`checkpoint-card ${selectedCheckpointId === checkpoint.id ? 'active' : ''}`}
                      onClick={() => setSelectedCheckpointId(checkpoint.id)}
                    >
                      <span>Sequence {checkpoint.sequence}</span>
                      <strong>Restore {ranking.restore_value.toFixed(2)}</strong>
                      <small>Replay {ranking.replay_value.toFixed(2)}</small>
                      <small>{ranking.retention_tier}</small>
                    </button>
                  )
                }) ?? <p>No checkpoints captured.</p>}
              </div>
              {selectedCheckpoint && (
                <>
                  <div className="checkpoint-actions">
                    <button
                      type="button"
                      onClick={() => {
                        inspectEvent(selectedCheckpoint.event_id)
                        setReplayMode('focus')
                      }}
                    >
                      Focus replay
                    </button>
                    <button type="button" onClick={() => inspectEvent(selectedCheckpoint.event_id)}>
                      Inspect event
                    </button>
                  </div>
                  {selectedCheckpointRanking && (
                    <div className="analysis-strip">
                      <span>Restore {selectedCheckpointRanking.restore_value.toFixed(2)}</span>
                      <span>Replay {selectedCheckpointRanking.replay_value.toFixed(2)}</span>
                      <span>Importance {selectedCheckpointRanking.importance.toFixed(2)}</span>
                      <span>Tier {selectedCheckpointRanking.retention_tier}</span>
                    </div>
                  )}
                  <div className="checkpoint-compare-grid">
                    <CheckpointSnapshot title="Selected checkpoint" checkpoint={selectedCheckpoint} />
                    {replay?.nearest_checkpoint && replay.nearest_checkpoint.id !== selectedCheckpoint.id ? (
                      <CheckpointSnapshot title="Replay anchor" checkpoint={replay.nearest_checkpoint} />
                    ) : null}
                  </div>
                </>
              )}
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
          <section className="panel search-panel">
            <div className="search-head">
              <div>
                <p className="eyebrow">Trace Search</p>
                <h2>Find the exact moment</h2>
              </div>
              <button type="button" className="search-submit" onClick={() => void runTraceSearch()} disabled={searchLoading}>
                {searchLoading ? 'Searching…' : 'Search'}
              </button>
            </div>
            <div className="search-controls">
              <label>
                Query
                <input
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault()
                      void runTraceSearch()
                    }
                  }}
                  placeholder="Belgrade, missing token, critic turn…"
                />
              </label>
              <label>
                Event type
                <select value={searchEventType} onChange={(event) => setSearchEventType(event.target.value as '' | EventType)}>
                  {searchableEventTypes.map((option) => (
                    <option key={option.label} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="mode-switches search-scope-switches">
              {(['current', 'all'] as SearchScope[]).map((scope) => (
                <button key={scope} type="button" className={searchScope === scope ? 'active' : ''} onClick={() => setSearchScope(scope)}>
                  {scope === 'current' ? 'Current session' : 'All sessions'}
                </button>
              ))}
            </div>
            {searchError ? <p className="search-status error">{searchError}</p> : null}
            {!searchError && searchResponse ? (
              <p className="search-status">
                {searchResponse.total} result{searchResponse.total === 1 ? '' : 's'} for “{searchResponse.query}”
              </p>
            ) : null}
            <div className="search-results">
              {searchResponse?.results.length ? (
                searchResponse.results.map((result) => {
                  const resultSession = searchSessionLookup.get(result.session_id)
                  return (
                    <button key={result.id} type="button" className="search-result" onClick={() => jumpToSearchResult(result)}>
                      <div className="search-result-topline">
                        <span className={`event-chip ${result.event_type}`}>{result.event_type.replaceAll('_', ' ')}</span>
                        <span>{new Date(result.timestamp).toLocaleTimeString()}</span>
                      </div>
                      <strong>{formatEventHeadline(result)}</strong>
                      <p>{resultSession?.agent_name ?? result.session_id}</p>
                    </button>
                  )
                })
              ) : (
                <p className="search-empty">
                  {searchResponse ? 'No matching trace events yet.' : 'Search across names, payloads, and metadata.'}
                </p>
              )}
            </div>
          </section>
          <EventDetail
            event={activeEventForInspectors}
            ranking={selectedRanking}
            diagnosis={selectedDiagnosis}
            eventLookup={eventLookup}
            onSelectEvent={inspectEvent}
            onFocusReplay={(eventId) => {
              inspectEvent(eventId)
              setReplayMode('focus')
            }}
            onResetReplay={() => setReplayMode('full')}
          />
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
                    onClick={() => inspectEvent(alert.event_id)}
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
