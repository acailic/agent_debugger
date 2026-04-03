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

const repairAttemptEvent: TraceEvent = {
  id: 'repair-2',
  session_id: 'session-1',
  timestamp: '2024-01-01T10:02:00Z',
  event_type: 'repair_attempt',
  parent_id: null,
  name: 'Repair attempt',
  data: {},
  metadata: {},
  importance: 0.8,
  upstream_event_ids: [],
  attempted_fix: 'Increase timeout and retry the request',
  validation_result: 'Checks still flaky under load',
  repair_outcome: 'partial',
  repair_sequence_id: 'repair-seq-1',
  repair_diff: '+ timeout: 60\n+ retry: 2',
}

const priorRepairAttemptEvent: TraceEvent = {
  id: 'repair-1',
  session_id: 'session-1',
  timestamp: '2024-01-01T10:01:00Z',
  event_type: 'repair_attempt',
  parent_id: null,
  name: 'Repair attempt',
  data: {},
  metadata: {},
  importance: 0.6,
  upstream_event_ids: [],
  attempted_fix: 'Retry the request once',
  repair_outcome: 'failure',
  repair_sequence_id: 'repair-seq-1',
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
    expect(screen.getByText('generate_content')).toBeInTheDocument()
    expect(screen.getByText('Policy violation')).toBeInTheDocument()
    expect(screen.getByText('summarize request')).toBeInTheDocument()
  })

  it('surfaces repair attempt context and prior repairs', () => {
    render(
      <EventDetail
        event={repairAttemptEvent}
        ranking={undefined}
        diagnosis={undefined}
        highlight={null}
        eventLookup={new Map([
          [repairAttemptEvent.id, repairAttemptEvent],
          [priorRepairAttemptEvent.id, priorRepairAttemptEvent],
        ])}
        onSelectEvent={vi.fn()}
        onFocusReplay={vi.fn()}
        onReplayFromHere={vi.fn()}
        onResetReplay={vi.fn()}
      />,
    )

    expect(screen.getByText('Repair Attempt')).toBeInTheDocument()
    expect(screen.getByText('Increase timeout and retry the request')).toBeInTheDocument()
    expect(screen.getByText('Checks still flaky under load')).toBeInTheDocument()
    expect(screen.getByText('repair-seq-1')).toBeInTheDocument()
    expect(screen.getByText('Prior Repair Attempts')).toBeInTheDocument()
    expect(screen.getByText('Retry the request once')).toBeInTheDocument()
    expect(screen.getByText('+ timeout: 60')).toBeInTheDocument()
  })
})
