import { describe, expect, test } from "vitest";
import { resizeAnalysisSplit } from "./analysis-split";

describe("resizeAnalysisSplit", () => {
  test("moves the graph height by the pointer delta", () => {
    expect(resizeAnalysisSplit(420, 80, 180)).toBe(500);
  });

  test("enforces the minimum panel height", () => {
    expect(resizeAnalysisSplit(220, -100, 180)).toBe(180);
  });

  test("enforces the maximum panel height", () => {
    expect(resizeAnalysisSplit(420, 500, 180, 600)).toBe(600);
  });
});
