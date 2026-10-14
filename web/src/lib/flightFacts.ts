import type { FlightAnalysis } from "../types/contract";

// Spec 10 §4.3 (D20): the Flight view header's *Flight facts* row carries
// per-flight figures a pilot records rather than judges. This list IS the
// §4.3 table — the one place a fact is admitted. Anything not listed here
// is dropped by flightFacts(), whatever a caller builds; adding a fact
// means adding a §4.3 row first.
export const FLIGHT_FACT_IDS = ["fuel_burned", "cruise_nmpg", "cruise_fuel_flow", "lane_check"] as const;
export type FlightFactId = (typeof FLIGHT_FACT_IDS)[number];

export interface FlightFact {
  id: FlightFactId;
  label: string;
  value: string; // plain value, "—" when unavailable — no badge, no severity
}

const LANE_CHECK_TEXT: Record<NonNullable<FlightAnalysis["ecu_lane_check"]>, string> = {
  both: "both lanes ✓",
  single: "one lane only",
  none: "not detected",
};

function num(v: unknown, digits: number, unit: string): string {
  return typeof v === "number" ? `${v.toFixed(digits)} ${unit}` : "—";
}

// Every candidate the Flight view knows how to compute. Only ids in
// FLIGHT_FACT_IDS survive admitFacts().
function candidateFacts(fa: FlightAnalysis): { id: string; label: string; value: string }[] {
  const m = fa.metrics;
  // A log without the CAS channel has nothing to say about the lane check.
  const lane = m.cas_engine_ecu_events?.missing ? undefined : fa.ecu_lane_check;
  return [
    { id: "fuel_burned", label: "Fuel burned", value: num(m.fadec_gallons?.value, 1, "gal") },
    { id: "cruise_nmpg", label: "Cruise", value: num(m.cruise_nmpg?.value, 1, "nm/gal") },
    { id: "cruise_fuel_flow", label: "Cruise fuel flow", value: num(m.cruise_fuel_flow_gph?.value, 1, "gal/hr") },
    { id: "lane_check", label: "Lane check", value: lane ? LANE_CHECK_TEXT[lane] : "—" },
  ];
}

export function admitFacts(facts: { id: string; label: string; value: string }[]): FlightFact[] {
  const allowed = new Set<string>(FLIGHT_FACT_IDS);
  return facts.filter((f): f is FlightFact => allowed.has(f.id));
}

export function flightFacts(fa: FlightAnalysis): FlightFact[] {
  return admitFacts(candidateFacts(fa));
}
