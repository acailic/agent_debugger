import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SearchPanel } from '../components/SearchPanel'
import * as client from '../api/client'
import type { TraceEvent, TraceSearchResponse } from '../types'

// Mock the API client
vi.mock('../api/client', () => ({
  searchTraces: vi.fn(),
}))

// Helper functions to build test data
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

function createSearchResponse(overrides: Partial<TraceSearchResponse> = {}): TraceSearchResponse {
  return {
    query: 'test query',
    session_id: null,
    event_type: null,
    total: 1,
    results: [createEvent()],
    ...overrides,
  }
}

describe('SearchPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders search input', () => {
    render(<SearchPanel />)

    expect(screen.getByText('Trace Search')).toBeInTheDocument()
    expect(screen.getByText('Find the exact moment')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Belgrade, missing token, critic turn...')).toBeInTheDocument()
  })

  it('renders search button', () => {
    render(<SearchPanel />)

    expect(screen.getByRole('button', { name: 'Search' })).toBeInTheDocument()
  })

  it('renders event type selector', () => {
    render(<SearchPanel />)

    const select = screen.getByRole('combobox')
    expect(select).toBeInTheDocument()
  })

  it('renders scope switches', () => {
    render(<SearchPanel />)

    expect(screen.getByRole('button', { name: 'Current session' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'All sessions' })).toBeInTheDocument()
  })

  it('shows empty state when no search results', () => {
    render(<SearchPanel />)

    expect(screen.getByText('Search your traces')).toBeInTheDocument()
    expect(screen.getByText('Find events by name, payload content, or metadata')).toBeInTheDocument()
    expect(screen.getByText('error messages')).toBeInTheDocument()
    expect(screen.getByText('function names')).toBeInTheDocument()
    expect(screen.getByText('agent IDs')).toBeInTheDocument()
    expect(screen.getByText('tool calls')).toBeInTheDocument()
  })

  it('shows "no results" message when search returns empty', async () => {
    const user = userEvent.setup()
    const mockResponse = createSearchResponse({
      query: 'nonexistent',
      total: 0,
      results: [],
    })
    vi.mocked(client.searchTraces).mockResolvedValueOnce(mockResponse)

    render(<SearchPanel />)

    // Type in search input
    const input = screen.getByPlaceholderText('Belgrade, missing token, critic turn...')
    await user.type(input, 'nonexistent')

    // Click search button
    const searchButton = screen.getByRole('button', { name: 'Search' })
    await user.click(searchButton)

    await waitFor(() => {
      expect(screen.getByText('No results found')).toBeInTheDocument()
      expect(screen.getByText('Try adjusting your search terms or filters')).toBeInTheDocument()
    })
  })

  it('shows search results after successful search', async () => {
    const user = userEvent.setup()
    const mockEvent = createEvent({
      id: 'event-123',
      event_type: 'tool_call',
      name: 'search',
      tool_name: 'search_tool',
      timestamp: '2024-01-01T12:30:45Z',
    })
    const mockResponse = createSearchResponse({
      query: 'search',
      total: 1,
      results: [mockEvent],
    })
    vi.mocked(client.searchTraces).mockResolvedValueOnce(mockResponse)

    render(<SearchPanel />)

    // Type in search input
    const input = screen.getByPlaceholderText('Belgrade, missing token, critic turn...')
    await user.type(input, 'search')

    // Click search button
    const searchButton = screen.getByRole('button', { name: 'Search' })
    await user.click(searchButton)

    await waitFor(() => {
      expect(screen.getByText('1 result for "search"')).toBeInTheDocument()
    })
  })

  it('shows multiple search results', async () => {
    const user = userEvent.setup()
    const mockEvents = [
      createEvent({ id: 'event-1', event_type: 'decision', name: 'Decision 1' }),
      createEvent({ id: 'event-2', event_type: 'tool_call', name: 'Tool call 1' }),
      createEvent({ id: 'event-3', event_type: 'error', name: 'Error 1' }),
    ]
    const mockResponse = createSearchResponse({
      query: 'test',
      total: 3,
      results: mockEvents,
    })
    vi.mocked(client.searchTraces).mockResolvedValueOnce(mockResponse)

    render(<SearchPanel />)

    const input = screen.getByPlaceholderText('Belgrade, missing token, critic turn...')
    await user.type(input, 'test')

    const searchButton = screen.getByRole('button', { name: 'Search' })
    await user.click(searchButton)

    await waitFor(() => {
      expect(screen.getByText('3 results for "test"')).toBeInTheDocument()
    })
  })

  it('handles empty queries by clearing results', async () => {
    const user = userEvent.setup()
    render(<SearchPanel />)

    const input = screen.getByPlaceholderText('Belgrade, missing token, critic turn...')
    await user.clear(input)
    await user.type(input, '   ')

    const searchButton = screen.getByRole('button', { name: 'Search' })
    await user.click(searchButton)

    // Should not call search API with empty query
    expect(client.searchTraces).not.toHaveBeenCalled()
  })

  it('displays event type chips', async () => {
    const user = userEvent.setup()
    const mockEvents = [
      createEvent({ id: 'event-1', event_type: 'tool_call', name: 'Tool 1' }),
      createEvent({ id: 'event-2', event_type: 'llm_request', name: 'LLM 1' }),
      createEvent({ id: 'event-3', event_type: 'decision', name: 'Decision 1' }),
    ]
    const mockResponse = createSearchResponse({
      results: mockEvents,
    })
    vi.mocked(client.searchTraces).mockResolvedValueOnce(mockResponse)

    render(<SearchPanel />)

    const input = screen.getByPlaceholderText('Belgrade, missing token, critic turn...')
    await user.type(input, 'test')

    const searchButton = screen.getByRole('button', { name: 'Search' })
    await user.click(searchButton)

    await waitFor(() => {
      expect(screen.getByText('tool call')).toBeInTheDocument()
      expect(screen.getByText('llm request')).toBeInTheDocument()
      expect(screen.getByText('decision')).toBeInTheDocument()
    })
  })

  it('displays timestamp for search results', async () => {
    const user = userEvent.setup()
    const mockEvent = createEvent({
      id: 'event-1',
      event_type: 'decision',
      timestamp: '2024-01-15T14:30:45Z',
    })
    const mockResponse = createSearchResponse({
      results: [mockEvent],
    })
    vi.mocked(client.searchTraces).mockResolvedValueOnce(mockResponse)

    render(<SearchPanel />)

    const input = screen.getByPlaceholderText('Belgrade, missing token, critic turn...')
    await user.type(input, 'test')

    const searchButton = screen.getByRole('button', { name: 'Search' })
    await user.click(searchButton)

    // Check that a time is displayed (format depends on locale)
    await waitFor(() => {
      expect(screen.getByText(/\d{1,2}:\d{2}:\d{2}/)).toBeInTheDocument()
    })
  })

  it('handles search submission via Enter key', async () => {
    const user = userEvent.setup()
    const mockResponse = createSearchResponse()
    vi.mocked(client.searchTraces).mockResolvedValueOnce(mockResponse)

    render(<SearchPanel />)

    const input = screen.getByPlaceholderText('Belgrade, missing token, critic turn...')
    await user.type(input, 'test query{Enter}')

    await waitFor(() => {
      expect(client.searchTraces).toHaveBeenCalled()
    })
  })

  it('handles edge case: search result with special characters in name', async () => {
    const user = userEvent.setup()
    const mockEvent = createEvent({
      id: 'event-1',
      event_type: 'error',
      name: 'Error: <script>alert("xss")</script>',
    })
    const mockResponse = createSearchResponse({
      results: [mockEvent],
    })
    vi.mocked(client.searchTraces).mockResolvedValueOnce(mockResponse)

    render(<SearchPanel />)

    const input = screen.getByPlaceholderText('Belgrade, missing token, critic turn...')
    await user.type(input, 'test')

    const searchButton = screen.getByRole('button', { name: 'Search' })
    await user.click(searchButton)

    // The text should be displayed, not rendered as HTML
    await waitFor(() => {
      expect(screen.getByText('Error: <script>alert("xss")</script>')).toBeInTheDocument()
    })
  })

  it('handles edge case: very long search query', async () => {
    const user = userEvent.setup()
    const longQuery = 'a'.repeat(100)
    const mockResponse = createSearchResponse()
    vi.mocked(client.searchTraces).mockResolvedValueOnce(mockResponse)

    render(<SearchPanel />)

    const input = screen.getByPlaceholderText('Belgrade, missing token, critic turn...')
    await user.type(input, longQuery)

    const searchButton = screen.getByRole('button', { name: 'Search' })
    await user.click(searchButton)

    await waitFor(() => {
      expect(client.searchTraces).toHaveBeenCalled()
    })
  })
})
