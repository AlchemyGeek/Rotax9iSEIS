// Spec 14 §7.4 — the one registry of inline help text, keyed by setting
// or trigger id. One sentence each, naming the consequence of changing
// the thing rather than the statistic behind it. Only the items in
// §7.4's "Gets help" column live here; adding one means reporting it
// (Spec 13 reuses this registry as its first tier, so the two cannot
// drift).
export const INLINE_HELP = {
  // Settings → Reference & Models
  "reference.outlier_z_threshold":
    "How far from your usual a flight must be before it is called out — lower flags more flights, including more ordinary variation.",
  "reference.recent_window":
    "How many of your latest flights Trends checks against the reference — a smaller window shows a change sooner but can be swayed by one odd flight.",
  "reference.pinning":
    "Pinning freezes which flights count as normal for a metric, so new flights are compared with those flights instead of with everything flown so far.",
  "reference.contributing_flights":
    "The flights that define what normal looks like for your engine — every other flight is judged against them.",
  "reference.stratification":
    "Temperatures and EGT are compared with flights flown in similar outside air temperature, and cruise fuel figures with flights at similar density altitude, so weather is not mistaken for an engine change.",

  // Settings → Engine
  "engine.suppression":
    "When a limit is checked — only in some flight phases, or only once it has been exceeded for a set time — so expected moments such as takeoff power are not reported as exceedances.",
  "engine.overrides":
    "None means every limit is the Operator's Manual value shown here; nothing has been changed for this aircraft.",

  // Topic card triggers
  "trigger.enabled": "Stops this topic reporting on every flight; past Journal entries stay.",
  "trigger.r2_min":
    "How clearly the points must line up before a trend is reported — lower reports trends sooner, with more false alarms.",
  "trigger.n_min":
    "How many of your other flights are needed before this check runs — lower starts checking sooner, against a less settled picture of normal.",
  "trigger.baseline_deviation":
    "Fires when this flight is further from the average of your other flights than they usually vary (σ), by more than the z-threshold set in Settings → Reference & Models.",

  // Preview
  "preview.counts":
    "Counts flights, not insights: newly flagged flights gain an insight from this topic, cleared ones lose it, and changed ones keep it at a different severity.",

  // Journal
  "journal.backfilled":
    "Recorded before the Journal existed, so it is dated to when it was imported and has no count of what it changed.",
  "journal.change_notices":
    "A past decision whose basis has moved since you made it — for example, a limit filter whose recent flights now breach or drift from its band — so you can check it still holds.",

  // Flight view header
  "flight.excluded_from_reference":
    "This flight is still analysed, but it no longer shapes what normal looks like for your other flights.",
} as const;

export type InlineHelpId = keyof typeof INLINE_HELP;
