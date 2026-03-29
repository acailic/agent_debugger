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
} from '../types'

type AppTab = 'trace' | 'analytics'
type ReplayMode = 'full' | 'focus' | 'failure' | 'highlights'
type SessionSortMode = 'started_at' | 'replay_value'
type SearchScope = 'current' | 'all'

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

  // UI state
  activeTab: AppTab
  sessionSortMode: SessionSortMode
  selectedEventId: string | null
  focusEventId: string | null
  selectedCheckpointId: string | null
  currentHighlightIndex: number

  // Breakpoint config
  breakpointEventTypes: string
  breakpointToolNames: string
  breakpointConfidenceBelow: string
  breakpointSafetyOutcomes: string
  stopAtBreakpoint: boolean

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
  clearLiveEvents: () => void

  // UI actions
  setActiveTab: (tab: AppTab) => void
  setSessionSortMode: (mode: SessionSortMode) => void
  setSelectedEventId: (id: string | null) => void
  setFocusEventId: (id: string | null) => void
  setSelectedCheckpointId: (id: string | null) => void
  setCurrentHighlightIndex: (index: number) => void

  // Breakpoint config actions
  setBreakpointEventTypes: (types: string) => void
  setBreakpointToolNames: (names: string) => void
  setBreakpointConfidenceBelow: (value: string) => void
  setBreakpointSafetyOutcomes: (outcomes: string) => void
  setStopAtBreakpoint: (stop: boolean) => void

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

  // UI state
  activeTab: 'trace' as AppTab,
  sessionSortMode: 'replay_value' as SessionSortMode,
  selectedEventId: null,
  focusEventId: null,
  selectedCheckpointId: null,
  currentHighlightIndex: 0,

  // Breakpoint config
  breakpointEventTypes: 'error,refusal,policy_violation',
  breakpointToolNames: '',
  breakpointConfidenceBelow: '0.45',
  breakpointSafetyOutcomes: 'warn,block',
  stopAtBreakpoint: true,

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
  clearLiveEvents: () => set({ liveEvents: [] }),

  // UI actions
  setActiveTab: (activeTab) => set({ activeTab }),
  setSessionSortMode: (sessionSortMode) => set({ sessionSortMode }),
  setSelectedEventId: (selectedEventId) => set({ selectedEventId }),
  setFocusEventId: (focusEventId) => set({ focusEventId }),
  setSelectedCheckpointId: (selectedCheckpointId) => set({ selectedCheckpointId }),
  setCurrentHighlightIndex: (currentHighlightIndex) => set({ currentHighlightIndex }),

  // Breakpoint config actions
  setBreakpointEventTypes: (breakpointEventTypes) => set({ breakpointEventTypes }),
  setBreakpointToolNames: (breakpointToolNames) => set({ breakpointToolNames }),
  setBreakpointConfidenceBelow: (breakpointConfidenceBelow) => set({ breakpointConfidenceBelow }),
  setBreakpointSafetyOutcomes: (breakpointSafetyOutcomes) => set({ breakpointSafetyOutcomes }),
  setStopAtBreakpoint: (stopAtBreakpoint) => set({ stopAtBreakpoint }),

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
      // Need to call inspectEvent logic here
      set({ selectedEventId: result.id })
    }
  },

  resetSessionState: () => set({
    bundle: null,
    replay: null,
    liveEvents: [],
    liveSummary: null,
    streamConnected: false,
    selectedEventId: null,
    focusEventId: null,
    selectedCheckpointId: null,
    currentIndex: 0,
    isPlaying: false,
  }),

  reset: () => set(initialState),
}))
