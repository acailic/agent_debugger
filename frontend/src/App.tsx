import { useEffect, useMemo, useState } from 'react'
import './App.css'
import { createEventSource, getAgentDrift, getLiveSummary, getReplay, getSessions, getTraceBundle } from './api/client'
import { AnalyticsTab } from './components/AnalyticsTab'
import { EmptyState } from './components/EmptyState'
import { Logo } from './components/Logo'
import { ConversationPanel } from './components/ConversationPanel'
import { DecisionTree } from './components/DecisionTree'
import { DriftAlertsPanel } from './components/DriftAlertsPanel'
import { FailureClusterPanel } from './components/FailureClusterPanel'
import { LLMViewer } from './components/LLMViewer'
import { LiveDashboard } from './components/LiveDashboard'
import { MultiAgentCoordinationPanel } from './components/MultiAgentCoordinationPanel'
import { SearchPanel } from './components/SearchPanel'
import { SessionComparisonPanel } from './components/SessionComparisonPanel'
import { SessionReplay } from './components/SessionReplay'
import { SessionRail } from './components/SessionRail'
import { ToolInspector } from './components/ToolInspector'
import { TraceTimeline } from './components/TraceTimeline'
import WhyButton from './components/WhyButton'
import HighlightChip from './components/HighlightChip'
import { CheckpointSnapshot } from './components/CheckpointSnapshot'
import { EventDetail } from './components/EventDetail'
import { formatEventHeadline, formatNumber } from './utils/formatting'
import { useSessionStore } from './stores/sessionStore'
import type { AppTab, Highlight, TraceEvent } from './types'

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
    liveEvents,
    liveSummary,
    streamConnected,
    activeTab,
    sessionSortMode,
    selectedEventId,
    focusEventId,
    selectedCheckpointId,
    currentHighlightIndex,
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
    toggleExpandedSegment,
    addLiveEvent,
    setLiveSummary,
    setStreamConnected,
    clearLiveEvents,
    setActiveTab,
    setSelectedEventId,
    setFocusEventId,
    setSelectedCheckpointId,
    setCurrentHighlightIndex,
    setLoading,
    setCompareLoading,
    setError,
    setDriftData,
    setDriftLoading,
  } = useSessionStore()

  // Local state for items not yet moved to the store
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({})

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
      // Get breakpoint config from store directly
      const breakpointConfig = useSessionStore.getState()
      try {
        const response = await getReplay(sessionId, {
          mode: replayMode,
          focusEventId: replayMode === 'focus' ? (focusEventId ?? selectedEventId) : null,
          breakpointEventTypes: breakpointConfig.breakpointEventTypes.split(',').map((item) => item.trim()).filter(Boolean),
          breakpointToolNames: breakpointConfig.breakpointToolNames.split(',').map((item) => item.trim()).filter(Boolean),
          breakpointConfidenceBelow: breakpointConfig.breakpointConfidenceBelow ? Number(breakpointConfig.breakpointConfidenceBelow) : null,
          breakpointSafetyOutcomes: breakpointConfig.breakpointSafetyOutcomes.split(',').map((item) => item.trim()).filter(Boolean),
          stopAtBreakpoint: breakpointConfig.stopAtBreakpoint,
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
  const selectedCheckpoint = (
    (selectedCheckpointId ? checkpointLookup.get(selectedCheckpointId) : null)
    ?? (replay?.nearest_checkpoint ? checkpointLookup.get(replay.nearest_checkpoint.id) ?? replay.nearest_checkpoint : null)
    ?? null
  )
  const selectedCheckpointRanking = selectedCheckpoint ? checkpointRankingLookup.get(selectedCheckpoint.id) : null
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Logo size={24} />
          <div>
            <h1>Peaky Peek</h1>
          </div>
        </div>
        <div className="hero-metrics">
          <div>
            <span className="metric-label">Sessions</span>
            <strong>{formatNumber(sessions.length)}</strong>
          </div>
          <div>
            <span className="metric-label">Failures</span>
            <strong>{formatNumber(bundle?.analysis.failure_clusters.length ?? 0)}</strong>
          </div>
          <div>
            <span className="metric-label">Replay value</span>
            <strong>{(bundle?.analysis.session_replay_value ?? currentSession?.replay_value ?? 0).toFixed(2)}</strong>
          </div>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <nav className="app-tabs">
        {(['trace', 'inspect', 'analytics'] as AppTab[]).map((tab) => (
          <button
            key={tab}
            type="button"
            className={`tab-btn ${activeTab === tab ? 'active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab === 'trace' ? 'Trace' : tab === 'inspect' ? 'Inspect' : 'Analytics'}
          </button>
        ))}
      </nav>

      {activeTab === 'analytics' && <AnalyticsTab />}

      {activeTab === 'inspect' && (
        <main className="workspace workspace--inspect">
          <section className="main-stage">
            {!selectedSessionId ? (
              <EmptyState
                icon="&#128300;"
                title="No session selected"
                description="Go to the Trace tab and select a session to inspect its decision tree, checkpoints, and behavior alerts."
              />
            ) : null}
            <div className="trace-layout" style={selectedSessionId ? undefined : { opacity: 0.3, pointerEvents: 'none' as const }}>
              <div className="panel panel--primary timeline-panel">
                <DecisionTree tree={bundle?.tree ?? null} selectedEventId={selectedEventId} onSelectEvent={setSelectedEventId} />
              </div>
            </div>

            <div className="inspect-grid">
              {/* Analysis Group: Inspectors + Conversation + Comparison */}
              <div
                className={`inspect-section-divider ${collapsedSections['analysis'] ? 'collapsed' : ''}`}
                onClick={() => setCollapsedSections((prev: Record<string, boolean>) => ({ ...prev, analysis: !prev.analysis }))}
              >
                <span className="inspect-section-label">Analysis</span>
              </div>

              <div data-section="analysis" data-section-hidden={collapsedSections['analysis'] ? 'true' : 'false'}>
                <section className="panel panel--primary">
                <div className="inspectors-grid">
                  <div className="inspector-wrapper">
                    <span className="inspector-label">Tool Inspector</span>
                    <ToolInspector event={toolEvent} />
                  </div>
                  <div className="inspector-separator" />
                  <div className="inspector-wrapper">
                    <span className="inspector-label">LLM Viewer</span>
                    <LLMViewer request={llmRequest} response={llmResponse} />
                  </div>
                </div>
              </section>

              <section className="panel panel--secondary">
                <ConversationPanel
                  events={mergedSessionEvents}
                  selectedEventId={selectedEventId}
                  onSelectEvent={handleInspectEvent}
                />
              </section>

              <section className="panel panel--secondary">
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
              </div>

              {/* Monitoring Group: Live Dashboard + Checkpoints + Alerts */}
              <div
                className={`inspect-section-divider ${collapsedSections['monitoring'] ? 'collapsed' : ''}`}
                onClick={() => setCollapsedSections((prev: Record<string, boolean>) => ({ ...prev, monitoring: !prev.monitoring }))}
              >
                <span className="inspect-section-label">Monitoring</span>
              </div>

              <div data-section="monitoring" data-section-hidden={collapsedSections['monitoring'] ? 'true' : 'false'}>
                <section className="panel panel--secondary">
                <LiveDashboard
                  session={currentSession}
                  events={mergedSessionEvents}
                  checkpoints={bundle?.checkpoints ?? []}
                  liveSummary={liveSummary}
                  isConnected={streamConnected}
                  liveEventCount={liveEvents.length}
                  onSelectEvent={handleInspectEvent}
                />
              </section>

              <section className="panel panel--secondary">
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
                        data-tier={ranking.retention_tier.replace('tier-', '')}
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
                      <CheckpointSnapshot title="Selected checkpoint" checkpoint={selectedCheckpoint} variant="selected" />
                      {replay?.nearest_checkpoint && replay.nearest_checkpoint.id !== selectedCheckpoint.id ? (
                        <CheckpointSnapshot title="Replay anchor" checkpoint={replay.nearest_checkpoint} variant="anchor" />
                      ) : null}
                    </div>
                  </>
                )}
              </section>

              <section className="panel alerts-panel">
                <div className="panel-head">
                  <p className="eyebrow">Behavior Alerts</p>
                  <h2>
                    Live heuristics
                    {bundle?.analysis?.behavior_alerts && bundle.analysis.behavior_alerts.length > 0 && (
                      <span className="alert-badge">{bundle.analysis.behavior_alerts.length}</span>
                    )}
                  </h2>
                </div>
                <div className="alert-list">
                  {bundle?.analysis?.behavior_alerts?.length ? (
                    bundle.analysis.behavior_alerts.map((alert) => (
                      <button
                        key={`${alert.alert_type}-${alert.event_id}`}
                        type="button"
                        className="alert-row"
                        data-severity={alert.severity.toLowerCase()}
                        onClick={() => handleInspectEvent(alert.event_id)}
                      >
                        <span>{alert.alert_type}</span>
                        <strong>{alert.severity}</strong>
                        <small>{alert.signal}</small>
                      </button>
                    ))
                  ) : (
                    <div className="empty-state">
                      <div className="empty-state-icon">🔍</div>
                      <h3>All clear</h3>
                      <p>No oscillation, looping, or confidence drops detected.</p>
                      <small>Alerts appear here when behavior patterns need attention</small>
                    </div>
                  )}
                </div>
              </section>

              <DriftAlertsPanel
                agentName={currentSession?.agent_name ?? null}
                driftData={driftData}
                loading={driftLoading}
              />
              </div>

              {/* Intelligence Group: Drift + Policy + Failure Clusters + Coordination */}
              <div
                className={`inspect-section-divider ${collapsedSections['intelligence'] ? 'collapsed' : ''}`}
                onClick={() => setCollapsedSections((prev: Record<string, boolean>) => ({ ...prev, intelligence: !prev.intelligence }))}
              >
                <span className="inspect-section-label">Intelligence</span>
              </div>

              <div data-section="intelligence" data-section-hidden={collapsedSections['intelligence'] ? 'true' : 'false'}>
                <section className="panel panel--accent failure-cluster-panel">
                <FailureClusterPanel
                  clusters={[]}
                  onSelectSession={setSelectedSessionId}
                  selectedSessionId={selectedSessionId}
                  analysisClusters={bundle?.analysis.failure_clusters ?? []}
                  events={mergedSessionEvents}
                />
              </section>

              <section className="panel panel--accent coordination-panel">
                <MultiAgentCoordinationPanel bundle={bundle} />
              </section>
              </div>
            </div>
          </section>
        </main>
      )}

      {activeTab === 'trace' && (
      <main className="workspace">
        <SessionRail />

        <section className="main-stage">
          {!selectedSessionId ? (
            <EmptyState
              icon="&#128065;"
              title="Select a session to inspect"
              description="Choose a captured run from the sidebar to replay its trace, inspect decisions, and search events."
            />
          ) : null}

          <section className="panel panel--primary replay-panel">
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

          <section className="panel panel--primary timeline-panel">
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
        </section>

        <aside className="detail-rail">
          <SearchPanel />
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
        </aside>
      </main>
      )}
    </div>
  )
}

export default App
