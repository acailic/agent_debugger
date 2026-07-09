import { useEffect, useState } from 'react'
import { fetchAlertSummary, fetchAlertTrending } from '../api/client'
import type { AlertSummary, AlertTrendingPoint } from '../types'

interface UseAlertSummaryReturn {
  summary: AlertSummary | null
  trending: AlertTrendingPoint[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}

export function useAlertSummary(days: number = 7): UseAlertSummaryReturn {
  const [summary, setSummary] = useState<AlertSummary | null>(null)
  const [trending, setTrending] = useState<AlertTrendingPoint[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  // Guard: reset loading when days changes (setState-during-render pattern)
  const [prevDays, setPrevDays] = useState(days)
  if (prevDays !== days) {
    setPrevDays(days)
    setLoading(true)
    setError(null)
  }

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const [summaryData, trendingData] = await Promise.all([
          fetchAlertSummary(),
          fetchAlertTrending(days),
        ])
        if (!cancelled) {
          setSummary(summaryData)
          setTrending(trendingData)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load alert summary')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    void load()
    return () => { cancelled = true }
  }, [days, refreshTrigger])

  const refresh = async () => {
    setLoading(true)
    setError(null)
    setRefreshTrigger(c => c + 1)
  }

  return {
    summary,
    trending,
    loading,
    error,
    refresh,
  }
}
