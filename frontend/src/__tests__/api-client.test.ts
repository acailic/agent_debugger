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
  })

  it('getSessions returns a promise with sessions array shape', async () => {
    const mockSessions = { sessions: [], total: 0, limit: 20, offset: 0 }
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve(mockSessions) } as Response)
    )

    const result = await getSessions()
    expect(result).toEqual(mockSessions)
  })

  it('getSessions throws on non-ok response', async () => {
    vi.useFakeTimers()
    try {
      globalThis.fetch = vi.fn(() =>
        Promise.resolve({ ok: false, status: 500, statusText: 'Internal Server Error' } as Response)
      )

      const result = expect(getSessions()).rejects.toThrow('API error: 500 Internal Server Error')
      await vi.runAllTimersAsync()
      await result
    } finally {
      vi.useRealTimers()
    }
  })
})
