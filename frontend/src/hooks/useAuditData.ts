import { useEffect } from 'react'
import { useSessionStore } from '../stores/sessionStore'
import { getSessionAudit } from '../api/client'
import { logger } from '../utils/logger'

/**
 * Custom hook for fetching the audit / trust report for the selected session.
 * Refetches whenever the selected session changes. The report answers the five
 * operator questions (what / why / evidence / outcome / where-failed) and
 * carries an explainable trust score.
 */
export function useAuditData(): void {
  const selectedSessionId = useSessionStore((state) => state.selectedSessionId)
  const setAuditReport = useSessionStore((state) => state.setAuditReport)
  const setAuditLoading = useSessionStore((state) => state.setAuditLoading)
  const setAuditError = useSessionStore((state) => state.setAuditError)

  useEffect(() => {
    if (!selectedSessionId) {
      setAuditReport(null)
      setAuditLoading(false)
      setAuditError(null)
      return
    }

    let ignore = false
    async function fetchAudit(sessionId: string): Promise<void> {
      setAuditLoading(true)
      setAuditError(null)
      try {
        const response = await getSessionAudit(sessionId)
        if (!ignore) {
          setAuditReport(response.audit)
        }
      } catch (err) {
        if (!ignore) {
          logger.warn('Failed to load audit report', { component: 'useAuditData' })
          setAuditReport(null)
          setAuditError(err instanceof Error ? err.message : 'Failed to load audit report')
        }
      } finally {
        if (!ignore) {
          setAuditLoading(false)
        }
      }
    }

    void fetchAudit(selectedSessionId)
    return () => {
      ignore = true
    }
  }, [selectedSessionId, setAuditReport, setAuditLoading, setAuditError])
}
