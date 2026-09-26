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

export interface ExceedanceEvent {
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
  time_limit_s: number | null;
  note?: string;
}

export interface Provenance {
  engine_version: string;
  schema_version: string;
  engine_profile: { id: string; hash: string; source_status: string };
  params_hash: string;
  source_keys: string[];
  rules_hash?: string;
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
  exceedances: ExceedanceEvent[];
  cas_events: unknown[];
  ecu_runs: unknown[];
  quality: Diagnostic[];
  provenance: Provenance;
  available_channels: string[];
}

export type Evidence =
  | { kind: "metric"; metric_id: string }
  | { kind: "baseline_point"; metric_id: string; flight_id: string }
  | { kind: "series_window"; channels: string[]; start_s: number; end_s: number }
  | { kind: "exceedance" | "ecu_run"; ref: string };

export interface Insight {
  id: string;
  topic_id: string;
  rule_id: string;
  trigger: "threshold" | "baseline_deviation" | "trend";
  severity: InsightSeverity;
  message: { text: string };
  evidence: Evidence[];
  confidence: { level: string; n: number };
  note?: string;
}

export interface TopicResult {
  topic_id: string;
  analysis: { text: string };
  insights: Insight[];
  metric_ids: string[];
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
  limit?: number;
  unit?: string;
  condition?: string;
  tolerance_hpa?: number;
  n_min?: number;
  // "either" (Spec 08 §6) fires on a clear trend in both directions.
  direction?: TrendDirection;
  r2_min?: number;
  // cylinder_rank's hot_cyl_changed condition (Spec 08 §6).
  margin_min_f?: number;
  consecutive_flights?: number;
}

export type TrendDirection = "increasing" | "decreasing" | "either";

export interface RuleSet {
  version: string;
  // applies_to (Spec 08 §6): one rule block shared by several fleet metric ids.
  rules: Record<string, { enabled: boolean; triggers: RuleTrigger[]; applies_to?: string[]; _comment?: string }>;
}

export interface WorkspaceRulesResult {
  rules: RuleSet;
  shipped_rules: RuleSet;
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
// 03 §5.3 v0.10), absent when that band didn't clear trend()'s own n>0.
export interface FleetBandStats extends FleetMetricBand {
  trend?: FleetMetricTrend;
}

export interface FleetMetric {
  metric_id: string;
  baseline: FleetMetricBand;
  trend: FleetMetricTrend | null;
  points: FleetMetricPoint[];
  outliers: { flight_id: string; z_score: number }[];
  by_band?: { band_kind: string; bands: Record<string, FleetBandStats> };
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
  models: { id: string; n: number; r_squared: number; [key: string]: unknown }[];
  quality: Diagnostic[];
  provenance: FleetProvenance;
  // Optional: fleet results written before Spec 08 don't carry it.
  cylinder_balance?: CylinderBalance;
}

// ── ECU (Spec 01 §8.6) ───────────────────────────────────────────────────────

export type EcuClassification = "POWERUP" | "LANE_CHECK" | "SHUTDOWN" | "IN_FLIGHT";

export interface EcuRunContext {
  mean_rpm: number | null;
  mean_power_pct: number | null;
  mean_oil_press_psi: number | null;
  mean_oil_temp_f: number | null;
  mean_coolant_temp_f: number | null;
  mean_main_volts: number | null;
  mean_batt_amps: number | null;
  mean_fuel_press_psi: number | null;
  mean_ias_kt: number | null;
  mean_baro_alt_ft: number | null;
  oil_nan_frac: number | null;
}

export interface EcuRun {
  flight_id: string;
  start_utc: string | null;
  end_utc: string | null;
  duration_s: number;
  classification: EcuClassification;
  lane_check_pair: boolean;
  lane_check_note: string;
  co_alerts: string[];
  context: EcuRunContext;
}

export interface EcuInflightEvent {
  flight_id: string;
  start_time: string | null;
  duration_s: number;
  oil_nan_frac: number | null;
  co_alerts: string[];
  direct_correlation_alerts: string[];
}

// Matches analyze_ecu()'s real, schema-validated output shape exactly
// (contract/schema/ecu_analysis.schema.json) — an earlier draft of this
// type (fleet_key/run_counts/params_hash) never matched what the engine
// actually produces; this is the corrected version, not a redesign.
export interface EcuAnalysis {
  flight_ids: string[];
  runs: EcuRun[];
  counts: Record<string, number>;
  inflight_pattern: {
    events: EcuInflightEvent[];
    oil_nan_pattern: "strong" | "mixed" | null;
    recommended_actions: string[];
  };
  provenance: { engine_version: string; schema_version: string | null; source_keys: string[]; flight_analysis_keys: string[] };
}

// ── Annotations (Spec 02 §6.5) ────────────────────────────────────────────────

export type AnnotationRef =
  | { kind: "insight"; insight_id: string }
  | { kind: "exceedance" | "ecu_run" | "cas_event"; ref: string };

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
  flight_chart: { last_preset_id?: string };
}

export interface WorkspaceSettings {
  anonymize_by_default: boolean;
  active_engine_profile: string;
  last_view?: { kind: string; flight_id?: string };
}

// ── Flights table (Spec 03 §5.1) — not a Spec 01/02 contract type itself; ────
// a UI-level projection combining FlightAnalysis, FlightSources (Spec 02
// §6.2), and FleetSelection (§6.3) into one row. A real host would build
// this client-side from those three; this fixture stands in for that join.

export type FlightRowStatus =
  | "analyzed"
  | "needs_reanalysis"
  | "missing"
  | "folder_unreachable"
  | "ground_session"
  | "unreadable";

export interface FlightTableRow {
  flight_id: string;
  date: string;
  airport: string;
  duration_min: number;
  engine_hours: number | null;
  insight_count: number;
  worst_severity: InsightSeverity | null;
  in_baselines: boolean;
  excluded_reason?: string;
  status: FlightRowStatus;
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
