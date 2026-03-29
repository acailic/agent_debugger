import { useEffect, useMemo } from 'react'
import './App.css'
import { createEventSource, getAgentDrift, getLiveSummary, getReplay, getSessions, getTraceBundle, searchTraces } from './api/client'
import { AnalyticsPanel } from './components/AnalyticsPanel'
import { Logo } from './components/Logo'
import { ConversationPanel } from './components/ConversationPanel'
import CostPanel from './components/CostPanel'
import CostSummary from './components/CostSummary'
import { DecisionTree } from './components/DecisionTree'
import { DriftAlertsPanel } from './components/DriftAlertsPanel'
import { FailureClusterPanel } from './components/FailureClusterPanel'
import FixAnnotation from './components/FixAnnotation'
import { LLMViewer } from './components/LLMViewer'
import { LiveSummaryPanel } from './components/LiveSummaryPanel'
import { PolicyDiffView } from './components/PolicyDiffView'
import SearchBar from './components/SearchBar'
import { SessionComparisonPanel } from './components/SessionComparisonPanel'
import { SessionReplay } from './components/SessionReplay'
import { ToolInspector } from './components/ToolInspector'
import { TraceTimeline } from './components/TraceTimeline'
import WhyButton from './components/WhyButton'
import HighlightChip from './components/HighlightChip'
import { CheckpointSnapshot } from './components/CheckpointSnapshot'
import { EventDetail } from './components/EventDetail'
import { FailureExplanationCard } from './components/FailureExplanationCard'
import { formatEventHeadline, formatNumber, SEARCHABLE_EVENT_TYPES } from './utils/formatting'
import { useSessionStore } from './stores/sessionStore'
import type { FailureCluster, Highlight, PolicyShift, RollingSummary, TraceEvent } from './types'

type AppTab = 'trace' | 'analytics'
type ReplayMode = 'full' | 'focus' | 'failure' | 'highlights'
type SessionSortMode = 'started_at' | 'replay_value'
type SearchScope = 'current' | 'all'

function App() {
  // Get all state and actions from the store
  const {
    sessions,
    selectedSessionId,
    secondarySessionId,
    bundle,
    secondaryBundle,
    replay,
    replayMode,
    currentIndex,
    isPlaying,
    speed,
    collapseThreshold,
    expandedSegments,
    searchQuery,
    searchEventType,
    searchScope,
    searchResponse,
    searchLoading,
    searchError,
    liveEvents,
    liveSummary,
    streamConnected,
    activeTab,
    sessionSortMode,
    selectedEventId,
    focusEventId,
    selectedCheckpointId,
    currentHighlightIndex,
    breakpointEventTypes,
    breakpointToolNames,
    breakpointConfidenceBelow,
    breakpointSafetyOutcomes,
    stopAtBreakpoint,
    loading,
    compareLoading,
    error,
    driftData,
    driftLoading,
    // Actions
    setSessions,
    setSelectedSessionId,
    setSecondarySessionId,
    setBundle,
    setSecondaryBundle,
    setReplay,
    setReplayMode,
    setCurrentIndex,
    setIsPlaying,
    setSpeed,
    setCollapseThreshold,
    toggleExpandedSegment,
    setSearchQuery,
    setSearchEventType,
    setSearchScope,
    setSearchResponse,
    setSearchLoading,
    setSearchError,
    addLiveEvent,
    setLiveSummary,
    setStreamConnected,
    clearLiveEvents,
    setActiveTab,
    setSessionSortMode,
    setSelectedEventId,
    setFocusEventId,
    setSelectedCheckpointId,
    setCurrentHighlightIndex,
    setBreakpointEventTypes,
    setBreakpointToolNames,
    setBreakpointConfidenceBelow,
    setBreakpointSafetyOutcomes,
    setStopAtBreakpoint,
    setLoading,
    setCompareLoading,
    setError,
    setDriftData,
    setDriftLoading,
  } = useSessionStore()

  // Local state for items not yet moved to the store
  const rollingSummaryData: RollingSummary | null = null
  const policyShifts: PolicyShift[] = []
  const failureClusters: FailureCluster[] = []

  useEffect(() => {
    let ignore = false
    async function loadSessions() {
      setLoading(true)
      setError(null)
      try {
        const response = await getSessions({ sortBy: sessionSortMode })
        if (ignore) return
        setSessions(response.sessions)
        const currentId = useSessionStore.getState().selectedSessionId
        setSelectedSessionId(currentId ?? response.sessions[0]?.id ?? null)
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
  }, [sessionSortMode, setSessions, setSelectedSessionId, setLoading, setError])

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
        const currentEventId = useSessionStore.getState().selectedEventId
        setSelectedEventId(currentEventId ?? response.events[0]?.id ?? null)
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
  }, [selectedSessionId, setBundle, setLiveSummary, setSelectedEventId, setLoading, setError])

  useEffect(() => {
    if (!selectedSessionId) {
      clearLiveEvents()
      setLiveSummary(null)
      setStreamConnected(false)
      return
    }

    clearLiveEvents()
    const source = createEventSource(selectedSessionId)

    source.onopen = () => {
      setStreamConnected(true)
    }

    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as TraceEvent
        addLiveEvent(event)
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
  }, [selectedSessionId, clearLiveEvents, addLiveEvent, setStreamConnected, setLiveSummary])

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
  }, [selectedSessionId, liveEvents.length, setLiveSummary, setError])

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
  }, [secondarySessionId, selectedSessionId, setSecondaryBundle, setCompareLoading, setError])

  useEffect(() => {
    if (!selectedSessionId || !bundle) return
    const sessionId = selectedSessionId
    let ignore = false
    async function loadReplay() {
      try {
        const response = await getReplay(sessionId, {
          mode: replayMode,
          focusEventId: replayMode === 'focus' ? (focusEventId ?? selectedEventId) : null,
          breakpointEventTypes: breakpointEventTypes.split(',').map((item) => item.trim()).filter(Boolean),
          breakpointToolNames: breakpointToolNames.split(',').map((item) => item.trim()).filter(Boolean),
          breakpointConfidenceBelow: breakpointConfidenceBelow ? Number(breakpointConfidenceBelow) : null,
          breakpointSafetyOutcomes: breakpointSafetyOutcomes.split(',').map((item) => item.trim()).filter(Boolean),
          stopAtBreakpoint,
          collapseThreshold: replayMode === 'highlights' ? collapseThreshold : undefined,
        })
        if (ignore) return
        setReplay(response)
        if (response.stopped_at_breakpoint && response.stopped_at_index !== null) {
          setCurrentIndex(response.stopped_at_index)
        } else {
          setCurrentIndex(0)
        }
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
    focusEventId,
    breakpointEventTypes,
    breakpointToolNames,
    breakpointConfidenceBelow,
    breakpointSafetyOutcomes,
    stopAtBreakpoint,
    collapseThreshold,
    setReplay,
    setCurrentIndex,
    setIsPlaying,
    setError,
  ])

  // Derived state (useMemo calculations) - kept in component
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

  const highlights = bundle?.analysis.highlights ?? []
  const highlightEventIds = useMemo(
    () => new Set(highlights.map((h) => h.event_id)),
    [highlights],
  )
  const highlightsMap = useMemo(
    () => new Map(highlights.map((h) => [h.event_id, h])),
    [highlights],
  )
  const highlightEvents = useMemo(
    () => mergedSessionEvents.filter((event) => highlightEventIds.has(event.id)),
    [mergedSessionEvents, highlightEventIds],
  )

  const displayEvents = replayMode === 'highlights' ? highlightEvents : activeEvents
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

  useEffect(() => {
    const agentName = currentSession?.agent_name
    if (!agentName) {
      setDriftData(null)
      return
    }

    let ignore = false
    async function fetchDrift(name: string) {
      setDriftLoading(true)
      try {
        const data = await getAgentDrift(name)
        if (!ignore) setDriftData(data)
      } catch {
        if (!ignore) setDriftData(null)
      } finally {
        if (!ignore) setDriftLoading(false)
      }
    }
    void fetchDrift(agentName)
    return () => {
      ignore = true
    }
  }, [currentSession?.agent_name, setDriftData, setDriftLoading])

  function seekReplayIndex(nextIndex: number) {
    const clampedIndex = Math.min(Math.max(nextIndex, 0), Math.max(displayEvents.length - 1, 0))
    setCurrentIndex(clampedIndex)
    const event = displayEvents[clampedIndex]
    if (event) {
      setSelectedEventId(event.id)
    }
  }

  function handleInspectEvent(eventId: string) {
    setSelectedEventId(eventId)
    const nextIndex = displayEvents.findIndex((event) => event.id === eventId)
    if (nextIndex >= 0) {
      setCurrentIndex(nextIndex)
    }
  }

  function getHighlightForEvent(eventId: string | null): Highlight | null {
    if (!eventId) return null
    return highlights.find((h) => h.event_id === eventId) ?? null
  }

  function goToHighlight(delta: number) {
    if (highlightEvents.length === 0) return
    const newIndex = Math.max(0, Math.min(currentHighlightIndex + delta, highlightEvents.length - 1))
    setCurrentHighlightIndex(newIndex)
    const event = highlightEvents[newIndex]
    if (event) {
      setSelectedEventId(event.id)
      const displayIndex = displayEvents.findIndex((e) => e.id === event.id)
      if (displayIndex >= 0) setCurrentIndex(displayIndex)
    }
  }

  const selectedHighlight = getHighlightForEvent(selectedEventId)

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
    handleInspectEvent(result.id)
  }

  useEffect(() => {
    if (!isPlaying || !currentReplayEvent || currentIndex === 0) return
    if (breakpointEventIdSet.has(currentReplayEvent.id)) {
      setIsPlaying(false)
    }
  }, [breakpointEventIdSet, currentIndex, currentReplayEvent, isPlaying, setIsPlaying])

  useEffect(() => {
    const defaultCheckpointId = bundle?.analysis.checkpoint_rankings[0]?.checkpoint_id
      ?? replay?.nearest_checkpoint?.id
      ?? bundle?.checkpoints[0]?.id
      ?? null
    const currentCheckpointId = useSessionStore.getState().selectedCheckpointId
    if (currentCheckpointId && checkpointLookup.has(currentCheckpointId)) {
      // Keep current selection if valid
      return
    }
    setSelectedCheckpointId(defaultCheckpointId)
  }, [bundle?.analysis.checkpoint_rankings, bundle?.checkpoints, checkpointLookup, replay?.nearest_checkpoint?.id, setSelectedCheckpointId])

  return (
    <div className="app-shell">
      <header className="hero">
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <Logo size={40} />
          <div>
            <p className="eyebrow">Research-grade agent debugging</p>
          <h1>Edge Trace Console</h1>
          <p className="hero-copy">
            One coherent surface for safety-aware traces, provenance, adaptive replay, and failure clustering.
          </p>
        </div>
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

      <div className="search-container">
        <SearchBar onSelectSession={(sessionId: string) => {
          setSelectedSessionId(sessionId)
          setActiveTab('trace')
        }} />
      </div>

      {error && <div className="error-banner">{error}</div>}

      <nav className="app-tabs">
        {(['trace', 'analytics'] as AppTab[]).map((tab) => (
          <button
            key={tab}
            type="button"
            className={`tab-btn ${activeTab === tab ? 'active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab === 'trace' ? 'Trace Inspector' : 'Analytics'}
          </button>
        ))}
      </nav>

      {activeTab === 'analytics' && (
        <div className="analytics-view">
          <CostSummary />
          <AnalyticsPanel />
        </div>
      )}

      {activeTab === 'trace' && (
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
          {loading && !sessions.length ? <p>Loading sessions...</p> : null}
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
                  <span className={`retention-pill ${session.retention_tier ?? 'downsampled'}`}>{session.retention_tier ?? 'downsampled'}</span>
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

        <section className="main-stage">
          <section className="control-bar panel">
            <div className="control-copy">
              <p className="eyebrow">Replay</p>
              <h2>Checkpoint-aware playback</h2>
            </div>
            <div className="mode-switches">
              {(['full', 'focus', 'failure', 'highlights'] as ReplayMode[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className={replayMode === mode ? 'active' : ''}
                  onClick={() => setReplayMode(mode)}
                >
                  {mode}
                </button>
              ))}
              {replayMode === 'highlights' && (
                <div className="threshold-presets">
                  {([
                    { label: 'Critical', value: 0.7 },
                    { label: 'Standard', value: 0.35 },
                    { label: 'Show most', value: 0.1 },
                  ] as const).map(({ label, value }) => (
                    <button
                      key={value}
                      type="button"
                      className={`threshold-preset${collapseThreshold === value ? ' active' : ''}`}
                      onClick={() => setCollapseThreshold(value)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              )}
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
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={stopAtBreakpoint}
                  onChange={(event) => setStopAtBreakpoint(event.target.checked)}
                />
                Stop at breakpoint
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
                  onInspect={handleInspectEvent}
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
              onSelectEvent={handleInspectEvent}
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
              rollingSummaryData={rollingSummaryData}
              isConnected={streamConnected}
              liveEventCount={liveEvents.length}
              onSelectEvent={handleInspectEvent}
            />
          </section>

          {currentSession && (currentSession.status === 'error' || (currentSession.failure_count ?? 0) > 0) && (
            <WhyButton
              sessionId={currentSession.id}
              onSelectEvent={(eventId) => {
                setSelectedEventId(eventId)
                setReplayMode('focus')
              }}
              onFocusReplay={(eventId) => {
                setSelectedEventId(eventId)
                setReplayMode('focus')
              }}
            />
          )}

          <div className="trace-layout">
            <div className="panel timeline-panel">
              {replayMode === 'highlights' && (
                <div className="highlight-nav">
                  <button type="button" onClick={() => goToHighlight(-1)} disabled={currentHighlightIndex === 0}>
                    Prev
                  </button>
                  <span className="highlight-position">
                    {highlightEvents.length > 0 ? `${currentHighlightIndex + 1} of ${highlightEvents.length} highlights` : 'No highlights in this session'}
                  </span>
                  <button type="button" onClick={() => goToHighlight(1)} disabled={currentHighlightIndex >= highlightEvents.length - 1}>
                    Next
                  </button>
                </div>
              )}
              <TraceTimeline
                events={displayEvents}
                selectedEventId={selectedEventId}
                onSelectEvent={handleInspectEvent}
                highlightEventIds={highlightEventIds}
                highlightsMap={highlightsMap}
              />
              {replayMode === 'highlights' && replay?.collapsed_segments?.map((segment, index) => (
                <HighlightChip
                  key={index}
                  segment={segment}
                  isExpanded={expandedSegments.has(index)}
                  onToggle={() => toggleExpandedSegment(index)}
                >
                  {mergedSessionEvents
                    .slice(segment.start_index, segment.end_index + 1)
                    .map((event) => (
                      <button
                        key={event.id}
                        type="button"
                        className="reference-chip"
                        onClick={() => handleInspectEvent(event.id)}
                      >
                        <span>{event.event_type.replaceAll('_', ' ')}</span>
                        <strong>{formatEventHeadline(event)}</strong>
                      </button>
                    ))}
                </HighlightChip>
              ))}
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
                {replay?.collapsed_segments && replay.collapsed_segments.length > 0 && (
                  <span>Collapsed segments: {replay.collapsed_segments.length}</span>
                )}
                {replay?.highlight_indices && replay.highlight_indices.length > 0 && (
                  <span>Highlights: {replay.highlight_indices.length}</span>
                )}
                {replay?.stopped_at_breakpoint && (
                  <span className="breakpoint-stop-indicator">Stopped at breakpoint</span>
                )}
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
                        handleInspectEvent(selectedCheckpoint.event_id)
                        setReplayMode('focus')
                      }}
                    >
                      Focus replay
                    </button>
                    <button type="button" onClick={() => handleInspectEvent(selectedCheckpoint.event_id)}>
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
                {searchLoading ? 'Searching...' : 'Search'}
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
                  placeholder="Belgrade, missing token, critic turn..."
                />
              </label>
              <label>
                Event type
                <select value={searchEventType} onChange={(event) => setSearchEventType(event.target.value as '' | import('./types').EventType)}>
                  {SEARCHABLE_EVENT_TYPES.map((option: { value: '' | import('./types').EventType; label: string }) => (
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
                {searchResponse.total} result{searchResponse.total === 1 ? '' : 's'} for "{searchResponse.query}"
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
            highlight={selectedHighlight}
            eventLookup={eventLookup}
            onSelectEvent={handleInspectEvent}
            onFocusReplay={(eventId) => {
              handleInspectEvent(eventId)
              setReplayMode('focus')
            }}
            onReplayFromHere={(eventId) => {
              setFocusEventId(eventId)
              setReplayMode('focus')
              setSelectedEventId(eventId)
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
                    onClick={() => handleInspectEvent(alert.event_id)}
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
          <DriftAlertsPanel
            agentName={currentSession?.agent_name ?? null}
            driftData={driftData}
            loading={driftLoading}
          />
          <PolicyDiffView
            policyShifts={policyShifts}
            onSelectEvent={handleInspectEvent}
          />
          <FailureClusterPanel
            clusters={failureClusters}
            onSelectSession={setSelectedSessionId}
            selectedSessionId={selectedSessionId}
          />
        </aside>
      </main>
      )}
    </div>
  )
}

export default App
