import type { GraphData } from "./types";

export type ElementStates = {
  nodes: Record<string, string[]>;
  edges: Record<string, string[]>;
};

export function chronologicalEdgeIds(data: GraphData): string[] {
  return [...data.edges]
    .sort((a, b) =>
      a.first_transaction_time.localeCompare(b.first_transaction_time),
    )
    .map((edge) => edge.id);
}

export function buildFocusStates(
  data: GraphData,
  selectedNode: string | null,
  selectedEdge: string | null,
  playingEdge: string | null,
): ElementStates {
  const nodes = Object.fromEntries(data.nodes.map((node) => [node.id, [] as string[]]));
  const edges = Object.fromEntries(data.edges.map((edge) => [edge.id, [] as string[]]));

  if (playingEdge) {
    const active = data.edges.find((edge) => edge.id === playingEdge);
    for (const node of data.nodes) nodes[node.id] = ["inactive"];
    for (const edge of data.edges) edges[edge.id] = ["inactive"];
    if (active) {
      edges[active.id] = ["playing"];
      nodes[active.source] = ["playing-source"];
      nodes[active.target] = ["playing-target"];
    }
    return { nodes, edges };
  }

  if (selectedNode) {
    for (const node of data.nodes) nodes[node.id] = ["inactive"];
    for (const edge of data.edges) {
      edges[edge.id] = ["inactive"];
      if (edge.source === selectedNode) {
        edges[edge.id] = ["outgoing"];
        nodes[edge.target] = ["outgoing-neighbor"];
      }
      if (edge.target === selectedNode) {
        edges[edge.id] = ["incoming"];
        nodes[edge.source] = ["incoming-neighbor"];
      }
    }
    nodes[selectedNode] = ["selected"];
    return { nodes, edges };
  }

  if (selectedEdge) {
    for (const node of data.nodes) nodes[node.id] = ["inactive"];
    for (const edge of data.edges) edges[edge.id] = ["inactive"];
    const active = data.edges.find((edge) => edge.id === selectedEdge);
    if (active) {
      edges[active.id] = ["selected"];
      nodes[active.source] = ["edge-endpoint"];
      nodes[active.target] = ["edge-endpoint"];
    }
  }
  return { nodes, edges };
}
