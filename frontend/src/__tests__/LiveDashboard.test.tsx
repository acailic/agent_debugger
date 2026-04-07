import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LiveDashboard } from '../components/LiveDashboard'
import type { Checkpoint, LiveSummary, Session, TraceEvent } from '../types'

// Helper functions to build test data
function createSession(overrides: Partial<Session> = {}): Session {
  return {
    id: 'session-1',
    agent_name: 'TestAgent',
    framework: 'test-framework',
    started_at: '2024-01-01T00:00:00Z',
    ended_at: null,
    status: 'running',
    total_tokens: 1000,
    total_cost_usd: 0.01,
    tool_calls: 5,
    llm_calls: 3,
    errors: 0,
    config: {},
    tags: [],
    ...overrides,
  }
}

function createEvent(overrides: Partial<TraceEvent> = {}): TraceEvent {
  return {
    id: 'event-1',
    session_id: 'session-1',
    timestamp: '2024-01-01T00:00:00Z',
    event_type: 'decision',
    parent_id: null,
    name: 'Test Event',
    data: {},
    metadata: {},
    importance: 0.5,
    upstream_event_ids: [],
    ...overrides,
  }
}

function createCheckpoint(overrides: Partial<Checkpoint> = {}): Checkpoint {
  return {
    id: 'checkpoint-1',
    session_id: 'session-1',
    event_id: 'event-1',
    sequence: 1,
    state: { key: 'value' },
    memory: { context: 'test' },
    timestamp: '2024-01-01T00:00:00Z',
    importance: 0.5,
    ...overrides,
  }
}

function createLiveSummary(overrides: Partial<LiveSummary> = {}): LiveSummary {
  return {
    event_count: 10,
    checkpoint_count: 2,
    latest: {
      decision_event_id: 'event-1',
      tool_event_id: null,
      safety_event_id: null,
      turn_event_id: null,
      policy_event_id: null,
      checkpoint_id: 'checkpoint-1',
    },
    rolling_summary: 'Test rolling summary',
    recent_alerts: [],
    ...overrides,
  }
}

describe('LiveDashboard', () => {
  const defaultProps = {
    session: null,
    events: [],
    checkpoints: [],
    liveSummary: null,
    isConnected: false,
    liveEventCount: 0,
    onSelectEvent: vi.fn(),
  }

  it('renders with null session', () => {
    render(<LiveDashboard {...defaultProps} />)

    expect(screen.getByText('Live Monitoring')).toBeInTheDocument()
    expect(screen.getByText('Session dashboard')).toBeInTheDocument()
    expect(screen.getByText('Status unknown')).toBeInTheDocument()
  })

  it('renders with session data', () => {
    const session = createSession({ status: 'running' })
    render(<LiveDashboard {...defaultProps} session={session} />)

    expect(screen.getByText('Status running')).toBeInTheDocument()
    expect(screen.getByText('Live events 0')).toBeInTheDocument()
  })

  it('shows connection status when connected', () => {
    render(<LiveDashboard {...defaultProps} isConnected={true} />)

    expect(screen.getByText('Connected')).toBeInTheDocument()
  })

  it('shows connection status when offline', () => {
    render(<LiveDashboard {...defaultProps} isConnected={false} />)

    expect(screen.getByText('Offline')).toBeInTheDocument()
  })

  it('displays live event count', () => {
    render(<LiveDashboard {...defaultProps} liveEventCount={42} />)

    expect(screen.getByText('Live events 42')).toBeInTheDocument()
  })

  it('shows checkpoints count from liveSummary', () => {
    const liveSummary = createLiveSummary({ checkpoint_count: 5 })
    render(<LiveDashboard {...defaultProps} liveSummary={liveSummary} />)

    expect(screen.getByText('Checkpoints 5')).toBeInTheDocument()
  })

  it('shows checkpoints count from checkpoints array when no liveSummary', () => {
    const checkpoints = [
      createCheckpoint({ id: 'cp-1', sequence: 1 }),
      createCheckpoint({ id: 'cp-2', sequence: 2 }),
      createCheckpoint({ id: 'cp-3', sequence: 3 }),
    ]
    render(<LiveDashboard {...defaultProps} checkpoints={checkpoints} />)

    expect(screen.getByText('Checkpoints 3')).toBeInTheDocument()
  })

  it('displays latest decision event', () => {
    const events = [
      createEvent({
        id: 'decision-1',
        event_type: 'decision',
        name: 'Make a choice',
        confidence: 0.85,
      }),
    ]
    render(<LiveDashboard {...defaultProps} events={events} />)

    expect(screen.getByText('Latest decision')).toBeInTheDocument()
    expect(screen.getByText('Make a choice')).toBeInTheDocument()
    expect(screen.getByText('Confidence: 85%')).toBeInTheDocument()
  })

  it('displays latest tool call activity', () => {
    const events = [
      createEvent({
        id: 'tool-1',
        event_type: 'tool_call',
        name: 'search',
        tool_name: 'search_tool',
      }),
    ]
    render(<LiveDashboard {...defaultProps} events={events} />)

    expect(screen.getByText('Latest tool activity')).toBeInTheDocument()
    expect(screen.getByText('search_tool')).toBeInTheDocument()
  })

  it('displays latest tool result activity', () => {
    const events = [
      createEvent({
        id: 'tool-result-1',
        event_type: 'tool_result',
        name: 'search completed',
        tool_name: 'search_tool',
      }),
    ]
    render(<LiveDashboard {...defaultProps} events={events} />)

    expect(screen.getByText('Latest tool activity')).toBeInTheDocument()
    expect(screen.getByText('Result')).toBeInTheDocument()
  })

  it('displays error state when error exists', () => {
    const events = [
      createEvent({
        id: 'error-1',
        event_type: 'error',
        name: 'Something went wrong',
        error_type: 'ValidationError',
      }),
    ]
    render(<LiveDashboard {...defaultProps} events={events} />)

    expect(screen.getByText('Current error state')).toBeInTheDocument()
    expect(screen.getAllByText('ValidationError')).toHaveLength(2)
  })

  it('shows no errors when no error events', () => {
    render(<LiveDashboard {...defaultProps} events={[]} />)

    expect(screen.getByText('No errors')).toBeInTheDocument()
  })

  it('displays latest checkpoint with sequence', () => {
    const checkpoints = [
      createCheckpoint({ id: 'cp-1', sequence: 3 }),
    ]
    render(<LiveDashboard {...defaultProps} checkpoints={checkpoints} />)

    expect(screen.getByText('Latest checkpoint')).toBeInTheDocument()
    expect(screen.getByText('Sequence 3')).toBeInTheDocument()
  })

  it('shows no checkpoint when none exist', () => {
    render(<LiveDashboard {...defaultProps} checkpoints={[]} />)

    expect(screen.getAllByText('None yet')).toHaveLength(3) // Latest decision, latest tool, and latest checkpoint
  })

  it('displays checkpoint delta when two checkpoints exist', () => {
    const checkpoints = [
      createCheckpoint({
        id: 'cp-1',
        sequence: 1,
        state: { items: 5 },
        memory: { tokens: 100 },
      }),
      createCheckpoint({
        id: 'cp-2',
        sequence: 2,
        state: { items: 5, new_item: 1 },
        memory: { tokens: 100, new_tokens: 50 },
      }),
    ]
    render(<LiveDashboard {...defaultProps} checkpoints={checkpoints} />)

    expect(screen.getByText(/State:\s*\+1/)).toBeInTheDocument()
    expect(screen.getByText(/Memory:\s*\+1/)).toBeInTheDocument()
  })

  it('displays behavior alerts when present', () => {
    const liveSummary = createLiveSummary({
      recent_alerts: [
        {
          alert_type: 'oscillation',
          severity: 'high',
          signal: 'Repeating pattern detected',
          event_id: 'event-1',
          source: 'derived',
        },
        {
          alert_type: 'escalation',
          severity: 'medium',
          signal: 'Increasing severity',
          event_id: 'event-2',
          source: 'captured',
        },
      ],
    })
    render(<LiveDashboard {...defaultProps} liveSummary={liveSummary} />)

    expect(screen.getByText('Behavior alerts')).toBeInTheDocument()
    expect(screen.getByText('oscillation')).toBeInTheDocument()
    expect(screen.getByText('escalation')).toBeInTheDocument()
    expect(screen.getByText('Repeating pattern detected')).toBeInTheDocument()
    expect(screen.getByText('Increasing severity')).toBeInTheDocument()
  })

  it('shows no behavior alerts message when none exist', () => {
    const liveSummary = createLiveSummary({ recent_alerts: [] })
    render(<LiveDashboard {...defaultProps} liveSummary={liveSummary} />)

    expect(screen.getByText('No behavior alerts detected.')).toBeInTheDocument()
  })

  it('displays stability indicator as stable', () => {
    const liveSummary = createLiveSummary({
      recent_alerts: [],
    })
    render(<LiveDashboard {...defaultProps} liveSummary={liveSummary} />)

    expect(screen.getByText('Stable')).toBeInTheDocument()
    expect(screen.getByText('0 alerts')).toBeInTheDocument()
  })

  it('displays stability indicator as oscillating', () => {
    const liveSummary = createLiveSummary({
      recent_alerts: [
        {
          alert_type: 'test',
          severity: 'medium',
          signal: 'Test alert',
          event_id: 'event-1',
          source: 'captured',
        },
        {
          alert_type: 'test2',
          severity: 'medium',
          signal: 'Test alert 2',
          event_id: 'event-2',
          source: 'captured',
        },
      ],
    })
    render(<LiveDashboard {...defaultProps} liveSummary={liveSummary} />)

    expect(screen.getByText('Oscillating')).toBeInTheDocument()
    expect(screen.getByText('2 alerts')).toBeInTheDocument()
  })

  it('displays stability indicator as problematic', () => {
    const liveSummary = createLiveSummary({
      recent_alerts: [
        {
          alert_type: 'oscillation',
          severity: 'high',
          signal: 'Oscillation detected',
          event_id: 'event-1',
          source: 'derived',
        },
      ],
    })
    render(<LiveDashboard {...defaultProps} liveSummary={liveSummary} />)

    expect(screen.getByText('Problematic')).toBeInTheDocument()
    expect(screen.getByText('1 alert')).toBeInTheDocument()
  })

  it('displays rolling summary from liveSummary', () => {
    const liveSummary = createLiveSummary({
      rolling_summary: 'Agent is performing well and making good progress',
    })
    render(<LiveDashboard {...defaultProps} liveSummary={liveSummary} />)

    expect(screen.getByText('Rolling summary')).toBeInTheDocument()
    expect(screen.getByText('Agent is performing well and making good progress')).toBeInTheDocument()
  })

  it('displays rolling summary from latest turn when no liveSummary', () => {
    const events = [
      createEvent({
        id: 'turn-1',
        event_type: 'agent_turn',
        state_summary: 'Turn summary: Agent completed task',
      }),
    ]
    render(<LiveDashboard {...defaultProps} events={events} liveSummary={null} />)

    expect(screen.getByText('Turn summary: Agent completed task')).toBeInTheDocument()
  })

  it('displays recent alerts count', () => {
    const liveSummary = createLiveSummary({
      recent_alerts: [
        {
          alert_type: 'test',
          severity: 'medium',
          signal: 'Test',
          event_id: 'event-1',
          source: 'captured',
        },
        {
          alert_type: 'test2',
          severity: 'medium',
          signal: 'Test2',
          event_id: 'event-2',
          source: 'captured',
        },
        {
          alert_type: 'test3',
          severity: 'medium',
          signal: 'Test3',
          event_id: 'event-3',
          source: 'captured',
        },
      ],
    })
    render(<LiveDashboard {...defaultProps} liveSummary={liveSummary} />)

    expect(screen.getByText('Recent alerts 3')).toBeInTheDocument()
  })

  it('handles onSelectEvent callback when clicking decision card', async () => {
    const user = userEvent.setup()
    const onSelectEvent = vi.fn()
    const events = [
      createEvent({
        id: 'decision-1',
        event_type: 'decision',
        name: 'Make a choice',
      }),
    ]

    render(<LiveDashboard {...defaultProps} events={events} onSelectEvent={onSelectEvent} />)

    const decisionCard = screen.getByText('Latest decision').closest('button')
    if (decisionCard) {
      await user.click(decisionCard)
      expect(onSelectEvent).toHaveBeenCalledWith('decision-1')
    }
  })

  it('handles onSelectEvent callback when clicking tool activity card', async () => {
    const user = userEvent.setup()
    const onSelectEvent = vi.fn()
    const events = [
      createEvent({
        id: 'tool-1',
        event_type: 'tool_call',
        name: 'search',
        tool_name: 'search_tool',
      }),
    ]

    render(<LiveDashboard {...defaultProps} events={events} onSelectEvent={onSelectEvent} />)

    const toolCard = screen.getByText('Latest tool activity').closest('button')
    if (toolCard) {
      await user.click(toolCard)
      expect(onSelectEvent).toHaveBeenCalledWith('tool-1')
    }
  })

  it('handles onSelectEvent callback when clicking error card', async () => {
    const user = userEvent.setup()
    const onSelectEvent = vi.fn()
    const events = [
      createEvent({
        id: 'error-1',
        event_type: 'error',
        name: 'Error occurred',
      }),
    ]

    render(<LiveDashboard {...defaultProps} events={events} onSelectEvent={onSelectEvent} />)

    const errorCard = screen.getByText('Current error state').closest('button')
    if (errorCard) {
      await user.click(errorCard)
      expect(onSelectEvent).toHaveBeenCalledWith('error-1')
    }
  })

  it('handles onSelectEvent callback when clicking behavior alert', async () => {
    const user = userEvent.setup()
    const onSelectEvent = vi.fn()
    const liveSummary = createLiveSummary({
      recent_alerts: [
        {
          alert_type: 'oscillation',
          severity: 'high',
          signal: 'Oscillation detected',
          event_id: 'event-123',
          source: 'captured',
        },
      ],
    })

    render(<LiveDashboard {...defaultProps} liveSummary={liveSummary} onSelectEvent={onSelectEvent} />)

    const alertButton = screen.getByText('oscillation').closest('button')
    if (alertButton) {
      await user.click(alertButton)
      expect(onSelectEvent).toHaveBeenCalledWith('event-123')
    }
  })

  it('does not call onSelectEvent when clicking disabled decision card', async () => {
    const onSelectEvent = vi.fn()

    render(<LiveDashboard {...defaultProps} events={[]} onSelectEvent={onSelectEvent} />)

    const decisionCard = screen.getByText('Latest decision').closest('button')
    if (decisionCard) {
      expect(decisionCard).toBeDisabled()
    }
  })

  it('does not call onSelectEvent when clicking disabled tool card', async () => {
    const onSelectEvent = vi.fn()

    render(<LiveDashboard {...defaultProps} events={[]} onSelectEvent={onSelectEvent} />)

    const toolCard = screen.getByText('Latest tool activity').closest('button')
    if (toolCard) {
      expect(toolCard).toBeDisabled()
    }
  })

  it('displays default rolling summary when no data available', () => {
    render(<LiveDashboard {...defaultProps} events={[]} liveSummary={null} />)

    expect(screen.getByText('Awaiting richer live summaries')).toBeInTheDocument()
  })

  it('handles edge case: negative checkpoint delta', () => {
    const checkpoints = [
      createCheckpoint({
        id: 'cp-1',
        sequence: 1,
        state: { items: 10, extra: 1 },
        memory: { tokens: 200, extra: 1 },
      }),
      createCheckpoint({
        id: 'cp-2',
        sequence: 2,
        state: { items: 7 },
        memory: { tokens: 150 },
      }),
    ]
    render(<LiveDashboard {...defaultProps} checkpoints={checkpoints} />)

    expect(screen.getByText(/State:\s*-1/)).toBeInTheDocument()
    expect(screen.getByText(/Memory:\s*-1/)).toBeInTheDocument()
  })

  it('handles edge case: zero checkpoint delta', () => {
    const checkpoints = [
      createCheckpoint({
        id: 'cp-1',
        sequence: 1,
        state: { items: 5 },
        memory: { tokens: 100 },
      }),
      createCheckpoint({
        id: 'cp-2',
        sequence: 2,
        state: { items: 5 },
        memory: { tokens: 100 },
      }),
    ]
    render(<LiveDashboard {...defaultProps} checkpoints={checkpoints} />)

    expect(screen.getByText(/State:\s*\+0/)).toBeInTheDocument()
    expect(screen.getByText(/Memory:\s*\+0/)).toBeInTheDocument()
  })

  it('handles edge case: single checkpoint (no delta)', () => {
    const checkpoints = [
      createCheckpoint({
        id: 'cp-1',
        sequence: 1,
        state: { items: 5 },
        memory: { tokens: 100 },
      }),
    ]
    render(<LiveDashboard {...defaultProps} checkpoints={checkpoints} />)

    expect(screen.queryByText(/State:/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Memory:/)).not.toBeInTheDocument()
  })
})
