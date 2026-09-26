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

  accent: "#4fc3b0",
  accentHover: "#6dd4c3",

  severityLimit: "#e5484d",
  severityWarning: "#f5a524",
  severityWatch: "#fde047", // Spec 03 v0.3 §5.2 — was #eab308, too close to warning's #f5a524
  severityInfo: "#64748b",

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
