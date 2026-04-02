import { useSessionStore } from '../stores/sessionStore'
import type { TraceEvent } from '../types'

/**
 * Custom hook for event inspection composite action
 * Combines event selection with replay index updating
 */
export function useInspectEvent(displayEvents: TraceEvent[]) {
  const setSelectedEventId = useSessionStore((state) => state.setSelectedEventId)
  const setCurrentIndex = useSessionStore((state) => state.setCurrentIndex)

  /**
   * Inspect an event by selecting it and updating the replay index
   */
  function inspectEvent(eventId: string): void {
    setSelectedEventId(eventId)
    const nextIndex = displayEvents.findIndex((event) => event.id === eventId)
    if (nextIndex >= 0) {
      setCurrentIndex(nextIndex)
    }
  }

  return inspectEvent
}
