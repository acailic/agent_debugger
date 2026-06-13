/**
 * Type-safe wrappers around the D3 functions used by visualization components.
 *
 * This module re-exports only the D3 primitives that Peaky Peek uses,
 * providing a single import point and typed references.
 *
 * Currently used by:
 * - DecisionTree.tsx (d3-hierarchy: tree layout)
 * - WorkflowGraphPanel.tsx (d3-force: force simulation)
 * - ReasoningGraphPanel.tsx (d3-force: force simulation)
 *
 * If D3 is ever replaced, only this module needs to change.
 */

import {
  hierarchy,
  HierarchyNode,
  tree,
  SimulationNodeDatum,
  SimulationLinkDatum,
  forceSimulation,
  forceManyBody,
  forceLink,
  forceCollide,
  forceCenter,
  zoom,
  drag,
  select,
} from "d3"

export {
  hierarchy,
  tree,
  zoom,
  drag,
  select,
  forceSimulation,
  forceManyBody,
  forceLink,
  forceCollide,
  forceCenter,
}

export type { HierarchyNode, SimulationNodeDatum, SimulationLinkDatum }
