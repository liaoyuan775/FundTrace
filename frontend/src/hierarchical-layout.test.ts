import { expect, test } from "vitest";
import { buildHierarchicalLayout } from "./hierarchical-layout";
import type { GraphData, GraphEdge, GraphNode } from "./types";

const node = (id: string): GraphNode => ({
  id,
  label: id,
  account: id,
  bank: "",
  incoming: 0,
  outgoing: 0,
  risk: 0,
  risk_level: "低风险",
  risk_factors: [],
});

const edge = (source: string, target: string, time: string, amount = 100): GraphEdge => ({
  id: `${source}>${target}`,
  source,
  target,
  amount,
  count: 1,
  transaction_ids: [`${source}-${target}`],
  first_transaction_time: time,
});

const graph = (nodes: string[], edges: GraphEdge[]): GraphData => ({
  nodes: nodes.map(node),
  edges,
  transaction_count: edges.length,
  total_amount: edges.reduce((sum, item) => sum + item.amount, 0),
  risk_summary: {
    score: 0,
    level: "低风险",
    account_id: null,
    account_label: "无",
    method: "test",
    disclaimer: "",
  },
});

test("lays out branches and convergence from left to right", () => {
  const data = graph(
    ["root-a", "root-b", "branch", "merge", "leaf"],
    [
      edge("root-a", "branch", "2026-01-01T09:00:00"),
      edge("branch", "merge", "2026-01-01T09:05:00", 500),
      edge("root-b", "merge", "2026-01-01T09:02:00", 200),
      edge("merge", "leaf", "2026-01-01T09:10:00"),
    ],
  );

  const result = buildHierarchicalLayout(data);

  expect(result.positions["root-a"].depth).toBe(0);
  expect(result.positions.branch.depth).toBe(1);
  expect(result.positions.merge.depth).toBe(1);
  expect(result.positions.leaf.depth).toBe(2);
  expect(result.positions.leaf.x).toBeGreaterThan(result.positions.merge.x);
  expect(result.positions.leaf.x - result.positions.merge.x).toBe(260);
  expect(Math.abs(result.positions.branch.y - result.positions.merge.y)).toBe(40);
  expect(result.primaryEdgeIds).toEqual(
    new Set(["root-a>branch", "root-b>merge", "merge>leaf"]),
  );
});

test("handles cycles and isolated nodes with deterministic coordinates", () => {
  const edges = [
    edge("root", "child", "2026-01-01T09:00:00"),
    edge("cycle-a", "cycle-b", "2026-01-01T09:01:00"),
    edge("cycle-b", "cycle-a", "2026-01-01T09:02:00"),
  ];
  const forward = graph(["root", "child", "cycle-a", "cycle-b", "isolated"], edges);
  const reversed = graph(
    ["isolated", "cycle-b", "cycle-a", "child", "root"],
    [...edges].reverse(),
  );

  const result = buildHierarchicalLayout(forward);
  const repeated = buildHierarchicalLayout(reversed);

  expect(result.positions.isolated.depth).toBe(0);
  expect(result.positions["cycle-a"].depth).toBe(0);
  expect(result.positions["cycle-b"].depth).toBe(1);
  expect(result.primaryEdgeIds).toContain("cycle-a>cycle-b");
  expect(repeated.positions).toEqual(result.positions);
  expect(repeated.primaryEdgeIds).toEqual(result.primaryEdgeIds);
});
