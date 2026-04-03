import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TraceTimeline, TraceTimelineMemo } from '../components/TraceTimeline'
import type { TraceEvent, Highlight } from '../types'

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

const base: TraceEvent = {
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
  return { ...base, ...overrides }
}

const mockEvents: TraceEvent[] = [
  makeEvent({ id: '1', event_type: 'llm_request', name: 'LLM Call 1', model: 'gpt-4', duration_ms: 500 }),
  makeEvent({ id: '2', event_type: 'tool_call', name: 'Tool Call 1', tool_name: 'search', arguments: { query: 'test' }, duration_ms: 1500 }),
  makeEvent({ id: '3', event_type: 'decision', name: 'Decision 1', reasoning: 'Test reasoning', confidence: 0.9, chosen_action: 'action1', duration_ms: 100 }),
  makeEvent({ id: '4', event_type: 'error', name: 'Error 1', error_type: 'ValidationError', error_message: 'Invalid input', duration_ms: 0 }),
  makeEvent({ id: '5', event_type: 'agent_start', name: 'Agent Start', agent_id: 'agent-1' }),
  makeEvent({ id: '6', event_type: 'safety_check', name: 'Safety Check', policy_name: 'content_policy', outcome: 'block', risk_level: 'high', rationale: 'Violates policy', blocked_action: 'generate_content', reason: 'Policy violation' }),
  makeEvent({ id: '7', event_type: 'refusal', name: 'Refusal', policy_name: 'safety_policy', risk_level: 'medium', reason: 'Unsafe request', blocked_action: 'execute_code' }),
  makeEvent({ id: '8', event_type: 'policy_violation', name: 'Policy Violation', policy_name: 'security_policy', severity: 'high', violation_type: 'injection_attempt', reason: 'SQL injection detected' }),
]

/** Non-blocked events (ids 1-5) for tests that don't need blocked events */
const nonBlockedEvents = mockEvents.slice(0, 5)

const mockHighlightsMap = new Map<string, Highlight>([
  ['1', {
    event_id: '1',
    event_type: 'llm_request',
    highlight_type: 'decision',
    importance: 0.8,
    reason: 'Key decision point',
    timestamp: '2024-01-01T10:00:00Z',
    headline: 'Important LLM request',
  }],
])

describe('TraceTimeline', () => {
  // -----------------------------------------------------------------------
  // Basic rendering
  // -----------------------------------------------------------------------

  it('renders timeline with header and event count', () => {
    render(
      <TraceTimeline events={mockEvents} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    expect(screen.getByText('Event Timeline')).toBeInTheDocument()
    // Blocked events hidden by default: 8 total - 3 blocked = 5 visible
    expect(screen.getByText('5 events')).toBeInTheDocument()
  })

  it('handles empty events array', () => {
    render(
      <TraceTimeline events={[]} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    expect(screen.getByText('0 events')).toBeInTheDocument()
  })

  it('renders event type labels correctly', () => {
    render(
      <TraceTimeline events={nonBlockedEvents} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    expect(screen.getByText('llm request')).toBeInTheDocument()
    expect(screen.getByText('tool call')).toBeInTheDocument()
    expect(screen.getByText('decision')).toBeInTheDocument()
    expect(screen.getByText('error')).toBeInTheDocument()
    expect(screen.getByText('agent start')).toBeInTheDocument()
  })

  it('renders event summaries via formatEventHeadline', () => {
    render(
      <TraceTimeline events={nonBlockedEvents} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    expect(screen.getByText('LLM Request')).toBeInTheDocument()
    expect(screen.getByText('search')).toBeInTheDocument()
    expect(screen.getByText('action1')).toBeInTheDocument()
    expect(screen.getByText('ValidationError')).toBeInTheDocument()
    expect(screen.getByText('Agent Start')).toBeInTheDocument()
  })

  it('renders event timestamps as locale time', () => {
    render(
      <TraceTimeline events={mockEvents.slice(0, 1)} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    const timeElements = screen.getAllByText(/\d{1,2}:\d{2}:\d{2}/)
    expect(timeElements.length).toBeGreaterThan(0)
  })

  // -----------------------------------------------------------------------
  // Filter chips
  // -----------------------------------------------------------------------

  it('renders all event type filter chips', () => {
    render(
      <TraceTimeline events={mockEvents} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    expect(screen.getByRole('button', { name: /^All$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /LLM/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Tools/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Decisions/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Errors/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Agents/ })).toBeInTheDocument()
  })

  it('shows correct count on each filter chip', () => {
    render(
      <TraceTimeline events={mockEvents} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    expect(screen.getByRole('button', { name: /LLM/ })).toHaveTextContent('1')
    expect(screen.getByRole('button', { name: /Tools/ })).toHaveTextContent('1')
    expect(screen.getByRole('button', { name: /Decisions/ })).toHaveTextContent('1')
    expect(screen.getByRole('button', { name: /Errors/ })).toHaveTextContent('1')
    expect(screen.getByRole('button', { name: /Agents/ })).toHaveTextContent('1')
  })

  it('activates the "All" filter chip by default', () => {
    render(
      <TraceTimeline events={mockEvents} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    expect(screen.getByRole('button', { name: /^All$/i })).toHaveClass('active')
  })

  it('filters events when LLM chip is clicked', async () => {
    render(
      <TraceTimeline events={mockEvents} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    expect(screen.getByText('5 events')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /LLM/ }))

    expect(screen.getByText('1 events')).toBeInTheDocument()
    expect(screen.getByText('LLM Request')).toBeInTheDocument()
  })

  it('filters Tools events correctly', async () => {
    render(
      <TraceTimeline events={mockEvents} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    await userEvent.click(screen.getByRole('button', { name: /Tools/ }))

    expect(screen.getByText('1 events')).toBeInTheDocument()
    expect(screen.getByText('search')).toBeInTheDocument()
    expect(screen.queryByText('LLM Request')).not.toBeInTheDocument()
  })

  it('updates event count when switching filters', async () => {
    render(
      <TraceTimeline events={mockEvents} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    expect(screen.getByText('5 events')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Errors/ }))
    expect(screen.getByText('1 events')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /^All$/i }))
    expect(screen.getByText('5 events')).toBeInTheDocument()
  })

  // -----------------------------------------------------------------------
  // Blocked events toggle
  // -----------------------------------------------------------------------

  it('renders the "Show Blocked Actions" checkbox', () => {
    render(
      <TraceTimeline events={mockEvents} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    const toggle = screen.getByRole('checkbox')
    expect(toggle).toBeInTheDocument()
    expect(toggle).not.toBeChecked()
    expect(screen.getByText('Show Blocked Actions')).toBeInTheDocument()
  })

  it('hides blocked events by default', () => {
    render(
      <TraceTimeline events={mockEvents} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    expect(screen.getByText('5 events')).toBeInTheDocument()
    expect(screen.queryByText(/content_policy/)).not.toBeInTheDocument()
    expect(screen.queryByText('Unsafe request')).not.toBeInTheDocument()
    expect(screen.queryByText('injection_attempt')).not.toBeInTheDocument()
  })

  it('shows blocked events when checkbox is toggled on', async () => {
    render(
      <TraceTimeline events={mockEvents} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    const toggle = screen.getByRole('checkbox')
    await userEvent.click(toggle)

    expect(toggle).toBeChecked()
    expect(screen.getByText('8 events')).toBeInTheDocument()
    expect(screen.getByText(/content_policy/)).toBeInTheDocument()
    expect(screen.getByText('Unsafe request')).toBeInTheDocument()
    expect(screen.getByText('injection_attempt')).toBeInTheDocument()
  })

  it('supports controlled blocked-action visibility', async () => {
    const onToggleShowBlockedActions = vi.fn()
    render(
      <TraceTimeline
        events={mockEvents}
        selectedEventId={null}
        onSelectEvent={vi.fn()}
        showBlockedActions={true}
        onToggleShowBlockedActions={onToggleShowBlockedActions}
      />,
    )

    const toggle = screen.getByRole('checkbox')
    expect(toggle).toBeChecked()
    expect(screen.getByText('8 events')).toBeInTheDocument()

    await userEvent.click(toggle)
    expect(onToggleShowBlockedActions).toHaveBeenCalledWith(false)
  })

  it('hides blocked events again when toggled back off', async () => {
    render(
      <TraceTimeline events={mockEvents} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    const toggle = screen.getByRole('checkbox')
    await userEvent.click(toggle)
    expect(screen.getByText('8 events')).toBeInTheDocument()

    await userEvent.click(toggle)
    expect(screen.getByText('5 events')).toBeInTheDocument()
    expect(screen.queryByText(/content_policy/)).not.toBeInTheDocument()
  })

  it('displays BLOCKED badge for blocked events when visible', async () => {
    render(
      <TraceTimeline events={mockEvents} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    expect(screen.queryByText('BLOCKED')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('checkbox'))
    expect(screen.getAllByText('BLOCKED')).toHaveLength(3)
  })

  it('shows blocked_action and reason details for blocked events', async () => {
    render(
      <TraceTimeline events={mockEvents} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    await userEvent.click(screen.getByRole('checkbox'))
    expect(screen.getByText('Blocked: generate_content')).toBeInTheDocument()
    expect(screen.getByText('Reason: Policy violation')).toBeInTheDocument()
  })

  it('correctly counts events with blocked toggle and filter combined', async () => {
    render(
      <TraceTimeline events={mockEvents} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    expect(screen.getByText('5 events')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('checkbox'))
    expect(screen.getByText('8 events')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /LLM/ }))
    expect(screen.getByText('1 events')).toBeInTheDocument()
  })

  // -----------------------------------------------------------------------
  // Latency bars
  // -----------------------------------------------------------------------

  it('renders latency bar for events with duration_ms', () => {
    render(
      <TraceTimeline events={nonBlockedEvents} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    expect(screen.getByText('500ms')).toBeInTheDocument()
    expect(screen.getByText('1500ms')).toBeInTheDocument()
  })

  it('color-codes latency bars based on relative duration', () => {
    const eventsWithDuration = [
      makeEvent({ id: 'a', event_type: 'llm_request', name: 'Fast', duration_ms: 100 }),
      makeEvent({ id: 'b', event_type: 'tool_call', name: 'Slow', tool_name: 'x', duration_ms: 5000 }),
    ]

    render(
      <TraceTimeline events={eventsWithDuration} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    const latencyBars = screen.getAllByTitle(/Duration:/)
    expect(latencyBars).toHaveLength(2)

    // avg=2550. 100ms<avg => green. 5000ms > avg*1.5=3825 => orange
    expect(latencyBars[0].style.backgroundColor).toBe('rgb(16, 185, 129)')
    expect(latencyBars[1].style.backgroundColor).toBe('rgb(245, 158, 11)')
  })

  it('renders red latency bar for events far above average', () => {
    const eventsWithSpread = [
      makeEvent({ id: 'a', event_type: 'llm_request', name: 'A', duration_ms: 100 }),
      makeEvent({ id: 'b', event_type: 'tool_call', name: 'B', tool_name: 't', duration_ms: 100 }),
      makeEvent({ id: 'c', event_type: 'decision', name: 'C', chosen_action: 'x', duration_ms: 10000 }),
    ]
    // avg = 3400, avg*2 = 6800, 10000 > 6800 => red

    render(
      <TraceTimeline events={eventsWithSpread} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    const latencyBars = screen.getAllByTitle(/Duration:/)
    expect(latencyBars[2].style.backgroundColor).toBe('rgb(239, 68, 68)')
  })

  it('renders latency bar with correct marker type for llm_request', () => {
    render(
      <TraceTimeline events={[mockEvents[0]]} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    const latencyBar = screen.getByTitle('Duration: 500ms')
    expect(latencyBar).toBeInTheDocument()
    expect(latencyBar.closest('.timeline-event')?.className).toContain('llm_request')
  })

  it('does not render latency bar for events without duration_ms', () => {
    render(
      <TraceTimeline events={[mockEvents[4]]} selectedEventId={null} onSelectEvent={vi.fn()} />,
    )
    expect(screen.queryByText(/\d+ms/)).not.toBeInTheDocument()
  })

  // -----------------------------------------------------------------------
  // Event selection
  // -----------------------------------------------------------------------

  it('calls onSelectEvent when an event row is clicked', async () => {
    const onSelectEvent = vi.fn()
    render(
      <TraceTimeline events={nonBlockedEvents} selectedEventId={null} onSelectEvent={onSelectEvent} />,
    )
    const eventRow = screen.getByText('LLM Request').closest('.timeline-event')!
    await userEvent.click(eventRow)
    expect(onSelectEvent).toHaveBeenCalledWith('1')
  })

  it('applies selected class to selected event', () => {
    render(
      <TraceTimeline events={nonBlockedEvents} selectedEventId="1" onSelectEvent={vi.fn()} />,
    )
    expect(screen.getByText('LLM Request').closest('.timeline-event')).toHaveClass('selected')
    expect(screen.getByText('search').closest('.timeline-event')).not.toHaveClass('selected')
  })

  it('updates selection when a different event is clicked', async () => {
    const onSelectEvent = vi.fn()
    render(
      <TraceTimeline events={nonBlockedEvents} selectedEventId="1" onSelectEvent={onSelectEvent} />,
    )
    const eventRow = screen.getByText('search').closest('.timeline-event')!
    await userEvent.click(eventRow)
    expect(onSelectEvent).toHaveBeenCalledWith('2')
  })

  // -----------------------------------------------------------------------
  // Highlights
  // -----------------------------------------------------------------------

  it('displays highlight marker for highlighted events', () => {
    render(
      <TraceTimeline events={nonBlockedEvents} selectedEventId={null} onSelectEvent={vi.fn()} highlightEventIds={new Set(['1'])} />,
    )
    expect(screen.getAllByTitle('Highlighted event').length).toBeGreaterThan(0)
  })

  it('displays highlight reason from highlightsMap', () => {
    render(
      <TraceTimeline events={nonBlockedEvents} selectedEventId={null} onSelectEvent={vi.fn()} highlightEventIds={new Set(['1'])} highlightsMap={mockHighlightsMap} />,
    )
    expect(screen.getByText('Key decision point')).toBeInTheDocument()
  })

  it('applies highlight class to highlighted events', () => {
    render(
      <TraceTimeline events={nonBlockedEvents} selectedEventId={null} onSelectEvent={vi.fn()} highlightEventIds={new Set(['1'])} />,
    )
    expect(screen.getByText('LLM Request').closest('.timeline-event')).toHaveClass('highlight')
  })

  // -----------------------------------------------------------------------
  // Edge cases
  // -----------------------------------------------------------------------

  it('does not crash with undefined highlightEventIds', () => {
    render(
      <TraceTimeline events={nonBlockedEvents} selectedEventId={null} onSelectEvent={vi.fn()} highlightEventIds={undefined} />,
    )
    expect(screen.getByText('5 events')).toBeInTheDocument()
  })

  it('does not crash with undefined highlightsMap', () => {
    render(
      <TraceTimeline events={nonBlockedEvents} selectedEventId={null} onSelectEvent={vi.fn()} highlightEventIds={new Set(['1'])} highlightsMap={undefined} />,
    )
    expect(screen.getByText('5 events')).toBeInTheDocument()
    expect(screen.queryByText('Key decision point')).not.toBeInTheDocument()
  })
})

describe('TraceTimelineMemo', () => {
  it('memoizes component and avoids unnecessary re-renders', () => {
    const onSelectEvent = vi.fn()
    const { rerender } = render(
      <TraceTimelineMemo events={nonBlockedEvents} selectedEventId="1" onSelectEvent={onSelectEvent} />,
    )
    rerender(
      <TraceTimelineMemo events={nonBlockedEvents} selectedEventId="1" onSelectEvent={onSelectEvent} />,
    )
    expect(screen.getByText('Event Timeline')).toBeInTheDocument()
  })

  it('re-renders when selectedEventId changes', () => {
    const onSelectEvent = vi.fn()
    const { rerender } = render(
      <TraceTimelineMemo events={nonBlockedEvents} selectedEventId="1" onSelectEvent={onSelectEvent} />,
    )
    expect(screen.getByText('LLM Request').closest('.timeline-event')).toHaveClass('selected')

    rerender(
      <TraceTimelineMemo events={nonBlockedEvents} selectedEventId="2" onSelectEvent={onSelectEvent} />,
    )
    expect(screen.getByText('LLM Request').closest('.timeline-event')).not.toHaveClass('selected')
    expect(screen.getByText('search').closest('.timeline-event')).toHaveClass('selected')
  })
})
