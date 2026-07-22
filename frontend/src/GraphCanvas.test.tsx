import { render, waitFor } from "@testing-library/react";
import { vi, expect, test } from "vitest";
import GraphCanvas from "./GraphCanvas";
import type { GraphData } from "./types";

const GraphMock = vi.hoisted(() => vi.fn());

vi.mock("@antv/g6", () => ({ Graph: GraphMock }));

const graph = {
  nodes: ["root", "cross", "child"].map((id) => ({
    id,
    label: id,
    account: id,
    bank: "",
    incoming: 0,
    outgoing: 0,
    risk: 0,
    risk_level: "低风险",
    risk_factors: [],
  })),
  edges: [
    {
      id: "root>child",
      source: "root",
      target: "child",
      amount: 100,
      count: 1,
      transaction_ids: ["tx-1"],
      first_transaction_time: "2026-01-01T09:00:00",
    },
    {
      id: "cross>child",
      source: "cross",
      target: "child",
      amount: 80,
      count: 1,
      transaction_ids: ["tx-2"],
      first_transaction_time: "2026-01-01T09:05:00",
    },
  ],
} as GraphData;

test("configures a hierarchical topology with whole-surface panning", async () => {
  GraphMock.mockImplementation(() => ({
    on: vi.fn(),
    render: vi.fn().mockResolvedValue(undefined),
    setElementState: vi.fn().mockResolvedValue(undefined),
    destroy: vi.fn(),
  }));

  render(
    <GraphCanvas
      data={graph}
      selectedNode={null}
      selectedEdge={null}
      onNode={vi.fn()}
      onEdge={vi.fn()}
      playing={false}
      playTick={0}
    />,
  );

  await waitFor(() => expect(GraphMock).toHaveBeenCalled());
  const options = GraphMock.mock.calls[0][0];
  expect(options.background).toBe("#f7faff");
  expect(options.data.nodes[0].style.fill).toBe("#2878b8");
  expect(options.edge.state.selected.stroke).toBe("#15508a");
  expect(options.layout).toBeUndefined();
  expect(options.cursor).toBe("grab");
  expect(options.behaviors).toEqual([
    { type: "drag-canvas", enable: true },
    { type: "zoom-canvas", sensitivity: 1.4 },
  ]);
  expect(options.data.nodes[0].style).toMatchObject({
    x: expect.any(Number),
    y: expect.any(Number),
    labelPlacement: "right",
  });
  const primaryEdge = options.data.edges.find((edge: any) => edge.id === "root>child");
  const auxiliaryEdge = options.data.edges.find((edge: any) => edge.id === "cross>child");
  expect(primaryEdge).toMatchObject({
    type: "polyline",
    style: { opacity: 0.68, stroke: "#6d8ca5", lineWidth: 1.5 },
  });
  expect(auxiliaryEdge).toMatchObject({
    type: "cubic-horizontal",
    style: { opacity: 0.68, stroke: "#6d8ca5", lineWidth: 1.5 },
  });
  expect(auxiliaryEdge.style).toEqual(primaryEdge.style);
  expect(options.node.state.selected).not.toHaveProperty("shadowColor");
  expect(options.edge.state.playing).not.toHaveProperty("shadowBlur");
});

test("uses the priority level only for the node border", async () => {
  GraphMock.mockImplementation(() => ({
    on: vi.fn(),
    render: vi.fn().mockResolvedValue(undefined),
    setElementState: vi.fn().mockResolvedValue(undefined),
    destroy: vi.fn(),
  }));
  (graph.nodes[0] as any).priority_level = "一级重点";

  render(
    <GraphCanvas
      data={graph}
      selectedNode={null}
      selectedEdge={null}
      onNode={vi.fn()}
      onEdge={vi.fn()}
      playing={false}
      playTick={0}
    />,
  );

  await waitFor(() => expect(GraphMock).toHaveBeenCalled());
  const style = GraphMock.mock.calls.at(-1)![0].data.nodes[0].style;
  expect(style).toMatchObject({
    labelText: "root",
    fill: "#2878b8",
    stroke: "#c9363e",
    lineWidth: 4,
  });
});
