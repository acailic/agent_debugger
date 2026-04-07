import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ToolInspector } from '../components/ToolInspector'
import type { TraceEvent } from '../types'

function createTraceEvent(overrides: Partial<TraceEvent> = {}): TraceEvent {
  return {
    id: 'event-1',
    session_id: 'session-1',
    timestamp: '2024-01-01T10:00:00Z',
    event_type: 'tool_result',
    parent_id: null,
    name: 'Tool Call',
    data: {},
    metadata: {},
    importance: 0.5,
    upstream_event_ids: [],
    tool_name: 'search',
    arguments: { query: 'test', limit: 5 },
    ...overrides,
  }
}

describe('ToolInspector', () => {
  it('renders empty state when event is null', () => {
    render(<ToolInspector event={null} />)

    expect(screen.getByText('Select a tool call to inspect')).toBeInTheDocument()
    expect(screen.getByText('🔍')).toBeInTheDocument()
  })

  it('renders tool name and icon', () => {
    const event = createTraceEvent({ tool_name: 'search' })
    render(<ToolInspector event={event} />)

    expect(screen.getByText('search')).toBeInTheDocument()
    expect(screen.getByText('🔧')).toBeInTheDocument()
  })

  it('renders tool ID and timestamp', () => {
    const event = createTraceEvent({
      id: 'tool-123',
      timestamp: '2024-01-01T10:00:00Z',
    })
    render(<ToolInspector event={event} />)

    expect(screen.getByText('tool-123')).toBeInTheDocument()
    expect(screen.getByText(/10:00:00/)).toBeInTheDocument()
  })

  it('renders arguments section when arguments exist', () => {
    const event = createTraceEvent({
      arguments: { query: 'Paris', limit: 10, filters: { type: 'city' } },
    })
    const { container } = render(<ToolInspector event={event} />)

    expect(container.querySelector('.tool-section')).toBeInTheDocument()
    expect(container.textContent).toContain('Arguments')
    expect(container.textContent).toContain('"query"')
    expect(container.textContent).toContain('Paris')
    expect(container.textContent).toContain('"limit"')
    expect(container.textContent).toContain('10')
    expect(container.textContent).toContain('"filters"')
  })

  it('does not render arguments section when arguments are empty', () => {
    const event = createTraceEvent({ arguments: {} })
    render(<ToolInspector event={event} />)

    expect(screen.queryByText('Arguments')).not.toBeInTheDocument()
  })

  it('toggles arguments section on click', () => {
    const event = createTraceEvent({
      arguments: { query: 'test' },
    })
    const { container } = render(<ToolInspector event={event} />)

    const argumentsSection = container.querySelector('.tool-section')

    if (!argumentsSection) throw new Error('Arguments section not found')

    const argumentsHeader = argumentsSection.querySelector('h4')
    if (!argumentsHeader) throw new Error('Arguments header not found')

    // Initially expanded (no collapsed class)
    expect(argumentsSection.classList.contains('collapsed')).toBe(false)

    // Collapse
    fireEvent.click(argumentsHeader)
    expect(argumentsSection.classList.contains('collapsed')).toBe(true)

    // Expand again
    fireEvent.click(argumentsHeader)
    expect(argumentsSection.classList.contains('collapsed')).toBe(false)
  })

  it('renders loading state for tool_call without result', () => {
    const event = createTraceEvent({
      event_type: 'tool_call',
      tool_name: 'search',
    })
    render(<ToolInspector event={event} />)

    expect(screen.getByText('Waiting for result...')).toBeInTheDocument()
    expect(screen.getByText('⏳')).toBeInTheDocument()
  })

  it('renders success badge for tool_result', () => {
    const event = createTraceEvent({
      event_type: 'tool_result',
      tool_name: 'search',
      result: { results: ['item1', 'item2'] },
    })
    render(<ToolInspector event={event} />)

    expect(screen.getByText('✓')).toBeInTheDocument()
  })

  it('renders error badge and error message', () => {
    const event = createTraceEvent({
      event_type: 'tool_result',
      tool_name: 'search',
      error: 'Search failed: timeout',
      result: null,
    })
    const { container } = render(<ToolInspector event={event} />)

    expect(screen.getByText('✗')).toBeInTheDocument()
    expect(container.textContent).toContain('Error')
    expect(screen.getByText('Search failed: timeout')).toBeInTheDocument()
    expect(screen.getByText('⚠️')).toBeInTheDocument()
  })

  it('renders result section for tool_result', () => {
    const event = createTraceEvent({
      event_type: 'tool_result',
      tool_name: 'search',
      result: { results: ['item1', 'item2'], total: 2 },
    })
    const { container } = render(<ToolInspector event={event} />)

    expect(container.textContent).toContain('Result')
    expect(container.textContent).toContain('"results"')
    expect(container.textContent).toContain('"total"')
    expect(container.textContent).toContain('2')
  })

  it('toggles result section on click', () => {
    const event = createTraceEvent({
      event_type: 'tool_result',
      result: { data: 'test' },
    })
    const { container } = render(<ToolInspector event={event} />)

    const resultSection = container.querySelectorAll('.tool-section')[1]

    if (!resultSection) throw new Error('Result section not found')

    const resultHeader = resultSection.querySelector('h4')
    if (!resultHeader) throw new Error('Result header not found')

    // Initially expanded (no collapsed class)
    expect(resultSection.classList.contains('collapsed')).toBe(false)

    // Collapse
    fireEvent.click(resultHeader)
    expect(resultSection.classList.contains('collapsed')).toBe(true)

    // Expand again
    fireEvent.click(resultHeader)
    expect(resultSection.classList.contains('collapsed')).toBe(false)
  })

  it('renders duration when available', () => {
    const event = createTraceEvent({
      duration_ms: 1234,
    })
    render(<ToolInspector event={event} />)

    expect(screen.getByText('1.2s')).toBeInTheDocument()
  })

  it('does not render duration when null', () => {
    const event = createTraceEvent({
      duration_ms: undefined,
    })
    const { container } = render(<ToolInspector event={event} />)

    // Should not show duration element
    expect(container.querySelector('.duration')).not.toBeInTheDocument()
  })

  it('applies error-state class when error is present', () => {
    const event = createTraceEvent({
      event_type: 'tool_result',
      error: 'Failed',
    })
    const { container } = render(<ToolInspector event={event} />)

    expect(container.querySelector('.tool-inspector.error-state')).toBeInTheDocument()
  })

  it('renders tool_result with error and error section styling', () => {
    const event = createTraceEvent({
      event_type: 'tool_result',
      error: 'Something went wrong',
    })
    const { container } = render(<ToolInspector event={event} />)

    expect(container.querySelector('.tool-section.error')).toBeInTheDocument()
    expect(container.textContent).toContain('Error')
  })

  it('handles null arguments (defaults to empty object)', () => {
    const event = createTraceEvent({
      arguments: undefined,
    })
    render(<ToolInspector event={event} />)

    expect(screen.queryByText('Arguments')).not.toBeInTheDocument()
  })

  it('handles tool_call with no result (loading state)', () => {
    const event = createTraceEvent({
      event_type: 'tool_call',
      tool_name: 'api_call',
    })
    render(<ToolInspector event={event} />)

    expect(screen.getByText('Waiting for result...')).toBeInTheDocument()
    expect(screen.queryByText('Result')).not.toBeInTheDocument()
  })

  it('does not show status badge for tool_call without result', () => {
    const event = createTraceEvent({
      event_type: 'tool_call',
      tool_name: 'search',
    })
    render(<ToolInspector event={event} />)

    expect(screen.queryByText('✓')).not.toBeInTheDocument()
    expect(screen.queryByText('✗')).not.toBeInTheDocument()
  })

  it('renders complex nested arguments', () => {
    const event = createTraceEvent({
      arguments: {
        filters: {
          type: 'article',
          date_range: { start: '2024-01-01', end: '2024-12-31' },
          tags: ['ai', 'ml'],
        },
        options: { limit: 10, offset: 0 },
      },
    })
    const { container } = render(<ToolInspector event={event} />)

    expect(container.textContent).toContain('"filters"')
    expect(container.textContent).toContain('"type"')
    expect(container.textContent).toContain('article')
    expect(container.textContent).toContain('"date_range"')
    expect(container.textContent).toContain('"tags"')
    expect(container.textContent).toContain('ai')
    expect(container.textContent).toContain('ml')
  })

  it('renders complex nested result', () => {
    const event = createTraceEvent({
      event_type: 'tool_result',
      result: {
        items: [{ id: 1, name: 'Item 1' }, { id: 2, name: 'Item 2' }],
        pagination: { total: 2, page: 1 },
      },
    })
    const { container } = render(<ToolInspector event={event} />)

    expect(container.textContent).toContain('"items"')
    expect(container.textContent).toContain('"pagination"')
    expect(container.textContent).toContain('"total"')
  })
})
