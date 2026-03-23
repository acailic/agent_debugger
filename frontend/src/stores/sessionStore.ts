import { create } from 'zustand'
import type { Session, TraceEvent, TreeNode, ReplayState } from '../types'

interface SessionStore {
  sessions: Session[]
  currentSession: Session | null
  events: TraceEvent[]
  tree: TreeNode | null
  selectedEvent: TraceEvent | null
  replay: ReplayState
  isLoading: boolean
  error: string | null

  setSessions: (sessions: Session[]) => void
  setCurrentSession: (session: Session | null) => void
  setEvents: (events: TraceEvent[]) => void
  setTree: (tree: TreeNode | null) => void
  setSelectedEvent: (event: TraceEvent | null) => void
  setReplay: (replay: Partial<ReplayState>) => void
  addEvent: (event: TraceEvent) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  reset: () => void
}

const initialState = {
  sessions: [],
  currentSession: null,
  events: [],
  tree: null,
  selectedEvent: null,
  replay: {
    isPlaying: false,
    currentIndex: 0,
    speed: 1,
  },
  isLoading: false,
  error: null,
}

export const useSessionStore = create<SessionStore>((set) => ({
  ...initialState,

  setSessions: (sessions) => set({ sessions }),
  setCurrentSession: (session) => set({ currentSession: session }),
  setEvents: (events) => set({ events }),
  setTree: (tree) => set({ tree }),
  setSelectedEvent: (event) => set({ selectedEvent: event }),
  setReplay: (replay) => set((state) => ({
    replay: { ...state.replay, ...replay }
  })),
  addEvent: (event) => set((state) => ({
    events: [...state.events, event]
  })),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
  reset: () => set(initialState),
}))
