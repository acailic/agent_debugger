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
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadSummary = async () => {
    setLoading(true)
    setError(null)
    try {
      const [summaryData, trendingData] = await Promise.all([
        fetchAlertSummary(),
        fetchAlertTrending(days),
      ])
      setSummary(summaryData)
      setTrending(trendingData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load alert summary')
    } finally {
      setLoading(false)
    }
  }

  const refresh = async () => {
    await loadSummary()
  }

  useEffect(() => {
    void loadSummary()
  }, [days])

  return {
    summary,
    trending,
    loading,
    error,
    refresh,
  }
}
