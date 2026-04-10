import { create } from 'zustand'
import type {
  Session,
  TraceEvent,
  TraceBundle,
  ReplayResponse,
  TraceSearchResponse,
  LiveSummary,
  DriftResponse,
  EventType,
  AppTab,
  ReplayMode,
  SearchScope,
  SessionSortMode,
} from '../types'

const BLOCKED_ACTIONS_STORAGE_KEY = 'peaky-peek:show-blocked-actions'
const BREAKPOINT_EVENT_TYPES_STORAGE_KEY = 'peaky-peek:breakpoint-event-types'
const BREAKPOINT_TOOL_NAMES_STORAGE_KEY = 'peaky-peek:breakpoint-tool-names'
const BREAKPOINT_CONFIDENCE_STORAGE_KEY = 'peaky-peek:breakpoint-confidence-below'
const BREAKPOINT_SAFETY_STORAGE_KEY = 'peaky-peek:breakpoint-safety-outcomes'
const STOP_AT_BREAKPOINT_STORAGE_KEY = 'peaky-peek:stop-at-breakpoint'

function loadBooleanPreference(key: string, fallback: boolean): boolean {
  if (typeof window === 'undefined') {
    return fallback
  }

  try {
    const stored = window.localStorage.getItem(key)
    if (stored === null) {
      return fallback
    }
    return stored === 'true'
  } catch {
    return fallback
  }
}

function saveBooleanPreference(key: string, value: boolean): void {
  if (typeof window === 'undefined') {
    return
  }

  try {
    window.localStorage.setItem(key, String(value))
  } catch {
    // Ignore storage failures; the in-memory store still reflects the preference.
  }
}

function loadStringPreference(key: string, fallback: string): string {
  if (typeof window === 'undefined') {
    return fallback
  }

  try {
    return window.localStorage.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}

function saveStringPreference(key: string, value: string): void {
  if (typeof window === 'undefined') {
    return
  }

  try {
    window.localStorage.setItem(key, value)
  } catch {
    // Ignore storage failures; the in-memory store still reflects the preference.
  }
}

function splitCsv(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

export interface ReplayBreakpointConfig {
  breakpointEventTypes: string
  breakpointToolNames: string
  breakpointConfidenceBelow: string
  breakpointSafetyOutcomes: string
  stopAtBreakpoint: boolean
}

export function buildReplayBreakpointParams(config: ReplayBreakpointConfig): {
  breakpointEventTypes: string[]
  breakpointToolNames: string[]
  breakpointConfidenceBelow: number | null
  breakpointSafetyOutcomes: string[]
  stopAtBreakpoint: boolean
} {
  const rawConfidence = config.breakpointConfidenceBelow.trim()
  const parsedConfidence = rawConfidence ? Number(rawConfidence) : null
  return {
    breakpointEventTypes: splitCsv(config.breakpointEventTypes),
    breakpointToolNames: splitCsv(config.breakpointToolNames),
    breakpointConfidenceBelow:
      parsedConfidence !== null && Number.isFinite(parsedConfidence) ? parsedConfidence : null,
    breakpointSafetyOutcomes: splitCsv(config.breakpointSafetyOutcomes),
    stopAtBreakpoint: config.stopAtBreakpoint,
  }
}

interface SessionStore {
  // Sessions list and selection
  sessions: Session[]
  selectedSessionId: string | null
  secondarySessionId: string | null

  // Bundle state
  bundle: TraceBundle | null
  secondaryBundle: TraceBundle | null

  // Replay state
  replay: ReplayResponse | null
  replayMode: ReplayMode
  currentIndex: number
  isPlaying: boolean
  speed: number
  collapseThreshold: number
  expandedSegments: Set<number>

  // Search state
  searchQuery: string
  searchEventType: '' | EventType
  searchScope: SearchScope
  searchResponse: TraceSearchResponse | null
  searchLoading: boolean
  searchError: string | null

  // Live streaming state
  liveEvents: TraceEvent[]
  liveSummary: LiveSummary | null
  streamConnected: boolean
  streamHealth: 'healthy' | 'degraded' | 'disconnected'
  streamReconnectAttempts: number
  streamParseFailures: number

  // UI state
  activeTab: AppTab
  sessionSortMode: SessionSortMode
  selectedEventId: string | null
  focusEventId: string | null
  selectedCheckpointId: string | null
  currentHighlightIndex: number
  showBlockedActions: boolean

  // Breakpoint config
  breakpointEventTypes: string
  breakpointToolNames: string
  breakpointConfidenceBelow: string
  breakpointSafetyOutcomes: string
  stopAtBreakpoint: boolean

  // User-defined breakpoints (set from EventDetail)
  userBreakpointIds: Set<string>

  // Loading/error states
  loading: boolean
  compareLoading: boolean
  error: string | null

  // Drift data
  driftData: DriftResponse | null
  driftLoading: boolean

  // Session actions
  setSessions: (sessions: Session[]) => void
  setSelectedSessionId: (id: string | null) => void
  setSecondarySessionId: (id: string | null) => void

  // Bundle actions
  setBundle: (bundle: TraceBundle | null) => void
  setSecondaryBundle: (bundle: TraceBundle | null) => void

  // Replay actions
  setReplay: (replay: ReplayResponse | null) => void
  setReplayMode: (mode: ReplayMode) => void
  setCurrentIndex: (index: number) => void
  setIsPlaying: (playing: boolean) => void
  setSpeed: (speed: number) => void
  setCollapseThreshold: (threshold: number) => void
  setExpandedSegments: (segments: Set<number>) => void
  toggleExpandedSegment: (index: number) => void

  // Search actions
  setSearchQuery: (query: string) => void
  setSearchEventType: (type: '' | EventType) => void
  setSearchScope: (scope: SearchScope) => void
  setSearchResponse: (response: TraceSearchResponse | null) => void
  setSearchLoading: (loading: boolean) => void
  setSearchError: (error: string | null) => void

  // Live streaming actions
  setLiveEvents: (events: TraceEvent[]) => void
  addLiveEvent: (event: TraceEvent) => void
  setLiveSummary: (summary: LiveSummary | null) => void
  setStreamConnected: (connected: boolean) => void
  setStreamHealth: (health: 'healthy' | 'degraded' | 'disconnected') => void
  setStreamReconnectAttempts: (attempts: number) => void
  setStreamParseFailures: (failures: number) => void
  clearLiveEvents: () => void

  // UI actions
  setActiveTab: (tab: AppTab) => void
  setSessionSortMode: (mode: SessionSortMode) => void
  setSelectedEventId: (id: string | null) => void
  setFocusEventId: (id: string | null) => void
  setSelectedCheckpointId: (id: string | null) => void
  setCurrentHighlightIndex: (index: number) => void
  setShowBlockedActions: (show: boolean) => void

  // Breakpoint config actions
  setBreakpointEventTypes: (types: string) => void
  setBreakpointToolNames: (names: string) => void
  setBreakpointConfidenceBelow: (value: string) => void
  setBreakpointSafetyOutcomes: (outcomes: string) => void
  setStopAtBreakpoint: (stop: boolean) => void

  // User breakpoint actions
  toggleUserBreakpoint: (eventId: string) => void
  clearUserBreakpoints: () => void

  // Loading/error actions
  setLoading: (loading: boolean) => void
  setCompareLoading: (loading: boolean) => void
  setError: (error: string | null) => void

  // Drift actions
  setDriftData: (data: DriftResponse | null) => void
  setDriftLoading: (loading: boolean) => void

  // Composite actions
  inspectEvent: (eventId: string, displayEvents: TraceEvent[]) => void
  jumpToSearchResult: (result: TraceEvent) => void
  resetSessionState: () => void
  reset: () => void
}

// Derived state selectors for commonly accessed computed values
export const sessionSelectors = {
  getCurrentSession: (state: SessionStore): Session | null => {
    return state.sessions.find((s) => s.id === state.selectedSessionId) ?? state.bundle?.session ?? null
  },

  getDisplayEvents: (state: SessionStore): TraceEvent[] => {
    const bundle = state.replayMode === 'full' ? state.bundle : state.secondaryBundle
    return bundle?.events ?? []
  },

  getFilteredSessions: (state: SessionStore): Session[] => {
    const sessions = [...state.sessions]
    if (state.sessionSortMode === 'replay_value') {
      return sessions.sort((a, b) => (b.replay_value ?? 0) - (a.replay_value ?? 0))
    }
    return sessions.sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime())
  },

  hasActiveSearch: (state: SessionStore): boolean => {
    return !!(state.searchQuery || state.searchEventType)
  },

  getLiveEventsCount: (state: SessionStore): number => {
    return state.liveEvents.length
  },

  isSessionLoaded: (state: SessionStore): boolean => {
    return !!state.bundle || !!state.secondaryBundle
  },

  getReplayBreakpointParams: (state: SessionStore): {
    breakpointEventTypes: string[]
    breakpointToolNames: string[]
    breakpointConfidenceBelow: number | null
    breakpointSafetyOutcomes: string[]
    stopAtBreakpoint: boolean
  } =>
    buildReplayBreakpointParams({
      breakpointEventTypes: state.breakpointEventTypes,
      breakpointToolNames: state.breakpointToolNames,
      breakpointConfidenceBelow: state.breakpointConfidenceBelow,
      breakpointSafetyOutcomes: state.breakpointSafetyOutcomes,
      stopAtBreakpoint: state.stopAtBreakpoint,
    }),
}

const initialState = {
  // Sessions list and selection
  sessions: [],
  selectedSessionId: null,
  secondarySessionId: null,

  // Bundle state
  bundle: null,
  secondaryBundle: null,

  // Replay state
  replay: null,
  replayMode: 'full' as ReplayMode,
  currentIndex: 0,
  isPlaying: false,
  speed: 1,
  collapseThreshold: 0.35,
  expandedSegments: new Set<number>(),

  // Search state
  searchQuery: '',
  searchEventType: '' as '' | EventType,
  searchScope: 'current' as SearchScope,
  searchResponse: null,
  searchLoading: false,
  searchError: null,

  // Live streaming state
  liveEvents: [],
  liveSummary: null,
  streamConnected: false,
  streamHealth: 'disconnected' as 'healthy' | 'degraded' | 'disconnected',
  streamReconnectAttempts: 0,
  streamParseFailures: 0,

  // UI state
  activeTab: 'trace' as AppTab,
  sessionSortMode: 'replay_value' as SessionSortMode,
  selectedEventId: null,
  focusEventId: null,
  selectedCheckpointId: null,
  currentHighlightIndex: 0,
  showBlockedActions: loadBooleanPreference(BLOCKED_ACTIONS_STORAGE_KEY, false),

  // Breakpoint config
  breakpointEventTypes: loadStringPreference(BREAKPOINT_EVENT_TYPES_STORAGE_KEY, 'error,refusal,policy_violation'),
  breakpointToolNames: loadStringPreference(BREAKPOINT_TOOL_NAMES_STORAGE_KEY, ''),
  breakpointConfidenceBelow: loadStringPreference(BREAKPOINT_CONFIDENCE_STORAGE_KEY, '0.45'),
  breakpointSafetyOutcomes: loadStringPreference(BREAKPOINT_SAFETY_STORAGE_KEY, 'warn,block'),
  stopAtBreakpoint: loadBooleanPreference(STOP_AT_BREAKPOINT_STORAGE_KEY, true),

  // User-defined breakpoints
  userBreakpointIds: new Set<string>(),

  // Loading/error states
  loading: true,
  compareLoading: false,
  error: null,

  // Drift data
  driftData: null,
  driftLoading: false,
}

export const useSessionStore = create<SessionStore>((set, get) => ({
  ...initialState,

  // Session actions
  setSessions: (sessions) => set({ sessions }),
  setSelectedSessionId: (selectedSessionId) => set({ selectedSessionId }),
  setSecondarySessionId: (secondarySessionId) => set({ secondarySessionId }),

  // Bundle actions
  setBundle: (bundle) => set({ bundle }),
  setSecondaryBundle: (secondaryBundle) => set({ secondaryBundle }),

  // Replay actions
  setReplay: (replay) => set({ replay }),
  setReplayMode: (replayMode) => set({ replayMode }),
  setCurrentIndex: (currentIndex) => set({ currentIndex }),
  setIsPlaying: (isPlaying) => set({ isPlaying }),
  setSpeed: (speed) => set({ speed }),
  setCollapseThreshold: (collapseThreshold) => set({ collapseThreshold, expandedSegments: new Set() }),
  setExpandedSegments: (expandedSegments) => set({ expandedSegments }),
  toggleExpandedSegment: (index) => set((state) => {
    const next = new Set(state.expandedSegments)
    if (next.has(index)) next.delete(index)
    else next.add(index)
    return { expandedSegments: next }
  }),

  // Search actions
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  setSearchEventType: (searchEventType) => set({ searchEventType }),
  setSearchScope: (searchScope) => set({ searchScope }),
  setSearchResponse: (searchResponse) => set({ searchResponse }),
  setSearchLoading: (searchLoading) => set({ searchLoading }),
  setSearchError: (searchError) => set({ searchError }),

  // Live streaming actions
  setLiveEvents: (liveEvents) => set({ liveEvents }),
  addLiveEvent: (event) => set((state) => {
    if (state.liveEvents.some((item) => item.id === event.id)) {
      return state
    }
    return { liveEvents: [...state.liveEvents, event] }
  }),
  setLiveSummary: (liveSummary) => set({ liveSummary }),
  setStreamConnected: (streamConnected) => set({ streamConnected }),
  setStreamHealth: (streamHealth) => set({ streamHealth }),
  setStreamReconnectAttempts: (streamReconnectAttempts) => set({ streamReconnectAttempts }),
  setStreamParseFailures: (streamParseFailures) => set({ streamParseFailures }),
  clearLiveEvents: () => set({ liveEvents: [] }),

  // UI actions
  setActiveTab: (activeTab) => set({ activeTab }),
  setSessionSortMode: (sessionSortMode) => set({ sessionSortMode }),
  setSelectedEventId: (selectedEventId) => set({ selectedEventId }),
  setFocusEventId: (focusEventId) => set({ focusEventId }),
  setSelectedCheckpointId: (selectedCheckpointId) => set({ selectedCheckpointId }),
  setCurrentHighlightIndex: (currentHighlightIndex) => set({ currentHighlightIndex }),
  setShowBlockedActions: (showBlockedActions) => {
    saveBooleanPreference(BLOCKED_ACTIONS_STORAGE_KEY, showBlockedActions)
    set({ showBlockedActions })
  },

  // Breakpoint config actions
  setBreakpointEventTypes: (breakpointEventTypes) => {
    saveStringPreference(BREAKPOINT_EVENT_TYPES_STORAGE_KEY, breakpointEventTypes)
    set({ breakpointEventTypes })
  },
  setBreakpointToolNames: (breakpointToolNames) => {
    saveStringPreference(BREAKPOINT_TOOL_NAMES_STORAGE_KEY, breakpointToolNames)
    set({ breakpointToolNames })
  },
  setBreakpointConfidenceBelow: (breakpointConfidenceBelow) => {
    saveStringPreference(BREAKPOINT_CONFIDENCE_STORAGE_KEY, breakpointConfidenceBelow)
    set({ breakpointConfidenceBelow })
  },
  setBreakpointSafetyOutcomes: (breakpointSafetyOutcomes) => {
    saveStringPreference(BREAKPOINT_SAFETY_STORAGE_KEY, breakpointSafetyOutcomes)
    set({ breakpointSafetyOutcomes })
  },
  setStopAtBreakpoint: (stopAtBreakpoint) => {
    saveBooleanPreference(STOP_AT_BREAKPOINT_STORAGE_KEY, stopAtBreakpoint)
    set({ stopAtBreakpoint })
  },

  // User breakpoint actions
  toggleUserBreakpoint: (eventId) => set((state) => {
    const next = new Set(state.userBreakpointIds)
    if (next.has(eventId)) {
      next.delete(eventId)
    } else {
      next.add(eventId)
    }
    return { userBreakpointIds: next }
  }),
  clearUserBreakpoints: () => set({ userBreakpointIds: new Set() }),

  // Loading/error actions
  setLoading: (loading) => set({ loading }),
  setCompareLoading: (compareLoading) => set({ compareLoading }),
  setError: (error) => set({ error }),

  // Drift actions
  setDriftData: (driftData) => set({ driftData }),
  setDriftLoading: (driftLoading) => set({ driftLoading }),

  // Composite actions
  inspectEvent: (eventId, displayEvents) => {
    set({ selectedEventId: eventId })
    const nextIndex = displayEvents.findIndex((event) => event.id === eventId)
    if (nextIndex >= 0) {
      set({ currentIndex: nextIndex })
    }
  },

  jumpToSearchResult: (result) => {
    const state = get()
    set({ replayMode: 'full' })
    if (result.session_id !== state.selectedSessionId) {
      set({ selectedSessionId: result.session_id, selectedEventId: result.id })
    } else {
      // Same session: use inspectEvent to properly update index
      const displayEvents = state.replayMode === 'full' ? state.bundle?.events : state.secondaryBundle?.events
      const events = displayEvents || []
      const nextIndex = events.findIndex((event) => event.id === result.id)
      set({ selectedEventId: result.id, currentIndex: nextIndex >= 0 ? nextIndex : 0 })
    }
  },

  resetSessionState: () => set({
    bundle: null,
    replay: null,
    liveEvents: [],
    liveSummary: null,
    streamConnected: false,
    streamHealth: 'disconnected',
    streamReconnectAttempts: 0,
    streamParseFailures: 0,
    selectedEventId: null,
    focusEventId: null,
    selectedCheckpointId: null,
    currentIndex: 0,
    isPlaying: false,
    userBreakpointIds: new Set(),
  }),

  reset: () => set({
    ...initialState,
    showBlockedActions: loadBooleanPreference(BLOCKED_ACTIONS_STORAGE_KEY, false),
    breakpointEventTypes: loadStringPreference(BREAKPOINT_EVENT_TYPES_STORAGE_KEY, 'error,refusal,policy_violation'),
    breakpointToolNames: loadStringPreference(BREAKPOINT_TOOL_NAMES_STORAGE_KEY, ''),
    breakpointConfidenceBelow: loadStringPreference(BREAKPOINT_CONFIDENCE_STORAGE_KEY, '0.45'),
    breakpointSafetyOutcomes: loadStringPreference(BREAKPOINT_SAFETY_STORAGE_KEY, 'warn,block'),
    stopAtBreakpoint: loadBooleanPreference(STOP_AT_BREAKPOINT_STORAGE_KEY, true),
    userBreakpointIds: new Set(),
  }),
}))
