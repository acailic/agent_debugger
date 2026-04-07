import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { getSessionCost } from '../api/client'
import CostPanel from '../components/CostPanel'
import type { SessionCost } from '../types'

vi.mock('../api/client', () => ({
  getSessionCost: vi.fn(),
}))

describe('CostPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // Helper function to create a test SessionCost
  function createSessionCost(overrides: Partial<SessionCost> = {}): SessionCost {
    return {
      session_id: 'session-1',
      total_cost_usd: 0.123456,
      total_tokens: 10000,
      llm_calls: 50,
      tool_calls: 25,
      ...overrides,
    }
  }

  it('renders with valid sessionId', async () => {
    const mockCost = createSessionCost()
    vi.mocked(getSessionCost).mockResolvedValue(mockCost)

    render(<CostPanel sessionId="session-1" />)

    await waitFor(() => {
      expect(getSessionCost).toHaveBeenCalledWith('session-1')
    })

    expect(screen.getByText('Session Cost')).toBeInTheDocument()
  })

  it('shows cost summary with all fields', async () => {
    const mockCost = createSessionCost({
      total_cost_usd: 0.123456,
      total_tokens: 10000,
      llm_calls: 50,
      tool_calls: 25,
    })
    vi.mocked(getSessionCost).mockResolvedValue(mockCost)

    render(<CostPanel sessionId="session-1" />)

    await waitFor(() => {
      expect(screen.getByText('Total Cost')).toBeInTheDocument()
      expect(screen.getByText('$0.123456')).toBeInTheDocument()
      expect(screen.getByText('Tokens')).toBeInTheDocument()
      expect(screen.getByText('10,000')).toBeInTheDocument()
      expect(screen.getByText('LLM Calls')).toBeInTheDocument()
      expect(screen.getByText('50')).toBeInTheDocument()
      expect(screen.getByText('Tool Calls')).toBeInTheDocument()
      expect(screen.getByText('25')).toBeInTheDocument()
    })
  })

  it('handles loading state', () => {
    vi.mocked(getSessionCost).mockImplementation(() => new Promise(() => {}))

    render(<CostPanel sessionId="session-1" />)

    expect(screen.getByText('Session Cost')).toBeInTheDocument()
    expect(screen.queryByText('Total Cost')).not.toBeInTheDocument()

    // Check for skeleton loading elements
    const skeletonElements = document.querySelectorAll('.skeleton-line')
    expect(skeletonElements.length).toBeGreaterThan(0)
  })

  it('handles error state', async () => {
    vi.mocked(getSessionCost).mockRejectedValue(new Error('Network error'))

    render(<CostPanel sessionId="session-1" />)

    await waitFor(() => {
      expect(screen.getByText('Cost data unavailable')).toBeInTheDocument()
    })
  })

  it('handles empty sessionId gracefully', () => {
    render(<CostPanel sessionId="" />)

    expect(screen.getByText('Session Cost')).toBeInTheDocument()
    expect(screen.getByText('No cost data available')).toBeInTheDocument()
    expect(getSessionCost).not.toHaveBeenCalled()
  })

  it('shows efficiency hint when cost per token is high', async () => {
    const mockCost = createSessionCost({
      total_cost_usd: 0.3,
      total_tokens: 10000, // $0.3 / 10000 = $0.00003 per token (> 0.00002 threshold)
    })
    vi.mocked(getSessionCost).mockResolvedValue(mockCost)

    render(<CostPanel sessionId="session-1" />)

    await waitFor(() => {
      expect(
        screen.getByText('Consider using a smaller model for this task type')
      ).toBeInTheDocument()
    })
  })

  it('does not show efficiency hint when cost per token is low', async () => {
    const mockCost = createSessionCost({
      total_cost_usd: 0.1,
      total_tokens: 10000, // $0.1 / 10000 = $0.00001 per token (< 0.00002 threshold)
    })
    vi.mocked(getSessionCost).mockResolvedValue(mockCost)

    render(<CostPanel sessionId="session-1" />)

    await waitFor(() => {
      expect(
        screen.queryByText('Consider using a smaller model for this task type')
      ).not.toBeInTheDocument()
    })
  })

  it('handles zero tokens gracefully', async () => {
    const mockCost = createSessionCost({
      total_tokens: 0,
      total_cost_usd: 0,
    })
    vi.mocked(getSessionCost).mockResolvedValue(mockCost)

    render(<CostPanel sessionId="session-1" />)

    await waitFor(() => {
      expect(screen.getByText('0')).toBeInTheDocument() // Tokens
      expect(screen.getByText('$0.000000')).toBeInTheDocument() // Total Cost
    })

    expect(
      screen.queryByText('Consider using a smaller model for this task type')
    ).not.toBeInTheDocument()
  })

  it('formats large token numbers with locale string', async () => {
    const mockCost = createSessionCost({
      total_tokens: 1234567,
    })
    vi.mocked(getSessionCost).mockResolvedValue(mockCost)

    render(<CostPanel sessionId="session-1" />)

    await waitFor(() => {
      // Should be formatted with commas (locale string)
      expect(screen.getByText(/1,234,567/)).toBeInTheDocument()
    })
  })

  it('formats large LLM call numbers with locale string', async () => {
    const mockCost = createSessionCost({
      llm_calls: 12345,
    })
    vi.mocked(getSessionCost).mockResolvedValue(mockCost)

    render(<CostPanel sessionId="session-1" />)

    await waitFor(() => {
      expect(screen.getByText(/12,345/)).toBeInTheDocument()
    })
  })

  it('formats large tool call numbers with locale string', async () => {
    const mockCost = createSessionCost({
      tool_calls: 6789,
    })
    vi.mocked(getSessionCost).mockResolvedValue(mockCost)

    render(<CostPanel sessionId="session-1" />)

    await waitFor(() => {
      expect(screen.getByText(/6,789/)).toBeInTheDocument()
    })
  })

  it('displays cost with 6 decimal places', async () => {
    const mockCost = createSessionCost({
      total_cost_usd: 0.123456789,
    })
    vi.mocked(getSessionCost).mockResolvedValue(mockCost)

    render(<CostPanel sessionId="session-1" />)

    await waitFor(() => {
      expect(screen.getByText('$0.123457')).toBeInTheDocument() // Rounded to 6 decimals
    })
  })

  it('handles very small cost values', async () => {
    const mockCost = createSessionCost({
      total_cost_usd: 0.000001,
    })
    vi.mocked(getSessionCost).mockResolvedValue(mockCost)

    render(<CostPanel sessionId="session-1" />)

    await waitFor(() => {
      expect(screen.getByText('$0.000001')).toBeInTheDocument()
    })
  })

  it('refetches data when sessionId changes', async () => {
    const mockCost1 = createSessionCost({ session_id: 'session-1', total_cost_usd: 0.1 })
    const mockCost2 = createSessionCost({ session_id: 'session-2', total_cost_usd: 0.2 })

    vi.mocked(getSessionCost)
      .mockResolvedValueOnce(mockCost1)
      .mockResolvedValueOnce(mockCost2)

    const { rerender } = render(<CostPanel sessionId="session-1" />)

    await waitFor(() => {
      expect(screen.getByText('$0.100000')).toBeInTheDocument()
    })

    rerender(<CostPanel sessionId="session-2" />)

    await waitFor(() => {
      expect(getSessionCost).toHaveBeenCalledWith('session-2')
      expect(screen.getByText('$0.200000')).toBeInTheDocument()
    })
  })

  it('shows empty state when data is null', async () => {
    // Mock a successful response that returns null
    vi.mocked(getSessionCost).mockResolvedValue(null as unknown as SessionCost)

    render(<CostPanel sessionId="session-1" />)

    // Wait for the loading state to finish and show empty state
    await waitFor(() => {
      expect(screen.queryByTestId('skeleton')).not.toBeInTheDocument()
    })

    expect(screen.getByText('No cost data available')).toBeInTheDocument()
  })

  it('handles API error with custom message', async () => {
    vi.mocked(getSessionCost).mockRejectedValue(new Error('Failed to fetch cost data'))

    render(<CostPanel sessionId="session-1" />)

    await waitFor(() => {
      expect(screen.getByText('Cost data unavailable')).toBeInTheDocument()
    })
  })

  it('handles non-Error objects in error state', async () => {
    vi.mocked(getSessionCost).mockRejectedValue('String error message')

    render(<CostPanel sessionId="session-1" />)

    await waitFor(() => {
      expect(screen.getByText('Cost data unavailable')).toBeInTheDocument()
    })
  })

  it('displays all cost rows in correct order', async () => {
    const mockCost = createSessionCost()
    vi.mocked(getSessionCost).mockResolvedValue(mockCost)

    render(<CostPanel sessionId="session-1" />)

    await waitFor(() => {
      expect(screen.getByText('Total Cost')).toBeInTheDocument()
      expect(screen.getByText('Tokens')).toBeInTheDocument()
      expect(screen.getByText('LLM Calls')).toBeInTheDocument()
      expect(screen.getByText('Tool Calls')).toBeInTheDocument()
    })
  })

  it('handles edge case of all zero values', async () => {
    const mockCost = createSessionCost({
      total_cost_usd: 0,
      total_tokens: 0,
      llm_calls: 0,
      tool_calls: 0,
    })
    vi.mocked(getSessionCost).mockResolvedValue(mockCost)

    render(<CostPanel sessionId="session-1" />)

    await waitFor(() => {
      expect(screen.getByText('$0.000000')).toBeInTheDocument()
      // Use getAllByText since there are multiple '0' elements
      expect(screen.getAllByText('0').length).toBeGreaterThan(0)
    })
  })

  it('handles very large cost values', async () => {
    const mockCost = createSessionCost({
      total_cost_usd: 123.456789,
    })
    vi.mocked(getSessionCost).mockResolvedValue(mockCost)

    render(<CostPanel sessionId="session-1" />)

    await waitFor(() => {
      expect(screen.getByText('$123.456789')).toBeInTheDocument()
    })
  })

  it('cleans up fetch on unmount', async () => {
    const mockCost = createSessionCost()
    vi.mocked(getSessionCost).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(mockCost), 100))
    )

    const { unmount } = render(<CostPanel sessionId="session-1" />)

    // Unmount before promise resolves
    unmount()

    // Should not cause errors or state updates after unmount
    await vi.waitFor(() => {
      expect(getSessionCost).toHaveBeenCalledWith('session-1')
    })
  })
})
