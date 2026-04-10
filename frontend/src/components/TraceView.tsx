import { useSessionStore } from '../stores/sessionStore'
import { useDerivedSessionData } from '../hooks/useDerivedSessionData'
import { useInspectEvent } from '../hooks/useInspectEvent'
import { useReplayBreakpoint } from '../hooks/useReplayBreakpoint'
import { ErrorBoundary } from './ErrorBoundary'
import { EmptyState } from './EmptyState'
import { SessionReplay } from './SessionReplay'
import { SessionRailMemo } from './SessionRail'
import { TraceTimelineMemo } from './TraceTimeline'
import { EventDetailMemo } from './EventDetail'
import { SearchPanel } from './SearchPanel'
import { SimilarFailuresPanelMemo } from './SimilarFailuresPanel'
import { ReplayBar } from './ReplayBar'
import WhyButton from './WhyButton'
import CostPanel from './CostPanel'
import HighlightChip from './HighlightChip'
import { formatEventHeadline } from '../utils/formatting'
import type { Highlight } from '../types'
import { useMemo } from 'react'

export function TraceView() {
  const derived = useDerivedSessionData()
  const handleInspectEvent = useInspectEvent(derived.displayEvents)
  useReplayBreakpoint()

  // Store subscriptions for actions
  const {
    selectedSessionId,
    selectedEventId,
    currentIndex,
    isPlaying,
    speed,
    replayMode,
    showBlockedActions,
    expandedSegments,
    currentHighlightIndex,
    replay,
    userBreakpointIds,
  } = useSessionStore(
    (state) => ({
      selectedSessionId: state.selectedSessionId,
      selectedEventId: state.selectedEventId,
      currentIndex: state.currentIndex,
      isPlaying: state.isPlaying,
      speed: state.speed,
      replayMode: state.replayMode,
      showBlockedActions: state.showBlockedActions,
      expandedSegments: state.expandedSegments,
      currentHighlightIndex: state.currentHighlightIndex,
      replay: state.replay,
      userBreakpointIds: state.userBreakpointIds,
    }),
  )

  const {
    setSelectedEventId,
    setSelectedSessionId,
    setIsPlaying,
    setCurrentIndex,
    setSpeed,
    setReplayMode,
    setFocusEventId,
    setShowBlockedActions,
    toggleExpandedSegment,
    setCurrentHighlightIndex,
    toggleUserBreakpoint,
  } = useSessionStore(
    (state) => ({
      setSelectedEventId: state.setSelectedEventId,
      setSelectedSessionId: state.setSelectedSessionId,
      setIsPlaying: state.setIsPlaying,
      setCurrentIndex: state.setCurrentIndex,
      setSpeed: state.setSpeed,
      setReplayMode: state.setReplayMode,
      setFocusEventId: state.setFocusEventId,
      setShowBlockedActions: state.setShowBlockedActions,
      toggleExpandedSegment: state.toggleExpandedSegment,
      setCurrentHighlightIndex: state.setCurrentHighlightIndex,
      toggleUserBreakpoint: state.toggleUserBreakpoint,
    }),
  )

  function seekReplayIndex(nextIndex: number) {
    const clampedIndex = Math.min(Math.max(nextIndex, 0), Math.max(derived.displayEvents.length - 1, 0))
    setCurrentIndex(clampedIndex)
    const event = derived.displayEvents[clampedIndex]
    if (event) {
      setSelectedEventId(event.id)
    }
  }

  function getHighlightForEvent(eventId: string | null): Highlight | null {
    if (!eventId) return null
    return derived.highlights.find((h) => h.event_id === eventId) ?? null
  }

  function goToHighlight(delta: number) {
    if (derived.highlightEvents.length === 0) return
    const newIndex = Math.max(0, Math.min(currentHighlightIndex + delta, derived.highlightEvents.length - 1))
    setCurrentHighlightIndex(newIndex)
    const event = derived.highlightEvents[newIndex]
    if (event) {
      setSelectedEventId(event.id)
      const displayIndex = derived.displayEvents.findIndex((e) => e.id === event.id)
      if (displayIndex >= 0) setCurrentIndex(displayIndex)
    }
  }

  // Build event tree for tree-aware navigation
  const eventTree = useMemo(() => {
    const parentMap = new Map<string, string | null>()
    const childrenMap = new Map<string, string[]>()

    for (const event of derived.displayEvents) {
      parentMap.set(event.id, event.parent_id)
      const parentId = event.parent_id
      if (parentId) {
        const siblings = childrenMap.get(parentId) ?? []
        siblings.push(event.id)
        childrenMap.set(parentId, siblings)
      }
    }

    const result = new Map<string, { parentId: string | null; childIds: string[]; siblingIds: string[] }>()
    for (const event of derived.displayEvents) {
      const parentId = parentMap.get(event.id) ?? null
      const childIds = childrenMap.get(event.id) ?? []
      const siblingIds = parentId ? (childrenMap.get(parentId) ?? []) : []
      result.set(event.id, { parentId, childIds, siblingIds })
    }
    return result
  }, [derived.displayEvents])

  function stepInto() {
    const current = derived.displayEvents[currentIndex]
    if (!current) return
    const node = eventTree.get(current.id)
    if (node && node.childIds.length > 0) {
      const firstChildIndex = derived.displayEvents.findIndex((e) => e.id === node.childIds[0])
      if (firstChildIndex >= 0) seekReplayIndex(firstChildIndex)
    }
  }

  function stepOver() {
    const current = derived.displayEvents[currentIndex]
    if (!current) return
    const node = eventTree.get(current.id)
    if (node) {
      const myIndex = node.siblingIds.indexOf(current.id)
      if (myIndex >= 0 && myIndex < node.siblingIds.length - 1) {
        const nextSiblingId = node.siblingIds[myIndex + 1]
        const nextIndex = derived.displayEvents.findIndex((e) => e.id === nextSiblingId)
        if (nextIndex >= 0) seekReplayIndex(nextIndex)
      }
    }
  }

  function stepOut() {
    const current = derived.displayEvents[currentIndex]
    if (!current) return
    const node = eventTree.get(current.id)
    if (node && node.parentId) {
      const parentNode = eventTree.get(node.parentId)
      if (parentNode) {
        const parentSiblingIndex = parentNode.siblingIds.indexOf(node.parentId!)
        if (parentSiblingIndex >= 0 && parentSiblingIndex < parentNode.siblingIds.length - 1) {
          const nextParentSiblingId = parentNode.siblingIds[parentSiblingIndex + 1]
          const nextIndex = derived.displayEvents.findIndex((e) => e.id === nextParentSiblingId)
          if (nextIndex >= 0) seekReplayIndex(nextIndex)
        }
      }
    }
  }

  // Compute canStep* booleans
  const currentEvent = currentIndex >= 0 && currentIndex < derived.displayEvents.length
    ? derived.displayEvents[currentIndex]
    : undefined
  const currentTreeNode = currentEvent ? eventTree.get(currentEvent.id) : undefined
  const canStepInto = !!(currentTreeNode && currentTreeNode.childIds.length > 0)
  const canStepOver = !!(currentTreeNode && currentEvent && currentTreeNode.siblingIds.indexOf(currentEvent.id) < currentTreeNode.siblingIds.length - 1)
  const canStepOut = !!(currentTreeNode && currentTreeNode.parentId)


  const selectedHighlight = getHighlightForEvent(selectedEventId)

  return (
    <main className="workspace slide-up">
      <SessionRailMemo />

      <section className="main-stage">
        {!selectedSessionId ? (
          <EmptyState
            icon="&#128065;"
            title="Select a session to inspect"
            description="Choose a captured run from the sidebar to replay its trace, inspect decisions, and search events."
          />
        ) : null}

        <ErrorBoundary>
          <ReplayBar disabled={!selectedSessionId} />
          <section className="panel panel--primary replay-panel">
            <SessionReplay
              events={derived.activeEvents}
              breakpointEventIds={derived.breakpointEventIds}
              currentIndex={currentIndex}
              isPlaying={isPlaying}
              onPlay={() => setIsPlaying(true)}
              onPause={() => setIsPlaying(false)}
              onStepForward={() => seekReplayIndex(currentIndex + 1)}
              onStepBackward={() => seekReplayIndex(currentIndex - 1)}
              onSeek={seekReplayIndex}
              speed={speed}
              onSpeedChange={setSpeed}
              showBlockedActions={showBlockedActions}
              onToggleShowBlockedActions={setShowBlockedActions}
              onStepInto={stepInto}
              onStepOver={stepOver}
              onStepOut={stepOut}
              canStepInto={canStepInto}
              canStepOver={canStepOver}
              canStepOut={canStepOut}
            />
            <div className="replay-summary">
              <span>Scope events: {derived.activeEvents.length}</span>
              <span>Nearest checkpoint: {replay?.nearest_checkpoint?.sequence ?? 'none'}</span>
              <span>Breakpoints hit: {replay?.breakpoints.length ?? 0}</span>
              <span>Failures: {replay?.failure_event_ids.length ?? 0}</span>
              {derived.replayRepairAttemptCount > 0 && (
                <span>Repair attempts: {derived.replayRepairAttemptCount}</span>
              )}
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
        </ErrorBoundary>

        <ErrorBoundary>
          <section className="panel panel--primary timeline-panel">
            {replayMode === 'highlights' && (
              <div className="highlight-nav">
                <button type="button" onClick={() => goToHighlight(-1)} disabled={currentHighlightIndex === 0}>
                  Prev
                </button>
                <span className="highlight-position">
                  {derived.highlightEvents.length > 0
                    ? `${currentHighlightIndex + 1} of ${derived.highlightEvents.length} highlights`
                    : 'No highlights in this session'}
                </span>
                <button
                  type="button"
                  onClick={() => goToHighlight(1)}
                  disabled={currentHighlightIndex >= derived.highlightEvents.length - 1}
                >
                  Next
                </button>
              </div>
            )}
            <TraceTimelineMemo
              events={derived.displayEvents}
              selectedEventId={selectedEventId}
              onSelectEvent={handleInspectEvent}
              highlightEventIds={derived.highlightEventIds}
              highlightsMap={derived.highlightsMap}
              showBlockedActions={showBlockedActions}
              onToggleShowBlockedActions={setShowBlockedActions}
            />
            {useSessionStore.getState().replayMode === 'highlights' &&
              replay?.collapsed_segments?.map((segment, index) => (
                <HighlightChip
                  key={index}
                  segment={segment}
                  isExpanded={expandedSegments.has(index)}
                  onToggle={() => toggleExpandedSegment(index)}
                >
                  {derived.mergedSessionEvents
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
        </ErrorBoundary>

        {derived.currentSession && (derived.currentSession.status === 'error' || (derived.currentSession.failure_count ?? 0) > 0) && (
          <WhyButton
            sessionId={derived.currentSession.id}
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
        {selectedSessionId && <CostPanel sessionId={selectedSessionId} />}
        <EventDetailMemo
          event={derived.activeEventForInspectors}
          ranking={derived.selectedRanking}
          diagnosis={derived.selectedDiagnosis}
          highlight={selectedHighlight}
          eventLookup={derived.eventLookup}
          checkpoints={derived.currentBundle?.checkpoints}
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
          userBreakpointIds={userBreakpointIds}
          onToggleBreakpoint={toggleUserBreakpoint}
        />
        <SimilarFailuresPanelMemo
          sessionId={selectedSessionId}
          failureEvent={derived.selectedEvent}
          onSelectSession={setSelectedSessionId}
          selectedSessionId={selectedSessionId}
        />
      </aside>
    </main>
  )
}
