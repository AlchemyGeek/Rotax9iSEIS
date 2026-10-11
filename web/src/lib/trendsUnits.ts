// Spec 12 — display units for fleet metrics with a known, fixed unit.
// Per-limit metrics (and overboost_time) carry their real unit straight
// from the engine profile as FleetMetric.unit (§11.7, Session C) — this
// table/fallback is only consulted when that field is absent.
export const TRENDS_METRIC_UNITS: Record<string, string> = {
  egt_spread: "°F",
  egt1_deviation: "°F",
  egt2_deviation: "°F",
  egt3_deviation: "°F",
  egt4_deviation: "°F",
  oil_temp_peak: "°F",
  coolant_temp_peak: "°F",
  oil_coolant_ratio: "",
  overboost_time: "s",
  cruise_efficiency: "nm/gal",
  cruise_fuel_flow: "gal/hr",
  climb_thermal_rate: "°F/min",
  takeoff_map_residual_inhg: "inHg",
};

export function unitFor(metricId: string): string {
  if (metricId in TRENDS_METRIC_UNITS) return TRENDS_METRIC_UNITS[metricId];
  if (metricId.endsWith("_time_above_pct")) return "%";
  if (metricId.endsWith("_block_s")) return "s";
  return "";
}

// "cylinder 3" for egt3_deviation, else the metric id humanized.
export function metricLabel(metricId: string): string {
  const cyl = /^egt([1-4])_deviation$/.exec(metricId);
  if (cyl) return `cylinder ${cyl[1]}`;
  if (metricId === "egt_spread") return "EGT spread";
  return metricId.replace(/_/g, " ");
}

export const PANEL_LABELS: Record<string, string> = {
  cylinder_balance: "Cylinder balance",
  thermal: "Thermal",
  boost_power: "Boost / power",
  fuel: "Fuel",
};

export function panelLabel(panel: string): string {
  if (panel.startsWith("limit:")) return `Limit: ${panel.slice("limit:".length).replace(/_/g, " ")}`;
  return PANEL_LABELS[panel] ?? panel.replace(/_/g, " ");
}
