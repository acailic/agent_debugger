import { useEffect, useMemo, lazy, Suspense } from 'react'
import './App.css'
import { createEventSource, getLiveSummary, getReplay, getSessions, getTraceBundle } from './api/client'
import { InspectView } from './components/InspectView'
import { TraceView } from './components/TraceView'
import { Logo } from './components/Logo'
import { buildReplayBreakpointParams, useSessionStore } from './stores/sessionStore'
import { useShallow } from 'zustand/react/shallow'
import { formatNumber } from './utils/formatting'
import type { AppTab, TraceEvent } from './types'

// Lazy load analytics (heavy, rarely used)
const AnalyticsTab = lazy(() => import('./components/AnalyticsTab').then((m) => ({ default: m.AnalyticsTab })))

// Keyboard shortcuts
const TAB_SHORTCUTS: Record<string, AppTab> = {
  '1': 'trace',
  '2': 'inspect',
  '3': 'analytics',
}

function App() {
  // ── Store subscriptions for effects ──────────────────────────────

  const { sessions, selectedSessionId, secondarySessionId, sessionSortMode } = useSessionStore(
    useShallow((state) => ({
      sessions: state.sessions,
      selectedSessionId: state.selectedSessionId,
      secondarySessionId: state.secondarySessionId,
      sessionSortMode: state.sessionSortMode,
    })),
  )

  const { bundle, replayMode, selectedEventId, focusEventId, collapseThreshold, liveEvents, activeTab, error, streamHealth, streamReconnectAttempts } = useSessionStore(
    useShallow((state) => ({
      bundle: state.bundle,
      replayMode: state.replayMode,
      selectedEventId: state.selectedEventId,
      focusEventId: state.focusEventId,
      collapseThreshold: state.collapseThreshold,
      liveEvents: state.liveEvents,
      activeTab: state.activeTab,
      error: state.error,
      streamHealth: state.streamHealth,
      streamReconnectAttempts: state.streamReconnectAttempts,
    })),
  )

  const { setSessions, setSelectedSessionId, setBundle, setSecondaryBundle } = useSessionStore(
    useShallow((state) => ({
      setSessions: state.setSessions,
      setSelectedSessionId: state.setSelectedSessionId,
      setBundle: state.setBundle,
      setSecondaryBundle: state.setSecondaryBundle,
    })),
  )

  const { setReplay, setCurrentIndex, setIsPlaying, setLoading, setCompareLoading, setError } = useSessionStore(
    useShallow((state) => ({
      setReplay: state.setReplay,
      setCurrentIndex: state.setCurrentIndex,
      setIsPlaying: state.setIsPlaying,
      setLoading: state.setLoading,
      setCompareLoading: state.setCompareLoading,
      setError: state.setError,
    })),
  )

  const { addLiveEvent, setLiveSummary, setStreamConnected, setStreamHealth, setStreamReconnectAttempts, setStreamParseFailures, clearLiveEvents, setActiveTab, setSelectedEventId } = useSessionStore(
    useShallow((state) => ({
      addLiveEvent: state.addLiveEvent,
      setLiveSummary: state.setLiveSummary,
      setStreamConnected: state.setStreamConnected,
      setStreamHealth: state.setStreamHealth,
      setStreamReconnectAttempts: state.setStreamReconnectAttempts,
      setStreamParseFailures: state.setStreamParseFailures,
      clearLiveEvents: state.clearLiveEvents,
      setActiveTab: state.setActiveTab,
      setSelectedEventId: state.setSelectedEventId,
    })),
  )

  // Breakpoint params for replay loading effect
  const { breakpointEventTypes, breakpointToolNames, breakpointConfidenceBelow, breakpointSafetyOutcomes, stopAtBreakpoint } = useSessionStore(
    useShallow((state) => ({
      breakpointEventTypes: state.breakpointEventTypes,
      breakpointToolNames: state.breakpointToolNames,
      breakpointConfidenceBelow: state.breakpointConfidenceBelow,
      breakpointSafetyOutcomes: state.breakpointSafetyOutcomes,
      stopAtBreakpoint: state.stopAtBreakpoint,
    })),
  )
  const replayBreakpointParams = useMemo(
    () =>
      buildReplayBreakpointParams({
        breakpointEventTypes,
        breakpointToolNames,
        breakpointConfidenceBelow,
        breakpointSafetyOutcomes,
        stopAtBreakpoint,
      }),
    [breakpointEventTypes, breakpointToolNames, breakpointConfidenceBelow, breakpointSafetyOutcomes, stopAtBreakpoint],
  )

  // ── Effects ──────────────────────────────────────────────────────

  // Load sessions list
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

  // Load trace bundle when session changes
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

  // SSE live streaming connection
  useEffect(() => {
    if (!selectedSessionId) {
      clearLiveEvents()
      setLiveSummary(null)
      setStreamConnected(false)
      setStreamHealth('disconnected')
      setStreamReconnectAttempts(0)
      return
    }

    clearLiveEvents()
    setStreamReconnectAttempts(0)

    const getReconnectDelay = (attempt: number): number => {
      const delays = [1000, 2000, 4000, 8000, 16000, 30000]
      return delays[Math.min(attempt, delays.length - 1)]
    }

    let reconnectTimeoutId: ReturnType<typeof setTimeout> | null = null
    let eventSource: EventSource | null = null

    const connect = () => {
      if (eventSource) {
        eventSource.close()
      }

      eventSource = createEventSource(selectedSessionId)

      eventSource.onopen = () => {
        setStreamConnected(true)
        setStreamHealth('healthy')
        setStreamReconnectAttempts(0)
      }

      eventSource.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as TraceEvent
          addLiveEvent(event)
          setStreamHealth('healthy')
          const currentFailures = useSessionStore.getState().streamParseFailures || 0
          if (currentFailures > 0) {
            setStreamParseFailures(0)
          }
        } catch {
          const currentFailures = useSessionStore.getState().streamParseFailures || 0
          const newFailures = currentFailures + 1
          setStreamParseFailures(newFailures)
          console.warn('[SSE] Failed to parse event, skipping:', message.data)
          setStreamHealth('degraded')
          if (newFailures >= 3) {
            console.error(`[SSE] ${newFailures} consecutive parse failures - check event format`)
          }
        }
      }

      eventSource.onerror = () => {
        setStreamConnected(false)
        setStreamHealth('disconnected')

        if (eventSource) {
          eventSource.close()
        }

        const currentAttempt = useSessionStore.getState().streamReconnectAttempts
        const nextAttempt = currentAttempt + 1
        setStreamReconnectAttempts(nextAttempt)

        const delay = getReconnectDelay(nextAttempt)
        console.log(`[SSE] Reconnection attempt ${nextAttempt} in ${delay}ms`)

        reconnectTimeoutId = setTimeout(() => {
          connect()
        }, delay)
      }
    }

    connect()

    return () => {
      if (reconnectTimeoutId) {
        clearTimeout(reconnectTimeoutId)
      }
      if (eventSource) {
        eventSource.close()
      }
      setStreamConnected(false)
      setStreamHealth('disconnected')
      setStreamReconnectAttempts(0)
    }
  }, [selectedSessionId, clearLiveEvents, addLiveEvent, setStreamConnected, setStreamHealth, setStreamReconnectAttempts, setLiveSummary])

  // Poll live summary when new live events arrive
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

  // Load secondary session for comparison
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
    let timeoutId: ReturnType<typeof setTimeout> | null = null

    async function loadSecondaryBundle() {
      const targetSessionId = secondarySessionId
      if (!targetSessionId) return
      setCompareLoading(true)

      timeoutId = setTimeout(() => {
        if (!ignore) {
          setCompareLoading(false)
          setError('Comparison session loading timed out after 10 seconds. The session may be too large or the server may be slow.')
        }
      }, 10000)

      try {
        const response = await getTraceBundle(targetSessionId)
        if (ignore) return

        if (timeoutId) {
          clearTimeout(timeoutId)
          timeoutId = null
        }

        setSecondaryBundle(response)
      } catch (err) {
        if (!ignore) {
          if (timeoutId) {
            clearTimeout(timeoutId)
            timeoutId = null
          }
          setError(err instanceof Error ? err.message : 'Failed to load comparison session')
        }
      } finally {
        if (!ignore && !timeoutId) {
          setCompareLoading(false)
        }
      }
    }

    void loadSecondaryBundle()
    return () => {
      ignore = true
      if (timeoutId) {
        clearTimeout(timeoutId)
      }
    }
  }, [secondarySessionId, selectedSessionId, setSecondaryBundle, setCompareLoading, setError])

  // Load replay data when session/mode/params change
  useEffect(() => {
    if (!selectedSessionId || !bundle) return
    const sessionId = selectedSessionId
    let ignore = false
    async function loadReplay() {
      try {
        const response = await getReplay(sessionId, {
          mode: replayMode,
          focusEventId: replayMode === 'focus' ? (focusEventId ?? selectedEventId) : null,
          ...replayBreakpointParams,
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
    replayBreakpointParams,
    setReplay,
    setCurrentIndex,
    setIsPlaying,
    setError,
  ])

  // Keyboard shortcuts for tab switching and search focus
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey) {
        const key = event.key
        if (key in TAB_SHORTCUTS) {
          event.preventDefault()
          setActiveTab(TAB_SHORTCUTS[key])
        } else if (key === 'k' || key === 'K') {
          event.preventDefault()
          const searchInput = document.getElementById('search-input') as HTMLInputElement | null
          searchInput?.focus()
        }
      } else if (event.key === '/' && !event.metaKey && !event.ctrlKey) {
        const activeTag = document.activeElement?.tagName.toLowerCase()
        if (activeTag !== 'input' && activeTag !== 'textarea') {
          event.preventDefault()
          const searchInput = document.getElementById('search-input') as HTMLInputElement | null
          searchInput?.focus()
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [setActiveTab])

  // ── Derived values for header ────────────────────────────────────

  const currentSession = sessions.find((session) => session.id === selectedSessionId) ?? bundle?.session ?? null

  // ── Render ───────────────────────────────────────────────────────

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
            <span className="metric-label" title="A metric measuring how closely this trace matches expected behavior patterns">Replay value</span>
            <strong>{(bundle?.analysis.session_replay_value ?? currentSession?.replay_value ?? 0).toFixed(2)}</strong>
          </div>
          {selectedSessionId && (
            <div
              className="connection-health-indicator"
              title={`Connection: ${streamHealth}${streamReconnectAttempts > 0 ? ` (reconnect attempt ${streamReconnectAttempts})` : ''}`}
              data-health={streamHealth}
            >
              <span className={`connection-dot ${streamHealth}`} />
              <strong>{streamHealth === 'healthy' ? 'Connected' : streamHealth === 'degraded' ? 'Degraded' : 'Disconnected'}</strong>
            </div>
          )}
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

      {activeTab === 'analytics' && (
        <Suspense fallback={<div className="loading-placeholder fade-in">Loading analytics...</div>}>
          <AnalyticsTab />
        </Suspense>
      )}

      {activeTab === 'inspect' && <InspectView />}

      {activeTab === 'trace' && <TraceView />}
    </div>
  )
}

export default App
