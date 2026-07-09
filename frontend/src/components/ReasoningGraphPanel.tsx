import { useState, useCallback, useMemo, useRef, useEffect, memo } from 'react'
import * as d3 from 'd3'
import type { TraceEvent, TreeNode } from '../types'
import { formatEventHeadline } from '../utils/formatting'
import './ReasoningGraphPanel.css'

export type ViewMode = 'sequential' | 'tree' | 'graph'

interface ReasoningGraphPanelProps {
  events: TraceEvent[]
  tree: TreeNode | null
  selectedEventId: string | null
  onSelectEvent: (eventId: string) => void
}

interface ReasoningStep {
  event: TraceEvent
  depth: number
  parentIds: string[]
  children: ReasoningStep[]
}

// Build reasoning graph structure from events
function buildReasoningGraph(events: TraceEvent[]): ReasoningStep[] {
  const eventMap = new Map<string, ReasoningStep>()
  const rootSteps: ReasoningStep[] = []

  // First pass: create all steps
  events.forEach((event) => {
    const step: ReasoningStep = {
      event,
      depth: 0,
      parentIds: event.upstream_event_ids || [],
      children: [],
    }
    eventMap.set(event.id, step)
  })

  // Second pass: establish relationships and compute depths
  events.forEach((event) => {
    const step = eventMap.get(event.id)
    if (!step) return

    if (step.parentIds.length === 0) {
      // Root node
      rootSteps.push(step)
    } else {
      // Add as child to parents
      step.parentIds.forEach((parentId) => {
        const parentStep = eventMap.get(parentId)
        if (parentStep) {
          parentStep.children.push(step)
          step.depth = Math.max(step.depth, parentStep.depth + 1)
        }
      })
    }
  })

  return rootSteps
}

// Convert TreeNode to ReasoningStep for tree view
function convertTreeToReasoningSteps(node: TreeNode): ReasoningStep {
  const step: ReasoningStep = {
    event: node.event,
    depth: 0,
    parentIds: node.event.upstream_event_ids || [],
    children: node.children.map(convertTreeToReasoningSteps),
  }

  // Compute depth for children
  const computeDepth = (step: ReasoningStep, currentDepth: number) => {
    step.depth = currentDepth
    step.children.forEach(child => computeDepth(child, currentDepth + 1))
  }
  computeDepth(step, 0)

  return step
}

// Node colors for reasoning graph
const NODE_COLORS: Record<string, string> = {
  trace_root: 'var(--node-default)',
  agent_start: 'var(--node-session)',
  agent_end: 'var(--node-session)',
  llm_request: 'var(--node-llm)',
  llm_response: 'var(--node-llm)',
  tool_call: 'var(--node-tool)',
  tool_result: 'var(--node-tool)',
  decision: 'var(--node-decision)',
  error: 'var(--node-risk)',
  checkpoint: 'var(--node-checkpoint)',
  safety_check: 'var(--node-decision)',
  refusal: 'var(--node-risk)',
  policy_violation: 'var(--node-risk)',
  prompt_policy: 'var(--node-llm)',
  agent_turn: 'var(--node-session)',
  behavior_alert: 'var(--node-decision)',
}

// Sequential View Component
interface SequentialViewProps {
  steps: ReasoningStep[]
  selectedEventId: string | null
  onSelectEvent: (eventId: string) => void
}

function SequentialView({ steps, selectedEventId, onSelectEvent }: SequentialViewProps) {
  const allSteps = useMemo(() => {
    const result: ReasoningStep[] = []
    const traverse = (step: ReasoningStep) => {
      result.push(step)
      step.children.forEach(traverse)
    }
    steps.forEach(traverse)
    // Sort by timestamp for sequential view
    return result.sort((a, b) => a.event.timestamp.localeCompare(b.event.timestamp))
  }, [steps])

  return (
    <div className="sequential-view">
      <div className="sequential-list">
        {allSteps.map((step) => (
          <div
            key={step.event.id}
            className={`sequential-item ${step.event.id === selectedEventId ? 'selected' : ''}`}
            onClick={() => onSelectEvent(step.event.id)}
          >
            <div className="sequential-number">{step.event.sequence || step.event.timestamp.slice(-6)}</div>
            <div className="sequential-content">
              <div className="sequential-header">
                <span className="sequential-type">{step.event.event_type.replace(/_/g, ' ')}</span>
                <span className="sequential-time">
                  {new Date(step.event.timestamp).toLocaleTimeString()}
                </span>
              </div>
              <div className="sequential-title">{formatEventHeadline(step.event)}</div>
              {step.event.reasoning && (
                <div className="sequential-reasoning">{step.event.reasoning}</div>
              )}
              {step.children.length > 0 && (
                <div className="sequential-branches">
                  <span className="branch-count">{step.children.length} branch{step.children.length > 1 ? 'es' : ''}</span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// Tree View Component
interface TreeViewProps {
  steps: ReasoningStep[]
  selectedEventId: string | null
  onSelectEvent: (eventId: string) => void
}

function TreeView({ steps, selectedEventId, onSelectEvent }: TreeViewProps) {
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set())

  const toggleCollapse = useCallback((stepId: string) => {
    setCollapsedIds(prev => {
      const next = new Set(prev)
      if (next.has(stepId)) {
        next.delete(stepId)
      } else {
        next.add(stepId)
      }
      return next
    })
  }, [])

  function renderTree(step: ReasoningStep, depth: number = 0) {
    const isCollapsed = collapsedIds.has(step.event.id)
    const hasChildren = step.children.length > 0

    return (
      <div key={step.event.id} className="tree-node-wrapper" style={{ marginLeft: `${depth * 20}px` }}>
        <div
          className={`tree-node ${step.event.id === selectedEventId ? 'selected' : ''}`}
          onClick={() => onSelectEvent(step.event.id)}
        >
          {hasChildren && (
            <button
              className="tree-collapse-btn"
              onClick={(e) => {
                e.stopPropagation()
                toggleCollapse(step.event.id)
              }}
            >
              {isCollapsed ? '▶' : '▼'}
            </button>
          )}
          <div
            className="tree-node-marker"
            style={{ backgroundColor: NODE_COLORS[step.event.event_type] || 'var(--node-default)' }}
          />
          <div className="tree-node-content">
            <span className="tree-node-type">{step.event.event_type.replace(/_/g, ' ')}</span>
            <span className="tree-node-title">{formatEventHeadline(step.event)}</span>
          </div>
        </div>
        {!isCollapsed && hasChildren && (
          <div className="tree-children">
            {step.children.map(child => renderTree(child, depth + 1))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="tree-view">
      <div className="tree-container">
        {steps.map(step => renderTree(step))}
      </div>
    </div>
  )
}

// Graph View Component with D3 Force Layout
interface GraphViewProps {
  steps: ReasoningStep[]
  selectedEventId: string | null
  onSelectEvent: (eventId: string) => void
}

interface GraphNode extends d3.SimulationNodeDatum {
  id: string
  event: TraceEvent
  radius: number
  color: string
}

interface GraphLink extends d3.SimulationLinkDatum<GraphNode> {
  source: GraphNode | string
  target: GraphNode | string
}

function GraphView({ steps, selectedEventId, onSelectEvent }: GraphViewProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
  const [zoom, setZoom] = useState(1)

  // Flatten steps into nodes and links
  const { nodes, links } = useMemo(() => {
    const nodeMap = new Map<string, GraphNode>()
    const linkArray: GraphLink[] = []

    const traverse = (step: ReasoningStep) => {
      const node: GraphNode = {
        id: step.event.id,
        event: step.event,
        radius: 8,
        color: NODE_COLORS[step.event.event_type] || 'var(--node-default)',
      }
      nodeMap.set(step.event.id, node)

      step.children.forEach(child => {
        linkArray.push({
          source: step.event.id,
          target: child.event.id,
        })
        traverse(child)
      })
    }

    steps.forEach(traverse)
    return { nodes: Array.from(nodeMap.values()), links: linkArray }
  }, [steps])

  // D3 Force Simulation
  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    // Create simulation
    const simulation = d3.forceSimulation<GraphNode>(nodes)
      .force('link', d3.forceLink<GraphNode, GraphLink>(links)
        .id(d => d.id)
        .distance(100)
      )
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(dimensions.width / 2, dimensions.height / 2))
      .force('collision', d3.forceCollide().radius(20))

    // Create SVG group for zoom
    const g = svg.append('g')

    // Add zoom behavior
    const zoomBehavior = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform)
        setZoom(event.transform.k)
      })

    svg.call(zoomBehavior)

    // Create links
    const link = g.append('g')
      .selectAll('line')
      .data(links)
      .enter()
      .append('line')
      .attr('stroke', 'var(--link-stroke)')
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', 1.5)

    // Create nodes
    const node = g.append('g')
      .selectAll<SVGGElement, GraphNode>('g')
      .data(nodes)
      .enter()
      .append('g')
      .attr('class', 'graph-node')
      .call(d3.drag<SVGGElement, GraphNode>()
        .on('start', (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart()
          d.fx = d.x
          d.fy = d.y
        })
        .on('drag', (event, d) => {
          d.fx = event.x
          d.fy = event.y
        })
        .on('end', (event, d) => {
          if (!event.active) simulation.alphaTarget(0)
          d.fx = null
          d.fy = null
        })
      )

    // Add circles to nodes
    node.append('circle')
      .attr('r', d => d.radius)
      .attr('fill', d => d.color)
      .attr('stroke', d => d.id === selectedEventId ? 'var(--node-selected)' : 'var(--node-stroke)')
      .attr('stroke-width', d => d.id === selectedEventId ? 2.5 : 1.5)
      .style('cursor', 'pointer')

    // Add labels
    node.append('text')
      .attr('dy', 4)
      .attr('text-anchor', 'middle')
      .attr('fill', 'white')
      .attr('font-size', '8px')
      .attr('font-weight', '600')
      .attr('pointer-events', 'none')
      .text(d => d.event.event_type.charAt(0).toUpperCase())

    // Click handler
    node.on('click', (event, d) => {
      event.stopPropagation()
      onSelectEvent(d.id)
    })

    // Update positions on tick
    simulation.on('tick', () => {
      link
        .attr('x1', d => (d.source as GraphNode).x || 0)
        .attr('y1', d => (d.source as GraphNode).y || 0)
        .attr('x2', d => (d.target as GraphNode).x || 0)
        .attr('y2', d => (d.target as GraphNode).y || 0)

      node.attr('transform', d => `translate(${d.x || 0},${d.y || 0})`)
    })

    return () => {
      simulation.stop()
      svg.selectAll('*').remove()
    }
  }, [nodes, links, dimensions, selectedEventId, onSelectEvent])

  // Handle resize
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        const width = Math.max(400, containerRef.current.clientWidth)
        const height = Math.max(300, containerRef.current.clientHeight)
        setDimensions({ width, height })
      }
    }

    updateDimensions()
    const resizeObserver = new ResizeObserver(updateDimensions)
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current)
    }

    return () => resizeObserver.disconnect()
  }, [])

  return (
    <div className="graph-view" ref={containerRef}>
      <svg
        ref={svgRef}
        width={dimensions.width}
        height={dimensions.height}
        style={{ border: '1px solid var(--panel-border)', borderRadius: '8px' }}
      />
      <div className="graph-controls">
        <span className="zoom-indicator">{Math.round(zoom * 100)}%</span>
      </div>
    </div>
  )
}

// View Mode Switcher Component
interface ViewModeSwitcherProps {
  currentMode: ViewMode
  onModeChange: (mode: ViewMode) => void
}

function ViewModeSwitcher({ currentMode, onModeChange }: ViewModeSwitcherProps) {
  const modes: Array<{ mode: ViewMode; label: string; icon: string }> = [
    { mode: 'sequential', label: 'Sequential', icon: '📋' },
    { mode: 'tree', label: 'Tree', icon: '🌳' },
    { mode: 'graph', label: 'Graph', icon: '🕸️' },
  ]

  return (
    <div className="view-mode-switcher">
      {modes.map(({ mode, label, icon }) => (
        <button
          key={mode}
          type="button"
          className={`mode-btn ${currentMode === mode ? 'active' : ''}`}
          onClick={() => onModeChange(mode)}
          title={`${label} view`}
        >
          <span className="mode-icon">{icon}</span>
          <span className="mode-label">{label}</span>
        </button>
      ))}
    </div>
  )
}

// Main ReasoningGraphPanel Component
export function ReasoningGraphPanel({
  events,
  tree,
  selectedEventId,
  onSelectEvent,
}: ReasoningGraphPanelProps) {
  const [viewMode, setViewMode] = useState<ViewMode>('sequential')

  // Build reasoning steps from either tree or events
  const reasoningSteps = useMemo(() => {
    if (tree) {
      return [convertTreeToReasoningSteps(tree)]
    }
    return buildReasoningGraph(events)
  }, [tree, events])

  const handleModeChange = useCallback((mode: ViewMode) => {
    setViewMode(mode)
  }, [])

  return (
    <div className="reasoning-graph-panel">
      <div className="panel-head">
        <div className="panel-head-left">
          <p className="eyebrow">Reasoning Visualization</p>
          <h2>Enhanced Reasoning Graph</h2>
        </div>
        <ViewModeSwitcher currentMode={viewMode} onModeChange={handleModeChange} />
      </div>

      <div className="reasoning-content">
        {viewMode === 'sequential' && (
          <SequentialView
            steps={reasoningSteps}
            selectedEventId={selectedEventId}
            onSelectEvent={onSelectEvent}
          />
        )}
        {viewMode === 'tree' && (
          <TreeView
            steps={reasoningSteps}
            selectedEventId={selectedEventId}
            onSelectEvent={onSelectEvent}
          />
        )}
        {viewMode === 'graph' && (
          <GraphView
            steps={reasoningSteps}
            selectedEventId={selectedEventId}
            onSelectEvent={onSelectEvent}
          />
        )}
      </div>
    </div>
  )
}

// Memoized version for performance
function arePropsEqual(
  prevProps: Readonly<ReasoningGraphPanelProps>,
  nextProps: Readonly<ReasoningGraphPanelProps>
): boolean {
  return (
    prevProps.selectedEventId === nextProps.selectedEventId &&
    prevProps.events === nextProps.events &&
    prevProps.tree === nextProps.tree
  )
}

export const ReasoningGraphPanelMemo = memo(ReasoningGraphPanel, arePropsEqual)