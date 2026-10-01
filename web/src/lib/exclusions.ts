import type { ExclusionEntry } from "../types/contract";

// Skipped logs (Spec: Workspace Flight Exclusions) — a file that never
// became a flight_id, tagged with why. Deliberately separate from
// FlightRowStatus's STATUS_LABEL/STATUS_COLOR, which describes a real,
// analyzed flight's state, not "this was never one." Shared between the
// Flights tab's Skipped panel and the skipped-log preview screen.
export const EXCLUSION_CATEGORY_LABEL: Record<ExclusionEntry["category"], string> = {
  ground_session: "Ground session",
  short_flight: "Short flight",
  corrupt_log: "Corrupt log",
  user_defined: "User excluded",
};

export const EXCLUSION_CATEGORY_COLOR: Record<ExclusionEntry["category"], string> = {
  ground_session: "var(--text-tertiary)",
  short_flight: "var(--text-tertiary)",
  corrupt_log: "var(--severity-warning)",
  user_defined: "var(--text-secondary)",
};
