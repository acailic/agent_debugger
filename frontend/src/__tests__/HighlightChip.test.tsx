import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import HighlightChip from '../components/HighlightChip'

const mockSegment = {
  start_index: 5,
  end_index: 17,
  event_count: 12,
  summary: '12 similar tool calls',
  event_types: ['tool_call', 'tool_result'],
  total_duration_ms: 2300,
}

describe('HighlightChip', () => {
  it('renders collapsed state with summary and event count', () => {
    render(
      <HighlightChip
        segment={mockSegment}
        isExpanded={false}
        onToggle={vi.fn()}
      >
        <div>expanded content</div>
      </HighlightChip>
    )

    expect(screen.getByText('12 similar tool calls')).toBeInTheDocument()
    expect(screen.getByText('12 events')).toBeInTheDocument()
    expect(screen.queryByText('expanded content')).not.toBeInTheDocument()
  })

  it('renders event type tags in collapsed state', () => {
    render(
      <HighlightChip
        segment={mockSegment}
        isExpanded={false}
        onToggle={vi.fn()}
      >
        <div>expanded content</div>
      </HighlightChip>
    )

    expect(screen.getByText('tool call')).toBeInTheDocument()
    expect(screen.getByText('tool result')).toBeInTheDocument()
  })

  it('renders duration when total_duration_ms is provided', () => {
    render(
      <HighlightChip
        segment={mockSegment}
        isExpanded={false}
        onToggle={vi.fn()}
      >
        <div>expanded content</div>
      </HighlightChip>
    )

    expect(screen.getByText('~2.3s')).toBeInTheDocument()
  })

  it('does not render duration when total_duration_ms is null', () => {
    const segmentNoDuration = { ...mockSegment, total_duration_ms: null }
    render(
      <HighlightChip
        segment={segmentNoDuration}
        isExpanded={false}
        onToggle={vi.fn()}
      >
        <div>expanded content</div>
      </HighlightChip>
    )

    expect(screen.queryByText('~')).not.toBeInTheDocument()
  })

  it('formats ms duration correctly', () => {
    const segmentMs = { ...mockSegment, total_duration_ms: 450 }
    render(
      <HighlightChip segment={segmentMs} isExpanded={false} onToggle={vi.fn()}>
        <div>expanded content</div>
      </HighlightChip>
    )

    expect(screen.getByText('~450ms')).toBeInTheDocument()
  })

  it('formats minute duration correctly', () => {
    const segmentMin = { ...mockSegment, total_duration_ms: 125000 }
    render(
      <HighlightChip segment={segmentMin} isExpanded={false} onToggle={vi.fn()}>
        <div>expanded content</div>
      </HighlightChip>
    )

    expect(screen.getByText('~2.1m')).toBeInTheDocument()
  })

  it('uses singular "event" for count of 1', () => {
    const singleSegment = { ...mockSegment, event_count: 1 }
    render(
      <HighlightChip segment={singleSegment} isExpanded={false} onToggle={vi.fn()}>
        <div>expanded content</div>
      </HighlightChip>
    )

    expect(screen.getByText('1 event')).toBeInTheDocument()
  })

  it('calls onToggle when collapsed chip is clicked', async () => {
    const onToggle = vi.fn()
    render(
      <HighlightChip segment={mockSegment} isExpanded={false} onToggle={onToggle}>
        <div>expanded content</div>
      </HighlightChip>
    )

    await userEvent.click(screen.getByRole('button'))
    expect(onToggle).toHaveBeenCalledOnce()
  })

  it('renders expanded state with children content', () => {
    render(
      <HighlightChip segment={mockSegment} isExpanded={true} onToggle={vi.fn()}>
        <div data-testid="expanded-events">Event 1</div>
        <div data-testid="expanded-events">Event 2</div>
      </HighlightChip>
    )

    expect(screen.getAllByTestId('expanded-events')).toHaveLength(2)
    expect(screen.getByText('Event 1')).toBeInTheDocument()
    expect(screen.getByText('Event 2')).toBeInTheDocument()
    expect(screen.getByText('12 similar tool calls')).toBeInTheDocument()
  })

  it('shows collapse button in expanded state', () => {
    render(
      <HighlightChip segment={mockSegment} isExpanded={true} onToggle={vi.fn()}>
        <div>expanded content</div>
      </HighlightChip>
    )

    expect(screen.getByRole('button', { name: /collapse/i })).toBeInTheDocument()
  })

  it('calls onToggle when collapse button is clicked', async () => {
    const onToggle = vi.fn()
    render(
      <HighlightChip segment={mockSegment} isExpanded={true} onToggle={onToggle}>
        <div>expanded content</div>
      </HighlightChip>
    )

    await userEvent.click(screen.getByRole('button', { name: /collapse/i }))
    expect(onToggle).toHaveBeenCalledOnce()
  })

  it('renders correctly with empty event_types array', () => {
    const segmentNoTypes = { ...mockSegment, event_types: [] }
    render(
      <HighlightChip segment={segmentNoTypes} isExpanded={false} onToggle={vi.fn()}>
        <div>expanded content</div>
      </HighlightChip>
    )

    expect(screen.getByText('12 similar tool calls')).toBeInTheDocument()
  })
})
