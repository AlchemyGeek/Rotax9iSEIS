// ECharts renders to <canvas>, and the Canvas 2D API does not resolve CSS
// custom properties (fillStyle/strokeStyle just silently fail on a
// "var(--x)" string and fall back to black) — unlike regular DOM/CSS,
// where var(--x) works fine. So every color handed to an ECharts `option`
// must be a literal value. This file is that literal mirror of
// index.css's tokens, for chart code only — DOM styling should keep using
// var(--x) directly.
export const colors = {
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
} as const;

// Canvas text doesn't inherit the page's CSS font-family either — same
// class of bug as the color one above. Every ECharts textStyle/label
// needs this set explicitly or it silently falls back to the browser's
// generic sans-serif, which is how the Trends mean-line label ended up
// visibly inconsistent with the rest of the UI.
export const fontSans = "'IBM Plex Sans', system-ui, sans-serif";
export const fontMono = "'IBM Plex Mono', ui-monospace, monospace";
