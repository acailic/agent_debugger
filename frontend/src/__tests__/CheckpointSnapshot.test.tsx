import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CheckpointSnapshot } from '../components/CheckpointSnapshot'
import type { Checkpoint } from '../types'

describe('CheckpointSnapshot', () => {
  const mockCheckpoint: Checkpoint = {
    id: 'ckpt-1',
    session_id: 'session-1',
    event_id: 'event-1',
    sequence: 5,
    state: { step: 'processing', value: 42 },
    memory: { context: 'test context', history: [] },
    timestamp: '2025-01-01T00:00:00Z',
    importance: 0.8
  }

  it('renders with checkpoint data', () => {
    render(
      <CheckpointSnapshot
        title="Test Checkpoint"
        checkpoint={mockCheckpoint}
      />
    )

    expect(screen.getByText('Test Checkpoint')).toBeInTheDocument()
    expect(screen.getByText('Sequence 5')).toBeInTheDocument()
    expect(screen.getByText('State')).toBeInTheDocument()
    expect(screen.getByText('Memory')).toBeInTheDocument()
  })

  it('renders state and memory as JSON', () => {
    render(
      <CheckpointSnapshot
        title="Test Checkpoint"
        checkpoint={mockCheckpoint}
      />
    )

    expect(screen.getByText(/"step": "processing"/)).toBeInTheDocument()
    expect(screen.getByText(/"value": 42/)).toBeInTheDocument()
    expect(screen.getByText(/"context": "test context"/)).toBeInTheDocument()
  })

  it('renders with selected variant', () => {
    const { container } = render(
      <CheckpointSnapshot
        title="Selected Checkpoint"
        checkpoint={mockCheckpoint}
        variant="selected"
      />
    )

    const wrapper = container.querySelector('.checkpoint-preview')
    expect(wrapper).toHaveClass('selected')
  })

  it('renders with anchor variant', () => {
    const { container } = render(
      <CheckpointSnapshot
        title="Anchor Checkpoint"
        checkpoint={mockCheckpoint}
        variant="anchor"
      />
    )

    const wrapper = container.querySelector('.checkpoint-preview')
    expect(wrapper).toHaveClass('anchor')
  })

  it('applies scale-in animation class', () => {
    const { container } = render(
      <CheckpointSnapshot
        title="Animated Checkpoint"
        checkpoint={mockCheckpoint}
      />
    )

    const wrapper = container.querySelector('.checkpoint-preview')
    expect(wrapper).toHaveClass('scale-in')
  })

  it('renders empty state and memory objects', () => {
    const emptyCheckpoint: Checkpoint = {
      id: 'ckpt-empty',
      session_id: 'session-1',
      event_id: 'event-1',
      sequence: 1,
      state: {},
      memory: {},
      timestamp: '2025-01-01T00:00:00Z',
      importance: 0
    }

    render(
      <CheckpointSnapshot
        title="Empty Checkpoint"
        checkpoint={emptyCheckpoint}
      />
    )

    expect(screen.getAllByText('{}')).toHaveLength(2)
  })
})
