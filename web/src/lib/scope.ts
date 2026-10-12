// Spec 14 §7.5 — the fixed scope wording every decision control shows
// before it is touched, and that its Apply button repeats. One place, so
// the wording is the same everywhere. Not help text (§7.4): always shown.
export type Scope = "flight" | "metric" | "limit" | "topic" | "reference_settings" | "all_limits";

export const SCOPE_CAPTION: Record<Scope, string> = {
  flight: "This flight only",
  metric: "All flights in this workspace — this metric",
  limit: "All flights in this workspace — this limit",
  topic: "All flights in this workspace — this topic",
  // Not in §7.5's table (reported): Settings → Reference & Models changes
  // the comparison for every metric at once.
  reference_settings: "All flights in this workspace — every metric",
  // Not in the table (reported): "Copy filters from…" brings in a filter
  // for every limit the other workspace has one for.
  all_limits: "All flights in this workspace — every limit copied",
};

// Shown with the "This flight only" caption on exclude-from-reference.
export const EXCLUDE_NOTE = "other flights' comparisons will move";

export const APPLY_LABEL: Record<Scope, string> = {
  flight: "Apply to this flight",
  metric: "Apply to all flights",
  limit: "Apply to all flights",
  topic: "Apply to all flights",
  reference_settings: "Apply to all flights",
  all_limits: "Apply to all flights",
};
