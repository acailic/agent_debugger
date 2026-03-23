import { useSessionStore } from '../stores/sessionStore'
import { getTraceBundle } from '../api/client'

export function useTrace(sessionId: string | null) {
  const { setEvents, setTree, setLoading, setError } = useSessionStore()

  async function loadTrace() {
    if (!sessionId) return

    setLoading(true)
    setError(null)

    try {
      const bundle = await getTraceBundle(sessionId)
      setEvents(bundle.events)
      setTree(bundle.tree)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load trace')
    } finally {
      setLoading(false)
    }
  }

  return { loadTrace }
}
