import { useEffect } from 'react'
import { useSessionStore } from '../stores/sessionStore'
import { getEvidenceGraph } from '../api/client'
import { logger } from '../utils/logger'

/**
 * Custom hook for fetching the evidence-provenance graph for the selected
 * session. Refetches whenever the selected session changes. The graph exposes
 * every claim and the facts available to the agent (tool results, user input),
 * plus evidence / causal edges — letting the operator see which evidence each
 * claim relies on and which facts existed but were never cited.
 */
export function useEvidenceGraph(): void {
  const selectedSessionId = useSessionStore((state) => state.selectedSessionId)
  const setEvidenceGraph = useSessionStore((state) => state.setEvidenceGraph)
  const setEvidenceGraphLoading = useSessionStore((state) => state.setEvidenceGraphLoading)
  const setEvidenceGraphError = useSessionStore((state) => state.setEvidenceGraphError)

  useEffect(() => {
    if (!selectedSessionId) {
      setEvidenceGraph(null)
      setEvidenceGraphLoading(false)
      setEvidenceGraphError(null)
      return
    }

    let ignore = false
    async function fetchGraph(sessionId: string): Promise<void> {
      setEvidenceGraphLoading(true)
      setEvidenceGraphError(null)
      try {
        const response = await getEvidenceGraph(sessionId)
        if (!ignore) {
          setEvidenceGraph(response.graph)
        }
      } catch (err) {
        if (!ignore) {
          logger.warn('Failed to load evidence graph', { component: 'useEvidenceGraph' })
          setEvidenceGraph(null)
          setEvidenceGraphError(err instanceof Error ? err.message : 'Failed to load evidence graph')
        }
      } finally {
        if (!ignore) {
          setEvidenceGraphLoading(false)
        }
      }
    }

    void fetchGraph(selectedSessionId)
    return () => {
      ignore = true
    }
  }, [selectedSessionId, setEvidenceGraph, setEvidenceGraphLoading, setEvidenceGraphError])
}
