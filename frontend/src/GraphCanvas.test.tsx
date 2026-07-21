import { render, waitFor } from "@testing-library/react";
import { vi, expect, test } from "vitest";
import GraphCanvas from "./GraphCanvas";
import type { GraphData } from "./types";

const GraphMock = vi.hoisted(() => vi.fn());

vi.mock("@antv/g6", () => ({ Graph: GraphMock }));

const graph = {
  nodes: [],
  edges: [],
} as GraphData;

test("configures the layered topology without glow styling", async () => {
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
      layout="layered"
      playing={false}
      playTick={0}
    />,
  );

  await waitFor(() => expect(GraphMock).toHaveBeenCalled());
  const options = GraphMock.mock.calls[0][0];
  expect(options.layout).toMatchObject({ type: "antv-dagre", rankdir: "LR" });
  expect(options.node.state.selected).not.toHaveProperty("shadowColor");
  expect(options.edge.state.playing).not.toHaveProperty("shadowBlur");
});
