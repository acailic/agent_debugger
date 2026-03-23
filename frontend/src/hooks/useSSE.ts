import { useEffect, useRef, useState, useCallback } from 'react'
import { useSessionStore } from '../stores/sessionStore'
import { createEventSource } from '../api/client'
import type { TraceEvent } from '../types'

interface ReconnectionState {
  isReconnecting: boolean
  retryCount: number
  maxRetries: number
  nextRetryDelay: number
}

const MAX_RETRIES = 5
const INITIAL_DELAY_MS = 1000
const MAX_DELAY_MS = 30000

export function useSSE(sessionId: string | null) {
  const eventSourceRef = useRef<EventSource | null>(null)
  const addEvent = useSessionStore((state) => state.addEvent)
  const setError = useSessionStore((state) => state.setError)
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryCountRef = useRef(0)
  const [reconnectionState, setReconnectionState] = useState<ReconnectionState>({
    isReconnecting: false,
    retryCount: 0,
    maxRetries: MAX_RETRIES,
    nextRetryDelay: 0,
  })

  const calculateBackoff = useCallback((retryCount: number): number => {
    // Exponential backoff with jitter
    const baseDelay = INITIAL_DELAY_MS * Math.pow(2, retryCount)
    const jitter = Math.random() * 0.3 * baseDelay // 30% jitter
    return Math.min(baseDelay + jitter, MAX_DELAY_MS)
  }, [])

  const clearRetryTimeout = useCallback(() => {
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current)
      retryTimeoutRef.current = null
    }
  }, [])

  const connect = useCallback(() => {
    if (!sessionId) return

    // Close any existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }

    const eventSource = createEventSource(sessionId)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => {
      // Connection established or reconnected successfully
      retryCountRef.current = 0
      setReconnectionState({
        isReconnecting: false,
        retryCount: 0,
        maxRetries: MAX_RETRIES,
        nextRetryDelay: 0,
      })
      setError(null)
    }

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as TraceEvent
        addEvent(data)
      } catch (e) {
        console.error('Failed to parse SSE event:', e)
      }
    }

    eventSource.onerror = () => {
      // Connection failed or lost
      eventSource.close()
      eventSourceRef.current = null

      const currentRetryCount = retryCountRef.current

      if (currentRetryCount >= MAX_RETRIES) {
        // Max retries exceeded
        setReconnectionState((prev) => ({ ...prev, isReconnecting: false }))
        setError('SSE connection failed. Maximum retry attempts exceeded.')
        return
      }

      // Calculate backoff and schedule reconnection
      const nextDelay = calculateBackoff(currentRetryCount)
      const nextRetryCount = currentRetryCount + 1
      retryCountRef.current = nextRetryCount

      setReconnectionState({
        isReconnecting: true,
        retryCount: nextRetryCount,
        maxRetries: MAX_RETRIES,
        nextRetryDelay: Math.round(nextDelay / 1000),
      })
      setError(`SSE connection lost. Reconnecting in ${Math.round(nextDelay / 1000)}s (attempt ${nextRetryCount}/${MAX_RETRIES})...`)

      clearRetryTimeout()
      retryTimeoutRef.current = setTimeout(() => {
        connect()
      }, nextDelay)
    }
  }, [sessionId, addEvent, setError, calculateBackoff, clearRetryTimeout])

  useEffect(() => {
    if (!sessionId) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      clearRetryTimeout()
      retryCountRef.current = 0
      setReconnectionState({
        isReconnecting: false,
        retryCount: 0,
        maxRetries: MAX_RETRIES,
        nextRetryDelay: 0,
      })
      setError(null)
      return
    }

    // Reset retry count for new session
    retryCountRef.current = 0
    connect()

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      clearRetryTimeout()
    }
  }, [sessionId, connect, clearRetryTimeout, setError])

  return {
    eventSource: eventSourceRef.current,
    reconnectionState,
  }
}
