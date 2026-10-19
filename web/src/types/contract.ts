// Mirrors Spec 01 §8 (engine contract types). A subset — only what the
// four Spec 05 views need — not a full transcription of every schema.

export type Severity = "info" | "warn" | "error";
export type InsightSeverity = "info" | "watch" | "warning" | "limit";
export type MissingReason =
  | "NO_PHASE"
  | "CHANNEL_MISSING"
  | "INSUFFICIENT_DATA"
  | "NOT_APPLICABLE"
  | "EXCLUDED";

export interface Diagnostic {
  code: string;
  severity: Severity;
  scope: "file" | "flight" | "fleet" | "topic";
  message: string;
  refs?: Record<string, string | number>;
}

export interface MetricValue {
  id: string;
  // number[] only for list-valued metrics, e.g. egt_rank_order (Spec 08 §4).
  value: number | string | boolean | number[] | null;
  unit?: string;
  missing?: MissingReason;
}

export interface Phase {
  phase: string;
  start_s: number;
  end_s: number;
}

// Spec 01 §8.6 (v0.21): FlightAnalysis.exceedances is the flight's one
// event list — OM-limit exceedances (source "limit") and classified CAS
// alert occurrences (source "cas"). Narrow on `source` before reading
// limit fields.
export type FlightEvent = ExceedanceEvent | CasEvent;

export type NotLaneCheckReason = "rpm_below_band" | "rpm_above_band" | "too_long" | "moving";

export interface CasEvent {
  source: "cas";
  cas_id: string;
  event_id: string;
  classification: "GROUND" | "IN_FLIGHT";
  phase: string;
  phase_uncertain: boolean;
  start_utc: string;
  elapsed_s: number | null;
  duration_s: number;
  context: { rpm: number | null; ias_kt: number | null; oil_nan_frac: number | null; co_alerts: string[] };
  not_lane_check_reason?: NotLaneCheckReason;
  lane_check_band?: { rpm: number; tolerance: number };
}

export interface ExceedanceEvent {
  source?: "limit"; // absent on analyses written before engine 0.29
  param: string;
  label: string;
  unit: string;
  severity: string;
  limit_type: "MIN" | "MAX";
  limit_value: number;
  observed_value: number;
  start_utc: string | null;
  elapsed_s: number;
  duration_s: number;
  note?: string;
  // Spec 09 §11.1 — absent on analyses written before engine 0.17.
  limit_id?: string | null;
  event_id?: string;
  excess?: number | null;
}

// Spec 09: one entry of the engine profile's limit catalogue, carried on
// FlightAnalysis.limits.
export interface LimitDef {
  // A CAS target's pseudo entry (Spec 09 v0.18): kind "cas", no limit value.
  kind?: "cas";
  cas_id?: string;
  id: string;
  param: string;
  label: string;
  unit: string;
  limit_type: "MIN" | "MAX";
  limit_value: number;
  severity: string;
  report_in_exceedances?: boolean;
  stratify_by?: string | null;
  filter_policy?: Record<string, unknown>;
  close_call_margin_s?: number;
  min_rpm?: number | null;
  // Spec 14 §5 Engine tab — phase-aware suppression, read-only display only.
  phases?: string[] | null;
  min_duration_s?: number | null;
  min_duration_by_phase?: Record<string, number> | null;
  requires_reached_since_start?: boolean;
  note?: string;
}

// Spec 14 §5 Engine tab.
export interface EngineLimitsResult {
  engine: { id: string; engine: string; variant?: string | null; om_reference?: string | null; source_status: string };
  limits: LimitDef[];
  // Spec 14 v0.13 §5: the engine version in effect.
  engine_version?: string;
  // Spec 14 §5.1 Stratification panel — research-paper §9 constants.
  band_edges: { da_band: { min: number; max: number; name: string }[]; oat_band: { min: number; max: number; name: string }[] };
}

export interface Provenance {
  engine_version: string;
  schema_version: string;
  engine_profile: { id: string; hash: string; source_status: string };
  params_hash: string;
  source_keys: string[];
  rules_hash?: string;
  // Spec 01 v0.23 §6.5: general-purpose channels exposed under a registry id.
  channel_assignments?: Record<string, string>;
}

export interface FlightAnalysis {
  flight_id: string;
  analysis_key: string;
  source_keys: string[];
  header: {
    date: string;
    start_utc: string | null;
    engine_hours_start: number | null;
    engine_hours_end: number | null;
    airport_hint: string | null;
    aircraft: { ident: string | null; system_id: string | null };
  };
  phases: Phase[];
  metrics: Record<string, MetricValue>;
  exceedances: FlightEvent[];
  cas_events: unknown[];
  // Spec 01 §8.6: the classifier's full output, every class — the CAS
  // event's expanded view lists it for research.
  ecu_runs: EcuRunRecord[];
  ecu_sub_threshold_blips?: number;
  ecu_lane_check?: "both" | "single" | "none";
  quality: Diagnostic[];
  provenance: Provenance;
  available_channels: string[];
  limits?: LimitDef[];
  // Spec 08 v0.3 §6 (Spec 10 D4): fleet-dependent context flag, set by
  // evaluate_insights() from FleetAnalysis.cylinder_balance — not present
  // (treat as false) on analyses written before Spec 10 Phase A.
  hot_cyl_changed?: boolean;
}

export type Evidence =
  | { kind: "metric"; metric_id: string }
  | { kind: "baseline_point"; metric_id: string; flight_id: string }
  | { kind: "series_window"; channels: string[]; start_s: number; end_s: number; marker_start_s?: number; marker_end_s?: number }
  | { kind: "exceedance" | "cas_event"; ref: string };

// comparison (Spec 01 §8.4 v0.13, R8): only baseline_deviation insights
// carry one — which leave-one-out baseline the flight was actually
// compared against, its own weather band or the whole fleet (fallback
// below n_min). The insight text already names it; this is for a future
// consumer that wants it structured rather than parsed out of the text.
export interface InsightMessage {
  text: string;
  values?: { comparison?: { scope: "band" | "all"; band?: string | null; n: number } };
}

export interface Insight {
  id: string;
  topic_id: string;
  rule_id: string;
  trigger: "threshold" | "baseline_deviation" | "trend";
  severity: InsightSeverity;
  message: InsightMessage;
  evidence: Evidence[];
  confidence: { level: string; n: number };
  note?: string;
  // Spec 09 §10.1/§11.3 — limit_exceedances insights: one per target per
  // flight (a limit, or from v0.18 a classified CAS alert), carrying its
  // events (evidence[i] is events[i]'s window).
  source?: "limit" | "cas";
  limit_id?: string;
  cas_id?: string;
  filter?: { filter_id: string; outcome: "suppressed" | "breach" };
  events?: (InsightEvent | CasInsightEvent)[];
  // Spec 09 §6.3: false when this limit can't be filtered (the editor says why).
  filterable?: boolean;
}

// A CAS event as carried on its limit_exceedances insight — no observed
// value or excess (Spec 01 v0.21).
export interface CasInsightEvent {
  event_id: string;
  start_utc?: string;
  elapsed_s: number | null;
  duration_s: number;
  classification: "GROUND" | "IN_FLIGHT";
  phase: string;
  phase_uncertain: boolean;
  rpm?: number | null;
  not_lane_check_reason?: NotLaneCheckReason;
  lane_check_band?: { rpm: number; tolerance: number };
  suppressed_by: "duration" | null;
}

export function isCasInsightEvent(e: InsightEvent | CasInsightEvent): e is CasInsightEvent {
  return "classification" in e;
}

export interface InsightEvent {
  event_id: string;
  start_utc?: string;
  elapsed_s: number | null;
  duration_s: number;
  observed_value: number;
  excess: number | null;
  // Spec 09 §11.3: the condition that tolerates it — phase, then
  // magnitude, then duration (v0.21).
  suppressed_by: "phase" | "duration" | "magnitude" | null;
  phases?: string[]; // v0.20: the phases the event's rows lie in, in order
}

// Spec 14 §7.3 — one entry per configured trigger on a topic, whether or
// not it fired this flight, for the topic card's triggers disclosure.
// `met` is null when there isn't enough data to evaluate at all (distinct
// from false = evaluated and not met).
export interface TriggerStatus {
  type: "threshold" | "baseline_deviation" | "trend";
  met: boolean | null;
  detail: string | null;
}

export interface TopicResult {
  topic_id: string;
  analysis: { text: string };
  insights: Insight[];
  metric_ids: string[];
  // Spec 10 §4.1 (Spec 01 §8.5): the rule's limit_refs, each resolved to
  // this flight's limit_exceedances insight for that limit, or null if
  // none fired. Drives the mirrored badge (Spec 03 §5.2); never an
  // insight of its own.
  // engine_ecu_inflight's references name its CAS alert instead (v0.21).
  limit_refs?: { limit_id?: string; cas_id?: string; insight_id: string | null }[];
  // Spec 14 §7.3 — the topic's enabled flag from rules/active.json and
  // its triggers' met/detail status, for the topic card's disclosure.
  enabled?: boolean;
  trigger_status?: TriggerStatus[];
}

export interface InsightSet {
  flight_id: string;
  analysis_key: string;
  fleet_key: string;
  rules_hash: string;
  topics: TopicResult[];
  header_warnings: Diagnostic[];
  provenance: Provenance;
}

// ── RuleSet (insight_rules.json / workspace rules/active.json) ──────────────
// z_score_threshold deliberately isn't a field here (Spec 01 §8.4 v0.8) —
// baseline_deviation's threshold is BaselineConfig's outlier_z_threshold,
// resolved server-side and injected before evaluate_insights runs, so a
// rule editor never edits two numbers that claim to mean the same thing.
export interface RuleTrigger {
  type: "threshold" | "baseline_deviation" | "trend";
  severity?: InsightSeverity;
  // Legacy (rules < 1.3): a bare number. Rules 1.3 (Spec 09 §10.2) name
  // the profile limit instead, so the threshold always follows the OM.
  limit?: number;
  limit_ref?: string;
  unit?: string;
  condition?: string;
  // map_at_takeoff's vs_personal_model condition (Spec 10 D5): z times
  // the leave-one-out fit's residual standard error, not a fixed band.
  z?: number;
  n_min?: number;
  // "either" (Spec 08 §6) fires on a clear trend in both directions.
  direction?: TrendDirection;
  r2_min?: number;
  // cylinder_rank's hot_cyl_changed condition (Spec 08 §6).
  margin_min_f?: number;
  consecutive_flights?: number;
}

export type TrendDirection = "increasing" | "decreasing" | "either";

export interface RuleTopic {
  enabled: boolean;
  // Spec 08 v0.3 §6 (Spec 10 D4): cylinder_rank ships with no triggers at
  // all — context only, nothing to fire — so this is optional, not a
  // guaranteed array.
  triggers?: RuleTrigger[];
  // applies_to (Spec 08 §6): one rule block shared by several fleet metric ids.
  applies_to?: string[];
  _comment?: string;
  // cylinder_rank's own margin/consecutive-flight settings (Spec 08 §6) —
  // top-level now, not nested in a trigger; the rule playground still
  // edits them even though the topic itself emits nothing.
  margin_min_f?: number;
  consecutive_flights?: number;
  // Spec 10 §4.1 (Spec 09 §10.2): oil_temp_peak / coolant_temp_peak /
  // overboost_time declare the limit(s) they mirror here, never as a
  // trigger of their own.
  limit_refs?: string[];
}

export interface RuleSet {
  version: string;
  rules: Record<string, RuleTopic>;
}

// Spec 01 §8.8: topic help. `values` is keyed by the literal placeholder
// text ("{limit:oil_temp_max}") so the UI can re-format each value in the
// pilot's units (Spec 02 §6.6) without re-parsing `template`.
export interface TopicHelp {
  id: string;
  title: string;
  template: string;
  values: Record<string, { value: number | string; unit: string | null }>;
  text: string;
  applies: boolean;
  validated: boolean;
  last_reviewed: string;
}

export interface TopicHelpResult {
  topics: TopicHelp[];
  diagnostics: Diagnostic[];
}

// Spec 02 v0.8 §5.6/§6.6: distinct aircraft across admitted flights,
// after aircraft_aliases grouping.
export interface AircraftSummary {
  idents: string[];
  raw_idents: string[];
  aliases: string[][];
}

export interface WorkspaceRulesResult {
  rules: RuleSet;
  shipped_rules: RuleSet;
  // Spec 14 §5.1 (v0.6): topics with a Flight view card, enabled or not.
  card_topic_ids: string[];
}

export interface WhatIfResult {
  flights: Record<string, { before: InsightSet; after: InsightSet }>;
}

export interface FleetMetricPoint {
  flight_id: string;
  date: string;
  x: number;
  value: number;
  // Sparse — only set when this metric has a band_kind and this flight's
  // own reading fell in a defined band (Spec 01 §8.4 v0.10). Determines
  // which stratified region a point draws in when Trends' "Stratify by"
  // toggle (Spec 03 §5.3 v0.10) is on.
  band?: string;
}

export interface FleetMetricTrend {
  n: number;
  slope: number | null;
  r_squared: number | null;
  direction: "increasing" | "decreasing" | "flat" | "insufficient_data";
  x: string;
  confidence: { level: string; n: number };
}

export interface FleetMetricBand {
  n: number;
  mean: number | null;
  std: number | null;
  min: number | null;
  max: number | null;
  confidence: { level: string; n: number };
}

// A per-band entry under by_band.bands — the same baseline shape, plus
// its own trend (gated by the same n_min as the unstratified one, Spec
// 03 §5.3 v0.10), absent when that band didn't clear trend()'s own n>0,
// and its own outliers (against that band's own all-flights baseline,
// same threshold — Spec 01 R8/Spec 03 §5.3 v0.11) so the stratified
// view's rings agree with baseline_deviation's within-band comparison.
export interface FleetBandStats extends FleetMetricBand {
  trend?: FleetMetricTrend;
  outliers: { flight_id: string; z_score: number }[];
}

// Spec 12 §5/§11.2 — absent below n_min or with no recent window.
export interface Shift {
  recent: { flight_ids: string[]; n: number; hours_from: number; hours_to: number; mean: number };
  reference: {
    kind: "rolling" | "pinned";
    n: number;
    hours_from: number | null;
    hours_to: number | null;
    label?: string;
    // Spec 12 §5.7.1 (Session D) — when the reference was pinned (ISO
    // 8601); the pin marker/badge's date fallback when no label was given.
    set_at?: string;
  } & FleetMetricBand & { by_band?: Record<string, FleetMetricBand> };
  shift_z: number | null; // null when comparison.scope === "insufficient"
  direction: "higher" | "lower" | "none";
  comparison: {
    scope: "band" | "all" | "mixed" | "insufficient";
    by_band?: Record<string, number>;
    unmatched: number;
  };
  bend?: { reference_slope: number; recent_slope: number; fires: boolean };
  level: {
    om_margin: boolean;
    filter_edge: boolean;
    limit?: number;
    margin_line?: number;
    // Session B: the resolved filter-band edge, in this metric's own
    // units — the boolean alone isn't enough to draw the line (§8.3).
    filter_edge_value?: number;
  };
  qualifies: boolean;
  // Spec 12 §11.7 (Session C) — a per-limit metric's unit, mirrored
  // from FleetMetric.unit onto its own Shift.
  unit?: string;
}

// Spec 12 §5.8/§11.7 (Session C) — event frequency, the primary
// limit-panel signal. Lives on the metric entry itself (not nested in
// Shift) so it's present even when the metric has no shift at all (the
// "rare" badge: peak_excess's own window can't form, but frequency —
// computed from the limit's full-coverage metric — still can).
export interface Frequency {
  recent: { events: number; flights: number };
  reference: { events: number; flights: number };
  delta: number | null;
  z: number | null;
  qualifies: boolean;
}

// Spec 12 §9.3 (Session C, extended Session D) — the fixed readiness-
// badge set, entirely engine-computed so the web never infers one from
// raw numbers. Present on a metric wherever a badge should show instead
// of its normal shift/trend. A badged metric is excluded from
// change_summary ranking EXCEPT *filtered* and *pinned* (v0.5 §9.3) —
// those describe a pilot choice, not a data limitation.
export interface Readiness {
  kind: "filtered" | "building" | "no_recent" | "no_events" | "rare" | "insufficient" | "pinned";
  count?: number;
  // Spec 12 §5.7.1 (Session D) — the *pinned* badge's text only: the
  // user's own label, or the pin date formatted short ("12 Oct").
  label?: string;
}

// preview_clear_reference (Spec 12 §5.7.1 item 5, Session D) — the
// unpin confirmation's prediction, computed by rebuilding the fleet
// with the pin hypothetically removed, nothing persisted.
export interface UnpinPreview {
  currently_in_summary: boolean;
  would_be_in_summary: boolean;
  changes: boolean;
}

// Spec 12 §8.4/§11.7 (Session C) — one tick per eligible flight, for
// the event strip on a limit panel (and overboost_time).
export interface EventTick {
  flight_id: string;
  date: string;
  x: number | null;
  has_event: boolean;
  // Spec 12 v0.10 §8.4: on a CAS alert's metric, the flight's events for
  // the tick tooltip.
  cas_events?: { classification: "GROUND" | "IN_FLIGHT"; phase: string; duration_s: number; not_lane_check_reason?: NotLaneCheckReason }[];
}

export interface FleetMetric {
  metric_id: string;
  baseline: FleetMetricBand;
  trend: FleetMetricTrend | null;
  points: FleetMetricPoint[];
  outliers: { flight_id: string; z_score: number }[];
  by_band?: { band_kind: string; bands: Record<string, FleetBandStats> };
  // Spec 12 §5/§11.2 (Session A).
  shift?: Shift;
  // Spec 12 §11.7 (Session C) — per-limit metrics only (and
  // overboost_time, which borrows the s unit from its own limit panel).
  unit?: string;
  frequency?: Frequency;
  events?: EventTick[];
  readiness?: Readiness;
}

// Spec 12 §7/§11.2 — engine-computed ordering over metrics[*].shift.
// §7.1/D4 (Session B): a coupled panel collapses to one row — metric_id
// is the lead (largest |shift_z|) member; panel/members present only
// for such a row.
export interface ChangeSummaryRow {
  metric_id: string;
  rank: number;
  panel?: string;
  members?: string[];
}

// Spec 12 §6 — shift_history.json. §7.1/D4 (Session B): a coupled event
// additionally carries panel/members/member_detail (one event for the
// whole panel, not one per member).
export interface ShiftEvent {
  id: string;
  metric_id: string;
  detected_at: string;
  cleared_at?: string;
  cleared_engine_hours?: number | null;
  // Spec 12 §5.7.1 (Session D) — set only when an unpin directly closed
  // this event, so the history doesn't read as the engine recovering.
  cleared_by?: "unpin";
  kind: "shift" | "om_margin" | "filter_edge" | "frequency";
  window: { flight_ids: string[]; hours_from: number; hours_to: number };
  shift_z: number | null;
  direction: "higher" | "lower" | "none";
  comparison: Shift["comparison"];
  reference: { kind: "rolling" | "pinned"; n: number; hours_from: number | null; hours_to: number | null };
  // Spec 12 §5.8/§11.7 (Session C) — present when this event's metric
  // carries one, a snapshot at open time (same shape as FleetMetric.frequency).
  frequency?: Frequency;
  panel?: string;
  members?: string[];
  member_detail?: Record<string, { shift_z: number | null; direction: "higher" | "lower" | "none" }>;
}

// Spec 10 §5.1 (docs/specs/topics/register.json) — the register's
// `trends` field per topic, read by the web for panel layout and
// phrasing (Spec 12 §8.1). Per-limit metrics have no register entry;
// their panel/worsening derive from the limit (engine side).
export interface TrendsDeclaration {
  panel: string | null;
  coupled?: boolean;
  role: "primary" | "context";
  phrasing: { higher: string; lower: string };
  worsening: "higher" | "lower" | "either";
}

// get_trends_panels (Session A/B) — the engine-built panel layout, so
// the web never hand-lists metrics/panels itself (Spec 12 D3/R3.3).
// phrasing/worsening come straight from the register (or a generic
// default for a generated limit panel, R3.2) — the web never reads
// register.json directly.
export interface TrendsPanel {
  panel: string; // "cylinder_balance" | "thermal" | "boost_power" | "fuel" | "limit:<id>" | "cas:<cas_id>"
  limit_id?: string; // present only for a generated "limit:<id>" panel
  cas_id?: string; // present only for a generated "cas:<cas_id>" panel (Spec 12 v0.10)
  filtered?: boolean;
  filter_max_event_s?: number; // CAS panel with a duration filter: shown as a header note

  metrics: {
    metric_id: string;
    role: "primary" | "context";
    worsening: "higher" | "lower" | "either";
    phrasing: { higher: string; lower: string } | null;
  }[];
}

// Spec 01 §8.4 v0.8 — outlier_z_threshold (resolved per metric as
// overrides[metric_id] ?? outlier_z_threshold) is the one value behind
// both FleetMetric.outliers and evaluate_insights's baseline_deviation
// trigger. Edited in the rule playground (Spec 03 §5.5), persisted via
// save_baseline_config — the other half of the playground's "one editor,
// two documents" (the other being RuleSet/rules/active.json, below).
export interface BaselineConfig {
  membership: "leave_one_out" | "all";
  band_kind_by_metric: Record<string, "oat_band" | "da_band" | null>;
  outlier_z_threshold: number;
  outlier_z_threshold_overrides?: Record<string, number>;
  // Spec 12 §11.1 (Session A) — Baselines & Models window/margin fields.
  recent_window_hours: number; // default 10
  recent_window_min_flights: number; // default 5
  recent_window_max_flights: number; // default 15
  om_margin_fraction: number; // default 0.25
  // metric_id -> frozen reference membership (Spec 12 §5.7).
  pinned_references?: Record<string, { flight_ids: string[]; set_at: string; label?: string }>;
}

// Not the same shape as FlightAnalysis.provenance (no engine_profile/
// params_hash here — a real inconsistency, see BACKLOG/Spec 01 notes).
export interface FleetProvenance {
  engine_version: string;
  schema_version: string;
  source_keys: string[];
  flight_analysis_keys: string[];
  baseline_config: BaselineConfig;
}

// Spec 08 §5 — each flight's hottest cylinder, and the aircraft's usual one:
// "learned" from its own flights, else the engine profile's "prior", else "none".
export interface HotCylinderPoint {
  flight_id: string;
  date: string;
  x: number | null;
  hottest_cyl: number;
  margin_f: number | null;
  rank_order: number[] | null;
  // Spec 08 v0.3 §6 (Spec 10 D4): context flag, not an insight.
  hot_cyl_changed: boolean;
}

export interface CylinderBalance {
  margin_min_f: number;
  expected_hot_cyl: number | null;
  established_hot_cyl: { cyl: number | null; share: number | null; n: number; source: "learned" | "prior" | "none" };
  points: HotCylinderPoint[];
}

export interface FleetAnalysis {
  fleet_key: string;
  flight_ids: string[];
  excluded: { flight_id: string; reason: string }[];
  metrics: Record<string, FleetMetric>;
  models: {
    id: string; n: number; r_squared: number;
    residual_se?: number | null; confidence?: { level: string; n: number }; capture?: string;
    [key: string]: unknown;
  }[];
  quality: Diagnostic[];
  provenance: FleetProvenance;
  // Optional: fleet results written before Spec 08 don't carry it.
  cylinder_balance?: CylinderBalance;
  // Spec 12 §7/§11.2 (Session A) and §6 (Phase 2) — defaults to [] on
  // fleet results written before Spec 12.
  change_summary: ChangeSummaryRow[];
  shift_history: ShiftEvent[];
}

// ── ECU (Spec 01 §8.6) ───────────────────────────────────────────────────────

// Spec 01 §8.6 (v0.19): by the flight phase the run overlaps.
export type EcuClassification = "GROUND_START" | "LANE_CHECK" | "GROUND" | "IN_FLIGHT" | "GROUND_SHUTDOWN";
export type EcuCounts = Record<EcuClassification, number>;

// One FlightAnalysis.ecu_runs entry (Spec 01 §8.6) — the classifier's
// full output, shown in a CAS event's expanded view for research.
export interface EcuRunRecord {
  classification: EcuClassification;
  phase: string;
  phase_uncertain: boolean;
  start_utc: string | null;
  end_utc: string | null;
  elapsed_s: number | null;
  duration_s: number;
  co_alerts: string[];
  oil_nan_frac: number | null;
  lane_check_pair: boolean;
  lane_check_note: string;
  mean_rpm: number | null;
  mean_ias_kt: number | null;
}

// ── Annotations (Spec 02 §6.5) ────────────────────────────────────────────────

export type AnnotationRef =
  | { kind: "insight"; insight_id: string }
  | { kind: "exceedance" | "ecu_run" | "cas_event"; ref: string }; // ecu_run: notes made in the retired ECU view

export interface Annotation {
  id: string;
  flight_id: string;
  ref: AnnotationRef;
  note: string;
  created_at: string;
  updated_at?: string;
}

export interface AnnotationStore {
  version: string;
  annotations: Annotation[];
}

// ── Chart channels and presets (Spec 07) ──────────────────────────────────────

export interface ChannelRegistryEntry {
  id: string;
  unit: string | null;
  description: string;
  label: string;
  group: string;
  slot_group: string | null;
  companions: string[];
  unit_variant_of: string | null;
}

export interface SlotGroupEntry {
  id: string;
  label: string;
  members: string[];
}

export interface ChannelRegistry {
  channels: ChannelRegistryEntry[];
  slot_groups: SlotGroupEntry[];
  max_chart_slots: number;
}

export interface ChartPreset {
  id: string;
  label: string;
  description: string;
  channels: string[];
}

export interface ChartPresetsResult {
  presets: ChartPreset[];
  diagnostics: Diagnostic[];
  max_chart_slots: number;
}

// ── Workspace (Spec 02 v0.5 §5-6) ─────────────────────────────────────────────

export interface WorkspaceRegistryEntry {
  id: string;
  name: string;
  engine_model: string;
  primary_tail_number?: string;
  created_at: string;
  last_opened_at: string;
  log_folder_count: number;
  flight_count: number;
}

export interface WorkspaceRegistry {
  version: string;
  workspaces: WorkspaceRegistryEntry[];
}

export interface LogFolder {
  path: string;
  reachable: boolean;
  last_scanned_at?: string;
  // Spec 02 §6.1: a folder the page holds (browser host), keyed by this.
  folder_id?: string;
}

export interface WorkspaceManifest {
  id: string;
  name: string;
  engine_model: string;
  primary_tail_number?: string;
  log_folders: LogFolder[];
  schema_version: string;
  created_at: string;
  updated_at: string;
  engine_version_seen: string[];
  flight_count: number;
  storage_backend: "filesystem" | "indexeddb";
}

export interface AppSettings {
  units: "imperial" | "metric";
  last_active_workspace_id: string | null;
  chart_presets: ChartPreset[];
  // phase_filter: null (default) shows insights from every phase; an
  // array restricts the Insights panel to insights with evidence/events
  // landing in one of those phases. Global, like last_preset_id — not
  // scoped per-flight or per-workspace, so it carries across both.
  flight_chart: { last_preset_id?: string; phase_filter?: string[] | null };
}

export interface WorkspaceSettings {
  // anonymize_by_default retired (Spec 02 v0.11 §6.6): anonymising is a
  // per-export choice.
  active_engine_profile: string;
  last_view?: { kind: string; flight_id?: string };
  // Spec 02 v0.8 §5.6/§6.6: groups of aircraft_ident values the pilot
  // confirmed are one aircraft, e.g. [["N117ZS", "N117Z"]].
  aircraft_aliases?: string[][];
  // Spec 12 §8.4/§8.3 (Session F) — per-panel "Show detail strips"
  // state (panel id -> on/off), replacing the page-level researcher
  // toggle. Decision (see report): workspace settings, not app
  // settings — §8.4's own wording is "remembered per workspace", and
  // this is the one place already round-tripped through the local
  // server scoped to exactly one workspace.
  trends_detail_strips?: Record<string, boolean>;
}

// Spec 14 v0.13 §5 — a results-affecting setting that differs from
// shipped (there is no Settings changelog). Settings marks it with the
// shipped value and links to its Journal entry.
export interface ChangedSetting {
  // "outlier_z_threshold", "recent_window", "om_margin_fraction",
  // "outlier_z_threshold_overrides:<metric>", "band_kind_by_metric:<metric>", …
  ref_id: string;
  label: string;
  current: string;
  shipped: string;
  entry_id: string | null;
}

// Spec 14 §6.1 — the kinds of decision the Journal register holds.
export type JournalEntryKind =
  | "acknowledged_insight" | "limit_filter" | "disabled_topic" | "rule_edit" | "changed_setting"
  | "exclusion" | "reference_pin" | "annotation";

// Spec 14 §7.1 — the Flight view header's "Contributes to reference /
// Excluded from reference (reason)" state, and an open "reference
// changed" marker (acceptance 8) for a flight whose verdict moved
// because another flight was excluded.
export interface ReferenceState {
  excluded: boolean;
  reason: string | null;
}

export interface ReferenceChangeMarker {
  id: string;
  flight_id: string;
  at: string;
  cause_journal_entry_id: string;
  cause_kind: "exclusion" | "rule_edit";
  cause_flight_id: string | null;
  cause_topic_id: string | null;
  reason: string;
  resolved: boolean;
}

// Spec 14 v0.10 §6 — one entry per decision in force, keyed by its
// source record (ref_id); removed when the decision is reversed, updated
// in place when it is edited. effect / current / notices are computed by
// the server when the Journal is read, never stored.
export interface JournalEntry {
  id: string;
  kind: JournalEntryKind;
  ref_id: string;
  what: string;
  where?: Record<string, unknown> | null;
  reason?: string | null;
  note?: string | null;
  created_at: string;
  updated_at: string;
  // The live counted effect; zero is the "currently suppresses nothing" case.
  effect?: { text: string; zero: boolean } | null;
  // The decision's current values ("up to +1.5 psi", "trend.r2_min 0.3 (shipped 0.5)").
  current?: string | null;
  notices?: JournalNotice[];
}

export interface JournalNotice {
  kind: "drifting" | "breached" | "no_effect";
  text: string;
}

// ── Flights table (Spec 03 §5.1) — not a Spec 01/02 contract type itself; ────
// a UI-level projection combining FlightAnalysis, FlightSources (Spec 02
// §6.2), and FleetSelection (§6.3) into one row. A real host would build
// this client-side from those three; this fixture stands in for that join.

export type FlightRowStatus =
  | "analyzed"
  | "needs_analysis" // Spec 03 v0.17: found in a folder (or dropped), not analysed yet — no results
  | "needs_reanalysis"
  | "missing"
  | "folder_unreachable"
  | "ground_session"
  | "unreadable";

// A needs_analysis row has no results yet: flight_id, duration, insights
// and reference membership are null, the date comes from the file name,
// and source_key (a folder log) or upload_key (a dropped file waiting in
// the browser) says which log it is.
export interface FlightTableRow {
  flight_id: string | null;
  source_key?: string;
  upload_key?: string;
  date: string;
  airport: string;
  duration_min: number | null;
  engine_hours: number | null;
  insight_count: number | null;
  worst_severity: InsightSeverity | null;
  in_baselines: boolean | null;
  excluded_reason?: string;
  status: FlightRowStatus;
  // Spec 03 §5.1 "Unreadable": why the log couldn't be read or analysed.
  unreadable_reason?: string;
  // Spec 03 v0.22 §5.1: which export format the log is.
  source_format?: LogSourceFormat;
  different_tail_number?: string;
  filename: string;
  log_folder: string;
}

export interface FlightsTableFixture {
  rows: FlightTableRow[];
}

// ── Live server-only shapes (Spec 02 v0.5 §5-6, workspace management) ───────
// Not fixture types — these only exist once server.py's workspace ops are
// actually called; no fixture stands in for them (the fixture-driven views
// use FlightsTableFixture/WorkspaceManifest/etc. above instead).

export interface FleetSelectionResult {
  excluded: { flight_id: string; reason: string }[];
  baseline_config: { membership: string; band_kind_by_metric: Record<string, string | null> };
}

export interface ScanResult {
  new_flight_ids: string[];
  rematched_flight_ids: string[];
  now_missing_flight_ids: string[];
  recovered_flight_ids: string[];
  unreachable_folders: string[];
  excluded: { flight_id: string; reason: string }[];
  reanalyzed_flight_ids: string[];
  // Ground session / short flight / corrupt log, newly recorded to
  // exclusions.json this scan (Spec 02 §5.11) — keyed by filename,
  // never became a
  // flight_id at all, unlike `excluded` above (duplicate exports).
  auto_excluded: { filename: string; category: "ground_session" | "short_flight" | "corrupt_log" | "not_in_sender"; reason: string }[];
  // Spec 03 v0.17 §5.1 — waiting for the pilot's go-ahead after a scan that
  // deferred (or restricted) analysis.
  pending_new_logs?: { source_key: string; log_folder: string; relative_path: string; filename: string; date: string | null }[];
  // Spec 03 §5.1 "Unreadable": logs this scan couldn't read or analyse.
  unreadable?: { filename: string; reason: string }[];
  pending_reanalysis_flight_ids?: string[];
}

// Spec 03 v0.17: Sync runs { analyze: false } (discovery only) and asks;
// Analyze runs everything, or just the given logs / flights.
export interface ScanOptions {
  analyze?: boolean;
  source_keys?: string[];
  flight_ids?: string[];
}

// Polled by the Sync button while a scan_workspace call is in flight
// (op_get_scan_progress) — a large initial sync can take minutes, so
// this is what turns "Syncing…" into "Analyzing 42 of 210 — <filename>".
// Spec 02 v0.10 §5.8.1 / Spec 14 v0.12 §5.2 — where the data root lives.
export type DataLocationSource = "environment" | "chosen" | "default";

export interface DataLocation {
  path: string;
  source: DataLocationSource;
  missing: boolean;
  workspace_count: number | null;
  default_path: string;
  env_var: string;
}

// What choosing a folder would do, before anything happens. start_fresh:
// an empty folder while the current location is missing (nothing to move).
export interface DataLocationAssessment {
  action: "move" | "use_existing" | "start_fresh" | "refused";
  path: string;
  workspace_count: number | null;
  bytes: number | null;
  reason: string | null;
  code: string | null;
}

export interface DataLocationChange {
  action: "move" | "use_existing" | "start_fresh";
  path: string;
  previous_path: string | null;
  location: DataLocation;
}

export interface DataLocationProgress {
  active: boolean;
  phase?: "starting" | "copying" | "checking";
  done?: number;
  total?: number;
}

export interface ScanProgress {
  active: boolean;
  phase?: "starting" | "reading" | "analyzing" | "reanalyzing";
  current?: number;
  total?: number;
  filename?: string;
  analysed?: number;   // of those, how many needed (re-)analysis so far (Spec 04 D9)
}

// Spec 02 §6.8 — a file that never became a
// flight_id at all (ground_session/short_flight/corrupt_log, auto; or
// user_defined). Distinct from FlightTableRow.excluded_reason, which is
// for a flight that WAS analyzed and is just held out of baselines.
export interface ExclusionEntry {
  filename: string;
  source: "auto" | "user";
  reason: string;
  // not_in_sender (Spec 02 v0.11 §7.5): an imported workspace holds out a
  // log whose flight isn't in the sender's workspace, until included.
  category: "ground_session" | "short_flight" | "corrupt_log" | "user_defined" | "not_in_sender";
  excluded_at: string;
  user_override: boolean;
  override_reason?: string;
  // Only present when listExclusions() was called with enrich=true — the
  // source file was re-located and re-parsed for this (not stored in
  // exclusions.json itself), so it's opt-in, not on every refresh().
  date?: string;
  duration_min?: number;
  airborne_min?: number;
  aircraft_ident?: string;
}

export interface ExclusionsResult {
  entries: ExclusionEntry[];
  summary: {
    ground_session: number;
    short_flight: number;
    corrupt_log: number;
    user_defined: number;
    not_in_sender?: number;
    overridden: number;
  };
  // Spec 02 v0.11 §7.5: an imported workspace's flights whose log hasn't
  // been found here; no actions — each resolves when its log is added.
  sender_missing?: SenderMissingFlight[];
}

// ── Host capabilities (Spec 04 v0.4 §9.5) ───────────────────────────────────

// What the host the UI talks to can do. The UI gates on `features`, never
// on `host`.
export interface HostCapabilities {
  host: "server" | "browser";
  engine_version: string;
  host_version: string;
  features: {
    data_location: boolean;
    add_folder_by_path: boolean;
    choose_folder: boolean;
    persistent_storage_status: boolean;
    download_url: boolean;
    folder_watching: boolean;
  };
}

// Spec 14 v0.16 §5.2.1 — the data root's size, measured by the host.
export interface StorageUsage {
  total_bytes: number;
  other_bytes: number;
  workspace_count: number;
  workspaces: { id: string; name: string; bytes: number }[];
}

// ── Log sources (Spec 01 v0.23 §6.5) ─────────────────────────────────────────

export type LogSourceFormat = "g3x_direct" | "garmin_pilot" | "axis" | "unknown";

// Spec 14 v0.14 §5.3 — a raw general-purpose channel seen in the workspace's
// logs, and its assignment to a registry channel (none by default).
export interface LogChannelRow {
  raw: string;            // "gp_analog_7"
  label: string;          // "analog 7"
  sources: string[];      // ["AXIS"]
  flights: number;
  min: number | null;
  max: number | null;
  assignment: { channel: string; name: string; unit: string | null } | null;
  options: { channel: string; name: string; unit: string | null }[];
}

// ── Workspace export and import (Spec 02 v0.11 §7) ──────────────────────────

export interface SenderMissingFlight {
  flight_id: string;
  date: string | null;
  airport_hint: string | null;
  sender_filename: string | null;
  reason: string;
}

export interface WorkspaceExportResult {
  filename: string;
  flights: number;
  logs_included: number;
  anonymised: boolean;
  download_url: string;
  size: number;
  notes: string[];
  documents: { path: string; class: string; note: string }[];
}

export interface WorkspaceExportSummary {
  workspace_name: string;
  engine_model: string;
  engine_version: string;
  exported_at: string;
  flight_count: number;
  date_range: [string, string] | null;
  carries: {
    filters: number; phase_filters: number; rule_edits: number; disabled_topics: number;
    reference_exclusions: number; pins: number; changed_settings: number; notes: number; journal_entries: number;
  };
  logs_included: boolean;
  anonymised: boolean;
  // Set when an unzipped export folder with logs/ was chosen (CLI).
  logs_folder: string | null;
  // Spec 02 v0.14: how many logs the chosen export zip carries; 0 means
  // the new workspace starts empty.
  logs_in_file: number;
  engine_check: { status: "same" | "newer" | "older"; ok: boolean; message: string | null };
}

// An export chosen in the import flow: an uploaded .eisworkspace, or (local
// server) a path to the file or to the folder an export zip unzips to.
// Spec 02 v0.14: in the app, the chosen file is sent to /upload as is and
// referred to by upload_id.
export type WorkspaceExportSource = { upload_id: string } | { path: string } | { content_base64: string; filename: string };

export interface ImportMatchResult {
  total: number;
  found: { flight_id: string; filename: string | null; date: string | null }[];
  missing: SenderMissingFlight[];
  extra: { filename: string; date: string | null }[];
}

export interface ImportInfo {
  imported: boolean;
  provenance?: { workspace_name: string; engine_version: string; exported_at: string; logs_included: boolean; anonymised: boolean };
  flights?: { flight_id: string; date: string | null; airport_hint: string | null; duration_min: number | null;
              sender_filename: string | null; found: boolean }[];
}

export interface ActiveWorkspace {
  active: boolean;
  workspace_dir?: string; // present when active === false (legacy/no-registry-workspace mode)
  manifest?: WorkspaceManifest;
  registry_entry?: WorkspaceRegistryEntry | null;
  settings?: WorkspaceSettings;
  diagnostic?: { code: string; severity: string; message: string } | null;
}

// ── Fixture-specific shapes (not Spec 01 contract types) ────────────────────

export interface RuleOverboostFixture {
  rule_id: string;
  trigger: string;
  shipped_default: { limit: number; severity: InsightSeverity };
  flights: { flight_id: string; date: string; engine_hours: number; overboost_total_s: number }[];
}

export interface SeriesChannel {
  unit: string;
  label: string;
  points: (number | null)[][]; // [elapsed_s, value][]
}

export interface SeriesFixture {
  flight_id: string;
  channels: Record<string, SeriesChannel>;
}

// ── Limit filters (Spec 09 §9, §11) ─────────────────────────────────────────

export type FilterMagnitudeMode = "absolute" | "percent" | "z";

// Spec 09 v0.18 §4: what a filter attaches to.
export type FilterTarget = { kind: "limit"; limit_id: string } | { kind: "cas"; cas_id: string };

export function targetKey(t: FilterTarget): string {
  return t.kind === "cas" ? `cas:${t.cas_id}` : t.limit_id;
}

// How a target is named to the pilot: a CAS target is "ENGINE ECU (alert)"
// so it isn't mistaken for an OM limit (Spec 09 v0.18, Spec 14 Journal).
export function targetLabel(t: FilterTarget, limitLabel?: string | null): string {
  return t.kind === "cas" ? `${t.cas_id} (alert)` : limitLabel ?? t.limit_id;
}

export interface LimitFilter {
  id: string;
  target: FilterTarget;
  magnitude?: { mode: FilterMagnitudeMode; value: number };
  duration?: { max_event_s: number };
  // Spec 09 v0.20 §7.5: excluded flight phases (detector names, never UNKNOWN).
  phases?: string[];
  note: string;
  created_from?: { flight_id: string; insight_id: string };
  copied_from?: { workspace_id: string; filter_id: string };
  reference: { flight_ids: string[]; set_at: string };
  created_at: string;
  created_engine_hours?: number;
  updated_at?: string;
  reviewed_at?: string;
  reviewed_engine_hours?: number;
  history: { at: string; action: "created" | "edited" | "rebaselined" | "reviewed"; before?: Partial<LimitFilter>; after?: Partial<LimitFilter> }[];
}

// What the filter editor sends: a new filter has no id and no reference yet.
export type LimitFilterDraft = Pick<LimitFilter, "target" | "magnitude" | "duration" | "phases" | "note" | "created_from"> & { id?: string };

// The detector's phases a filter may exclude, in the order a flight runs
// (Spec 09 v0.20 §12.1) — never UNKNOWN.
export const FILTER_PHASES = [
  "PRE_START", "ENGINE_START", "WARMUP", "TAXI", "TAKEOFF_ROLL", "CLIMB",
  "CRUISE", "DESCENT", "APPROACH", "LANDING_ROLL", "SHUTDOWN",
] as const;

export interface FilterPolicy {
  filterable: boolean;
  reason: string | null;
  severity: string;
  magnitude_modes: FilterMagnitudeMode[];
  duration_allowed: boolean;
  // Spec 09 v0.20 §6.3: may a filter on this limit exclude flight phases?
  phases_allowed?: boolean;
  max_band_abs: number | null;
  max_duration_s: number | null;
  note_required: boolean;
  review_interval_h: number;
}

export interface BaselineStats {
  n: number;
  mean?: number | null;
  std?: number | null;
  min?: number | null;
  max?: number | null;
}

export interface FilterProposal {
  target: FilterTarget;
  limit: LimitDef; // for a CAS target: its pseudo catalogue entry (kind "cas", duration-only policy)
  policy: FilterPolicy;
  // Filtering a limit exceeded on only a few reference flights is allowed
  // but not advisable; message says why, in pilot terms.
  advisory?: { advisable: boolean; flights_exceeded: number; flights_considered: number; message: string | null };
  live: {
    magnitude_metric?: string;
    magnitude?: BaselineStats;
    time_above_pct?: BaselineStats;
    share_with_events?: number | null;
    longest_event_s?: number | null; // CAS targets
  };
  suggested: { magnitude?: { mode: FilterMagnitudeMode; value: number }; duration?: { max_event_s: number } };
  reference: { flight_ids: string[]; n_with_events: number; collecting: boolean };
  z_available: boolean;
  z_n_min: number;
  existing: LimitFilter | null;
}

export interface FilterPreview {
  target: FilterTarget;
  valid: boolean;
  diagnostics: Diagnostic[];
  flights_considered: number;
  events_total: number;
  events_hidden: number;
  flights_affected: number;
  flights_with_breach: number;
  flights: {
    flight_id: string;
    date: string | null;
    events: number;
    suppressed: number;
    newly_suppressed: number;
    breaches: number;
    topic_insights_removed: { id: string; topic_id: string; text: string }[];
  }[];
  // Spec 09 v0.20 §12.1: for a phase condition, what it suppresses by
  // phase and what of this limit stays visible.
  phases?: {
    suppressed_by_phase: Record<string, { events: number; flights: number }>;
    visible_events: number;
    visible_by_phase: Record<string, number>;
    excludes_every_phase: boolean;
  } | null;
}

export interface FilterListEntry {
  filter: LimitFilter;
  limit: LimitDef | null;
  target_label: string;
  policy: FilterPolicy | null;
  valid: boolean;
  diagnostics: Diagnostic[];
  summary: string;
}

export type FilterStatus = "breached" | "drifting" | "review_due" | "quiet" | "collecting" | "stable";

// Spec 09 §11.3 FilterHealth. `peak_excess` (block_s for overboost) and
// `time_above_pct` are the §5 per-limit metrics for each included flight.
export interface FilterHealth {
  filter_id: string;
  target: FilterTarget;
  valid: boolean;
  status: FilterStatus;
  reasons: string[];
  diagnostics: Diagnostic[];
  summary?: string;
  resolved_band?: { value: number | null; unit: string } | null;
  reference?: { flight_ids: string[]; collecting: boolean };
  frozen_baseline?: {
    peak_excess?: BaselineStats & { by_band?: Record<string, BaselineStats> };
    block_s?: BaselineStats & { by_band?: Record<string, BaselineStats> };
    time_above_pct?: BaselineStats & { by_band?: Record<string, BaselineStats> };
    share_with_events: number | null;
  };
  series: {
    flight_id: string;
    date: string | null;
    engine_hours: number | null;
    band?: string | null;
    in_reference: boolean;
    monitored: boolean;
    peak_excess?: number | null;
    block_s?: number | null;
    time_above_pct?: number | null;
    events: number;
    suppressed: number;
    breaches: number;
    suppressed_by_phase?: number; // Spec 09 v0.20 §12.2
  }[];
  last_breach?: { flight_id: string; event_id: string | null };
  hours_since_review: number | null;
  // The numbers behind each Drifting reason, for a "details" tooltip; the
  // reasons themselves are written for pilots.
  drift_details?: {
    metric: string;
    values: number[];
    typical: number | null;
    std?: number | null;
    // null: above a reference with zero spread (no std devs to count)
    z?: (number | null)[];
    z_threshold?: number;
    comparison?: { scope: "band" | "all"; band: string | null; n: number };
    threshold_delta?: number;
    window?: number;
  }[];
}

export interface CopyFiltersResult {
  copied: { filter: LimitFilter; valid: boolean; diagnostics: Diagnostic[] }[];
  skipped: { target: FilterTarget; reason: string }[];
}
