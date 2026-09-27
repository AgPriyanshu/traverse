import type { Graph, GraphEdge, GraphNode } from "@/lib/api";

/** An edge with both endpoint names resolved, which is all the evidence panel needs to head itself. */
export type EdgeContext = {
  edge: GraphEdge;
  sourceName: string;
  targetName: string;
};

export const buildNodeIndex = (graph: Graph | undefined): Map<string, GraphNode> => {
  return new Map((graph?.nodes ?? []).map((node) => [node.id, node]));
};

export const contextFor = (
  edge: GraphEdge,
  nodes: ReadonlyMap<string, GraphNode>,
): EdgeContext => {
  return {
    edge,
    sourceName: nodes.get(edge.source)?.canonical_name ?? "Unknown character",
    targetName: nodes.get(edge.target)?.canonical_name ?? "Unknown character",
  };
};
