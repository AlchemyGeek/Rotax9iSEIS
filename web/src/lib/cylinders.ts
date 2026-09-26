import type { FleetAnalysis } from "../types/contract";

// Spec 08 — cylinder balance helpers shared by Trends and its chart.

export const CYLINDERS = [1, 2, 3, 4] as const;
export const CYL_METRIC_IDS = CYLINDERS.map((n) => `egt${n}_deviation`);

// Validated as a set against the chart panel (#171b1e): adjacent-pair CVD
// ΔE ≥ 9.4, normal-vision ≥ 24.6, all ≥ 3:1. Cyl 1 and 3 (blue/violet) are
// the closest non-adjacent pair, so identity never rests on color alone:
// lines carry end labels, strip marks a per-cylinder shape.
export const CYL_COLORS: Record<number, string> = {
  1: "#3987e5",
  2: "#d95926",
  3: "#9085e9",
  4: "#199e70",
};

/** ?metric= ids that open this view, and which cylinder they focus. */
export function cylinderFocusFor(metricId: string): number | null | undefined {
  if (metricId === "cylinder_balance") return null;
  if (metricId === "egt4_elevation") return 4; // deprecated alias (Spec 08 §4)
  const m = /^egt([1-4])_deviation$/.exec(metricId);
  return m ? Number(m[1]) : undefined;
}

export function hasCylinderBalance(fleet: FleetAnalysis): boolean {
  return CYL_METRIC_IDS.some((id) => fleet.metrics[id]);
}

// ECharts symbol per cylinder for the hottest-cylinder strip, and the
// matching legend glyph.
export const CYL_SYMBOLS: Record<number, { echarts: string; glyph: string }> = {
  1: { echarts: "circle", glyph: "●" },
  2: { echarts: "rect", glyph: "■" },
  3: { echarts: "triangle", glyph: "▲" },
  4: { echarts: "diamond", glyph: "◆" },
};
