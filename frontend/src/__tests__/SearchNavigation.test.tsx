import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import * as client from '../api/client'
import { useSessionStore } from '../stores/sessionStore'
import type { ReplayResponse, TraceBundle, TraceEvent } from '../types'

vi.mock('../api/client', () => ({
  getSessions: vi.fn(),
  getTraceBundle: vi.fn(),
  getReplay: vi.fn(),
  getLiveSummary: vi.fn(),
  createEventSource: vi.fn(),
  searchTraces: vi.fn(),
}))

// Keep the real search UI, derived event ordering, store, and App loading effects.
// Replace unrelated panels with a readout of the event shown by replay/inspectors.
vi.mock('../components/TraceView', async () => {
  const { SearchPanel } = await import('../components/SearchPanel')
  const { useDerivedSessionData } = await import('../hooks/useDerivedSessionData')
  return {
    TraceView: function SearchTraceView() {
      const { currentReplayEvent, activeEventForInspectors } = useDerivedSessionData()
      return <>
        <SearchPanel />
        <output data-testid="replay-event">{currentReplayEvent?.id}</output>
        <output data-testid="inspected-event">{activeEventForInspectors?.id}</output>
      </>
    },
  }
})
vi.mock('../components/InspectView', () => ({ InspectView: () => null }))

function event(id: string, second: number, sessionId = 'session-1'): TraceEvent {
  return {
    id, session_id: sessionId, timestamp: `2024-01-01T00:00:0${second}Z`,
    event_type: 'decision', parent_id: null, name: id, data: {}, metadata: {},
    importance: 0.5, upstream_event_ids: [],
  }
}

function bundle(sessionId: string, events: TraceEvent[]): TraceBundle {
  return {
    session: {
      id: sessionId, agent_name: sessionId, framework: 'custom',
      started_at: '2024-01-01T00:00:00Z', ended_at: null, status: 'running',
      total_tokens: 0, total_cost_usd: 0, tool_calls: 0, llm_calls: 0, errors: 0,
      config: {}, tags: [],
    },
    events, checkpoints: [], tree: null,
    analysis: {
      event_rankings: [], failure_clusters: [], representative_failure_ids: [],
      high_replay_value_ids: [], failure_explanations: [], checkpoint_rankings: [],
      session_replay_value: 0, retention_tier: 'full',
      session_summary: { failure_count: 0, behavior_alert_count: 0, high_severity_count: 0, checkpoint_count: 0 },
      live_summary: {
        event_count: events.length, checkpoint_count: 0, rolling_summary: '', recent_alerts: [],
        latest: { decision_event_id: null, tool_event_id: null, safety_event_id: null, turn_event_id: null, policy_event_id: null, checkpoint_id: null },
      },
      behavior_alerts: [], highlights: [],
    },
  }
}

function replay(trace: TraceBundle, mode: ReplayResponse['mode'] = 'full'): ReplayResponse {
  return {
    session_id: trace.session.id, mode, focus_event_id: null, start_index: 0,
    events: trace.events, checkpoints: [], nearest_checkpoint: null, breakpoints: [],
    failure_event_ids: [], collapsed_segments: [], highlight_indices: [],
    stopped_at_breakpoint: false, stopped_at_index: null,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

const first = event('first', 0)
const target = event('target', 3)
const initialBundle = bundle('session-1', [first, event('second', 1), target])

async function openTrace() {
  render(<App />)
  await waitFor(() => expect(useSessionStore.getState().replay?.session_id).toBe('session-1'))
}

async function clickResult(result: TraceEvent) {
  act(() => useSessionStore.getState().setSearchResponse({
    query: result.name, session_id: null, event_type: null, total: 1, results: [result],
  }))
  await userEvent.click(screen.getByRole('button', { name: new RegExp(result.name) }))
}

function expectTarget(result: TraceEvent, index: number) {
  expect(screen.getByTestId('replay-event')).toHaveTextContent(result.id)
  expect(screen.getByTestId('inspected-event')).toHaveTextContent(result.id)
  expect(useSessionStore.getState()).toMatchObject({
    selectedSessionId: result.session_id, selectedEventId: result.id,
    currentIndex: index, replayMode: 'full', isPlaying: false,
  })
}

describe('search result navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useSessionStore.getState().reset()
    vi.mocked(client.getSessions).mockResolvedValue({ sessions: [initialBundle.session], total: 1, limit: 50, offset: 0 })
    vi.mocked(client.getTraceBundle).mockResolvedValue(initialBundle)
    vi.mocked(client.getReplay).mockResolvedValue(replay(initialBundle))
    vi.mocked(client.getLiveSummary).mockResolvedValue({
      session_id: 'session-1', live_summary: initialBundle.analysis.live_summary,
    })
    vi.mocked(client.createEventSource).mockReturnValue({ close: vi.fn() } as unknown as EventSource)
  })

  afterEach(() => {
    cleanup()
    useSessionStore.getState().reset()
  })

  it('seeks a same-session result and keeps it selected when replay loading finishes', async () => {
    await openTrace()
    const response = deferred<ReplayResponse>()
    vi.mocked(client.getReplay).mockReturnValue(response.promise)
    act(() => useSessionStore.getState().setIsPlaying(true))

    await clickResult(target)
    expectTarget(target, 2)
    await act(async () => response.resolve({
      ...replay(initialBundle), stopped_at_breakpoint: true, stopped_at_index: 1,
    }))
    expectTarget(target, 2)
    expect(useSessionStore.getState().pendingSearchResult).toBeNull()
  })

  it('finds a live-only result in chronological, deduplicated display order', async () => {
    await openTrace()
    const liveTarget = event('live-target', 2)
    act(() => {
      useSessionStore.getState().addLiveEvent(target)
      useSessionStore.getState().addLiveEvent(liveTarget)
    })

    await clickResult(liveTarget)
    await waitFor(() => expect(useSessionStore.getState().pendingSearchResult).toBeNull())
    expectTarget(liveTarget, 2)
  })

  it('waits for the destination bundle before requesting replay for another session', async () => {
    await openTrace()
    const otherTarget = event('other-target', 4, 'session-2')
    const otherBundle = bundle('session-2', [otherTarget, event('other-first', 0, 'session-2')])
    const bundleResponse = deferred<TraceBundle>()
    const replayResponse = deferred<ReplayResponse>()
    vi.mocked(client.getTraceBundle).mockReturnValue(bundleResponse.promise)
    vi.mocked(client.getReplay).mockClear().mockReturnValue(replayResponse.promise)

    await clickResult(otherTarget)
    expect(client.getTraceBundle).toHaveBeenCalledWith('session-2')
    expect(client.getReplay).not.toHaveBeenCalled()
    await act(async () => bundleResponse.resolve(otherBundle))
    expect(client.getReplay).toHaveBeenCalledWith('session-2', expect.objectContaining({ mode: 'full' }))
    await act(async () => replayResponse.resolve(replay(otherBundle)))
    expectTarget(otherTarget, 1)
  })

  it.each(['focus', 'failure', 'highlights'] as const)(
    'switches from %s to full replay and ignores the obsolete mode response', async (mode) => {
      await openTrace()
      const obsoleteResponse = deferred<ReplayResponse>()
      const fullResponse = deferred<ReplayResponse>()
      vi.mocked(client.getReplay).mockImplementation((_id, options) =>
        options?.mode === 'full' ? fullResponse.promise : obsoleteResponse.promise,
      )
      act(() => useSessionStore.getState().setReplayMode(mode))
      await clickResult(target)
      expectTarget(target, 2)
      await act(async () => obsoleteResponse.resolve(replay(initialBundle, mode)))
      expectTarget(target, 2)
      await act(async () => fullResponse.resolve(replay(initialBundle)))
      expectTarget(target, 2)
    },
  )
})
