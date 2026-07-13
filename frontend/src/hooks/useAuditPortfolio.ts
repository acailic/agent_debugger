import { useEffect } from 'react'
import { useSessionStore } from '../stores/sessionStore'
import { getAuditPortfolio } from '../api/client'
import { logger } from '../utils/logger'

/**
 * Custom hook for fetching the cross-session audit portfolio (fleet-level
 * trust / verification / failure aggregate). The portfolio is independent of
 * the selected session, so it is fetched once on mount. It surfaces the
 * least-trustworthy runs and recurring failure modes across the whole fleet.
 */
export function useAuditPortfolio(): void {
  const setPortfolioReport = useSessionStore((state) => state.setPortfolioReport)
  const setPortfolioLoading = useSessionStore((state) => state.setPortfolioLoading)
  const setPortfolioError = useSessionStore((state) => state.setPortfolioError)

  useEffect(() => {
    let ignore = false
    async function fetchPortfolio(): Promise<void> {
      setPortfolioLoading(true)
      setPortfolioError(null)
      try {
        const response = await getAuditPortfolio(50)
        if (!ignore) {
          setPortfolioReport(response)
        }
      } catch (err) {
        if (!ignore) {
          logger.warn('Failed to load audit portfolio', { component: 'useAuditPortfolio' })
          setPortfolioReport(null)
          setPortfolioError(err instanceof Error ? err.message : 'Failed to load audit portfolio')
        }
      } finally {
        if (!ignore) {
          setPortfolioLoading(false)
        }
      }
    }

    void fetchPortfolio()
    return () => {
      ignore = true
    }
  }, [setPortfolioReport, setPortfolioLoading, setPortfolioError])
}
