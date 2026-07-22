import { expect, test } from "vitest";
import { GRAPH_PALETTE } from "./theme";

test("defines a blue-white graph palette with risk-only red", () => {
  expect(GRAPH_PALETTE.canvas).toBe("#f7faff");
  expect(GRAPH_PALETTE.node).toBe("#2878b8");
  expect(GRAPH_PALETTE.selected).toBe("#15508a");
  expect(GRAPH_PALETTE.risk).toBe("#c9363e");
  expect(GRAPH_PALETTE.edge).not.toBe(GRAPH_PALETTE.risk);
});
