import { useState, useEffect } from 'react'
import { fetchAlerts, updateAlertStatus, bulkUpdateAlertStatus } from '../api/client'
import type { AlertStatus, ManagedAlert } from '../types'

interface UseAlertsReturn {
  alerts: ManagedAlert[]
  loading: boolean
  error: string | null
  filters: Record<string, string>
  setFilter: (key: string, value: string) => void
  clearFilter: (key: string) => void
  clearAllFilters: () => void
  updateStatus: (alertId: string, status: AlertStatus, note?: string) => Promise<void>
  bulkUpdate: (alertIds: string[], status: AlertStatus) => Promise<void>
  refresh: () => Promise<void>
}

const DEFAULT_FILTERS: Record<string, string> = {}

export function useAlerts(initialFilters: Record<string, string> = DEFAULT_FILTERS): UseAlertsReturn {
  const [alerts, setAlerts] = useState<ManagedAlert[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<Record<string, string>>(initialFilters)
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  // Guard: reset loading when filters change (setState-during-render pattern)
  const [prevFilters, setPrevFilters] = useState(filters)
  if (!Object.is(prevFilters, filters)) {
    setPrevFilters(filters)
    setLoading(true)
    setError(null)
  }

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const response = await fetchAlerts(filters)
        if (!cancelled) {
          setAlerts(response.alerts)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load alerts')
          setAlerts([])
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    void load()
    return () => { cancelled = true }
  }, [filters, refreshTrigger])

  const setFilter = (key: string, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }))
  }

  const clearFilter = (key: string) => {
    setFilters((prev) => {
      const next = { ...prev }
      delete next[key]
      return next
    })
  }

  const clearAllFilters = () => {
    setFilters(DEFAULT_FILTERS)
  }

  const updateStatus = async (alertId: string, status: AlertStatus, note?: string) => {
    try {
      const updated = await updateAlertStatus(alertId, status, note)
      setAlerts((prev) => prev.map((alert) => (alert.id === alertId ? updated : alert)))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update alert status')
      throw err
    }
  }

  const bulkUpdate = async (alertIds: string[], status: AlertStatus) => {
    try {
      await bulkUpdateAlertStatus(alertIds, status)
      setRefreshTrigger(c => c + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to bulk update alerts')
      throw err
    }
  }

  const refresh = async () => {
    setLoading(true)
    setError(null)
    setRefreshTrigger(c => c + 1)
  }

  return {
    alerts,
    loading,
    error,
    filters,
    setFilter,
    clearFilter,
    clearAllFilters,
    updateStatus,
    bulkUpdate,
    refresh,
  }
}
