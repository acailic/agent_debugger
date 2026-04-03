import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SimilarFailuresPanel } from '../components/SimilarFailuresPanel'
import type { TraceEvent } from '../types'
import { getSimilarFailures } from '../api/client'

vi.mock('../api/client', () => ({
  getSimilarFailures: vi.fn(),
}))

const failureEvent: TraceEvent = {
  id: 'event-1',
  session_id: 'session-1',
  timestamp: '2026-04-03T10:00:00Z',
  event_type: 'error',
  parent_id: null,
  name: 'Runtime error',
  data: {},
  metadata: {},
  importance: 0.8,
  upstream_event_ids: [],
  error: 'search timeout after 30 seconds',
  error_type: 'RuntimeError',
  error_message: 'search timeout after 30 seconds',
}

describe('SimilarFailuresPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads and renders similar failures for a failure event', async () => {
    vi.mocked(getSimilarFailures).mockResolvedValue({
      session_id: 'session-1',
      failure_event_id: 'event-1',
      total: 1,
      similar_failures: [
        {
          session_id: 'session-2',
          agent_name: 'agent-b',
          framework: 'pytest',
          started_at: '2026-04-02T10:00:00Z',
          failure_type: 'error',
          failure_mode: 'runtime_error',
          root_cause: 'RuntimeError: search timeout after 30 seconds',
          similarity: 0.82,
          fix_note: 'increase timeout',
        },
      ],
    })

    const onSelectSession = vi.fn()
    render(
      <SimilarFailuresPanel
        sessionId="session-1"
        failureEvent={failureEvent}
        onSelectSession={onSelectSession}
        selectedSessionId={null}
      />,
    )

    await waitFor(() => {
      expect(getSimilarFailures).toHaveBeenCalledWith({
        sessionId: 'session-1',
        failureEventId: 'event-1',
        limit: 5,
      })
    })

    expect(await screen.findByText('RuntimeError: search timeout after 30 seconds')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /similar failure in session session-2/i }))
    expect(onSelectSession).toHaveBeenCalledWith('session-2')
  })

  it('does not render for non-failure events', () => {
    const nonFailureEvent: TraceEvent = {
      ...failureEvent,
      event_type: 'tool_call',
      error: undefined,
      error_message: undefined,
      error_type: undefined,
    }

    render(
      <SimilarFailuresPanel
        sessionId="session-1"
        failureEvent={nonFailureEvent}
        onSelectSession={vi.fn()}
        selectedSessionId={null}
      />,
    )

    expect(screen.queryByText('Historically similar failures')).not.toBeInTheDocument()
    expect(getSimilarFailures).not.toHaveBeenCalled()
  })
})
