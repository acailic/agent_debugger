import { describe, it, expect, vi } from 'vitest'
import {
  getSessions,
  getTraceBundle,
  getReplay,
  getAnalysis,
  getLiveSummary,
  searchTraces,
  getAgentBaseline,
  getAgentDrift,
  getAnalytics,
  getSimilarFailures,
  createEventSource,
} from '../api/client'

describe('API client', () => {
  it('exports all expected functions', () => {
    expect(typeof getSessions).toBe('function')
    expect(typeof getTraceBundle).toBe('function')
    expect(typeof getReplay).toBe('function')
    expect(typeof getAnalysis).toBe('function')
    expect(typeof createEventSource).toBe('function')
    expect(typeof getLiveSummary).toBe('function')
    expect(typeof searchTraces).toBe('function')
    expect(typeof getAgentBaseline).toBe('function')
    expect(typeof getAgentDrift).toBe('function')
    expect(typeof getAnalytics).toBe('function')
    expect(typeof getSimilarFailures).toBe('function')
  })

  it('getSessions returns a promise with sessions array shape', async () => {
    const mockSessions = { sessions: [], total: 0, limit: 20, offset: 0 }
    globalThis.fetch = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify(mockSessions), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    )

    const result = await getSessions()
    expect(result).toEqual(mockSessions)
  })

  it('deduplicates concurrent requests without sharing a consumed response body', async () => {
    const mockSessions = { sessions: [], total: 0, limit: 20, offset: 0 }
    const fetchMock = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify(mockSessions), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    )
    globalThis.fetch = fetchMock as typeof fetch

    const [first, second] = await Promise.all([getSessions(), getSessions()])

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(first).toEqual(mockSessions)
    expect(second).toEqual(mockSessions)
  })

  it('validates the drift and baseline response contract', async () => {
    const mockBaseline = {
      agent_name: 'agent-a',
      session_count: 12,
      total_llm_calls: 30,
      total_tool_calls: 18,
      total_tokens: 4200,
      total_cost_usd: 1.23,
      avg_llm_calls_per_session: 2.5,
      avg_tool_calls_per_session: 1.5,
      avg_tokens_per_session: 350,
      avg_cost_per_session: 0.1025,
      error_rate: 0.0833,
      avg_duration_seconds: 14.2,
    }
    const mockDrift = {
      agent_name: 'agent-a',
      baseline_session_count: 12,
      recent_session_count: 4,
      baseline: mockBaseline,
      current: {
        ...mockBaseline,
        session_count: 4,
        total_llm_calls: 12,
        total_tool_calls: 6,
        total_tokens: 1800,
        total_cost_usd: 0.51,
        avg_llm_calls_per_session: 3,
        avg_tool_calls_per_session: 1.5,
        avg_tokens_per_session: 450,
        avg_cost_per_session: 0.1275,
        error_rate: 0.125,
        avg_duration_seconds: 18.7,
      },
      alerts: [
        {
          metric: 'avg_cost_per_session',
          metric_label: 'Cost per session',
          baseline_value: 0.1025,
          current_value: 0.1275,
          change_percent: 24.4,
          severity: 'warning',
          description: 'Cost per session increased from 0.10 to 0.13',
        },
      ],
      message: 'Drift detected',
    }

    globalThis.fetch = vi.fn((input: RequestInfo | URL) => {
      const url = input.toString()
      if (url.includes('/baseline')) {
        return Promise.resolve(new Response(JSON.stringify(mockBaseline), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }))
      }
      if (url.includes('/drift')) {
        return Promise.resolve(new Response(JSON.stringify(mockDrift), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }))
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`))
    }) as typeof fetch

    await expect(getAgentBaseline('agent-a')).resolves.toEqual(mockBaseline)
    await expect(getAgentDrift('agent-a')).resolves.toEqual(mockDrift)
  })

  it('getSessions throws on non-ok response', async () => {
    vi.useFakeTimers()
    try {
      globalThis.fetch = vi.fn(() =>
        Promise.resolve(new Response('internal error', {
          status: 500,
          statusText: 'Internal Server Error',
        }))
      )

      const result = expect(getSessions()).rejects.toThrow('API error: 500 Internal Server Error')
      await vi.runAllTimersAsync()
      await result
    } finally {
      vi.useRealTimers()
    }
  })

  it('serializes similar failures params into query string', async () => {
    const payload = { session_id: 'session-1', failure_event_id: 'event-1', similar_failures: [], total: 0 }

    const fetchMock = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })),
    )
    globalThis.fetch = fetchMock as typeof fetch

    await getSimilarFailures({ sessionId: 'session-1', failureEventId: 'event-1', limit: 3 })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const firstCall = fetchMock.mock.calls[0] as unknown as [RequestInfo | URL, ...unknown[]]
    const calledUrl = firstCall ? String(firstCall[0]) : ''
    expect(calledUrl).toContain('/api/sessions/session-1/similar-failures?')
    expect(calledUrl).toContain('failure_event_id=event-1')
    expect(calledUrl).toContain('limit=3')
  })

  it('serializes breakpoint replay params into query string', async () => {
    const replayResponse = {
      session_id: 'session-1',
      mode: 'focus',
      focus_event_id: 'event-1',
      start_index: 0,
      events: [],
      checkpoints: [],
      nearest_checkpoint: null,
      breakpoints: [],
      failure_event_ids: [],
      collapsed_segments: [],
      highlight_indices: [],
      stopped_at_breakpoint: true,
      stopped_at_index: 0,
    }

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      void input
      return Promise.resolve(new Response(JSON.stringify(replayResponse), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    })
    globalThis.fetch = fetchMock as typeof fetch

    await getReplay('session-1', {
      mode: 'focus',
      focusEventId: 'event-1',
      breakpointEventTypes: ['error', 'decision'],
      breakpointToolNames: ['search'],
      breakpointConfidenceBelow: 0.4,
      breakpointSafetyOutcomes: ['warn', 'block'],
      stopAtBreakpoint: true,
      collapseThreshold: 0.35,
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const calledUrl = String((fetchMock.mock.calls as string[][])[0][0])
    expect(calledUrl).toContain('/api/sessions/session-1/replay?')
    expect(calledUrl).toContain('mode=focus')
    expect(calledUrl).toContain('focus_event_id=event-1')
    expect(calledUrl).toContain('breakpoint_event_types=error%2Cdecision')
    expect(calledUrl).toContain('breakpoint_tool_names=search')
    expect(calledUrl).toContain('breakpoint_confidence_below=0.4')
    expect(calledUrl).toContain('breakpoint_safety_outcomes=warn%2Cblock')
    expect(calledUrl).toContain('stop_at_breakpoint=true')
    expect(calledUrl).toContain('collapse_threshold=0.35')
  })
})
