import * as d3 from 'd3'
import { useEffect, useRef, useState, useCallback } from 'react'
import type { MouseEvent as ReactMouseEvent, WheelEvent as ReactWheelEvent } from 'react'
import type { TraceEvent, TreeNode } from '../types'

interface DecisionTreeProps {
  tree: TreeNode | null
  selectedEventId: string | null
  onSelectEvent: (eventId: string) => void
}

interface D3TreeNode {
  id: string
  event: TraceEvent
  children: D3TreeNode[]
  x?: number
  y?: number
  _collapsed?: boolean
}

const NODE_COLORS: Record<string, string> = {
  trace_root: '#64748b',
  agent_start: '#3b82f6',
  agent_end: '#1d4ed8',
  llm_request: '#a855f7',
  llm_response: '#a855f7',
  tool_call: '#22c55e',
  tool_result: '#22c55e',
  decision: '#f97316',
  error: '#ef4444',
  checkpoint: '#0f766e',
  safety_check: '#d97706',
  refusal: '#b91c1c',
  policy_violation: '#991b1b',
  prompt_policy: '#7c3aed',
  agent_turn: '#0369a1',
  behavior_alert: '#c2410c',
}

const NODE_SIZE = 12
const NODE_SPACING_X_BASE = 180
const NODE_SPACING_Y_BASE = 60
const TOOLTIP_OFFSET = 10
const TOOLTIP_MAX_WIDTH = 200
const TOOLTIP_MAX_HEIGHT = 100

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

  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        })
      }
    }

    updateDimensions()
    window.addEventListener('resize', updateDimensions)
    return () => window.removeEventListener('resize', updateDimensions)
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

    g.selectAll('.link')
      .data(root.links())
      .enter()
      .append('path')
      .attr('class', 'link')
      .attr('d', (d) => {
        const sourceX = d.source.x ?? 0
        const sourceY = d.source.y ?? 0
        const targetX = d.target.x ?? 0
        const targetY = d.target.y ?? 0
        const midY = (sourceY + targetY) / 2
        return `M${sourceX},${sourceY}C${sourceX},${midY} ${targetX},${midY} ${targetX},${targetY}`
      })
      .attr('fill', 'none')
      .attr('stroke', '#4b5563')
      .attr('stroke-width', 2)
      .attr('stroke-opacity', 0.6)

    const nodes = g
      .selectAll('.node')
      .data(root.descendants())
      .enter()
      .append('g')
      .attr('class', 'node')
      .attr('transform', (d) => `translate(${d.x ?? 0}, ${d.y ?? 0})`)
      .on('click', handleNodeClick)
      .on('dblclick', handleNodeDoubleClick)
      .on('mousemove', handleMouseMove)
      .on('mouseleave', handleMouseLeave)

    nodes
      .append('circle')
      .attr('r', (d) => {
        const importance = d.data.event.importance ?? 1
        return NODE_SIZE * Math.sqrt(importance)
      })
      .attr('fill', (d) => NODE_COLORS[d.data.event.event_type] || '#6b7280')
      .attr('stroke', (d) => (d.data.id === selectedEventId ? '#fbbf24' : '#1f2937'))
      .attr('stroke-width', (d) => (d.data.id === selectedEventId ? 3 : 2))
      .attr('cursor', 'pointer')
      .attr('transition', 'all 0.2s ease')

    nodes
      .append('text')
      .attr('dy', 4)
      .attr('text-anchor', 'middle')
      .attr('fill', '#fff')
      .attr('font-size', '10px')
      .attr('font-weight', 'bold')
      .attr('pointer-events', 'none')
      .text((d) => {
        const type = d.data.event.event_type
        return type.charAt(0).toUpperCase()
      })

    if (root.children) {
      root.children.forEach((child) => {
        if (child.data._collapsed) {
          const collapsedNode = g.select(`.node[data-id="${child.data.id}"]`)
          collapsedNode
            .append('text')
            .attr('x', 20)
            .attr('dy', 4)
            .attr('fill', '#9ca3af')
            .attr('font-size', '11px')
            .text(`+${child.data.children.length}`)
        }
      })
    }
  }, [tree, selectedEventId, zoom, pan, convertToD3Tree, handleNodeClick, handleNodeDoubleClick, handleMouseMove, handleMouseLeave])

  useEffect(() => {
    renderTree()
  }, [renderTree])

  const handleZoomIn = () => setZoom((z) => Math.min(z * 1.2, 3))
  const handleZoomOut = () => setZoom((z) => Math.max(z / 1.2, 0.3))
  const handleResetView = () => {
    setZoom(1)
    setPan({ x: 0, y: 0 })
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
          <span className="empty-icon">🌳</span>
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
