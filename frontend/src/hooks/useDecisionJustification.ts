import { useEffect } from 'react'
import { useSessionStore } from '../stores/sessionStore'
import { getDecisionJustification } from '../api/client'
import { logger } from '../utils/logger'

/**
 * Custom hook for fetching the per-decision justification (why / evidence /
 * outcome / where-failed / policy) for the currently selected event.
 *
 * Refetches whenever the selected session or selected event changes. The
 * justification endpoint is decision-specific: a 404 means the selected event
 * is not a decision, which is treated as a silent no-op (no error surfaced)
 * rather than a failure.
 */
export function useDecisionJustification(): void {
  const selectedSessionId = useSessionStore((state) => state.selectedSessionId)
  const selectedEventId = useSessionStore((state) => state.selectedEventId)
  const setDecisionJustification = useSessionStore((state) => state.setDecisionJustification)
  const setDecisionJustificationLoading = useSessionStore(
    (state) => state.setDecisionJustificationLoading,
  )
  const setDecisionJustificationError = useSessionStore((state) => state.setDecisionJustificationError)

  useEffect(() => {
    if (!selectedSessionId || !selectedEventId) {
      setDecisionJustification(null)
      setDecisionJustificationLoading(false)
      setDecisionJustificationError(null)
      return
    }

    let ignore = false
    async function fetchJustification(sessionId: string, eventId: string): Promise<void> {
      setDecisionJustificationLoading(true)
      setDecisionJustificationError(null)
      try {
        const response = await getDecisionJustification(sessionId, eventId)
        if (!ignore) {
          setDecisionJustification(response.justification)
        }
      } catch (err) {
        if (!ignore) {
          // 404 => selected event is not a decision; hide the panel silently.
          const message = err instanceof Error ? err.message : 'Failed to load justification'
          if (message.includes(' 404 ')) {
            setDecisionJustification(null)
            setDecisionJustificationError(null)
          } else {
            logger.warn('Failed to load decision justification', { component: 'useDecisionJustification' })
            setDecisionJustification(null)
            setDecisionJustificationError(message)
          }
        }
      } finally {
        if (!ignore) {
          setDecisionJustificationLoading(false)
        }
      }
    }

    void fetchJustification(selectedSessionId, selectedEventId)
    return () => {
      ignore = true
    }
  }, [
    selectedSessionId,
    selectedEventId,
    setDecisionJustification,
    setDecisionJustificationLoading,
    setDecisionJustificationError,
  ])
}
