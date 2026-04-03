import { useEffect } from 'react'
import { useSessionStore } from '../stores/sessionStore'
import { getAgentDrift } from '../api/client'

/**
 * Custom hook for fetching agent drift data
 * Fetches drift information when the current session's agent changes
 */
export function useDriftData(): void {
  const currentSession = useSessionStore((state) =>
    state.sessions.find((session) => session.id === state.selectedSessionId) ??
    state.bundle?.session ??
    null
  )
  const setDriftData = useSessionStore((state) => state.setDriftData)
  const setDriftLoading = useSessionStore((state) => state.setDriftLoading)

  useEffect(() => {
    const agentName = currentSession?.agent_name
    if (!agentName) {
      setDriftData(null)
      setDriftLoading(false)
      return
    }

    let ignore = false
    async function fetchDrift(name: string): Promise<void> {
      setDriftLoading(true)
      try {
        const data = await getAgentDrift(name)
        if (!ignore) {
          setDriftData(data)
        }
      } catch (err) {
        if (!ignore) {
          console.warn('Failed to load drift data:', err)
          setDriftData(null)
        }
      } finally {
        if (!ignore) {
          setDriftLoading(false)
        }
      }
    }

    void fetchDrift(agentName)
    return () => {
      ignore = true
    }
  }, [currentSession?.agent_name, setDriftData, setDriftLoading])
}
