import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { SessionReplay } from '../components/SessionReplay'
import type { TraceEvent } from '../types'

const baseEvent: TraceEvent = {
  id: '',
  session_id: 'session-1',
  timestamp: '2024-01-01T10:00:00Z',
  event_type: 'llm_request',
  parent_id: null,
  name: '',
  data: {},
  metadata: {},
  importance: 0.5,
  upstream_event_ids: [],
}

function makeEvent(overrides: Partial<TraceEvent> & { id: string }): TraceEvent {
  return { ...baseEvent, ...overrides }
}

function renderReplay(events: TraceEvent[], overrides: Partial<ComponentProps<typeof SessionReplay>> = {}) {
  return render(
    <SessionReplay
      events={events}
      breakpointEventIds={[]}
      currentIndex={0}
      isPlaying={false}
      onPlay={vi.fn()}
      onPause={vi.fn()}
      onStepForward={vi.fn()}
      onStepBackward={vi.fn()}
      onSeek={vi.fn()}
      speed={1}
      onSpeedChange={vi.fn()}
      {...overrides}
    />,
  )
}

describe('SessionReplay', () => {
  it('shows blocked replay context when blocked actions are enabled', () => {
    const events = [
      makeEvent({ id: '1', event_type: 'decision', chosen_action: 'search_docs' }),
      makeEvent({
        id: '2',
        event_type: 'refusal',
        blocked_action: 'execute_code',
        reason: 'Unsafe request',
        name: 'Refusal',
      }),
    ]

    renderReplay(events, { currentIndex: 1, showBlockedActions: true })

    expect(screen.getByRole('checkbox')).toBeChecked()
    expect(screen.getByText('Blocked events in scope: 1')).toBeInTheDocument()
    expect(screen.getByText(/Blocked action: execute_code/)).toBeInTheDocument()
  })

  it('calls the blocked-action toggle callback from replay controls', async () => {
    const onToggleShowBlockedActions = vi.fn()
    const events = [makeEvent({ id: '1', event_type: 'decision', chosen_action: 'search_docs' })]

    renderReplay(events, {
      showBlockedActions: false,
      onToggleShowBlockedActions,
    })

    await userEvent.click(screen.getByRole('checkbox'))

    expect(onToggleShowBlockedActions).toHaveBeenCalledWith(true)
  })
})
