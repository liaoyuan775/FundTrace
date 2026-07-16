import { useEffect, useRef } from "react";
import { Graph } from "@antv/g6";
import type { GraphData } from "./types";
import { buildFocusStates, chronologicalEdgeIds } from "./graph-state";

type Props = {
  data: GraphData;
  selectedNode: string | null;
  selectedEdge: string | null;
  onNode: (id: string) => void;
  onEdge: (id: string) => void;
  layout: string;
  playing: boolean;
  playTick: number;
};
export default function GraphCanvas({
  data,
  selectedNode,
  selectedEdge,
  onNode,
  onEdge,
  layout,
  playing,
  playTick,
}: Props) {
  const host = useRef<HTMLDivElement>(null);
  const graph = useRef<Graph | null>(null);
  const interaction = useRef({ selectedNode, selectedEdge, playing, playTick });
  interaction.current = { selectedNode, selectedEdge, playing, playTick };
  const callbacks = useRef({ onNode, onEdge });
  callbacks.current = { onNode, onEdge };
  useEffect(() => {
    if (!host.current) return;
    graph.current?.destroy();
    graph.current = null;
    let cancelled = false;
    const options: any = {
      container: host.current,
      autoFit: { type: "view", options: { when: "always" } },
      zoomRange: [0.08, 8],
      padding: 34,
      data: {
        nodes: data.nodes.map((n) => ({
          id: n.id,
          data: n,
          style: {
            labelText: n.label,
            labelFontSize: 10,
            labelFill: "#d8dbd7",
            labelBackground: true,
            labelBackgroundFill: "#111413",
            size: 10 + Math.min(16, n.risk / 8),
            fill: n.risk > 88 ? "#f04438" : n.risk > 75 ? "#e4a72c" : "#59b7bf",
            stroke: "#fffdf7",
            lineWidth: 1,
            opacity: 1,
          },
        })),
        edges: data.edges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          data: e,
          style: {
            stroke: "#69716c",
            lineWidth: Math.min(4, 1 + Math.log10(e.amount || 1) / 2.5),
            opacity: 0.65,
            endArrow: true,
          },
        })),
      },
      node: {
        state: {
          selected: { stroke: "#fffdf7", lineWidth: 4, opacity: 1, shadowColor: "#fffdf7", shadowBlur: 18 },
          "incoming-neighbor": { stroke: "#59b7bf", lineWidth: 3, opacity: 1 },
          "outgoing-neighbor": { stroke: "#e4a72c", lineWidth: 3, opacity: 1 },
          "edge-endpoint": { stroke: "#f04438", lineWidth: 3, opacity: 1 },
          "playing-source": { fill: "#e4a72c", stroke: "#fff7cf", lineWidth: 4, opacity: 1, shadowColor: "#e4a72c", shadowBlur: 24 },
          "playing-target": { fill: "#f04438", stroke: "#fff7cf", lineWidth: 4, opacity: 1, shadowColor: "#f04438", shadowBlur: 24 },
          inactive: { opacity: 0.16 },
        },
      },
      edge: {
        state: {
          selected: { stroke: "#f04438", lineWidth: 5, opacity: 1 },
          incoming: { stroke: "#59b7bf", lineWidth: 4, opacity: 1 },
          outgoing: { stroke: "#e4a72c", lineWidth: 4, opacity: 1 },
          playing: { stroke: "#fff06a", lineWidth: 6, opacity: 1, shadowColor: "#fff06a", shadowBlur: 14 },
          inactive: { opacity: 0.06 },
        },
      },
      layout:
        layout === "radial"
          ? { type: "radial", unitRadius: 90, preventOverlap: true }
          : { type: "antv-dagre", rankdir: "LR", ranksep: 75, nodesep: 18 },
      behaviors: [{ type: "drag-canvas" }, { type: "zoom-canvas", sensitivity: 1.4 }, "drag-element"],
      animation: false,
    };
    const instance = new Graph(options);
    instance.on("node:click", (event: any) => callbacks.current.onNode(event.target.id));
    instance.on("edge:click", (event: any) => callbacks.current.onEdge(event.target.id));
    void instance.render().then(() => {
      if (cancelled) return;
      graph.current = instance;
      const current = interaction.current;
      const order = chronologicalEdgeIds(data);
      const active = current.playing && order.length ? order[current.playTick % order.length] : null;
      const states = buildFocusStates(data, current.selectedNode, current.selectedEdge, active);
      return instance.setElementState({ ...states.nodes, ...states.edges }, false);
    });
    return () => {
      cancelled = true;
      instance.destroy();
      if (graph.current === instance) graph.current = null;
    };
  }, [data, layout]);
  useEffect(() => {
    const instance = graph.current;
    if (!instance) return;
    const playOrder = chronologicalEdgeIds(data);
    const playingEdge = playing && playOrder.length ? playOrder[playTick % playOrder.length] : null;
    const states = buildFocusStates(data, selectedNode, selectedEdge, playingEdge);
    void instance.setElementState({ ...states.nodes, ...states.edges }, false);
  }, [data, selectedNode, selectedEdge, playing, playTick]);
  return <div ref={host} className="graph-canvas" data-testid="graph-canvas" />;
}
