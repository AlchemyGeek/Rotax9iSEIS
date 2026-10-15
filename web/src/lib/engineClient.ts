import type { DataLocation, DataLocationAssessment, DataLocationChange, DataLocationProgress, ScanOptions } from "../types/contract";
import type {
  ActiveWorkspace,
  AircraftSummary,
  Annotation,
  AnnotationRef,
  AppSettings,
  BaselineConfig,
  ChannelRegistry,
  ChartPreset,
  ChartPresetsResult,
  CopyFiltersResult,
  Diagnostic,
  FilterTarget,
  EngineLimitsResult,
  ExclusionsResult,
  ChangedSetting,
  FleetAnalysis,
  FilterHealth,
  FilterListEntry,
  FilterPreview,
  FilterProposal,
  FleetSelectionResult,
  FlightAnalysis,
  JournalEntry,
  ReferenceChangeMarker,
  ReferenceState,
  LimitFilter,
  LimitFilterDraft,
  FlightTableRow,
  InsightSet,
  RuleSet,
  RuleTopic,
  ScanProgress,
  ScanResult,
  ShiftEvent,
  TopicHelpResult,
  TrendsPanel,
  UnpinPreview,
  WhatIfResult,
  WorkspaceManifest,
  WorkspaceRegistryEntry,
  WorkspaceRulesResult,
  WorkspaceSettings,
} from "../types/contract";
import { targetLabel } from "../types/contract";

// A server older than the Spec 09 v0.18 web (engine before the CAS-events
// change) names a filter's target with a top-level limit_id and no
// `target`. Read either shape, so a stale server can't crash a page.
function withTarget<T extends { target?: FilterTarget; limit_id?: string }>(x: T): T & { target: FilterTarget } {
  if (x.target) return x as T & { target: FilterTarget };
  return { ...x, target: { kind: "limit", limit_id: x.limit_id ?? "" } };
}

// Mirrors Spec 01 §7's operation envelope exactly — the same shape a
// future Pyodide Web Worker adapter will speak over postMessage instead
// of fetch (Spec 04 §9.1/§9.2): "all adapters expose the Spec 01
// operations through the same envelope, so the UI cannot tell them
// apart." This client interface is that seam.
export interface UploadFile {
  content: ArrayBuffer;
  filename: string;
}

export interface IngestResult {
  classification: "new" | "duplicate" | "ground_session" | "short_flight" | "corrupt_log";
  filename: string;
  reason?: string; // present for ground_session/short_flight/corrupt_log
  flight_id?: string; // present for new/duplicate
}

export interface ImportResult {
  results: IngestResult[];
  flight_count: number;
  fleet_key: string;
}

export interface FlightSummary {
  flight_id: string;
  header: FlightAnalysis["header"];
  quality: Diagnostic[];
  source_filename: string | null;
}

export interface SeriesResult {
  [channel: string]: [number, number | null][];
}

export interface EngineClient {
  listEngines(): Promise<{ id: string; engine: string; source_status: string; hash: string }[]>;
  getEngineLimits(): Promise<EngineLimitsResult>;
  // Spec 14 v0.13 §5 — settings that differ from shipped, each linked to
  // its Journal entry; reset one to shipped (from Settings or Journal).
  listChangedSettings(): Promise<{ settings: ChangedSetting[] }>;
  resetSetting(refId: string): Promise<FleetAnalysis>;
  getJournal(): Promise<{ entries: JournalEntry[] }>;
  getDefaultRules(): Promise<RuleSet>;
  ingestLog(file: UploadFile): Promise<IngestResult>;
  analyzeFlight(file: UploadFile, engine?: string): Promise<FlightAnalysis>;
  getSeries(file: UploadFile, channels: string[]): Promise<SeriesResult>;
  importFiles(files: UploadFile[], engine?: string): Promise<ImportResult>;
  listFlights(): Promise<FlightSummary[]>;
  getFlight(flightId: string): Promise<{
    flight_analysis: FlightAnalysis; insight_set: InsightSet; source_filename: string | null;
    reference_state: ReferenceState; reference_changes: ReferenceChangeMarker[];
  }>;
  getFleet(): Promise<FleetAnalysis>;
  rebuildFleet(): Promise<FleetAnalysis>;
  getFlightSeries(flightId: string, channels: string[]): Promise<SeriesResult>;

  // Spec 02 §6.5 annotations — pilot notes on a specific insight or
  // event, never a chart point or config (Spec 03's "not a valid ref
  // target" reasoning).
  listAnnotations(flightId?: string): Promise<{ annotations: Annotation[] }>;
  saveAnnotation(args: { id?: string; flightId: string; ref: AnnotationRef; note: string }): Promise<Annotation>;
  deleteAnnotation(id: string): Promise<{ deleted: boolean }>;

  // Spec 09 limit filters (§11.5).
  listFilters(): Promise<{ filters: FilterListEntry[] }>;
  // Spec 09 v0.18: a filter targets a limit or a classified CAS alert.
  proposeFilter(target: FilterTarget): Promise<FilterProposal>;
  previewFilter(filter: LimitFilterDraft): Promise<FilterPreview>;
  saveFilter(filter: LimitFilterDraft): Promise<LimitFilter>;
  deleteFilter(id: string): Promise<{ deleted: boolean }>;
  filterHealth(): Promise<{ health: FilterHealth[]; attention_count: number }>;
  reviewFilter(id: string): Promise<LimitFilter>;
  rebaselineFilter(id: string): Promise<LimitFilter>;
  copyFilters(sourceWorkspaceId: string): Promise<CopyFiltersResult>;

  // Spec 07 §4/§6 — the channel registry (single source of truth, D4) and
  // chart presets (shipped + user, D1). saveUserPreset with an id edits
  // that user preset in place (§6.6 rename); duplicating a shipped
  // preset is the same call with no id, seeded from its channels.
  getChannelRegistry(): Promise<ChannelRegistry>;
  getChartPresets(): Promise<ChartPresetsResult>;
  saveUserPreset(args: { id?: string; label: string; channels: string[]; description?: string }): Promise<ChartPreset>;
  deleteUserPreset(id: string): Promise<{ deleted: boolean }>;
  reorderUserPresets(order: string[]): Promise<{ presets: ChartPreset[] }>;

  // Spec 03 §5.1 Flights table + Spec 02 §6.3 FleetSelection
  listFlightsWithStatus(): Promise<{ rows: FlightTableRow[] }>;
  excludeFlight(flightId: string, reason: string): Promise<FleetSelectionResult>;
  includeFlight(flightId: string): Promise<FleetSelectionResult>;
  // Spec 14 §7.1 (v0.6) — read-only: the other flights whose verdict would
  // change if this flight were excluded from / included in the reference.
  previewReferenceMembership(flightId: string, action: "exclude" | "include"): Promise<{ changed_flight_ids: string[] }>;
  removeMissingFlight(flightId: string): Promise<{ removed: boolean }>;
  removeFlight(flightId: string): Promise<{ removed: boolean; scan_result: ScanResult | null }>;
  removeFlights(flightIds: string[]): Promise<{ removed_flight_ids: string[]; scan_result: ScanResult | null }>;

  // Spec 02 §5.11 — files that never became a
  // flight_id (ground session / short flight / corrupt log / user).
  listExclusions(enrich?: boolean): Promise<ExclusionsResult>;
  includeExcludedLog(filename: string, reason?: string): Promise<{ filename: string; included: boolean; scan_result: ScanResult | null }>;
  previewExcludedLog(filename: string): Promise<{ flight_analysis: FlightAnalysis; source_filename: string }>;
  getExcludedLogSeries(filename: string, channels: string[]): Promise<SeriesResult>;

  // Spec 02 v0.5 workspace management
  listWorkspaces(): Promise<WorkspaceRegistryEntry[]>;
  createWorkspace(name: string, engineModel: string, tailNumber?: string): Promise<WorkspaceManifest>;
  switchWorkspace(workspaceId: string): Promise<ActiveWorkspace>;
  deleteWorkspace(workspaceId: string): Promise<{ deleted: boolean; workspace_id: string }>;
  getActiveWorkspace(): Promise<ActiveWorkspace>;
  addLogFolder(path: string): Promise<WorkspaceManifest>;
  scanWorkspace(options?: ScanOptions): Promise<ScanResult>;
  getScanProgress(): Promise<ScanProgress>;
  // Spec 02 v0.10 §5.8.1 / Spec 14 v0.12 §5.2 — the data location.
  // `target` is a folder path, or { default: true } for the default folder.
  getDataLocation(): Promise<DataLocation>;
  assessDataLocation(target: DataLocationTarget): Promise<DataLocationAssessment>;
  changeDataLocation(target: DataLocationTarget): Promise<DataLocationChange>;
  getDataLocationProgress(): Promise<DataLocationProgress>;
  retryDataLocation(): Promise<DataLocation>;
  getAppSettings(): Promise<AppSettings>;
  saveAppSettings(settings: AppSettings): Promise<AppSettings>;
  getWorkspaceSettings(): Promise<WorkspaceSettings>;
  saveWorkspaceSettings(settings: WorkspaceSettings): Promise<WorkspaceSettings>;

  // Spec 01 §8.8 / Spec 03 §5.2 — fetched once per engine profile and
  // rule set and cached by the caller, not per flight.
  getTopicHelp(topicIds?: string[]): Promise<TopicHelpResult>;

  // Spec 02 v0.8 §5.6/§6.6
  getAircraftSummary(): Promise<AircraftSummary>;

  // Spec 03 §5.5 rule playground — one editor, two documents
  // (rules/active.json + BaselineConfig), plus the live per-flight diff.
  getWorkspaceRules(): Promise<WorkspaceRulesResult>;
  saveWorkspaceRules(rules: RuleSet): Promise<{ rules: RuleSet }>;
  // journal_entry: the topic's entry now in force (Spec 14 v0.10), or null
  // when the edit leaves no decision standing (Enable, back to shipped).
  applyCardRuleEdit(topicId: string, topic: RuleTopic): Promise<{ rules: RuleSet; journal_entry: JournalEntry | null; changed_flight_ids: string[] }>;
  revertRuleEdit(entryId: string): Promise<{ rules: RuleSet }>;
  // Spec 14 v0.10 §6.2 — keep a decision a notice questions; edit an exclusion's reason.
  confirmJournalNotice(entryId: string, notice: string): Promise<JournalEntry>;
  updateExclusionReason(flightId: string, reason: string): Promise<unknown>;
  resetWorkspaceRules(): Promise<{ rules: RuleSet }>;
  saveBaselineConfig(baselineConfig: BaselineConfig): Promise<FleetAnalysis>;
  whatIfRules(candidate: { rules?: RuleSet; baseline_config?: BaselineConfig }): Promise<WhatIfResult>;

  // Spec 12 §11.3 (Session A) — pinned references and shift-history deletion.
  setReference(metricId: string, flightIds: string[], label?: string): Promise<BaselineConfig>;
  clearReference(metricId: string): Promise<BaselineConfig>;
  // Spec 12 §5.7.1 item 5 (Session D) — read-only: whether unpinning
  // metricId right now would change its change_summary membership.
  previewClearReference(metricId: string): Promise<UnpinPreview>;
  deleteShiftEvent(eventId: string): Promise<{ shift_history: ShiftEvent[] }>;

  // Spec 12 R3.3 (Session A) — Trends panel layout, built by the engine
  // from the topic register, not a frontend metric list (D3).
  getTrendsPanels(): Promise<{ panels: TrendsPanel[] }>;
}

export class EngineRpcError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

function toBase64(buf: ArrayBuffer): string {
  let binary = "";
  const bytes = new Uint8Array(buf);
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

export type DataLocationTarget = string | { default: true };

function locationParams(target: DataLocationTarget) {
  return typeof target === "string" ? { path: target } : { default: true };
}

let nextRequestId = 1;

// The local-server adapter (Spec 04 §9.2): POST /rpc, same envelope on
// every call. `slingology-eis serve` runs this at 127.0.0.1:<port>.
export class LocalServerClient implements EngineClient {
  private baseUrl: string;

  constructor(baseUrl: string = "http://127.0.0.1:8420") {
    this.baseUrl = baseUrl;
  }

  private async rpc<T>(op: string, params: unknown): Promise<T> {
    const request_id = `r-${nextRequestId++}`;
    const res = await fetch(`${this.baseUrl}/rpc`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ op, request_id, params }),
    });
    const envelope = await res.json();
    if (!envelope.ok) {
      throw new EngineRpcError(envelope.error?.code ?? "UNKNOWN", envelope.error?.message ?? "request failed");
    }
    return envelope.result as T;
  }

  listEngines() {
    return this.rpc<{ id: string; engine: string; source_status: string; hash: string }[]>("list_engines", {});
  }

  getEngineLimits() {
    return this.rpc<EngineLimitsResult>("get_engine_limits", {});
  }

  listChangedSettings() {
    return this.rpc<{ settings: ChangedSetting[] }>("list_changed_settings", {});
  }

  resetSetting(refId: string) {
    return this.rpc<FleetAnalysis>("reset_setting", { ref_id: refId });
  }

  getJournal() {
    return this.rpc<{ entries: JournalEntry[] }>("get_journal", {});
  }

  getDefaultRules() {
    return this.rpc<RuleSet>("get_default_rules", {});
  }

  ingestLog(file: UploadFile) {
    return this.rpc<IngestResult>("ingest_log", { content_base64: toBase64(file.content), filename: file.filename });
  }

  analyzeFlight(file: UploadFile, engine?: string) {
    return this.rpc<FlightAnalysis>("analyze_flight", {
      content_base64: toBase64(file.content),
      filename: file.filename,
      engine,
    });
  }

  getSeries(file: UploadFile, channels: string[]) {
    return this.rpc<SeriesResult>("get_series", {
      content_base64: toBase64(file.content),
      filename: file.filename,
      channels,
    });
  }

  importFiles(files: UploadFile[], engine?: string) {
    return this.rpc<ImportResult>("import_files", {
      files: files.map((f) => ({ content_base64: toBase64(f.content), filename: f.filename })),
      engine,
    });
  }

  listFlights() {
    return this.rpc<FlightSummary[]>("list_flights", {});
  }

  getFlight(flightId: string) {
    return this.rpc<{
      flight_analysis: FlightAnalysis; insight_set: InsightSet; source_filename: string | null;
      reference_state: ReferenceState; reference_changes: ReferenceChangeMarker[];
    }>(
      "get_flight",
      { flight_id: flightId }
    );
  }

  getFleet() {
    return this.rpc<FleetAnalysis>("get_fleet", {});
  }

  rebuildFleet() {
    return this.rpc<FleetAnalysis>("rebuild_fleet", {});
  }

  getFlightSeries(flightId: string, channels: string[]) {
    return this.rpc<SeriesResult>("get_flight_series", { flight_id: flightId, channels });
  }

  listAnnotations(flightId?: string) {
    return this.rpc<{ annotations: Annotation[] }>("list_annotations", flightId ? { flight_id: flightId } : {});
  }

  saveAnnotation(args: { id?: string; flightId: string; ref: AnnotationRef; note: string }) {
    return this.rpc<Annotation>("save_annotation", { id: args.id, flight_id: args.flightId, ref: args.ref, note: args.note });
  }

  deleteAnnotation(id: string) {
    return this.rpc<{ deleted: boolean }>("delete_annotation", { id });
  }

  async listFilters() {
    const res = await this.rpc<{ filters: FilterListEntry[] }>("list_filters", {});
    return {
      ...res,
      filters: res.filters.map((e) => {
        const filter = withTarget(e.filter);
        return { ...e, filter, target_label: e.target_label ?? targetLabel(filter.target, e.limit?.label) };
      }),
    };
  }

  async proposeFilter(target: FilterTarget) {
    const p = await this.rpc<FilterProposal>("propose_filter", { target });
    return { ...p, target: p.target ?? target, existing: p.existing ? withTarget(p.existing) : null };
  }

  previewFilter(filter: LimitFilterDraft) {
    return this.rpc<FilterPreview>("preview_filter", { filter });
  }

  async saveFilter(filter: LimitFilterDraft) {
    return withTarget(await this.rpc<LimitFilter>("save_filter", { filter }));
  }

  deleteFilter(id: string) {
    return this.rpc<{ deleted: boolean }>("delete_filter", { id });
  }

  async filterHealth() {
    const res = await this.rpc<{ health: FilterHealth[]; attention_count: number }>("filter_health", {});
    return { ...res, health: res.health.map((h) => withTarget(h)) };
  }

  async reviewFilter(id: string) {
    return withTarget(await this.rpc<LimitFilter>("review_filter", { id }));
  }

  async rebaselineFilter(id: string) {
    return withTarget(await this.rpc<LimitFilter>("rebaseline_filter", { id }));
  }

  async copyFilters(sourceWorkspaceId: string) {
    const res = await this.rpc<CopyFiltersResult>("copy_filters", { source_workspace_id: sourceWorkspaceId });
    return { ...res, skipped: res.skipped.map((s) => withTarget(s)) };
  }

  getChannelRegistry() {
    return this.rpc<ChannelRegistry>("get_channel_registry", {});
  }

  getChartPresets() {
    return this.rpc<ChartPresetsResult>("get_chart_presets", {});
  }

  saveUserPreset(args: { id?: string; label: string; channels: string[]; description?: string }) {
    return this.rpc<ChartPreset>("save_user_preset", { id: args.id, label: args.label, channels: args.channels, description: args.description });
  }

  deleteUserPreset(id: string) {
    return this.rpc<{ deleted: boolean }>("delete_user_preset", { id });
  }

  reorderUserPresets(order: string[]) {
    return this.rpc<{ presets: ChartPreset[] }>("reorder_user_presets", { order });
  }

  listFlightsWithStatus() {
    return this.rpc<{ rows: FlightTableRow[] }>("list_flights_with_status", {});
  }

  excludeFlight(flightId: string, reason: string) {
    return this.rpc<FleetSelectionResult>("exclude_flight", { flight_id: flightId, reason });
  }

  includeFlight(flightId: string) {
    return this.rpc<FleetSelectionResult>("include_flight", { flight_id: flightId });
  }

  previewReferenceMembership(flightId: string, action: "exclude" | "include") {
    return this.rpc<{ changed_flight_ids: string[] }>("preview_reference_membership", { flight_id: flightId, action });
  }

  removeMissingFlight(flightId: string) {
    return this.rpc<{ removed: boolean }>("remove_missing_flight", { flight_id: flightId });
  }

  removeFlight(flightId: string) {
    return this.rpc<{ removed: boolean; scan_result: ScanResult | null }>("remove_flight", { flight_id: flightId });
  }

  removeFlights(flightIds: string[]) {
    return this.rpc<{ removed_flight_ids: string[]; scan_result: ScanResult | null }>("remove_flights", { flight_ids: flightIds });
  }

  listExclusions(enrich?: boolean) {
    return this.rpc<ExclusionsResult>("list_exclusions", { enrich: !!enrich });
  }

  includeExcludedLog(filename: string, reason?: string) {
    return this.rpc<{ filename: string; included: boolean; scan_result: ScanResult | null }>(
      "include_excluded_log", { filename, reason }
    );
  }

  previewExcludedLog(filename: string) {
    return this.rpc<{ flight_analysis: FlightAnalysis; source_filename: string }>("preview_excluded_log", { filename });
  }

  getExcludedLogSeries(filename: string, channels: string[]) {
    return this.rpc<SeriesResult>("get_excluded_log_series", { filename, channels });
  }

  listWorkspaces() {
    return this.rpc<WorkspaceRegistryEntry[]>("list_workspaces", {});
  }

  createWorkspace(name: string, engineModel: string, tailNumber?: string) {
    return this.rpc<WorkspaceManifest>("create_workspace", { name, engine_model: engineModel, tail_number: tailNumber });
  }

  switchWorkspace(workspaceId: string) {
    return this.rpc<ActiveWorkspace>("switch_workspace", { workspace_id: workspaceId });
  }

  deleteWorkspace(workspaceId: string) {
    return this.rpc<{ deleted: boolean; workspace_id: string }>("delete_workspace", { workspace_id: workspaceId });
  }

  getActiveWorkspace() {
    return this.rpc<ActiveWorkspace>("get_active_workspace", {});
  }

  addLogFolder(path: string) {
    return this.rpc<WorkspaceManifest>("add_log_folder", { path });
  }

  scanWorkspace(options: ScanOptions = {}) {
    return this.rpc<ScanResult>("scan_workspace", options);
  }

  getScanProgress() {
    return this.rpc<ScanProgress>("get_scan_progress", {});
  }

  getDataLocation() {
    return this.rpc<DataLocation>("get_data_location", {});
  }

  assessDataLocation(target: DataLocationTarget) {
    return this.rpc<DataLocationAssessment>("assess_data_location", locationParams(target));
  }

  changeDataLocation(target: DataLocationTarget) {
    return this.rpc<DataLocationChange>("change_data_location", locationParams(target));
  }

  getDataLocationProgress() {
    return this.rpc<DataLocationProgress>("get_data_location_progress", {});
  }

  retryDataLocation() {
    return this.rpc<DataLocation>("retry_data_location", {});
  }

  getAppSettings() {
    return this.rpc<AppSettings>("get_app_settings", {});
  }

  saveAppSettings(settings: AppSettings) {
    return this.rpc<AppSettings>("save_app_settings", { settings });
  }

  getWorkspaceSettings() {
    return this.rpc<WorkspaceSettings>("get_workspace_settings", {});
  }

  saveWorkspaceSettings(settings: WorkspaceSettings) {
    return this.rpc<WorkspaceSettings>("save_workspace_settings", { settings });
  }

  getTopicHelp(topicIds?: string[]) {
    return this.rpc<TopicHelpResult>("get_topic_help", { topic_ids: topicIds });
  }

  getAircraftSummary() {
    return this.rpc<AircraftSummary>("get_aircraft_summary", {});
  }

  getWorkspaceRules() {
    return this.rpc<WorkspaceRulesResult>("get_workspace_rules", {});
  }

  saveWorkspaceRules(rules: RuleSet) {
    return this.rpc<{ rules: RuleSet }>("save_workspace_rules", { rules });
  }

  applyCardRuleEdit(topicId: string, topic: RuleTopic) {
    return this.rpc<{ rules: RuleSet; journal_entry: JournalEntry | null; changed_flight_ids: string[] }>(
      "apply_card_rule_edit", { topic_id: topicId, topic },
    );
  }

  confirmJournalNotice(entryId: string, notice: string) {
    return this.rpc<JournalEntry>("confirm_journal_notice", { entry_id: entryId, notice });
  }

  updateExclusionReason(flightId: string, reason: string) {
    return this.rpc<unknown>("update_exclusion_reason", { flight_id: flightId, reason });
  }

  revertRuleEdit(entryId: string) {
    return this.rpc<{ rules: RuleSet }>("revert_rule_edit", { entry_id: entryId });
  }

  resetWorkspaceRules() {
    return this.rpc<{ rules: RuleSet }>("reset_workspace_rules", {});
  }

  saveBaselineConfig(baselineConfig: BaselineConfig) {
    return this.rpc<FleetAnalysis>("save_baseline_config", { baseline_config: baselineConfig });
  }

  whatIfRules(candidate: { rules?: RuleSet; baseline_config?: BaselineConfig }) {
    return this.rpc<WhatIfResult>("what_if_rules", candidate);
  }

  setReference(metricId: string, flightIds: string[], label?: string) {
    return this.rpc<BaselineConfig>("set_reference", { metric_id: metricId, flight_ids: flightIds, label });
  }

  clearReference(metricId: string) {
    return this.rpc<BaselineConfig>("clear_reference", { metric_id: metricId });
  }

  previewClearReference(metricId: string) {
    return this.rpc<UnpinPreview>("preview_clear_reference", { metric_id: metricId });
  }

  deleteShiftEvent(eventId: string) {
    return this.rpc<{ shift_history: ShiftEvent[] }>("delete_shift_event", { event_id: eventId });
  }

  getTrendsPanels() {
    return this.rpc<{ panels: TrendsPanel[] }>("get_trends_panels", {});
  }
}

// The switch point: today this always returns the local-server client.
// When the Pyodide Web Worker adapter (Spec 04 §9.1) exists, this becomes
// the one place that decides — e.g. "is a local server reachable at
// this origin? use LocalServerClient; otherwise (static hosting) use
// BrowserWorkerClient" — no other file needs to change.
//
// The base URL itself has two real cases, not one hardcoded port: when
// the built UI is served *by* the local server (the normal deployment —
// `slingology-eis serve`, `web/dist` and `/rpc` on the same origin),
// same-origin is correct regardless of which --port was used — a fixed
// 127.0.0.1:8420 default would silently break for anyone who ran `serve
// --port <anything else>`. Vite's dev server (`npm run dev`) is the one
// genuine exception — the page's own origin is Vite's port (5173/5174),
// never the Python server's, so dev mode needs the fixed cross-origin
// target `slingology-eis serve`'s own default binds to.
export function getEngineClient(): EngineClient {
  const baseUrl = import.meta.env.DEV ? "http://127.0.0.1:8420" : window.location.origin;
  return new LocalServerClient(baseUrl);
}
