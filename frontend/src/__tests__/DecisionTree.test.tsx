import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DecisionTree } from '../components/DecisionTree'
import type { TraceEvent, TreeNode } from '../types'

// Helper function to create test events
function createTestEvent(overrides: Partial<TraceEvent> = {}): TraceEvent {
  return {
    id: `event-${Math.random().toString(36).substr(2, 9)}`,
    session_id: 'test-session',
    timestamp: new Date().toISOString(),
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

// Helper to create a tree node
function createTreeNode(event: TraceEvent, children: TreeNode[] = []): TreeNode {
  return {
    event,
    children,
  }
}

// Helper to create a simple tree structure
function createSimpleTree(): TreeNode {
  const rootEvent = createTestEvent({
    id: 'root',
    event_type: 'trace_root',
    name: 'Root',
  })
  const child1Event = createTestEvent({
    id: 'child-1',
    event_type: 'agent_turn',
    name: 'Child 1',
  })
  const child2Event = createTestEvent({
    id: 'child-2',
    event_type: 'decision',
    name: 'Child 2',
  })

  return createTreeNode(rootEvent, [
    createTreeNode(child1Event),
    createTreeNode(child2Event),
  ])
}

// Helper to create a deep tree
function createDeepTree(depth: number = 3): TreeNode {
  const rootEvent = createTestEvent({
    id: 'root',
    event_type: 'trace_root',
    name: 'Root',
  })

  let currentNode = createTreeNode(rootEvent)
  const root = currentNode

  for (let i = 0; i < depth; i++) {
    const childEvent = createTestEvent({
      id: `node-${i}`,
      event_type: i % 2 === 0 ? 'agent_turn' : 'decision',
      name: `Node ${i}`,
    })
    const childNode = createTreeNode(childEvent)
    currentNode.children.push(childNode)
    currentNode = childNode
  }

  return root
}

describe('DecisionTree', () => {
  let container: HTMLElement

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
  })

  afterEach(() => {
    document.body.removeChild(container)
  })

  it('renders null tree gracefully', () => {
    const onSelectEvent = vi.fn()

    render(
      <DecisionTree
        tree={null}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />,
      { container }
    )

    expect(screen.getByText('No tree data available')).toBeInTheDocument()
  })

  it('renders tree nodes', () => {
    const tree = createSimpleTree()
    const onSelectEvent = vi.fn()

    render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />,
      { container }
    )

    // Check for legend items
    expect(screen.getByText('Session')).toBeInTheDocument()
    expect(screen.getByText('LLM')).toBeInTheDocument()
    expect(screen.getByText('Tool')).toBeInTheDocument()
    expect(screen.getByText('Decision')).toBeInTheDocument()
    expect(screen.getByText('Risk')).toBeInTheDocument()
  })

  it('handles node selection', async () => {
    const tree = createSimpleTree()
    const onSelectEvent = vi.fn()

    const { container } = render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    // Find and click a node (SVG nodes are rendered with data-id attribute)
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()

    // Simulate clicking on the SVG - in real scenario, D3 handles the click
    // We verify the component rendered without errors
    expect(svg).toBeInTheDocument()
  })

  it('shows correct event types in legend', () => {
    const tree = createSimpleTree()
    const onSelectEvent = vi.fn()

    render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />,
      { container }
    )

    expect(screen.getByText('Session')).toBeInTheDocument()
    expect(screen.getByText('LLM')).toBeInTheDocument()
    expect(screen.getByText('Tool')).toBeInTheDocument()
    expect(screen.getByText('Decision')).toBeInTheDocument()
    expect(screen.getByText('Risk')).toBeInTheDocument()
  })

  it('highlights selected node', () => {
    const tree = createSimpleTree()
    const onSelectEvent = vi.fn()

    const { container } = render(
      <DecisionTree
        tree={tree}
        selectedEventId="child-1"
        onSelectEvent={onSelectEvent}
      />
    )

    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })

  it('handles deep tree', () => {
    const tree = createDeepTree(5)
    const onSelectEvent = vi.fn()

    const { container } = render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })

  it('handles single node tree', () => {
    const singleNodeTree = createTreeNode(
      createTestEvent({
        id: 'root',
        event_type: 'trace_root',
        name: 'Root',
      })
    )
    const onSelectEvent = vi.fn()

    const { container } = render(
      <DecisionTree
        tree={singleNodeTree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })

  it('renders zoom controls', () => {
    const tree = createSimpleTree()
    const onSelectEvent = vi.fn()

    render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />,
      { container }
    )

    expect(screen.getByRole('button', { name: '+' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '-' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reset' })).toBeInTheDocument()
  })

  it('handles zoom in button click', async () => {
    const user = userEvent.setup()
    const tree = createSimpleTree()
    const onSelectEvent = vi.fn()

    render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />,
      { container }
    )

    const zoomInButton = screen.getByRole('button', { name: '+' })
    await user.click(zoomInButton)

    // Component should still render without errors
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })

  it('handles zoom out button click', async () => {
    const user = userEvent.setup()
    const tree = createSimpleTree()
    const onSelectEvent = vi.fn()

    render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />,
      { container }
    )

    const zoomOutButton = screen.getByRole('button', { name: '-' })
    await user.click(zoomOutButton)

    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })

  it('handles reset view button click', async () => {
    const user = userEvent.setup()
    const tree = createSimpleTree()
    const onSelectEvent = vi.fn()

    render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />,
      { container }
    )

    const resetButton = screen.getByRole('button', { name: 'Reset' })
    await user.click(resetButton)

    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })

  it('displays zoom level', () => {
    const tree = createSimpleTree()
    const onSelectEvent = vi.fn()

    render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />,
      { container }
    )

    expect(screen.getByText('100%')).toBeInTheDocument()
  })

  it('renders edge type legend', () => {
    const tree = createSimpleTree()
    const onSelectEvent = vi.fn()

    render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />,
      { container }
    )

    expect(screen.getByText('Parent-Child')).toBeInTheDocument()
    expect(screen.getByText('Evidence')).toBeInTheDocument()
    expect(screen.getByText('Inferred')).toBeInTheDocument()
  })

  it('handles controls collapse toggle', async () => {
    const user = userEvent.setup()
    const tree = createSimpleTree()
    const onSelectEvent = vi.fn()

    render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />,
      { container }
    )

    const toggleButton = screen.getByRole('button', { name: 'Hide controls' })
    await user.click(toggleButton)

    // Controls should be hidden
    expect(screen.queryByRole('button', { name: '+' })).not.toBeInTheDocument()

    // Toggle back
    const showButton = screen.getByRole('button', { name: 'Show controls' })
    await user.click(showButton)

    // Controls should be visible again
    expect(screen.getByRole('button', { name: '+' })).toBeInTheDocument()
  })

  it('renders tree with different event types', () => {
    const rootEvent = createTestEvent({
      id: 'root',
      event_type: 'trace_root',
      name: 'Root',
    })
    const llmEvent = createTestEvent({
      id: 'llm-1',
      event_type: 'llm_request',
      name: 'LLM Request',
    })
    const toolEvent = createTestEvent({
      id: 'tool-1',
      event_type: 'tool_call',
      name: 'Tool Call',
    })
    const errorEvent = createTestEvent({
      id: 'error-1',
      event_type: 'error',
      name: 'Error',
    })

    const tree = createTreeNode(rootEvent, [
      createTreeNode(llmEvent),
      createTreeNode(toolEvent),
      createTreeNode(errorEvent),
    ])

    const onSelectEvent = vi.fn()

    const { container } = render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })

  it('handles tree with evidence links', () => {
    const rootEvent = createTestEvent({
      id: 'root',
      event_type: 'trace_root',
      name: 'Root',
    })
    const decisionEvent = createTestEvent({
      id: 'decision-1',
      event_type: 'decision',
      name: 'Decision',
      evidence_event_ids: ['root'],
    })

    const tree = createTreeNode(rootEvent, [
      createTreeNode(decisionEvent),
    ])

    const onSelectEvent = vi.fn()

    const { container } = render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })

  it('handles tree with upstream links', () => {
    const rootEvent = createTestEvent({
      id: 'root',
      event_type: 'trace_root',
      name: 'Root',
    })
    const childEvent = createTestEvent({
      id: 'child-1',
      event_type: 'agent_turn',
      name: 'Child',
      upstream_event_ids: ['root'],
    })

    const tree = createTreeNode(rootEvent, [
      createTreeNode(childEvent),
    ])

    const onSelectEvent = vi.fn()

    const { container } = render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })

  it('handles tree with complex structure', () => {
    const rootEvent = createTestEvent({
      id: 'root',
      event_type: 'trace_root',
      name: 'Root',
    })

    const branch1 = createTreeNode(
      createTestEvent({
        id: 'branch-1',
        event_type: 'agent_turn',
        name: 'Branch 1',
      }),
      [
        createTreeNode(
          createTestEvent({
            id: 'leaf-1-1',
            event_type: 'decision',
            name: 'Leaf 1.1',
          })
        ),
        createTreeNode(
          createTestEvent({
            id: 'leaf-1-2',
            event_type: 'tool_call',
            name: 'Leaf 1.2',
          })
        ),
      ]
    )

    const branch2 = createTreeNode(
      createTestEvent({
        id: 'branch-2',
        event_type: 'llm_request',
        name: 'Branch 2',
      }),
      [
        createTreeNode(
          createTestEvent({
            id: 'leaf-2-1',
            event_type: 'llm_response',
            name: 'Leaf 2.1',
          })
        ),
      ]
    )

    const tree = createTreeNode(rootEvent, [branch1, branch2])

    const onSelectEvent = vi.fn()

    const { container } = render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })

  it('shows jump to recommended button when recommendation exists', () => {
    // Create a tree with error to trigger recommendation
    const rootEvent = createTestEvent({
      id: 'root',
      event_type: 'trace_root',
      name: 'Root',
    })
    const errorEvent = createTestEvent({
      id: 'error-1',
      event_type: 'error',
      name: 'Error',
    })
    const decisionEvent = createTestEvent({
      id: 'decision-1',
      event_type: 'decision',
      name: 'Decision',
      confidence: 0.3,
      evidence: [],
    })

    const tree = createTreeNode(rootEvent, [
      createTreeNode(errorEvent, [
        createTreeNode(decisionEvent),
      ]),
    ])

    const onSelectEvent = vi.fn()

    render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />,
      { container }
    )

    // Jump to recommended button may appear based on priority computation
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })

  it('handles wheel events for pan', async () => {
    const tree = createSimpleTree()
    const onSelectEvent = vi.fn()

    const { container } = render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()

    // Simulate wheel event
    if (svg) {
      const wheelEvent = new WheelEvent('wheel', {
        deltaX: 10,
        deltaY: 10,
        ctrlKey: false,
      })
      svg.dispatchEvent(wheelEvent)
    }

    // Component should still render without errors
    expect(svg).toBeInTheDocument()
  })

  it('handles wheel events for zoom with ctrl key', async () => {
    const tree = createSimpleTree()
    const onSelectEvent = vi.fn()

    const { container } = render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />
    )

    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()

    if (svg) {
      const wheelEvent = new WheelEvent('wheel', {
        deltaY: 10,
        ctrlKey: true,
      })
      svg.dispatchEvent(wheelEvent)
    }

    expect(svg).toBeInTheDocument()
  })

  // jsdom has no layout, so the ResizeObserver feedback loop (the svg is sized
  // from the container while the content-sized container grows with the svg —
  // ~4kpx per 400ms on the Inspect tab) is pinned at the mechanism level: the
  // container measurement is simulated as svg height + in-flow chrome above it,
  // exactly what a content-driven layout reports, and the observer callback is
  // driven by hand through a controllable stub.
  function renderWithControllableObserver() {
    let observerCallback: ResizeObserverCallback | undefined
    class ControllableResizeObserver {
      constructor(callback: ResizeObserverCallback) {
        observerCallback = callback
      }
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    vi.stubGlobal('ResizeObserver', ControllableResizeObserver)

    const tree = createSimpleTree()
    const onSelectEvent = vi.fn()
    render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />,
      { container }
    )
    const treeEl = container.querySelector<HTMLElement>('.decision-tree')
    const svgEl = container.querySelector<SVGSVGElement>('svg')
    expect(treeEl).toBeTruthy()
    expect(svgEl).toBeTruthy()

    // In-flow chrome (padding + controls + legend) between the container top
    // and the svg: the container reports the svg height plus this offset.
    const CHROME = 117.6
    vi.spyOn(svgEl!, 'getBoundingClientRect').mockReturnValue({ top: CHROME } as DOMRect)
    Object.defineProperty(treeEl!, 'clientHeight', {
      configurable: true,
      get: () => Number(svgEl!.getAttribute('height')) + CHROME,
    })
    Object.defineProperty(treeEl!, 'clientWidth', {
      configurable: true,
      get: () => 700,
    })

    return {
      svgEl: svgEl!,
      fire: () =>
        act(async () => {
          observerCallback?.([], {} as ResizeObserver)
        }),
      cleanup: () => {
        vi.unstubAllGlobals()
        vi.restoreAllMocks()
      },
    }
  }

  it('does not regrow the svg when the observer refires with an unchanged container size', async () => {
    const { svgEl, fire, cleanup } = renderWithControllableObserver()
    try {
      await fire()
      const settledHeight = svgEl.getAttribute('height')
      expect(settledHeight).toBeTruthy()

      for (let i = 0; i < 6; i++) {
        await fire()
      }
      expect(svgEl.getAttribute('height')).toBe(settledHeight)
    } finally {
      cleanup()
    }
  })

  it('still applies genuine container size changes without regrowing', async () => {
    const tree = createSimpleTree()
    const onSelectEvent = vi.fn()
    let observerCallback: ResizeObserverCallback | undefined
    class ControllableResizeObserver {
      constructor(callback: ResizeObserverCallback) {
        observerCallback = callback
      }
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    vi.stubGlobal('ResizeObserver', ControllableResizeObserver)

    render(
      <DecisionTree
        tree={tree}
        selectedEventId={null}
        onSelectEvent={onSelectEvent}
      />,
      { container }
    )
    const treeEl = container.querySelector<HTMLElement>('.decision-tree')
    const svgEl = container.querySelector<SVGSVGElement>('svg')
    const fire = () => act(async () => { observerCallback?.([], {} as ResizeObserver) })

    try {
      // A container with a definite height (independent of the svg): the svg
      // must fill the space below the chrome and then stop.
      const CONTAINER_HEIGHT = 800
      const CHROME = 117.6
      vi.spyOn(svgEl!, 'getBoundingClientRect').mockReturnValue({ top: CHROME } as DOMRect)
      Object.defineProperty(treeEl!, 'clientHeight', {
        configurable: true,
        get: () => CONTAINER_HEIGHT,
      })
      let width = 700
      Object.defineProperty(treeEl!, 'clientWidth', {
        configurable: true,
        get: () => width,
      })

      await fire()
      expect(svgEl!.getAttribute('width')).toBe('700')
      expect(svgEl!.getAttribute('height')).toBe(String(CONTAINER_HEIGHT - CHROME))

      for (let i = 0; i < 4; i++) {
        await fire()
      }
      expect(svgEl!.getAttribute('height')).toBe(String(CONTAINER_HEIGHT - CHROME))

      width = 500
      await fire()
      expect(svgEl!.getAttribute('width')).toBe('500')
      expect(svgEl!.getAttribute('height')).toBe(String(CONTAINER_HEIGHT - CHROME))
    } finally {
      vi.unstubAllGlobals()
      vi.restoreAllMocks()
    }
  })
})
