import type {
  ActiveWorkspace,
  Annotation,
  AnnotationRef,
  AppSettings,
  BaselineConfig,
  ChannelRegistry,
  ChartPreset,
  ChartPresetsResult,
  Diagnostic,
  EcuAnalysis,
  FleetAnalysis,
  FleetSelectionResult,
  FlightAnalysis,
  FlightTableRow,
  InsightSet,
  RuleSet,
  ScanResult,
  WhatIfResult,
  WorkspaceManifest,
  WorkspaceRegistryEntry,
  WorkspaceRulesResult,
  WorkspaceSettings,
} from "../types/contract";

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
  classification: "new" | "duplicate" | "ground_session";
  filename: string;
  airborne_min: number;
  flight_id?: string;
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
  getDefaultRules(): Promise<RuleSet>;
  ingestLog(file: UploadFile): Promise<IngestResult>;
  analyzeFlight(file: UploadFile, engine?: string): Promise<FlightAnalysis>;
  getSeries(file: UploadFile, channels: string[]): Promise<SeriesResult>;
  importFiles(files: UploadFile[], engine?: string): Promise<ImportResult>;
  listFlights(): Promise<FlightSummary[]>;
  getFlight(flightId: string): Promise<{ flight_analysis: FlightAnalysis; insight_set: InsightSet; source_filename: string | null }>;
  getFleet(): Promise<FleetAnalysis>;
  rebuildFleet(): Promise<FleetAnalysis>;
  getFlightSeries(flightId: string, channels: string[]): Promise<SeriesResult>;
  analyzeEcuWorkspace(): Promise<EcuAnalysis>;

  // Spec 02 §6.5 annotations — pilot notes on a specific insight or ECU
  // event, never a chart point or config (Spec 03's "not a valid ref
  // target" reasoning).
  listAnnotations(flightId?: string): Promise<{ annotations: Annotation[] }>;
  saveAnnotation(args: { id?: string; flightId: string; ref: AnnotationRef; note: string }): Promise<Annotation>;
  deleteAnnotation(id: string): Promise<{ deleted: boolean }>;

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
  removeMissingFlight(flightId: string): Promise<{ removed: boolean }>;
  removeFlight(flightId: string): Promise<{ removed: boolean; scan_result: ScanResult | null }>;
  removeFlights(flightIds: string[]): Promise<{ removed_flight_ids: string[]; scan_result: ScanResult | null }>;

  // Spec 02 v0.5 workspace management
  listWorkspaces(): Promise<WorkspaceRegistryEntry[]>;
  createWorkspace(name: string, engineModel: string, tailNumber?: string): Promise<WorkspaceManifest>;
  switchWorkspace(workspaceId: string): Promise<ActiveWorkspace>;
  getActiveWorkspace(): Promise<ActiveWorkspace>;
  addLogFolder(path: string): Promise<WorkspaceManifest>;
  scanWorkspace(): Promise<ScanResult>;
  getAppSettings(): Promise<AppSettings>;
  saveAppSettings(settings: AppSettings): Promise<AppSettings>;
  getWorkspaceSettings(): Promise<WorkspaceSettings>;
  saveWorkspaceSettings(settings: WorkspaceSettings): Promise<WorkspaceSettings>;

  // Spec 03 §5.5 rule playground — one editor, two documents
  // (rules/active.json + BaselineConfig), plus the live per-flight diff.
  getWorkspaceRules(): Promise<WorkspaceRulesResult>;
  saveWorkspaceRules(rules: RuleSet): Promise<{ rules: RuleSet }>;
  resetWorkspaceRules(): Promise<{ rules: RuleSet }>;
  saveBaselineConfig(baselineConfig: BaselineConfig): Promise<FleetAnalysis>;
  whatIfRules(candidate: { rules?: RuleSet; baseline_config?: BaselineConfig }): Promise<WhatIfResult>;
}

class EngineRpcError extends Error {
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
    return this.rpc<{ flight_analysis: FlightAnalysis; insight_set: InsightSet; source_filename: string | null }>(
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

  analyzeEcuWorkspace() {
    return this.rpc<EcuAnalysis>("analyze_ecu_workspace", {});
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

  removeMissingFlight(flightId: string) {
    return this.rpc<{ removed: boolean }>("remove_missing_flight", { flight_id: flightId });
  }

  removeFlight(flightId: string) {
    return this.rpc<{ removed: boolean; scan_result: ScanResult | null }>("remove_flight", { flight_id: flightId });
  }

  removeFlights(flightIds: string[]) {
    return this.rpc<{ removed_flight_ids: string[]; scan_result: ScanResult | null }>("remove_flights", { flight_ids: flightIds });
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

  getActiveWorkspace() {
    return this.rpc<ActiveWorkspace>("get_active_workspace", {});
  }

  addLogFolder(path: string) {
    return this.rpc<WorkspaceManifest>("add_log_folder", { path });
  }

  scanWorkspace() {
    return this.rpc<ScanResult>("scan_workspace", {});
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

  getWorkspaceRules() {
    return this.rpc<WorkspaceRulesResult>("get_workspace_rules", {});
  }

  saveWorkspaceRules(rules: RuleSet) {
    return this.rpc<{ rules: RuleSet }>("save_workspace_rules", { rules });
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
