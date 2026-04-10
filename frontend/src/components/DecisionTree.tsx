import * as d3 from 'd3'
import { useEffect, useRef, useState, useCallback, memo, useMemo } from 'react'
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

function convertToD3Tree(node: TreeNode): D3TreeNode {
  return {
    id: node.event.id,
    event: node.event,
    children: node.children.map(convertToD3Tree),
  }
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

const NODE_WIDTH = 50  // Pill-shaped node width
const NODE_HEIGHT = 24  // Pill-shaped node height
const NODE_SPACING_X_BASE = 180
const NODE_SPACING_Y_BASE = 60
const TOOLTIP_OFFSET = 10
const TOOLTIP_MAX_WIDTH = 200
const TOOLTIP_MAX_HEIGHT = 100

// Node type labels for display inside nodes
const NODE_LABELS: Record<string, string> = {
  trace_root: 'Root',
  agent_start: 'Sess',
  agent_end: 'Sess',
  llm_request: 'LLM',
  llm_response: 'LLM',
  tool_call: 'Tool',
  tool_result: 'Tool',
  decision: 'Dec',
  error: 'Err',
  checkpoint: 'Chk',
  safety_check: 'Dec',
  refusal: 'Err',
  policy_violation: 'Err',
  prompt_policy: 'LLM',
  agent_turn: 'Sess',
  behavior_alert: 'Dec',
}

/**
 * Computes branch priority for guided exploration based on:
 * - Failure proximity (+0.4): subtree contains error events
 * - Evidence weakness (+0.3): decision with empty evidence array
 * - Novelty (+0.2): branch not yet inspected
 * - Low confidence (+0.1): decision with confidence below 0.5
 * - Tool diversity (+0.1): different tool types in subtree
 * - Checkpoint presence (+0.15): contains checkpoint event
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

  // Check for tool diversity - different tool types in subtree
  const toolTypes = new Set<string>()
  node.descendants().forEach((d) => {
    if (d.data.event.event_type === 'tool_call' && d.data.event.tool_name) {
      toolTypes.add(d.data.event.tool_name)
    }
  })
  if (toolTypes.size >= 2) {
    score += 0.1
    reasons.push(`Tool diversity (${toolTypes.size} tools)`)
  }

  // Check for checkpoint - important for replay
  const hasCheckpoint = node.descendants().some((d) => d.data.event.event_type === 'checkpoint')
  if (hasCheckpoint) {
    score += 0.15
    reasons.push('Contains checkpoint')
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
  const [controlsCollapsed, setControlsCollapsed] = useState(false)

  // Scale node spacing based on container width for responsiveness
  const nodeSpacingX = useMemo(
    () => Math.max(100, Math.min(NODE_SPACING_X_BASE, dimensions.width * 0.22)),
    [dimensions.width]
  )
  const nodeSpacingY = useMemo(
    () => Math.max(40, Math.min(NODE_SPACING_Y_BASE, dimensions.height * 0.1)),
    [dimensions.height]
  )
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
  const recommendedNodeId = useMemo(() => {
    if (!tree) {
      return null
    }

    const root = d3.hierarchy(convertToD3Tree(tree))
    const priorities = root.descendants().flatMap((node) => {
      if (node.data.event.event_type !== 'decision' && node.depth === 0) {
        return []
      }

      const priority = computeBranchPriority(node, inspectedNodes)
      return priority.score > 0 ? [priority] : []
    })

    if (priorities.length === 0) {
      return null
    }

    return priorities.reduce((max, priority) => (priority.score > max.score ? priority : max)).nodeId
  }, [tree, inspectedNodes])
  const renderTreeRef = useRef<() => void>(() => {})

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
        renderTreeRef.current()
      }
    },
    []
  )

  const handleMouseMove = useCallback(
    (event: MouseEvent, d: d3.HierarchyNode<D3TreeNode>) => {
      const node = d.data
      const timestamp = new Date(node.event.timestamp).toLocaleTimeString()
      const eventType = node.event.event_type
      const nodeColor = NODE_COLORS[eventType] || 'var(--node-default)'
      const name = (node.event.name as string | undefined) || (node.event.data?.summary as string | undefined) || ''
      const displayName = name.length > 60 ? name.slice(0, 60) + '...' : name
      const importance = node.event.importance ?? 1

      // Check if this is the recommended node and has priority info
      const isRecommended = node.id === recommendedNodeId

      // Build rich tooltip content
      const content = JSON.stringify({
        eventType,
        timestamp,
        name: displayName,
        importance,
        color: nodeColor,
        priority: isRecommended && node._priority ? {
          score: node._priority.score.toFixed(2),
          reasons: node._priority.reasons.join(', ')
        } : undefined,
      })

      // Calculate tooltip position relative to container to avoid clipping
      const containerRect = containerRef.current?.getBoundingClientRect()
      const containerLeft = containerRect?.left ?? 0
      const containerTop = containerRect?.top ?? 0
      const containerRight = containerRect?.right ?? window.innerWidth
      const containerBottom = containerRect?.bottom ?? window.innerHeight

      // Position tooltip below and to the right of the node, within container bounds
      const tooltipX = Math.min(event.clientX + TOOLTIP_OFFSET + 15, containerRight - TOOLTIP_MAX_WIDTH - TOOLTIP_OFFSET)
      const tooltipY = Math.min(event.clientY + TOOLTIP_OFFSET + 15, containerBottom - TOOLTIP_MAX_HEIGHT - TOOLTIP_OFFSET)

      setTooltip({
        visible: true,
        x: Math.max(containerLeft + TOOLTIP_OFFSET, tooltipX - containerLeft),
        y: Math.max(containerTop + TOOLTIP_OFFSET, tooltipY - containerTop),
        content,
      })
    },
    [recommendedNodeId]
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

    // Add SVG definitions for arrow markers and drop shadow filter
    const defs = svg.append('defs')

    // Drop shadow filter for nodes
    defs.append('filter')
      .attr('id', 'node-shadow')
      .attr('x', '-50%')
      .attr('y', '-50%')
      .attr('width', '200%')
      .attr('height', '200%')
      .append('feDropShadow')
      .attr('dx', 0)
      .attr('dy', 2)
      .attr('stdDeviation', 2)
      .attr('flood-opacity', 0.2)

    // Arrow marker for parent-child links
    defs.append('marker')
      .attr('id', 'arrow-solid')
      .attr('viewBox', '0 0 10 10')
      .attr('refX', 8)
      .attr('refY', 5)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M 0 0 L 10 5 L 0 10 z')
      .attr('fill', EDGE_STYLES.solid.stroke)

    // Arrow marker for evidence links
    defs.append('marker')
      .attr('id', 'arrow-evidence')
      .attr('viewBox', '0 0 10 10')
      .attr('refX', 8)
      .attr('refY', 5)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M 0 0 L 10 5 L 0 10 z')
      .attr('fill', EDGE_STYLES.evidence.stroke)

    // Arrow marker for inferred links
    defs.append('marker')
      .attr('id', 'arrow-inferred')
      .attr('viewBox', '0 0 10 10')
      .attr('refX', 8)
      .attr('refY', 5)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M 0 0 L 10 5 L 0 10 z')
      .attr('fill', EDGE_STYLES.inferred.stroke)

    const g = svg
      .append('g')
      .attr('transform', `translate(${pan.x + offsetX}, ${pan.y + offsetY}) scale(${zoom})`)

    // Create a map of all events by ID for edge lookup and priority computation
    const eventMap = new Map<string, d3.HierarchyNode<D3TreeNode>>()

    root.descendants().forEach((d) => {
      eventMap.set(d.data.id, d)
    })

    // Compute priorities for all decision nodes and find recommendation
    root.descendants().forEach((d) => {
      if (d.data.event.event_type === 'decision' || d.depth > 0) {
        const priority = computeBranchPriority(d, inspectedNodes)
        d.data._priority = priority
      }
    })

    // Render depth guide lines (every 2 levels)
    const maxDepth = Math.max(...root.descendants().map(d => d.depth))
    for (let depth = 0; depth <= maxDepth; depth += 2) {
      const y = depth * nodeSpacingY
      g.append('line')
        .attr('class', 'depth-guide')
        .attr('x1', minX - 50)
        .attr('y1', y)
        .attr('x2', maxX + 50)
        .attr('y2', y)
        .attr('stroke', 'var(--muted)')
        .attr('stroke-width', 1)
        .attr('opacity', 0.1)
        .attr('stroke-dasharray', '4,4')
    }

    // Render parent-child links (solid lines with arrowheads)
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
        // Shorten the path to stop before the node edge (account for pill height)
        const nodeHalfHeight = NODE_HEIGHT / 2
        return `M${sourceX},${sourceY + nodeHalfHeight}C${sourceX},${midY} ${targetX},${midY} ${targetX},${targetY - nodeHalfHeight}`
      })
      .attr('fill', 'none')
      .attr('stroke', EDGE_STYLES.solid.stroke)
      .attr('stroke-width', EDGE_STYLES.solid.strokeWidth)
      .attr('stroke-dasharray', EDGE_STYLES.solid.strokeDasharray)
      .attr('opacity', 0.7)
      .attr('marker-end', 'url(#arrow-solid)')

    // Render evidence links (dotted blue lines, thicker)
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
        const nodeHalfHeight = NODE_HEIGHT / 2
        return `M${sourceX},${sourceY + nodeHalfHeight}C${sourceX},${midY} ${targetX},${midY} ${targetX},${targetY - nodeHalfHeight}`
      })
      .attr('fill', 'none')
      .attr('stroke', EDGE_STYLES.evidence.stroke)
      .attr('stroke-width', 2)  // Thicker for better visibility
      .attr('stroke-dasharray', EDGE_STYLES.evidence.strokeDasharray)
      .attr('opacity', 0.7)
      .attr('marker-end', 'url(#arrow-evidence)')

    // Render inferred causal links (dotted orange lines with animation)
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
        const nodeHalfHeight = NODE_HEIGHT / 2
        return `M${sourceX},${sourceY + nodeHalfHeight}C${sourceX},${midY} ${targetX},${midY} ${targetX},${targetY - nodeHalfHeight}`
      })
      .attr('fill', 'none')
      .attr('stroke', EDGE_STYLES.inferred.stroke)
      .attr('stroke-width', (d) => EDGE_STYLES.inferred.strokeWidth * d.confidence)
      .attr('stroke-dasharray', EDGE_STYLES.inferred.strokeDasharray)
      .attr('opacity', 0.5)
      .style('animation', 'dash-flow 1s linear infinite')
      .attr('marker-end', 'url(#arrow-inferred)')

    const nodes = g
      .selectAll('.node')
      .data(root.descendants())
      .enter()
      .append('g')
      .attr('class', (d) => {
        const classes = ['node']
        if ((d.data._priority?.score ?? 0) > 0 && d.data.id === recommendedNodeId) {
          classes.push('recommended')
        }
        if (d.data.id === selectedEventId) {
          classes.push('selected')
        }
        return classes.join(' ')
      })
      .attr('data-id', (d) => d.data.id)
      .attr('transform', (d) => `translate(${d.x ?? 0}, ${d.y ?? 0})`)
      .on('click', handleNodeClick)
      .on('dblclick', handleNodeDoubleClick)
      .on('mousemove', handleMouseMove)
      .on('mouseleave', handleMouseLeave)

    // Add pulsing glow effect for recommended nodes
    nodes
      .filter((d) => d.data.id === recommendedNodeId)
      .append('rect')
      .attr('class', 'recommended-glow-rect')
      .attr('x', -NODE_WIDTH / 2 - 6)
      .attr('y', -NODE_HEIGHT / 2 - 6)
      .attr('width', NODE_WIDTH + 12)
      .attr('height', NODE_HEIGHT + 12)
      .attr('rx', 8)
      .attr('fill', 'none')
      .attr('stroke', '#22c55e')
      .attr('stroke-width', 2)
      .attr('opacity', 0.6)
      .attr('pointer-events', 'none')
      .style('animation', 'pulse-border 2s ease-in-out infinite')

    // Main pill-shaped node
    nodes
      .append('rect')
      .attr('class', 'node-rect')
      .attr('x', -NODE_WIDTH / 2)
      .attr('y', -NODE_HEIGHT / 2)
      .attr('width', NODE_WIDTH)
      .attr('height', NODE_HEIGHT)
      .attr('rx', 6)  // Rounded corners for pill shape
      .attr('fill', (d) => NODE_COLORS[d.data.event.event_type] || 'var(--node-default)')
      .attr('stroke', (d) => {
        if (d.data.id === recommendedNodeId) return '#22c55e'
        return d.data.id === selectedEventId ? 'var(--node-selected)' : 'var(--node-stroke)'
      })
      .attr('stroke-width', (d) => {
        if (d.data.id === recommendedNodeId) return 2.5
        return d.data.id === selectedEventId ? 2.5 : 1.5
      })
      .attr('filter', 'url(#node-shadow)')
      .attr('cursor', 'pointer')
      .style('transition', 'all 0.2s ease')

    // Node type label inside the pill
    nodes
      .append('text')
      .attr('class', 'node-label')
      .attr('dy', 1)
      .attr('text-anchor', 'middle')
      .attr('fill', 'white')
      .attr('font-size', '11px')
      .attr('font-weight', '600')
      .attr('pointer-events', 'none')
      .text((d) => NODE_LABELS[d.data.event.event_type] || d.data.event.event_type.charAt(0).toUpperCase())

    // Importance bar below the node
    nodes
      .append('rect')
      .attr('class', 'importance-bar')
      .attr('x', -NODE_WIDTH / 2)
      .attr('y', NODE_HEIGHT / 2 + 3)
      .attr('height', 2)
      .attr('rx', 1)
      .attr('fill', (d) => NODE_COLORS[d.data.event.event_type] || 'var(--node-default)')
      .attr('opacity', 0.6)
      .attr('width', (d) => {
        const importance = d.data.event.importance ?? 1
        return Math.max(4, NODE_WIDTH * Math.min(importance, 1))
      })
      .attr('pointer-events', 'none')

    // Add "Recommended" badge for the top priority node
    nodes
      .filter((d) => d.data.id === recommendedNodeId)
      .append('text')
      .attr('x', NODE_WIDTH / 2 + 8)
      .attr('dy', -NODE_HEIGHT / 2 - 4)
      .attr('fill', '#22c55e')
      .attr('font-size', '9px')
      .attr('font-weight', 'bold')
      .attr('pointer-events', 'none')
      .text('⭐ Recommended')

    if (root.children) {
      root.children.forEach((child) => {
        if (child.data._collapsed) {
          const collapsedNode = g.select(`.node[data-id="${child.data.id}"]`)
          collapsedNode
            .append('text')
            .attr('x', NODE_WIDTH / 2 + 8)
            .attr('dy', 5)
            .attr('fill', 'var(--muted)')
            .attr('font-size', '11px')
            .text(`+${child.data.children.length}`)
        }
      })
    }
  }, [tree, selectedEventId, zoom, pan, handleNodeClick, handleNodeDoubleClick, handleMouseMove, handleMouseLeave, inspectedNodes, nodeSpacingX, nodeSpacingY, recommendedNodeId])

  useEffect(() => {
    renderTreeRef.current = renderTree
  }, [renderTree])

  useEffect(() => {
    renderTree()
    const currentSvg = svgRef.current

    // Cleanup D3 selections and event listeners on unmount
    return () => {
      if (currentSvg) {
        const svg = d3.select(currentSvg)
        svg.selectAll('*').on('click', null).on('dblclick', null).on('mousemove', null).on('mouseleave', null)
        svg.selectAll('*').remove()
      }
    }
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
      {!controlsCollapsed && (
        <>
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
            <button
              type="button"
              className="replay-btn next-branch-btn"
              disabled={!recommendedNodeId}
              onClick={() => {
                if (recommendedNodeId) {
                  onSelectEvent(recommendedNodeId)
                  setInspectedNodes((prev) => new Set(prev).add(recommendedNodeId))
                }
              }}
              title="Navigate to the highest-priority unexplored branch"
            >
              Next Best Branch
            </button>
            <span className="zoom-badge">{Math.round(zoom * 100)}%</span>
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
            <span className="legend-divider" />
            <span className="legend-item" aria-label="Parent-child links: direct causal relationships">
              <span className="legend-line" style={{ borderTop: `2px solid ${EDGE_STYLES.solid.stroke}` }} />
              Parent-Child
            </span>
            <span className="legend-item" aria-label="Evidence links: events referenced as evidence">
              <span className="legend-line" style={{ borderTop: `2px dotted ${EDGE_STYLES.evidence.stroke}` }} />
              Evidence
            </span>
            <span className="legend-item" aria-label="Inferred links: upstream causal relationships">
              <span className="legend-line" style={{ borderTop: `1.5px dashed ${EDGE_STYLES.inferred.stroke}` }} />
              Inferred
            </span>
          </div>
        </>
      )}
      <button
        className="tree-collapse-toggle"
        onClick={() => setControlsCollapsed(!controlsCollapsed)}
        title={controlsCollapsed ? 'Show controls' : 'Hide controls'}
        aria-label={controlsCollapsed ? 'Show controls' : 'Hide controls'}
      >
        {controlsCollapsed ? '▲' : '▼'}
      </button>
      <svg
        ref={svgRef}
        width={dimensions.width}
        height={dimensions.height}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
      />
      {tooltip.visible && (() => {
        try {
          const data = JSON.parse(tooltip.content)
          return (
            <div
              className="tree-tooltip"
              style={{
                left: tooltip.x,
                top: tooltip.y,
                borderLeftColor: data.color,
              }}
            >
              <div className="tooltip-header">
                <span className="tooltip-dot" style={{ backgroundColor: data.color }} />
                <span className="tooltip-type">{data.eventType}</span>
              </div>
              <div className="tooltip-time">{data.timestamp}</div>
              {data.name && <div className="tooltip-name">{data.name}</div>}
              <div className="tooltip-importance">Importance: {data.importance.toFixed(1)}</div>
              {data.priority && (
                <div className="tooltip-priority">
                  <div style={{ fontWeight: 600, fontSize: '0.7rem', color: '#22c55e', marginTop: '0.25rem' }}>
                    ⭐ Priority: {data.priority.score}
                  </div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--muted)' }}>
                    {data.priority.reasons}
                  </div>
                </div>
              )}
            </div>
          )
        } catch {
          return (
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
          )
        }
      })()}
    </div>
  )
}

// Custom comparison for DecisionTree to avoid unnecessary re-renders
// Compare tree structure and selectedEventId, but not the entire object
function arePropsEqual(
  prevProps: Readonly<DecisionTreeProps>,
  nextProps: Readonly<DecisionTreeProps>
): boolean {
  return (
    prevProps.selectedEventId === nextProps.selectedEventId &&
    prevProps.tree === nextProps.tree
  )
}

// Wrap component in memo for performance
export const DecisionTreeMemo = memo(DecisionTree, arePropsEqual)
export { DecisionTree as DecisionTreeInner } // Export unwrapped version for testing
