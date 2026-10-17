import type { LogSourceFormat } from "../types/contract";

// Spec 03 v0.22 §5.1 — the export format a log came from, as the pilot knows it.
export const SOURCE_FORMAT_LABEL: Record<LogSourceFormat, string> = {
  g3x_direct: "G3X",
  garmin_pilot: "Garmin Pilot",
  axis: "AXIS",
  unknown: "",
};
