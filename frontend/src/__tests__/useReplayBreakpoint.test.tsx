import { afterEach, describe, expect, it } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { useReplayBreakpoint } from '../hooks/useReplayBreakpoint'
import { useSessionStore } from '../stores/sessionStore'
import type { ReplayResponse, TraceEvent } from '../types'

function HookHarness() {
  useReplayBreakpoint()
  return null
}

const baseEvent: TraceEvent = {
  id: '',
  session_id: 'session-1',
  timestamp: '2024-01-01T10:00:00Z',
  event_type: 'decision',
  parent_id: null,
  name: '',
  data: {},
  metadata: {},
  importance: 0.5,
  upstream_event_ids: [],
}

function makeReplay(): ReplayResponse {
  const event1: TraceEvent = { ...baseEvent, id: 'event-1', chosen_action: 'search' } as TraceEvent
  const event2: TraceEvent = {
    ...baseEvent,
    id: 'event-2',
    event_type: 'error',
    error_type: 'ValueError',
    error_message: 'boom',
  }

  return {
    session_id: 'session-1',
    mode: 'focus',
    focus_event_id: 'event-2',
    start_index: 0,
    events: [event1, event2],
    checkpoints: [],
    nearest_checkpoint: null,
    breakpoints: [event2],
    failure_event_ids: ['event-2'],
    collapsed_segments: [],
    highlight_indices: [],
    stopped_at_breakpoint: true,
    stopped_at_index: 1,
  }
}

describe('useReplayBreakpoint', () => {
  afterEach(() => {
    useSessionStore.getState().reset()
  })

  it('pauses playback when stopAtBreakpoint is enabled and the current replay event is a breakpoint', async () => {
    useSessionStore.setState({
      replay: makeReplay(),
      currentIndex: 1,
      isPlaying: true,
      stopAtBreakpoint: true,
    })

    render(<HookHarness />)

    await waitFor(() => {
      expect(useSessionStore.getState().isPlaying).toBe(false)
    })
  })

  it('does not pause playback when stopAtBreakpoint is disabled', async () => {
    useSessionStore.setState({
      replay: makeReplay(),
      currentIndex: 1,
      isPlaying: true,
      stopAtBreakpoint: false,
    })

    render(<HookHarness />)

    await waitFor(() => {
      expect(useSessionStore.getState().isPlaying).toBe(true)
    })
  })
})
