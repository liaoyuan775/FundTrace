import type { GraphData, GraphEdge } from "./types";

export type HierarchicalLayout = {
  positions: Record<string, { x: number; y: number; depth: number }>;
  primaryEdgeIds: Set<string>;
};

const compareEdges = (left: GraphEdge, right: GraphEdge) =>
  left.first_transaction_time.localeCompare(right.first_transaction_time) ||
  right.amount - left.amount ||
  left.id.localeCompare(right.id);

export function buildHierarchicalLayout(data: GraphData): HierarchicalLayout {
  const ids = data.nodes.map((node) => node.id).sort();
  const outgoing = new Map(ids.map((id) => [id, [] as GraphEdge[]]));
  const incoming = new Map(ids.map((id) => [id, [] as GraphEdge[]]));

  for (const edge of data.edges) {
    outgoing.get(edge.source)?.push(edge);
    incoming.get(edge.target)?.push(edge);
  }
  outgoing.forEach((edges) => edges.sort(compareEdges));
  incoming.forEach((edges) => edges.sort(compareEdges));

  const depth = new Map<string, number>();
  const walk = (starts: string[]) => {
    const queue = [...starts];
    for (let index = 0; index < queue.length; index += 1) {
      const source = queue[index];
      for (const edge of outgoing.get(source) || []) {
        if (depth.has(edge.target)) continue;
        depth.set(edge.target, depth.get(source)! + 1);
        queue.push(edge.target);
      }
    }
  };

  const roots = ids.filter((id) => !(incoming.get(id)?.length));
  roots.forEach((id) => depth.set(id, 0));
  walk(roots);

  for (const id of ids) {
    if (depth.has(id)) continue;
    depth.set(id, 0);
    walk([id]);
  }

  const primaryByNode = new Map<string, GraphEdge>();
  for (const id of ids) {
    const candidate = (incoming.get(id) || []).find(
      (edge) => depth.get(edge.source) === depth.get(id)! - 1,
    );
    if (candidate) primaryByNode.set(id, candidate);
  }

  const layers = new Map<number, string[]>();
  for (const id of ids) {
    const level = depth.get(id)!;
    layers.set(level, [...(layers.get(level) || []), id]);
  }
  const maximumDepth = Math.max(0, ...depth.values());
  for (let level = 1; level <= maximumDepth; level += 1) {
    const previous = layers.get(level - 1) || [];
    const parentOrder = new Map(previous.map((id, index) => [id, index]));
    layers.get(level)?.sort((left, right) => {
      const leftParent = primaryByNode.get(left)?.source;
      const rightParent = primaryByNode.get(right)?.source;
      return (
        (parentOrder.get(leftParent || "") ?? Number.MAX_SAFE_INTEGER) -
          (parentOrder.get(rightParent || "") ?? Number.MAX_SAFE_INTEGER) ||
        left.localeCompare(right)
      );
    });
  }

  const maximumLayerSize = Math.max(
    1,
    ...[...layers.values()].map((layer) => layer.length),
  );
  const positions: HierarchicalLayout["positions"] = {};
  for (const [level, layer] of layers) {
    const top = 60 + ((maximumLayerSize - layer.length) * 40) / 2;
    layer.forEach((id, index) => {
      positions[id] = {
        x: 80 + level * 260,
        y: top + index * 40,
        depth: level,
      };
    });
  }

  return {
    positions,
    primaryEdgeIds: new Set(
      [...primaryByNode.values()].map((edge) => edge.id),
    ),
  };
}
