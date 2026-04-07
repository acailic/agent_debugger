import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EmptyState } from '../components/EmptyState'

function getByClassName(container: HTMLElement, className: string): HTMLElement | null {
  return container.querySelector(`.${className}`)
}

describe('EmptyState', () => {
  it('renders with all required props', () => {
    render(
      <EmptyState
        title="No Data"
        description="There is no data to display"
      />
    )

    expect(screen.getByText('No Data')).toBeInTheDocument()
    expect(screen.getByText('There is no data to display')).toBeInTheDocument()
  })

  it('renders with optional icon', () => {
    render(
      <EmptyState
        icon="📭"
        title="No Data"
        description="There is no data to display"
      />
    )

    expect(screen.getByText('📭')).toBeInTheDocument()
    expect(screen.getByText('No Data')).toBeInTheDocument()
  })

  it('renders without icon when not provided', () => {
    const { container } = render(
      <EmptyState
        title="No Data"
        description="There is no data to display"
      />
    )

    const icon = getByClassName(container, 'empty-state-icon')
    expect(icon).toBeNull()
  })

  it('renders with steps', () => {
    const steps = [
      { label: 'Step 1', detail: 'First action' },
      { label: 'Step 2', detail: 'Second action' },
      { label: 'Step 3', detail: 'Third action' },
    ]

    render(
      <EmptyState
        title="Getting Started"
        description="Follow these steps"
        steps={steps}
      />
    )

    expect(screen.getByText('Step 1')).toBeInTheDocument()
    expect(screen.getByText('First action')).toBeInTheDocument()
    expect(screen.getByText('Step 2')).toBeInTheDocument()
    expect(screen.getByText('Second action')).toBeInTheDocument()
    expect(screen.getByText('Step 3')).toBeInTheDocument()
    expect(screen.getByText('Third action')).toBeInTheDocument()
  })

  it('renders action button with href', () => {
    render(
      <EmptyState
        title="No Data"
        description="Create your first session"
        action={{ label: 'Create Session', href: '/sessions/new' }}
      />
    )

    const link = screen.getByRole('link', { name: 'Create Session' })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/sessions/new')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('renders action button with onClick handler', () => {
    const handleClick = vi.fn()

    render(
      <EmptyState
        title="No Data"
        description="Create your first session"
        action={{ label: 'Create Session', onClick: handleClick }}
      />
    )

    const button = screen.getByRole('button', { name: 'Create Session' })
    expect(button).toBeInTheDocument()

    button.click()
    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it('does not render steps when steps array is empty', () => {
    render(
      <EmptyState
        title="No Data"
        description="There is no data to display"
        steps={[]}
      />
    )

    const stepsList = screen.queryByRole('list')
    expect(stepsList).not.toBeInTheDocument()
  })

  it('renders with all props combined', () => {
    const handleClick = vi.fn()
    const steps = [
      { label: 'Step 1', detail: 'First action' },
      { label: 'Step 2', detail: 'Second action' },
    ]

    render(
      <EmptyState
        icon="🚀"
        title="Getting Started"
        description="Follow these steps to get started"
        steps={steps}
        action={{ label: 'Start Now', onClick: handleClick }}
      />
    )

    expect(screen.getByText('🚀')).toBeInTheDocument()
    expect(screen.getByText('Getting Started')).toBeInTheDocument()
    expect(screen.getByText('Follow these steps to get started')).toBeInTheDocument()
    expect(screen.getByText('Step 1')).toBeInTheDocument()
    expect(screen.getByText('First action')).toBeInTheDocument()
    expect(screen.getByText('Step 2')).toBeInTheDocument()
    expect(screen.getByText('Second action')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start Now' })).toBeInTheDocument()
  })
})
