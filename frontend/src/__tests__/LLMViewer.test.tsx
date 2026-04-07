import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LLMViewer } from '../components/LLMViewer'
import type { TraceEvent } from '../types'

function createTraceEvent(overrides: Partial<TraceEvent> = {}): TraceEvent {
  return {
    id: 'event-1',
    session_id: 'session-1',
    timestamp: '2024-01-01T10:00:00Z',
    event_type: 'llm_request',
    parent_id: null,
    name: 'LLM Request',
    data: {},
    metadata: {},
    importance: 0.5,
    upstream_event_ids: [],
    model: 'gpt-4',
    messages: [
      { role: 'system', content: 'You are a helpful assistant.' },
      { role: 'user', content: 'Hello!' },
    ],
    ...overrides,
  }
}

describe('LLMViewer', () => {
  it('renders empty state when request is null', () => {
    render(<LLMViewer request={null} response={null} />)

    expect(screen.getByText('No LLM interaction selected')).toBeInTheDocument()
    expect(
      screen.getByText('Select an LLM request or response event from the trace to view the conversation details.'),
    ).toBeInTheDocument()
  })

  it('renders LLM header with model name', () => {
    const request = createTraceEvent({ model: 'gpt-4-turbo' })
    render(<LLMViewer request={request} response={null} />)

    expect(screen.getByText('LLM Interaction')).toBeInTheDocument()
    expect(screen.getByText('gpt-4-turbo')).toBeInTheDocument()
  })

  it('renders request messages with roles and content', () => {
    const request = createTraceEvent({
      messages: [
        { role: 'system', content: 'You are a helpful assistant.' },
        { role: 'user', content: 'What is the capital of France?' },
        { role: 'assistant', content: 'The capital of France is Paris.' },
      ],
    })
    render(<LLMViewer request={request} response={null} />)

    expect(screen.getByText('Request Messages')).toBeInTheDocument()
    expect(screen.getByText('system')).toBeInTheDocument()
    expect(screen.getByText('You are a helpful assistant.')).toBeInTheDocument()
    expect(screen.getByText('user')).toBeInTheDocument()
    expect(screen.getByText('What is the capital of France?')).toBeInTheDocument()
    expect(screen.getByText('assistant')).toBeInTheDocument()
    expect(screen.getByText('The capital of France is Paris.')).toBeInTheDocument()
  })

  it('handles empty messages array', () => {
    const request = createTraceEvent({ messages: [] })
    render(<LLMViewer request={request} response={null} />)

    expect(screen.getByText('Request Messages')).toBeInTheDocument()
  })

  it('handles missing messages (undefined defaults to empty array)', () => {
    const request = createTraceEvent({ messages: undefined })
    render(<LLMViewer request={request} response={null} />)

    expect(screen.getByText('Request Messages')).toBeInTheDocument()
  })

  it('does not render response section when response is null', () => {
    const request = createTraceEvent()
    render(<LLMViewer request={request} response={null} />)

    expect(screen.queryByText('Response')).not.toBeInTheDocument()
  })

  it('renders response with text content', () => {
    const request = createTraceEvent()
    const response = createTraceEvent({
      id: 'event-2',
      event_type: 'llm_response',
      content: 'This is the response content.',
      usage: { input_tokens: 10, output_tokens: 20 },
      cost_usd: 0.001,
    })
    render(<LLMViewer request={request} response={response} />)

    expect(screen.getByText('Response')).toBeInTheDocument()
    expect(screen.getByText('This is the response content.')).toBeInTheDocument()
  })

  it('renders response with tool calls', () => {
    const request = createTraceEvent()
    const response = createTraceEvent({
      id: 'event-2',
      event_type: 'llm_response',
      tool_calls: [
        {
          id: 'call-1',
          name: 'search',
          arguments: { query: 'Paris', limit: 5 },
        },
        {
          id: 'call-2',
          name: 'calculate',
          arguments: { a: 1, b: 2 },
        },
      ],
    })
    render(<LLMViewer request={request} response={response} />)

    expect(screen.getByText('Response')).toBeInTheDocument()
    expect(screen.getByText('Tool Calls')).toBeInTheDocument()
    expect(screen.getByText('search')).toBeInTheDocument()
    expect(screen.getByText('calculate')).toBeInTheDocument()
    expect(screen.getByText(/"query": "Paris"/)).toBeInTheDocument()
    expect(screen.getByText(/"limit": 5/)).toBeInTheDocument()
  })

  it('does not render tool calls section when tool_calls is empty', () => {
    const request = createTraceEvent()
    const response = createTraceEvent({
      id: 'event-2',
      event_type: 'llm_response',
      tool_calls: [],
    })
    render(<LLMViewer request={request} response={response} />)

    expect(screen.queryByText('Tool Calls')).not.toBeInTheDocument()
  })

  it('renders usage information', () => {
    const request = createTraceEvent()
    const response = createTraceEvent({
      id: 'event-2',
      event_type: 'llm_response',
      usage: { input_tokens: 100, output_tokens: 50 },
      cost_usd: 0.003,
    })
    render(<LLMViewer request={request} response={response} />)

    expect(screen.getByText('Input: 100 tokens')).toBeInTheDocument()
    expect(screen.getByText('Output: 50 tokens')).toBeInTheDocument()
    expect(screen.getByText('Cost: $0.0030')).toBeInTheDocument()
  })

  it('defaults usage to zero when missing', () => {
    const request = createTraceEvent()
    const response = createTraceEvent({
      id: 'event-2',
      event_type: 'llm_response',
    })
    render(<LLMViewer request={request} response={response} />)

    expect(screen.getByText('Input: 0 tokens')).toBeInTheDocument()
    expect(screen.getByText('Output: 0 tokens')).toBeInTheDocument()
    expect(screen.getByText('Cost: $0.0000')).toBeInTheDocument()
  })

  it('renders response with both content and tool calls', () => {
    const request = createTraceEvent()
    const response = createTraceEvent({
      id: 'event-2',
      event_type: 'llm_response',
      content: 'I will search for that information.',
      tool_calls: [
        {
          id: 'call-1',
          name: 'search',
          arguments: { query: 'test' },
        },
      ],
    })
    render(<LLMViewer request={request} response={response} />)

    expect(screen.getByText('I will search for that information.')).toBeInTheDocument()
    expect(screen.getByText('Tool Calls')).toBeInTheDocument()
    expect(screen.getByText('search')).toBeInTheDocument()
  })

  it('formats cost with 4 decimal places', () => {
    const request = createTraceEvent()
    const response = createTraceEvent({
      id: 'event-2',
      event_type: 'llm_response',
      cost_usd: 0.123456,
    })
    render(<LLMViewer request={request} response={response} />)

    expect(screen.getByText('Cost: $0.1235')).toBeInTheDocument()
  })
})
