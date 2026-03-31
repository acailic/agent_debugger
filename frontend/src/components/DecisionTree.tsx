import * as d3 from 'd3'
import { useEffect, useRef, useState, useCallback } from 'react'
import type { MouseEvent as ReactMouseEvent, WheelEvent as ReactWheelEvent } from 'react'
import type { TraceEvent, TreeNode } from '../types'

interface DecisionTreeProps {
  tree: TreeNode | null
  selectedEventId: string | null
  onSelectEvent: (eventId: string) => void
}

interface BranchPriority {
  nodeId: string
  score: number
  reasons: string[]
}

interface D3TreeNode {
  id: string
  event: TraceEvent
  children: D3TreeNode[]
  x?: number
  y?: number
  _collapsed?: boolean
  _priority?: BranchPriority
}

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

const NODE_SIZE = 12
const NODE_SPACING_X_BASE = 180
const NODE_SPACING_Y_BASE = 60
const TOOLTIP_OFFSET = 10
const TOOLTIP_MAX_WIDTH = 200
const TOOLTIP_MAX_HEIGHT = 100

/**
 * Computes branch priority for guided exploration based on:
 * - Failure proximity (+0.4): subtree contains error events
 * - Evidence weakness (+0.3): decision with empty evidence array
 * - Novelty (+0.2): branch not yet inspected
 * - Low confidence (+0.1): decision with confidence below 0.5
 */
function computeBranchPriority(
  node: d3.HierarchyNode<D3TreeNode>,
  inspectedNodes: Set<string>
): BranchPriority {
  let score = 0
  const reasons: string[] = []

  // Check for failure proximity - does subtree contain error events?
  let hasErrorInSubtree = false
  node.descendants().forEach((d) => {
    if (d.data.event.event_type === 'error' || d.data.event.event_type === 'policy_violation') {
      hasErrorInSubtree = true
    }
  })
  if (hasErrorInSubtree) {
    score += 0.4
    reasons.push('Contains error in subtree')
  }

  // Check for evidence weakness - decision with empty evidence
  const event = node.data.event
  if (event.event_type === 'decision') {
    const evidenceCount = event.evidence?.length ?? 0
    if (evidenceCount === 0) {
      score += 0.3
      reasons.push('Decision with no evidence')
    }
  }

  // Check for novelty - not yet inspected
  if (!inspectedNodes.has(node.data.id)) {
    score += 0.2
    reasons.push('Uninspected branch')
  }

  // Check for low confidence
  if (event.event_type === 'decision' && (event.confidence ?? 1) < 0.5) {
    score += 0.1
    reasons.push('Low confidence decision')
  }

  return {
    nodeId: node.data.id,
    score,
    reasons,
  }
}

// Edge types for causal visualization
const EDGE_STYLES = {
  solid: {
    strokeDasharray: 'none',
    stroke: 'var(--link-stroke)',
    strokeWidth: 2,
  },
  evidence: {
    strokeDasharray: '4,4',
    stroke: '#3b82f6',
    strokeWidth: 1.5,
  },
  inferred: {
    strokeDasharray: '2,2',
    stroke: '#f59e0b',
    strokeWidth: 1.5,
  },
}

export function DecisionTree({ tree, selectedEventId, onSelectEvent }: DecisionTreeProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })

  // Scale node spacing based on container width for responsiveness
  const nodeSpacingX = Math.max(100, Math.min(NODE_SPACING_X_BASE, dimensions.width * 0.22))
  const nodeSpacingY = Math.max(40, Math.min(NODE_SPACING_Y_BASE, dimensions.height * 0.1))
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [tooltip, setTooltip] = useState<{ visible: boolean; x: number; y: number; content: string }>({
    visible: false,
    x: 0,
    y: 0,
    content: '',
  })

  // Track inspected nodes for guided exploration
  const [inspectedNodes, setInspectedNodes] = useState<Set<string>>(new Set())
  const [recommendedNodeId, setRecommendedNodeId] = useState<string | null>(null)

  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        const width = Math.max(400, containerRef.current.clientWidth)
        const height = Math.max(300, containerRef.current.clientHeight)
        setDimensions({ width, height })
      }
    }

    updateDimensions()

    // Use ResizeObserver for container-aware sizing
    const resizeObserver = new ResizeObserver(() => {
      updateDimensions()
    })

    if (containerRef.current) {
      resizeObserver.observe(containerRef.current)
    }

    return () => {
      resizeObserver.disconnect()
    }
  }, [])

  const convertToD3Tree = useCallback((node: TreeNode): D3TreeNode => {
    return {
      id: node.event.id,
      event: node.event,
      children: node.children.map(convertToD3Tree),
    }
  }, [])

  const handleNodeClick = useCallback(
    (event: MouseEvent, d: d3.HierarchyNode<D3TreeNode>) => {
      event.stopPropagation()
      onSelectEvent(d.data.id)
      // Track this node as inspected
      setInspectedNodes((prev) => new Set(prev).add(d.data.id))
    },
    [onSelectEvent]
  )

  const handleNodeDoubleClick = useCallback(
    (event: MouseEvent, d: d3.HierarchyNode<D3TreeNode>) => {
      event.stopPropagation()
      if (d.data.children.length > 0) {
        d.data._collapsed = !d.data._collapsed
        renderTree()
      }
    },
    []
  )

  const handleMouseMove = useCallback(
    (event: MouseEvent, d: d3.HierarchyNode<D3TreeNode>) => {
      const node = d.data
      const timestamp = new Date(node.event.timestamp).toLocaleTimeString()
      const content = `${node.event.event_type}\n${timestamp}\nID: ${node.id.slice(0, 8)}`

      // Calculate tooltip position with viewport boundary detection
      const tooltipX = Math.min(event.clientX + TOOLTIP_OFFSET, window.innerWidth - TOOLTIP_MAX_WIDTH - TOOLTIP_OFFSET)
      const tooltipY = Math.min(event.clientY + TOOLTIP_OFFSET, window.innerHeight - TOOLTIP_MAX_HEIGHT - TOOLTIP_OFFSET)

      setTooltip({
        visible: true,
        x: Math.max(TOOLTIP_OFFSET, tooltipX),
        y: Math.max(TOOLTIP_OFFSET, tooltipY),
        content,
      })
    },
    []
  )

  const handleMouseLeave = useCallback(() => {
    setTooltip((prev) => ({ ...prev, visible: false }))
  }, [])

  const renderTree = useCallback(() => {
    if (!svgRef.current || !tree) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const root = d3.hierarchy(convertToD3Tree(tree))
    const treeLayout = d3.tree<D3TreeNode>().nodeSize([nodeSpacingX, nodeSpacingY])
    treeLayout(root)

    let minX = Infinity
    let maxX = -Infinity
    let minY = Infinity
    let maxY = -Infinity
    root.each((d) => {
      minX = Math.min(minX, d.x ?? 0)
      maxX = Math.max(maxX, d.x ?? 0)
      minY = Math.min(minY, d.y ?? 0)
      maxY = Math.max(maxY, d.y ?? 0)
    })

    const offsetX = -minX + nodeSpacingX
    const offsetY = nodeSpacingY

    const g = svg
      .append('g')
      .attr('transform', `translate(${pan.x + offsetX}, ${pan.y + offsetY}) scale(${zoom})`)

    // Create a map of all events by ID for edge lookup and priority computation
    const eventMap = new Map<string, d3.HierarchyNode<D3TreeNode>>()

    root.descendants().forEach((d) => {
      eventMap.set(d.data.id, d)
    })

    // Compute priorities for all decision nodes and find recommendation
    const priorities: Array<{ nodeId: string; score: number }> = []
    root.descendants().forEach((d) => {
      if (d.data.event.event_type === 'decision' || d.depth > 0) {
        const priority = computeBranchPriority(d, inspectedNodes)
        d.data._priority = priority
        if (priority.score > 0) {
          priorities.push({ nodeId: priority.nodeId, score: priority.score })
        }
      }
    })
    const recommendedNodeId: string | null = priorities.length > 0
      ? priorities.reduce((max, p) => (p.score > max.score ? p : max)).nodeId
      : null
    setRecommendedNodeId(recommendedNodeId)

    // Render parent-child links (solid lines)
    g.selectAll('.link')
      .data(root.links())
      .enter()
      .append('path')
      .attr('class', 'link parent-child')
      .attr('d', (d) => {
        const sourceX = d.source.x ?? 0
        const sourceY = d.source.y ?? 0
        const targetX = d.target.x ?? 0
        const targetY = d.target.y ?? 0
        const midY = (sourceY + targetY) / 2
        return `M${sourceX},${sourceY}C${sourceX},${midY} ${targetX},${midY} ${targetX},${targetY}`
      })
      .attr('fill', 'none')
      .attr('stroke', EDGE_STYLES.solid.stroke)
      .attr('stroke-width', EDGE_STYLES.solid.strokeWidth)
      .attr('stroke-dasharray', EDGE_STYLES.solid.strokeDasharray)

    // Render evidence links (dotted blue lines)
    const evidenceLinks: Array<{ source: d3.HierarchyNode<D3TreeNode>; target: d3.HierarchyNode<D3TreeNode> }> = []
    root.descendants().forEach((d) => {
      const evidenceEventIds = d.data.event.evidence_event_ids ?? []
      evidenceEventIds.forEach((evidenceId) => {
        const evidenceNode = eventMap.get(evidenceId)
        if (evidenceNode && evidenceNode !== d.parent) {
          evidenceLinks.push({ source: evidenceNode, target: d })
        }
      })
    })

    g.selectAll('.link-evidence')
      .data(evidenceLinks)
      .enter()
      .append('path')
      .attr('class', 'link-evidence')
      .attr('d', (d) => {
        const sourceX = d.source.x ?? 0
        const sourceY = d.source.y ?? 0
        const targetX = d.target.x ?? 0
        const targetY = d.target.y ?? 0
        const midY = (sourceY + targetY) / 2
        return `M${sourceX},${sourceY}C${sourceX},${midY} ${targetX},${midY} ${targetX},${targetY}`
      })
      .attr('fill', 'none')
      .attr('stroke', EDGE_STYLES.evidence.stroke)
      .attr('stroke-width', EDGE_STYLES.evidence.strokeWidth)
      .attr('stroke-dasharray', EDGE_STYLES.evidence.strokeDasharray)
      .attr('opacity', 0.6)

    // Render inferred causal links (dotted orange lines)
    const inferredLinks: Array<{ source: d3.HierarchyNode<D3TreeNode>; target: d3.HierarchyNode<D3TreeNode>; confidence: number }> = []
    root.descendants().forEach((d) => {
      const upstreamEventIds = d.data.event.upstream_event_ids ?? []
      upstreamEventIds.forEach((upstreamId) => {
        const upstreamNode = eventMap.get(upstreamId)
        if (upstreamNode && upstreamNode !== d.parent && !d.data.event.evidence_event_ids?.includes(upstreamId)) {
          inferredLinks.push({
            source: upstreamNode,
            target: d,
            confidence: d.data.event.confidence ?? 0.5
          })
        }
      })
    })

    g.selectAll('.link-inferred')
      .data(inferredLinks)
      .enter()
      .append('path')
      .attr('class', 'link-inferred')
      .attr('d', (d) => {
        const sourceX = d.source.x ?? 0
        const sourceY = d.source.y ?? 0
        const targetX = d.target.x ?? 0
        const targetY = d.target.y ?? 0
        const midY = (sourceY + targetY) / 2
        return `M${sourceX},${sourceY}C${sourceX},${midY} ${targetX},${midY} ${targetX},${targetY}`
      })
      .attr('fill', 'none')
      .attr('stroke', EDGE_STYLES.inferred.stroke)
      .attr('stroke-width', (d) => EDGE_STYLES.inferred.strokeWidth * d.confidence)
      .attr('stroke-dasharray', EDGE_STYLES.inferred.strokeDasharray)
      .attr('opacity', 0.5)

    const nodes = g
      .selectAll('.node')
      .data(root.descendants())
      .enter()
      .append('g')
      .attr('class', (d) => `node ${(d.data._priority?.score ?? 0) > 0 && d.data.id === recommendedNodeId ? 'recommended' : ''}`)
      .attr('data-id', (d) => d.data.id)
      .attr('transform', (d) => `translate(${d.x ?? 0}, ${d.y ?? 0})`)
      .on('click', handleNodeClick)
      .on('dblclick', handleNodeDoubleClick)
      .on('mousemove', handleMouseMove)
      .on('mouseleave', handleMouseLeave)

    // Add glow effect for recommended nodes
    nodes
      .filter((d) => d.data.id === recommendedNodeId)
      .append('circle')
      .attr('class', 'recommended-glow')
      .attr('r', (d) => {
        const importance = d.data.event.importance ?? 1
        return NODE_SIZE * Math.sqrt(importance) + 8
      })
      .attr('fill', 'none')
      .attr('stroke', '#22c55e')
      .attr('stroke-width', 3)
      .attr('opacity', 0.6)
      .attr('pointer-events', 'none')

    nodes
      .append('circle')
      .attr('r', (d) => {
        const importance = d.data.event.importance ?? 1
        return NODE_SIZE * Math.sqrt(importance)
      })
      .attr('fill', (d) => NODE_COLORS[d.data.event.event_type] || 'var(--node-default)')
      .attr('stroke', (d) => {
        if (d.data.id === recommendedNodeId) return '#22c55e'
        return d.data.id === selectedEventId ? 'var(--node-selected)' : 'var(--node-stroke)'
      })
      .attr('stroke-width', (d) => {
        if (d.data.id === recommendedNodeId) return 3
        return d.data.id === selectedEventId ? 3 : 2
      })
      .attr('cursor', 'pointer')
      .attr('transition', 'all 0.2s ease')

    nodes
      .append('text')
      .attr('dy', 4)
      .attr('text-anchor', 'middle')
      .attr('fill', 'white')
      .attr('font-size', '10px')
      .attr('font-weight', 'bold')
      .attr('pointer-events', 'none')
      .text((d) => {
        const type = d.data.event.event_type
        return type.charAt(0).toUpperCase()
      })

    // Add "Recommended" badge for the top priority node
    nodes
      .filter((d) => d.data.id === recommendedNodeId)
      .append('text')
      .attr('x', 20)
      .attr('dy', -10)
      .attr('fill', '#22c55e')
      .attr('font-size', '10px')
      .attr('font-weight', 'bold')
      .attr('pointer-events', 'none')
      .text('⭐ Recommended')

    if (root.children) {
      root.children.forEach((child) => {
        if (child.data._collapsed) {
          const collapsedNode = g.select(`.node[data-id="${child.data.id}"]`)
          collapsedNode
            .append('text')
            .attr('x', 20)
            .attr('dy', 4)
            .attr('fill', 'var(--muted)')
            .attr('font-size', '11px')
            .text(`+${child.data.children.length}`)
        }
      })
    }
  }, [tree, selectedEventId, zoom, pan, convertToD3Tree, handleNodeClick, handleNodeDoubleClick, handleMouseMove, handleMouseLeave, inspectedNodes, recommendedNodeId, nodeSpacingX, nodeSpacingY])

  useEffect(() => {
    renderTree()
  }, [renderTree])

  const handleZoomIn = () => setZoom((z) => Math.min(z * 1.2, 3))
  const handleZoomOut = () => setZoom((z) => Math.max(z / 1.2, 0.3))
  const handleResetView = () => {
    setZoom(1)
    setPan({ x: 0, y: 0 })
  }

  const handleJumpToRecommended = () => {
    if (!recommendedNodeId) return
    onSelectEvent(recommendedNodeId)
    setInspectedNodes((prev) => new Set(prev).add(recommendedNodeId))
    // Center the view on the recommended node
    if (svgRef.current) {
      const svg = d3.select(svgRef.current)
      const node = svg.select(`.node[data-id="${recommendedNodeId}"]`)
      if (!node.empty()) {
        const transform = node.attr('transform')
        const match = /translate\(([^,]+),\s*([^)]+)\)/.exec(transform ?? '')
        if (match) {
          const nodeX = parseFloat(match[1])
          const nodeY = parseFloat(match[2])
          setPan({
            x: -nodeX + dimensions.width / 2,
            y: -nodeY + dimensions.height / 2,
          })
        }
      }
    }
  }

  const handleWheel = (e: ReactWheelEvent) => {
    e.preventDefault()
    if (e.ctrlKey) {
      const delta = e.deltaY > 0 ? 0.9 : 1.1
      setZoom((z) => Math.max(0.3, Math.min(3, z * delta)))
    } else {
      setPan((p) => ({
        x: p.x - e.deltaX,
        y: p.y - e.deltaY,
      }))
    }
  }

  const handleMouseDown = (e: ReactMouseEvent) => {
    if (e.button === 0) {
      const startX = e.clientX
      const startY = e.clientY
      const startPan = { ...pan }

      const handleMouseMove = (moveEvent: MouseEvent) => {
        setPan({
          x: startPan.x + moveEvent.clientX - startX,
          y: startPan.y + moveEvent.clientY - startY,
        })
      }

      const handleMouseUp = () => {
        window.removeEventListener('mousemove', handleMouseMove)
        window.removeEventListener('mouseup', handleMouseUp)
      }

      window.addEventListener('mousemove', handleMouseMove)
      window.addEventListener('mouseup', handleMouseUp)
    }
  }

  if (!tree) {
    return (
      <div className="decision-tree empty">
        <div className="empty-state">
          <span>No tree data available</span>
        </div>
      </div>
    )
  }

  return (
    <div className="decision-tree" ref={containerRef}>
      <div className="tree-controls">
        <button onClick={handleZoomIn} title="Zoom In">
          +
        </button>
        <button onClick={handleZoomOut} title="Zoom Out">
          -
        </button>
        <button onClick={handleResetView} title="Reset View">
          Reset
        </button>
        {recommendedNodeId && (
          <button onClick={handleJumpToRecommended} title="Jump to Recommended Branch" className="jump-recommended-btn">
            ⭐ Jump to Recommended
          </button>
        )}
        <span className="zoom-level">{Math.round(zoom * 100)}%</span>
      </div>
      <div className="tree-legend" role="legend" aria-label="Decision tree legend">
        <span className="legend-item" aria-label="Session nodes: agent start and end events">
          <span className="legend-dot" style={{ backgroundColor: NODE_COLORS.agent_start }} />
          Session
        </span>
        <span className="legend-item" aria-label="LLM nodes: large language model requests and responses">
          <span className="legend-dot" style={{ backgroundColor: NODE_COLORS.llm_request }} />
          LLM
        </span>
        <span className="legend-item" aria-label="Tool nodes: tool calls and results">
          <span className="legend-dot" style={{ backgroundColor: NODE_COLORS.tool_call }} />
          Tool
        </span>
        <span className="legend-item" aria-label="Decision nodes: agent decision points">
          <span className="legend-dot" style={{ backgroundColor: NODE_COLORS.decision }} />
          Decision
        </span>
        <span className="legend-item" aria-label="Risk nodes: errors and policy violations">
          <span className="legend-dot" style={{ backgroundColor: NODE_COLORS.error }} />
          Risk
        </span>
      </div>
      <div className="tree-edge-legend" role="legend" aria-label="Edge type legend">
        <span className="legend-item" aria-label="Parent-child links: direct causal relationships">
          <span className="legend-line" style={{ borderTop: `2px solid ${EDGE_STYLES.solid.stroke}` }} />
          Parent-Child
        </span>
        <span className="legend-item" aria-label="Evidence links: events referenced as evidence">
          <span className="legend-line" style={{ borderTop: `1.5px dotted ${EDGE_STYLES.evidence.stroke}` }} />
          Evidence
        </span>
        <span className="legend-item" aria-label="Inferred links: upstream causal relationships">
          <span className="legend-line" style={{ borderTop: `1.5px dashed ${EDGE_STYLES.inferred.stroke}` }} />
          Inferred
        </span>
      </div>
      <svg
        ref={svgRef}
        width={dimensions.width}
        height={dimensions.height}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
      />
      {tooltip.visible && (
        <div
          className="tree-tooltip"
          style={{
            left: tooltip.x,
            top: tooltip.y,
          }}
        >
          {tooltip.content.split('\n').map((line, i) => (
            <div key={i}>{line}</div>
          ))}
        </div>
      )}
    </div>
  )
}
