# Hierarchical Topology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dense force graph with a stable left-to-right hierarchical tree presentation and make dragging anywhere in the graph pan the whole viewport.

**Architecture:** Add a pure layout module that derives deterministic node coordinates and a primary tree-edge set from the existing directed `GraphData`. `GraphCanvas` will render those preset coordinates, style primary and auxiliary edges separately, and configure G6 so all drag targets pan the viewport while individual nodes remain fixed.

**Tech Stack:** React 18, TypeScript, AntV G6 5, Vitest, Testing Library

## Global Constraints

- Keep every account and every transfer path visible.
- Do not change the backend graph contract or persistence.
- Preserve node, edge, table, playback, zoom, and reset-selection behavior.
- Keep frontend port `5173` and backend port `8000`.

---

### Task 1: Deterministic Hierarchical Layout

**Files:**
- Create: `frontend/src/hierarchical-layout.ts`
- Create: `frontend/src/hierarchical-layout.test.ts`

**Interfaces:**
- Consumes: `GraphData`, `GraphNode`, and `GraphEdge` from `frontend/src/types.ts`.
- Produces: `buildHierarchicalLayout(data: GraphData): { positions: Record<string, { x: number; y: number; depth: number }>; primaryEdgeIds: Set<string> }`.

- [ ] **Step 1: Write failing tests for branches, convergence, cycles, multiple roots, and isolated nodes**

```ts
const result = buildHierarchicalLayout(graph);
expect(result.positions.root.depth).toBe(0);
expect(result.positions.child.depth).toBe(1);
expect(result.positions.leaf.x).toBeGreaterThan(result.positions.child.x);
expect(result.primaryEdgeIds).toEqual(new Set(["root>child", "child>leaf"]));
expect(buildHierarchicalLayout(graph)).toEqual(result);
```

- [ ] **Step 2: Run the focused test and verify the missing-module failure**

Run: `npm.cmd test -- --run src/hierarchical-layout.test.ts`

Expected: FAIL because `./hierarchical-layout` does not exist.

- [ ] **Step 3: Implement deterministic depth, parent, order, and coordinate calculation**

```ts
export type HierarchicalLayout = {
  positions: Record<string, { x: number; y: number; depth: number }>;
  primaryEdgeIds: Set<string>;
};

export function buildHierarchicalLayout(data: GraphData): HierarchicalLayout {
  const ids = data.nodes.map((node) => node.id).sort();
  const outgoing = new Map(ids.map((id) => [id, [] as GraphEdge[]]));
  const incoming = new Map(ids.map((id) => [id, [] as GraphEdge[]]));
  const compareEdges = (left: GraphEdge, right: GraphEdge) =>
    left.first_transaction_time.localeCompare(right.first_transaction_time) ||
    right.amount - left.amount ||
    left.id.localeCompare(right.id);

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

  const maximumLayerSize = Math.max(1, ...[...layers.values()].map((layer) => layer.length));
  const positions: HierarchicalLayout["positions"] = {};
  for (const [level, layer] of layers) {
    const top = 60 + ((maximumLayerSize - layer.length) * 40) / 2;
    layer.forEach((id, index) => {
      positions[id] = { x: 80 + level * 260, y: top + index * 40, depth: level };
    });
  }

  return {
    positions,
    primaryEdgeIds: new Set([...primaryByNode.values()].map((edge) => edge.id)),
  };
}
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `npm.cmd test -- --run src/hierarchical-layout.test.ts`

Expected: all hierarchical layout tests pass.

### Task 2: Tree Presentation And Whole-Surface Panning

**Files:**
- Modify: `frontend/src/GraphCanvas.tsx`
- Modify: `frontend/src/GraphCanvas.test.tsx`

**Interfaces:**
- Consumes: `buildHierarchicalLayout(data)` from Task 1.
- Produces: G6 graph options using preset positions, primary/auxiliary edge styles, and whole-surface panning.

- [ ] **Step 1: Change the graph configuration test to describe the new contract**

```ts
expect(options.layout).toBeUndefined();
expect(options.cursor).toBe("grab");
expect(options.behaviors).toEqual([
  { type: "drag-canvas", enable: true },
  { type: "zoom-canvas", sensitivity: 1.4 },
]);
expect(options.data.nodes[0].style).toMatchObject({ x: expect.any(Number), y: expect.any(Number) });
expect(options.data.edges.find((edge) => edge.id === "root>child").type).toBe("polyline");
expect(options.data.edges.find((edge) => edge.id === "cross>child").type).toBe("cubic-horizontal");
```

- [ ] **Step 2: Run the focused test and verify it fails against the force layout**

Run: `npm.cmd test -- --run src/GraphCanvas.test.tsx`

Expected: FAIL because the current graph uses `d3-force`, has no preset coordinates, and enables `drag-element`.

- [ ] **Step 3: Render the computed positions and separate visual hierarchy**

```ts
const hierarchy = buildHierarchicalLayout(data);

style: {
  x: hierarchy.positions[n.id].x,
  y: hierarchy.positions[n.id].y,
  labelPlacement: "right",
  labelOffsetX: 7,
}

type: hierarchy.primaryEdgeIds.has(e.id) ? "polyline" : "cubic-horizontal",
style: hierarchy.primaryEdgeIds.has(e.id)
  ? { stroke: "#69716c", lineWidth: 1.6, opacity: 0.62, endArrow: true }
  : { stroke: "#59605c", lineWidth: 1, opacity: 0.16, endArrow: true },
```

- [ ] **Step 4: Replace force simulation and conflicting node drag behavior**

```ts
cursor: "grab",
autoResize: true,
behaviors: [
  { type: "drag-canvas", enable: true },
  { type: "zoom-canvas", sensitivity: 1.4 },
],
```

- [ ] **Step 5: Run focused tests and verify they pass**

Run: `npm.cmd test -- --run src/hierarchical-layout.test.ts src/GraphCanvas.test.tsx`

Expected: both test files pass.

### Task 3: Regression And Browser Verification

**Files:**
- Verify only; no planned source changes.

**Interfaces:**
- Consumes: the completed layout and graph configuration.
- Produces: automated and browser evidence for the requested experience.

- [ ] **Step 1: Run the complete frontend test suite**

Run: `npm.cmd test -- --run`

Expected: all frontend tests pass, including selection and splitter regressions.

- [ ] **Step 2: Run the production build**

Run: `npm.cmd run build`

Expected: TypeScript and Vite build successfully; the existing bundle-size warning is acceptable.

- [ ] **Step 3: Verify in the fixed-port browser session**

Open: `http://127.0.0.1:5173`

Verify: 52 nodes and 117 edges render; layers progress left to right; primary tree paths are clear; auxiliary edges remain visible but subdued; dragging from background, a node, and an edge pans the viewport; node and edge clicks still update the inspector and transaction table.
