import { useEffect, useRef } from "react";
import { Graph } from "@antv/g6";
import type { GraphData } from "./types";
import { buildFocusStates, chronologicalEdgeIds } from "./graph-state";
import { buildHierarchicalLayout } from "./hierarchical-layout";
import { GRAPH_PALETTE } from "./theme";

type Props = {
  data: GraphData;
  selectedNode: string | null;
  selectedEdge: string | null;
  onNode: (id: string) => void;
  onEdge: (id: string) => void;
  playing: boolean;
  playTick: number;
};
function priorityBorder(level?: string) {
  if (level === "一级重点") {
    return { stroke: GRAPH_PALETTE.risk, lineWidth: 4 };
  }
  if (level === "二级重点") {
    return { stroke: GRAPH_PALETTE.mediumRisk, lineWidth: 3 };
  }
  if (level === "三级关注") {
    return { stroke: GRAPH_PALETTE.outgoing, lineWidth: 2 };
  }
  return { stroke: GRAPH_PALETTE.labelBackground, lineWidth: 1 };
}
export default function GraphCanvas({
  data,
  selectedNode,
  selectedEdge,
  onNode,
  onEdge,
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
    const hierarchy = buildHierarchicalLayout(data);
    const options: any = {
      container: host.current,
      background: GRAPH_PALETTE.canvas,
      cursor: "grab",
      autoResize: true,
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
            labelFill: GRAPH_PALETTE.label,
            labelBackground: true,
            labelBackgroundFill: GRAPH_PALETTE.labelBackground,
            labelPlacement: "right",
            labelOffsetX: 7,
            x: hierarchy.positions[n.id].x,
            y: hierarchy.positions[n.id].y,
            size: 10 + Math.min(16, n.risk / 8),
            fill: GRAPH_PALETTE.node,
            ...priorityBorder(n.priority_level),
            opacity: 1,
          },
        })),
        edges: data.edges.map((e) => {
          const primary = hierarchy.primaryEdgeIds.has(e.id);
          return {
            id: e.id,
            source: e.source,
            target: e.target,
            type: primary ? "polyline" : "cubic-horizontal",
            data: e,
            style: {
              stroke: GRAPH_PALETTE.edge,
              lineWidth: 1.5,
              opacity: 0.68,
              endArrow: true,
            },
          };
        }),
      },
      node: {
        state: {
          selected: { stroke: GRAPH_PALETTE.selected, lineWidth: 4, opacity: 1 },
          "incoming-neighbor": { stroke: GRAPH_PALETTE.incoming, lineWidth: 3, opacity: 1 },
          "outgoing-neighbor": { stroke: GRAPH_PALETTE.outgoing, lineWidth: 3, opacity: 1 },
          "edge-endpoint": { stroke: GRAPH_PALETTE.selected, lineWidth: 3, opacity: 1 },
          "playing-source": { fill: GRAPH_PALETTE.outgoing, stroke: GRAPH_PALETTE.labelBackground, lineWidth: 4, opacity: 1 },
          "playing-target": { fill: GRAPH_PALETTE.selected, stroke: GRAPH_PALETTE.labelBackground, lineWidth: 4, opacity: 1 },
          inactive: { opacity: 0.16 },
        },
      },
      edge: {
        state: {
          selected: { stroke: GRAPH_PALETTE.selected, lineWidth: 5, opacity: 1 },
          incoming: { stroke: GRAPH_PALETTE.incoming, lineWidth: 4, opacity: 1 },
          outgoing: { stroke: GRAPH_PALETTE.outgoing, lineWidth: 4, opacity: 1 },
          playing: { stroke: GRAPH_PALETTE.playing, lineWidth: 6, opacity: 1 },
          inactive: { opacity: 0.06 },
        },
      },
      behaviors: [
        { type: "drag-canvas", enable: true },
        { type: "zoom-canvas", sensitivity: 1.4 },
      ],
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
  }, [data]);
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
