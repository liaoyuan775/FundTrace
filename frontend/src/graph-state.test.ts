import { describe, expect, test } from "vitest";
import { buildFocusStates, chronologicalEdgeIds } from "./graph-state";
import type { GraphData } from "./types";

const graph = {
  nodes: ["A", "B", "C", "D"].map((id) => ({ id })),
  edges: [
    { id: "A>B", source: "A", target: "B", first_transaction_time: "2026-06-18T10:10:00" },
    { id: "C>A", source: "C", target: "A", first_transaction_time: "2026-06-18T10:05:00" },
    { id: "B>D", source: "B", target: "D", first_transaction_time: "2026-06-18T10:20:00" },
  ],
} as GraphData;

describe("graph interaction states", () => {
  test("node focus highlights only direct incoming and outgoing neighbors", () => {
    const states = buildFocusStates(graph, "A", null, null);
    expect(states.nodes.A).toEqual(["selected"]);
    expect(states.nodes.B).toEqual(["outgoing-neighbor"]);
    expect(states.nodes.C).toEqual(["incoming-neighbor"]);
    expect(states.nodes.D).toEqual(["inactive"]);
    expect(states.edges["A>B"]).toEqual(["outgoing"]);
    expect(states.edges["C>A"]).toEqual(["incoming"]);
    expect(states.edges["B>D"]).toEqual(["inactive"]);
  });

  test("playback highlights one chronological edge and both endpoints", () => {
    expect(chronologicalEdgeIds(graph)).toEqual(["C>A", "A>B", "B>D"]);
    const states = buildFocusStates(graph, null, null, "C>A");
    expect(states.edges["C>A"]).toEqual(["playing"]);
    expect(states.nodes.C).toEqual(["playing-source"]);
    expect(states.nodes.A).toEqual(["playing-target"]);
    expect(states.nodes.B).toEqual(["inactive"]);
  });

  test("edge focus replaces an existing node focus", () => {
    const states = buildFocusStates(graph, "A", "B>D", null);

    expect(states.edges["B>D"]).toEqual(["selected"]);
    expect(states.nodes.B).toEqual(["edge-endpoint"]);
    expect(states.nodes.D).toEqual(["edge-endpoint"]);
    expect(states.nodes.A).toEqual(["inactive"]);
    expect(states.edges["A>B"]).toEqual(["inactive"]);
  });
});
