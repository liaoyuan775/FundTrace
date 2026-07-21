# Police Blue Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the red-black visual theme with a deep-blue navigation shell and light blue-white work areas while preserving layout, interactions, and risk semantics.

**Architecture:** Keep CSS responsible for the page surfaces, controls, tables, and typography. Add one small TypeScript palette contract for the G6 canvas colors, so canvas colors and tests share named semantic values without changing business logic.

**Tech Stack:** React 18, TypeScript, CSS custom properties, AntV G6 5, Vitest

## Global Constraints

- Preserve current page structure, interaction, information density, and copy.
- Red remains reserved for high risk, errors, and conflicts; orange remains medium-risk.
- Keep frontend port `5173` and backend port `8000`.
- Do not change backend interfaces, data models, or graph behavior.

---

### Task 1: Canvas Palette Contract

**Files:**
- Create: `frontend/src/theme.ts`
- Create: `frontend/src/theme.test.ts`
- Modify: `frontend/src/GraphCanvas.tsx`
- Modify: `frontend/src/GraphCanvas.test.tsx`

**Interfaces:**
- Produces: `GRAPH_PALETTE` with `canvas`, `grid`, `label`, `labelBackground`, `node`, `risk`, `mediumRisk`, `incoming`, `outgoing`, `edge`, `auxiliaryEdge`, `selected` and `playing` string values.
- Consumes: `GRAPH_PALETTE` in all G6 node and edge styles.

- [ ] **Step 1: Write the failing palette test**

```ts
import { expect, test } from "vitest";
import { GRAPH_PALETTE } from "./theme";

test("defines a blue-white graph palette with risk-only red", () => {
  expect(GRAPH_PALETTE.canvas).toBe("#f7faff");
  expect(GRAPH_PALETTE.node).toBe("#2878b8");
  expect(GRAPH_PALETTE.selected).toBe("#15508a");
  expect(GRAPH_PALETTE.risk).toBe("#c9363e");
  expect(GRAPH_PALETTE.edge).not.toBe(GRAPH_PALETTE.risk);
});
```

- [ ] **Step 2: Run the focused test and verify the missing-module failure**

Run: `npm.cmd test -- --run src/theme.test.ts`

Expected: FAIL because `./theme` does not exist.

- [ ] **Step 3: Add the minimal semantic palette**

```ts
export const GRAPH_PALETTE = {
  canvas: "#f7faff",
  grid: "#dce9f5",
  label: "#17324d",
  labelBackground: "#ffffff",
  node: "#2878b8",
  risk: "#c9363e",
  mediumRisk: "#d58a22",
  incoming: "#2575a8",
  outgoing: "#3b82c4",
  edge: "#6d8ca5",
  auxiliaryEdge: "#a9bfd2",
  selected: "#15508a",
  playing: "#1769aa",
} as const;
```

- [ ] **Step 4: Replace hard-coded GraphCanvas colors with `GRAPH_PALETTE`**

Use `GRAPH_PALETTE` for node fills, labels, label backgrounds, primary and auxiliary edges, incoming/outgoing states, selected state, endpoint state, and playing states. Keep red only in the `risk` state and preserve node/edge opacity and widths.

- [ ] **Step 5: Run the focused tests and verify they pass**

Run: `npm.cmd test -- --run src/theme.test.ts src/GraphCanvas.test.tsx`

Expected: all palette and graph configuration tests pass.

### Task 2: CSS Blue-White Surfaces

**Files:**
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: the existing CSS class structure; no component API changes.
- Produces: deep-blue shell, light work areas, blue controls, and blue-gray table states.

- [ ] **Step 1: Define the new root theme variables**

```css
:root {
  color: #17324d;
  background: #123b63;
  --ink: #123b63;
  --ink2: #1b4f7d;
  --ink3: #eaf3fb;
  --line: #c8d9e8;
  --paper: #ffffff;
  --muted: #5d7488;
  --red: #c9363e;
  --amber: #d58a22;
  --cyan: #2878b8;
  --green: #2d8a62;
}
```

- [ ] **Step 2: Replace dark shell and work-area surfaces**

Set `.topbar` and `.rail` to `#123b63`; set `.filters`, `.inspector`, `.card`, and `.panel-block` to `#ffffff`; set `.graph-workspace` to `#f7faff`; set its grid lines to `#dce9f5`; and set shared borders to `#c8d9e8`.

- [ ] **Step 3: Replace control, alert, and table state colors**

Use action blue for active navigation, primary controls, focus borders, and selected table rows. Keep high-risk/error selectors red, medium-risk selectors amber, and successful states green. Change yellow/cream table hover and selected backgrounds to pale blue equivalents.

- [ ] **Step 4: Run CSS syntax/build verification**

Run: `npm.cmd run build`

Expected: TypeScript and Vite build successfully.

### Task 3: Regression And Browser QA

**Files:**
- Verify: `frontend/src/App.test.tsx`, `frontend/src/GraphCanvas.test.tsx`, `frontend/src/theme.test.ts`

- [ ] **Step 1: Run the complete frontend suite**

Run: `npm.cmd test -- --run`

Expected: all tests pass.

- [ ] **Step 2: Verify the fixed-port page**

Open: `http://127.0.0.1:5173`

Verify: cases, materials, review, seeds, and analysis retain the same structure; the shell is deep blue, content is white/light blue, topology labels remain readable, and red appears only for risk/error semantics.

- [ ] **Step 3: Check the final diff and fixed ports**

Run: `git diff --check` and `netstat -ano | Select-String 'LISTENING\\s+\\d+$' | Select-String ':5173\\s|:5174\\s|:8000\\s'`

Expected: no whitespace errors; listeners only on `5173` and `8000`, never `5174`.
