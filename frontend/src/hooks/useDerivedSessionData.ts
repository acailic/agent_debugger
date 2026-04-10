import { useMemo } from 'react'
import { useSessionStore, buildReplayBreakpointParams } from '../stores/sessionStore'
import { useShallow } from 'zustand/react/shallow'
import type {
  Checkpoint,
  FailureExplanation,
  Highlight,
  TraceAnalysisRanking,
  TraceEvent,
} from '../types'

export interface DerivedSessionData {
  // Merged and filtered event collections
  mergedSessionEvents: TraceEvent[]
  activeEvents: TraceEvent[]
  displayEvents: TraceEvent[]
  highlightEvents: TraceEvent[]

  // Highlight data
  highlights: Highlight[]
  highlightEventIds: Set<string>
  highlightsMap: Map<string, Highlight>

  // Lookup maps
  eventLookup: Map<string, TraceEvent>
  checkpointLookup: Map<string, Checkpoint>
  checkpointRankingLookup: Map<string, TraceAnalysis['checkpoint_rankings'][number]>

  // Replay metadata
  breakpointEventIds: string[]
  replayRepairAttemptCount: number
  replayBreakpointParams: ReturnType<typeof buildReplayBreakpointParams>

  // Active event for inspection
  selectedEvent: TraceEvent | null
  currentReplayEvent: TraceEvent | null
  activeEventForInspectors: TraceEvent | null
  llmRequest: TraceEvent | null
  llmResponse: TraceEvent | null
  toolEvent: TraceEvent | null

  // Analysis lookups
  selectedRanking: TraceAnalysisRanking | undefined
  selectedDiagnosis: FailureExplanation | undefined

  // Session and checkpoint
  currentSession: import('../types').Session | null
  currentBundle: import('../types').TraceBundle | null
  selectedCheckpoint: Checkpoint | null
  selectedCheckpointRanking: TraceAnalysis['checkpoint_rankings'][number] | undefined
}

/** Subset of TraceAnalysis needed for checkpoint_rankings shape. */
interface TraceAnalysis {
  checkpoint_rankings: Array<{
    checkpoint_id: string
    event_id: string
    sequence: number
    importance: number
    replay_value: number
    restore_value: number
    retention_tier: 'full' | 'summarized' | 'downsampled'
  }>
}

export function useDerivedSessionData(): DerivedSessionData {
  // Subscribe to raw store state needed for derived computations
  const {
    bundle,
    replay,
    replayMode,
    selectedEventId,
    currentIndex,
    sessions,
    selectedSessionId,
    selectedCheckpointId,
    liveEvents,
    breakpointEventTypes,
    breakpointToolNames,
    breakpointConfidenceBelow,
    breakpointSafetyOutcomes,
    stopAtBreakpoint,
    userBreakpointIds,
  } = useSessionStore(
    useShallow((state) => ({
      bundle: state.bundle,
      replay: state.replay,
      replayMode: state.replayMode,
      selectedEventId: state.selectedEventId,
      currentIndex: state.currentIndex,
      sessions: state.sessions,
      selectedSessionId: state.selectedSessionId,
      selectedCheckpointId: state.selectedCheckpointId,
      liveEvents: state.liveEvents,
      breakpointEventTypes: state.breakpointEventTypes,
      breakpointToolNames: state.breakpointToolNames,
      breakpointConfidenceBelow: state.breakpointConfidenceBelow,
      breakpointSafetyOutcomes: state.breakpointSafetyOutcomes,
      stopAtBreakpoint: state.stopAtBreakpoint,
      userBreakpointIds: state.userBreakpointIds,
    })),
  )

  // Replay breakpoint params (memoized)
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

  // Merge bundle events with live events
  const mergedSessionEvents = useMemo(() => {
    const seen = new Set<string>()
    const merged = [...(bundle?.events ?? [])]
    for (const item of merged) seen.add(item.id)
    for (const event of liveEvents) {
      if (!seen.has(event.id)) {
        merged.push(event)
        seen.add(event.id)
      }
    }
    merged.sort((left, right) => left.timestamp.localeCompare(right.timestamp))
    return merged
  }, [bundle?.events, liveEvents])

  // Active events based on replay mode
  const activeEvents = replayMode === 'full' ? mergedSessionEvents : replay?.events ?? mergedSessionEvents

  // Highlight data
  const highlights = useMemo(() => bundle?.analysis.highlights ?? [], [bundle?.analysis.highlights])
  const highlightEventIds = useMemo(() => new Set(highlights.map((h) => h.event_id)), [highlights])
  const highlightsMap = useMemo(() => new Map(highlights.map((h) => [h.event_id, h])), [highlights])
  const highlightEvents = useMemo(
    () => mergedSessionEvents.filter((event) => highlightEventIds.has(event.id)),
    [mergedSessionEvents, highlightEventIds],
  )

  // Display events (highlights mode filters)
  const displayEvents = replayMode === 'highlights' ? highlightEvents : activeEvents

  // Selected event lookup
  const selectedEvent = useMemo(
    () =>
      activeEvents.find((event) => event.id === selectedEventId) ??
      mergedSessionEvents.find((event) => event.id === selectedEventId) ??
      null,
    [activeEvents, mergedSessionEvents, selectedEventId],
  )

  // Replay current event
  const currentReplayEvent = activeEvents[currentIndex] ?? null
  const activeEventForInspectors = selectedEvent ?? currentReplayEvent

  // Lookup maps
  const eventLookup = useMemo(() => new Map(mergedSessionEvents.map((event) => [event.id, event])), [mergedSessionEvents])
  const checkpointLookup = useMemo(
    () => new Map((bundle?.checkpoints ?? []).map((checkpoint) => [checkpoint.id, checkpoint])),
    [bundle?.checkpoints],
  )
  const checkpointRankingLookup = useMemo(
    () => new Map((bundle?.analysis.checkpoint_rankings ?? []).map((ranking) => [ranking.checkpoint_id, ranking])),
    [bundle?.analysis.checkpoint_rankings],
  )

  // Replay metadata
  const breakpointEventIds = useMemo(() => {
    const replayIds = replay?.breakpoints.map((e) => e.id) ?? []
    return [...new Set([...replayIds, ...userBreakpointIds])]
  }, [replay?.breakpoints, userBreakpointIds])
  const replayRepairAttemptCount = useMemo(
    () => activeEvents.filter((event) => event.event_type === 'repair_attempt').length,
    [activeEvents],
  )

  // LLM request/response for the active inspector event
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
      return (
        bundle?.events.find((event) => event.parent_id === activeEventForInspectors.id && event.event_type === 'llm_response') ??
        null
      )
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

  // Analysis lookups
  const selectedRanking = useMemo(
    () =>
      bundle?.analysis.event_rankings.find(
        (ranking) => ranking.event_id === (activeEventForInspectors?.id ?? selectedEventId ?? ''),
      ),
    [bundle?.analysis.event_rankings, activeEventForInspectors?.id, selectedEventId],
  )

  const selectedDiagnosis = useMemo(() => {
    const activeEventId = activeEventForInspectors?.id ?? selectedEventId ?? ''
    if (!activeEventId) return undefined
    return bundle?.analysis.failure_explanations.find((explanation) => explanation.failure_event_id === activeEventId)
  }, [activeEventForInspectors?.id, bundle?.analysis.failure_explanations, selectedEventId])

  // Session and checkpoint
  const currentSession = sessions.find((session) => session.id === selectedSessionId) ?? bundle?.session ?? null

  const selectedCheckpoint = useMemo(() => {
    if (selectedCheckpointId) {
      const fromLookup = checkpointLookup.get(selectedCheckpointId)
      if (fromLookup) return fromLookup
    }
    return replay?.nearest_checkpoint ? checkpointLookup.get(replay.nearest_checkpoint.id) ?? replay.nearest_checkpoint : null
  }, [selectedCheckpointId, checkpointLookup, replay?.nearest_checkpoint])

  const selectedCheckpointRanking = selectedCheckpoint
    ? checkpointRankingLookup.get(selectedCheckpoint.id)
    : undefined

  return {
    mergedSessionEvents,
    activeEvents,
    displayEvents,
    highlightEvents,
    highlights,
    highlightEventIds,
    highlightsMap,
    eventLookup,
    checkpointLookup,
    checkpointRankingLookup,
    breakpointEventIds,
    replayRepairAttemptCount,
    replayBreakpointParams,
    selectedEvent,
    currentReplayEvent,
    activeEventForInspectors,
    llmRequest,
    llmResponse,
    toolEvent,
    selectedRanking,
    selectedDiagnosis,
    currentSession,
    currentBundle: bundle ?? null,
    selectedCheckpoint,
    selectedCheckpointRanking,
  }
}
