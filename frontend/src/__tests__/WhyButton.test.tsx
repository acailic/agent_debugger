import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import WhyButton from '../components/WhyButton'
import type { FailureExplanation } from '../types'

// Mock the API client
vi.mock('../api/client', () => ({
  getAnalysis: vi.fn(),
}))

import { getAnalysis } from '../api/client'

const mockExplanation: FailureExplanation = {
  failure_event_id: 'evt-1',
  failure_event_type: 'error',
  failure_headline: 'API timeout after 30s',
  failure_mode: 'tool_failure',
  symptom: 'The external search API did not respond within the configured timeout.',
  likely_cause: 'External API rate limit exceeded',
  likely_cause_event_id: 'evt-5',
  confidence: 0.87,
  supporting_event_ids: ['evt-2', 'evt-3'],
  next_inspection_event_id: 'evt-5',
  narrative: 'The tool call to search_api failed due to a timeout. This was likely caused by rate limiting on the external service.',
  candidates: [
    {
      event_id: 'evt-5',
      event_type: 'tool_call',
      headline: 'search_api timed out',
      score: 0.92,
      causal_depth: 0,
      relation: 'caused',
      relation_label: 'direct cause',
      explicit: true,
      supporting_event_ids: ['evt-2'],
      rationale: 'This tool call exceeded the timeout threshold.',
    },
    {
      event_id: 'evt-3',
      event_type: 'llm_response',
      headline: 'Model chose slow tool',
      score: 0.45,
      causal_depth: 1,
      relation: 'contributed',
      relation_label: 'indirect cause',
      explicit: false,
      supporting_event_ids: [],
      rationale: 'The model selected a tool with known latency issues.',
    },
  ],
}

const mockAnalysisResponse = {
  session_id: 's1',
  analysis: {
    failure_explanations: [mockExplanation],
  },
} as Parameters<typeof getAnalysis> extends Promise<infer R> ? R : never

const mockEmptyAnalysisResponse = {
  session_id: 's1',
  analysis: {
    failure_explanations: [],
  },
} as Parameters<typeof getAnalysis> extends Promise<infer R> ? R : never

describe('WhyButton', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the button in idle state', () => {
    render(
      <WhyButton sessionId="s1" onSelectEvent={vi.fn()} onFocusReplay={vi.fn()} />
    )
    expect(screen.getByRole('button', { name: /why did it fail/i })).toBeInTheDocument()
  })

  it('renders nothing when hasFailures is false', () => {
    const { container } = render(
      <WhyButton sessionId="s1" onSelectEvent={vi.fn()} onFocusReplay={vi.fn()} hasFailures={false} />
    )
    expect(container.innerHTML).toBe('')
  })

  it('shows explanation after clicking button', async () => {
    vi.mocked(getAnalysis).mockResolvedValue(mockAnalysisResponse)

    render(<WhyButton sessionId="s1" onSelectEvent={vi.fn()} onFocusReplay={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /why did it fail/i }))

    await waitFor(() => {
      expect(screen.getByText('API timeout after 30s')).toBeInTheDocument()
    })
    expect(screen.getByText(/87%/)).toBeInTheDocument()
    // failure_mode is rendered with underscores replaced by spaces
    expect(screen.getByText('tool failure')).toBeInTheDocument()
  })

  it('shows error state when API fails', async () => {
    vi.mocked(getAnalysis).mockRejectedValue(new Error('Network error'))

    render(<WhyButton sessionId="s1" onSelectEvent={vi.fn()} onFocusReplay={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /why did it fail/i }))

    await waitFor(() => {
      expect(screen.getByText(/analysis failed/i)).toBeInTheDocument()
    })
  })

  it('shows no failures message when response is empty', async () => {
    vi.mocked(getAnalysis).mockResolvedValue(mockEmptyAnalysisResponse)

    render(<WhyButton sessionId="s1" onSelectEvent={vi.fn()} onFocusReplay={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /why did it fail/i }))

    await waitFor(() => {
      expect(screen.getByText(/no failure patterns detected/i)).toBeInTheDocument()
    })
  })

  it('calls onSelectEvent when a candidate is clicked', async () => {
    vi.mocked(getAnalysis).mockResolvedValue(mockAnalysisResponse)

    const onSelectEvent = vi.fn()
    render(<WhyButton sessionId="s1" onSelectEvent={onSelectEvent} onFocusReplay={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /why did it fail/i }))

    await waitFor(() => {
      expect(screen.getByText('search_api timed out')).toBeInTheDocument()
    })
    await userEvent.click(screen.getByText('search_api timed out'))

    expect(onSelectEvent).toHaveBeenCalledWith('evt-5')
  })

  it('calls onSelectEvent and onFocusReplay when inspect likely cause is clicked', async () => {
    vi.mocked(getAnalysis).mockResolvedValue(mockAnalysisResponse)

    const onSelectEvent = vi.fn()
    const onFocusReplay = vi.fn()
    render(<WhyButton sessionId="s1" onSelectEvent={onSelectEvent} onFocusReplay={onFocusReplay} />)

    await userEvent.click(screen.getByRole('button', { name: /why did it fail/i }))

    await waitFor(() => {
      expect(screen.getByText(/inspect likely cause/i)).toBeInTheDocument()
    })
    await userEvent.click(screen.getByText(/inspect likely cause/i))

    expect(onSelectEvent).toHaveBeenCalledWith('evt-5')
    expect(onFocusReplay).toHaveBeenCalledWith('evt-5')
  })

  it('disables button while loading', async () => {
    let resolvePromise!: (value: typeof mockAnalysisResponse) => void
    vi.mocked(getAnalysis).mockReturnValue(
      new Promise<typeof mockAnalysisResponse>((resolve) => { resolvePromise = resolve })
    )

    render(<WhyButton sessionId="s1" onSelectEvent={vi.fn()} onFocusReplay={vi.fn()} />)

    const btn = screen.getByRole('button', { name: /why did it fail/i })
    await userEvent.click(btn)

    expect(btn).toBeDisabled()

    resolvePromise!(mockAnalysisResponse)

    await waitFor(() => {
      expect(btn).not.toBeDisabled()
    })
  })

  it('resets state when sessionId changes', async () => {
    vi.mocked(getAnalysis).mockResolvedValue(mockAnalysisResponse)

    const { rerender } = render(
      <WhyButton sessionId="s1" onSelectEvent={vi.fn()} onFocusReplay={vi.fn()} />
    )

    await userEvent.click(screen.getByRole('button', { name: /why did it fail/i }))

    await waitFor(() => {
      expect(screen.getByText('API timeout after 30s')).toBeInTheDocument()
    })

    // Rerender with new session -- should reset
    rerender(<WhyButton sessionId="s2" onSelectEvent={vi.fn()} onFocusReplay={vi.fn()} />)

    expect(screen.queryByText('API timeout after 30s')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /why did it fail/i })).toBeInTheDocument()
  })

  it('shows narrative when present', async () => {
    vi.mocked(getAnalysis).mockResolvedValue(mockAnalysisResponse)

    render(<WhyButton sessionId="s1" onSelectEvent={vi.fn()} onFocusReplay={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /why did it fail/i }))

    await waitFor(() => {
      expect(screen.getByText(/rate limiting on the external service/i)).toBeInTheDocument()
    })
  })
})
