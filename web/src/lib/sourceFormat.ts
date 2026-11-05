import type { LogSourceFormat } from "../types/contract";

// Spec 03 v0.22–0.23 §5.1 — the export format a log came from, as the pilot knows it.
export const SOURCE_FORMAT_LABEL: Record<LogSourceFormat, string> = {
  g3x_direct: "G3X",
  garmin_pilot: "Garmin Pilot",
  axis: "AXIS card",
  aircraft_log: "Aircraft log",
  unknown: "",
};

// Spec 03 §5.9 — the filled-row share of a resampled log, as a person reads it.
export function filledShareText(share: number): string {
  if (share <= 0) return "";
  if (share < 0.005) return "under 1% of rows filled";
  return `${Math.round(share * 100)}% of rows filled`;
}
