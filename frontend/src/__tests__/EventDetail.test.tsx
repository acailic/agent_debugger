import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EventDetail } from '../components/EventDetail'
import type { TraceEvent } from '../types'

const blockedEvent: TraceEvent = {
  id: 'blocked-1',
  session_id: 'session-1',
  timestamp: '2024-01-01T10:00:00Z',
  event_type: 'safety_check',
  parent_id: null,
  name: 'Safety Check',
  data: {},
  metadata: {},
  importance: 0.5,
  upstream_event_ids: [],
  policy_name: 'content_policy',
  outcome: 'block',
  risk_level: 'high',
  blocked_action: 'generate_content',
  reason: 'Policy violation',
  safe_alternative: 'summarize request',
  rationale: 'The requested content violates policy.',
}

describe('EventDetail', () => {
  it('surfaces blocked action context for blocked events', () => {
    render(
      <EventDetail
        event={blockedEvent}
        ranking={undefined}
        diagnosis={undefined}
        highlight={null}
        eventLookup={new Map()}
        onSelectEvent={vi.fn()}
        onFocusReplay={vi.fn()}
        onReplayFromHere={vi.fn()}
        onResetReplay={vi.fn()}
      />,
    )

    expect(screen.getByText('Blocked Action Context')).toBeInTheDocument()
    expect(screen.getByText(/Blocked:/)).toHaveTextContent('Blocked: generate_content')
    expect(screen.getByText(/Reason:/)).toHaveTextContent('Reason: Policy violation')
    expect(screen.getByText(/Safe alternative:/)).toHaveTextContent('Safe alternative: summarize request')
  })
})
