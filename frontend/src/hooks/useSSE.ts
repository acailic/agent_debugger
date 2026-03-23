import { useEffect, useRef } from 'react'
import { useSessionStore } from '../stores/sessionStore'
import { createEventSource } from '../api/client'
import type { TraceEvent } from '../types'

export function useSSE(sessionId: string | null) {
  const eventSourceRef = useRef<EventSource | null>(null)
  const addEvent = useSessionStore((state) => state.addEvent)

  useEffect(() => {
    if (!sessionId) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      return
    }

    const eventSource = createEventSource(sessionId)
    eventSourceRef.current = eventSource

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as TraceEvent
        addEvent(data)
      } catch (e) {
        console.error('Failed to parse SSE event:', e)
      }
    }

    eventSource.onerror = (error) => {
      console.error('SSE error:', error)
    }

    return () => {
      eventSource.close()
      eventSourceRef.current = null
    }
  }, [sessionId, addEvent])

  return eventSourceRef.current
}
