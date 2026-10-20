// ECharts renders to <canvas>, and the Canvas 2D API does not resolve CSS
// custom properties (fillStyle/strokeStyle just silently fail on a
// "var(--x)" string and fall back to black) — unlike regular DOM/CSS,
// where var(--x) works fine. So every color handed to an ECharts `option`
// must be a literal value. This file is that literal mirror of
// index.css's tokens, for chart code only — DOM styling should keep using
// var(--x) directly. Both themes (Spec 15 §9): keep each value equal to its
// index.css twin under :root (dark) and :root[data-theme="light"].
const dark = {
  bg: "#0f1214",
  panel: "#171b1e",
  panelControl: "#20252a",
  border: "#2a3136",
  borderSubtle: "#1f2427",

  textPrimary: "#e8eaed",
  textSecondary: "#c9d0d6",
  textTertiary: "#aeb7bf",

  // Spec 15: the brand, reserved for "active / primary" roles; the tint
  // is the same hue for lines and text on dark (the fill is 2.4:1 there).
  brand: "#3d5a73",
  brandTint: "#7fa3c2",
  ok: "#4fc3b0",

  severityLimit: "#e5484d",
  severityWarning: "#f5a524",
  severityWatch: "#fde047", // Spec 03 v0.3 §5.2 — was #eab308, too close to warning's #f5a524
  severityInfo: "#64748b",

  // Chart data colors — never the brand (Spec 15 §3–§4).
  chartHighlight: "#ffffff",
  chartData: "#4fc3b0",
  chartRecentFill: "rgba(79,195,176,0.07)",
  chartRpm: "#4fc3b0",
  chartIas: "#8b7fe8",
  chartOilTemp: "#e5484d",
  chartEgtSpread: "#eab308",
  chartCoolantTemp: "#5b9bd5",
  chartMap: "#7ed957",
  chartFuelFlow: "#ff8a4c",
  chartVs: "#e86ba6",
  // egt_cyl (Spec 07 D3): one hue family, four lightness steps, cylinder 1→4.
  egtCyl: ["#FDE68A", "#FBBF24", "#D97706", "#92400E"],
  // Chart shading: the reference band, flights not used, the minimap's
  // outside-the-window dimming.
  referenceFill: "rgba(174,183,191,0.10)",
  notUsedFill: "rgba(174,183,191,0.015)",
  minimapDim: "rgba(15,18,20,0.72)",
};

export type Palette = { [K in keyof typeof dark]: (typeof dark)[K] extends readonly string[] ? string[] : string };

// Spec 15 §9: the light theme. Every value re-checked on white rather than
// carried over — text ≥ 4.5:1, lines and markers ≥ 3:1; the severity
// colors darkened (the dark theme's pale watch yellow is ~1.3:1 on white);
// the brand's fill and tint swap roles (#3d5a73 itself reads at 7:1 here).
const light: Palette = {
  bg: "#f4f6f8",
  panel: "#ffffff",
  panelControl: "#eef1f4",
  border: "#d3d9df",
  borderSubtle: "#e6eaee",

  textPrimary: "#161b20",
  textSecondary: "#3a434c",
  textTertiary: "#5a6570",

  brand: "#3d5a73",
  brandTint: "#3d5a73",
  ok: "#0b7d6d",

  severityLimit: "#d1242f",
  severityWarning: "#c4530a",
  severityWatch: "#946800",
  severityInfo: "#5f6d80",

  chartHighlight: "#000000",
  chartData: "#0b7d6d",
  chartRecentFill: "rgba(11,125,109,0.07)",
  chartRpm: "#0e9a87",
  chartIas: "#6a5bd6",
  chartOilTemp: "#d1242f",
  chartEgtSpread: "#b98900",
  chartCoolantTemp: "#2f78c2",
  chartMap: "#3f9e1f",
  chartFuelFlow: "#e0661c",
  chartVs: "#c9417f",
  egtCyl: ["#E3A008", "#C27803", "#9F580A", "#723B13"],
  referenceFill: "rgba(90,101,112,0.10)",
  notUsedFill: "rgba(90,101,112,0.03)",
  minimapDim: "rgba(244,246,248,0.72)",
};

export type Theme = "dark" | "light";
export const palettes: Record<Theme, Palette> = { dark: dark as Palette, light };

/**
 * The palette in effect. Chart code reads it when it builds an option, so
 * it is one mutable object, switched in place by `applyPalette` (lib/theme.ts
 * remounts the views on a theme change, and every chart rebuilds).
 */
export const colors: Palette = { ...(dark as Palette), egtCyl: [...dark.egtCyl] };

export function applyPalette(theme: Theme) {
  const p = palettes[theme];
  Object.assign(colors, p, { egtCyl: [...p.egtCyl] });
}

// Canvas text doesn't inherit the page's CSS font-family either — same
// class of bug as the color one above. Every ECharts textStyle/label
// needs this set explicitly or it silently falls back to the browser's
// generic sans-serif, which is how the Trends mean-line label ended up
// visibly inconsistent with the rest of the UI.
export const fontSans = "'IBM Plex Sans', system-ui, sans-serif";
export const fontMono = "'IBM Plex Mono', ui-monospace, monospace";
