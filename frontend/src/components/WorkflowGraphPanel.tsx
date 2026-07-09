import { useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'
import type { WorkflowGraph } from '../types'
import { getWorkflowGraph } from '../api/client'

interface WorkflowGraphPanelProps {
  sessionId: string
}

interface D3Node extends d3.SimulationNodeDatum {
  id: string
  label: string
  nodeType: string
  status: 'success' | 'failure' | 'pending'
  durationMs: number | null
  tokenCount: number | null
}

interface D3Link extends d3.SimulationLinkDatum<D3Node> {
  source: D3Node | string
  target: D3Node | string
  edgeType: string
  label: string | null
}

const NODE_COLORS = {
  success: '#22c55e',
  failure: '#ef4444',
  pending: '#6b7280',
}

const NODE_TYPE_COLORS = {
  decision: '#3b82f6',
  tool_call: '#8b5cf6',
  llm_request: '#ec4899',
  error: '#ef4444',
  checkpoint: '#f59e0b',
}

export function WorkflowGraphPanel({ sessionId }: WorkflowGraphPanelProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [graph, setGraph] = useState<WorkflowGraph | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hoveredNode, setHoveredNode] = useState<D3Node | null>(null)

  useEffect(() => {
    async function loadGraph() {
      try {
        setLoading(true)
        setError(null)
        const response = await getWorkflowGraph(sessionId)
        setGraph(response.graph)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load workflow graph')
      } finally {
        setLoading(false)
      }
    }

    loadGraph()
  }, [sessionId])

  useEffect(() => {
    if (!graph || !svgRef.current) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const width = svgRef.current.clientWidth || 800
    const height = svgRef.current.clientHeight || 600

    // Convert data to D3 format
    const nodes: D3Node[] = graph.nodes.map(node => ({
      id: node.id,
      label: node.label,
      nodeType: node.node_type,
      status: node.status,
      durationMs: node.duration_ms,
      tokenCount: node.token_count,
    }))

    const links: D3Link[] = graph.edges.map(edge => ({
      source: edge.source_id,
      target: edge.target_id,
      edgeType: edge.edge_type,
      label: edge.label,
    }))

    // Create simulation
    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink<D3Node, D3Link>(links).id((d) => d.id).distance(100))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(30))

    // Create main group
    const g = svg.append('g')

    // Add zoom behavior
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform)
      })

    svg.call(zoom)

    // Create arrow markers
    svg.append('defs')
      .append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 8)
      .attr('markerHeight', 8)
      .append('path')
      .attr('d', 'M 0,-5 L 10,0 L 0,5')
      .attr('fill', '#6b7280')

    // Draw edges
    const link = g.append('g')
      .selectAll('line')
      .data(links)
      .enter()
      .append('line')
      .attr('stroke', '#6b7280')
      .attr('stroke-width', 2)
      .attr('marker-end', 'url(#arrowhead)')

    // Draw nodes
    const node = g.append('g')
      .selectAll('circle')
      .data(nodes)
      .enter()
      .append('circle')
      .attr('r', 20)
      .attr('fill', (d) => NODE_TYPE_COLORS[d.nodeType as keyof typeof NODE_TYPE_COLORS] || '#6b7280')
      .attr('stroke', (d) => NODE_COLORS[d.status])
      .attr('stroke-width', 3)
      .style('cursor', 'pointer')
      .on('mouseover', function(_event, d) {
        setHoveredNode(d)
        d3.select(this)
          .attr('r', 25)
          .attr('stroke-width', 4)
      })
      .on('mouseout', function() {
        setHoveredNode(null)
        d3.select(this)
          .attr('r', 20)
          .attr('stroke-width', 3)
      })

    // Add labels
    const labels = g.append('g')
      .selectAll('text')
      .data(nodes)
      .enter()
      .append('text')
      .text((d) => d.label)
      .attr('font-size', '12px')
      .attr('font-family', 'sans-serif')
      .attr('text-anchor', 'middle')
      .attr('dy', -25)
      .style('pointer-events', 'none')

    // Update positions on tick
    simulation.on('tick', () => {
      link
        .attr('x1', (d) => (d.source as D3Node).x ?? 0)
        .attr('y1', (d) => (d.source as D3Node).y ?? 0)
        .attr('x2', (d) => (d.target as D3Node).x ?? 0)
        .attr('y2', (d) => (d.target as D3Node).y ?? 0)

      node
        .attr('cx', (d) => d.x ?? 0)
        .attr('cy', (d) => d.y ?? 0)

      labels
        .attr('x', (d) => d.x ?? 0)
        .attr('y', (d) => d.y ?? 0)
    })

    // Cleanup
    return () => {
      simulation.stop()
    }
  }, [graph])

  if (loading) {
    return <div className="p-4 text-center">Loading workflow graph...</div>
  }

  if (error) {
    return <div className="p-4 text-center text-red-500">Error: {error}</div>
  }

  if (!graph) {
    return <div className="p-4 text-center">No workflow data available</div>
  }

  return (
    <div className="workflow-graph-panel">
      <div className="p-4 border-b">
        <h3 className="text-lg font-semibold">Workflow Graph</h3>
        <div className="flex gap-4 mt-2 text-sm">
          <div className="flex items-center gap-1">
            <div className="w-3 h-3 rounded-full bg-green-500"></div>
            <span>Success</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-3 h-3 rounded-full bg-red-500"></div>
            <span>Failure</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-3 h-3 rounded-full bg-gray-500"></div>
            <span>Pending</span>
          </div>
        </div>
      </div>

      {hoveredNode && (
        <div className="absolute top-16 right-4 bg-white border rounded-lg p-3 shadow-lg z-10">
          <h4 className="font-semibold">{hoveredNode.label}</h4>
          <div className="text-sm space-y-1 mt-2">
            <div>Type: {hoveredNode.nodeType}</div>
            <div>Status: {hoveredNode.status}</div>
            {hoveredNode.durationMs !== null && (
              <div>Duration: {hoveredNode.durationMs.toFixed(2)}ms</div>
            )}
            {hoveredNode.tokenCount !== null && (
              <div>Tokens: {hoveredNode.tokenCount}</div>
            )}
          </div>
        </div>
      )}

      <svg
        ref={svgRef}
        width="100%"
        height="600"
        style={{ border: '1px solid #e5e7eb' }}
      />
    </div>
  )
}