import { useEffect } from 'react'
import { useSessionStore } from '../stores/sessionStore'

/**
 * Custom hook for managing breakpoint-based replay stopping
 * Automatically pauses replay when a breakpoint event is encountered
 */
export function useReplayBreakpoint(): void {
  const isPlaying = useSessionStore((state) => state.isPlaying)
  const currentIndex = useSessionStore((state) => state.currentIndex)
  const replay = useSessionStore((state) => state.replay)
  const breakpointEventIdSet = new Set(replay?.breakpoints.map((event) => event.id) ?? [])
  const setIsPlaying = useSessionStore((state) => state.setIsPlaying)

  useEffect(() => {
    if (!isPlaying || currentIndex === 0) return

    const currentReplayEvent = replay?.events[currentIndex]
    if (!currentReplayEvent) return

    if (breakpointEventIdSet.has(currentReplayEvent.id)) {
      setIsPlaying(false)
    }
  }, [breakpointEventIdSet, currentIndex, isPlaying, replay, setIsPlaying])
}
