import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { NavShell } from "../components/NavShell";
import { InlineHelp } from "../components/InlineHelp";
import { DataLocationPanel } from "../components/DataLocation";
import { UnpinConfirmDialog } from "../components/PinDialogs";
import { bandLabel } from "../lib/bands";
import { getEngineClient } from "../lib/engineClient";
import { ScopeCaption } from "../components/ScopeCaption";
import { APPLY_LABEL } from "../lib/scope";
import {
  appSettings as fixtureAppSettings,
  engineLimits as fixtureEngineLimits,
  fleetAnalysis as fixtureFleet,
  workspaceManifest as fixtureManifest,
  workspaceSettings as fixtureWorkspaceSettings,
} from "../lib/fixtures";
import type {
  AppSettings, BaselineConfig, ChartPreset, EngineLimitsResult, FleetAnalysis,
  RuleSet, SettingsChangelogEntry, UnpinPreview, WorkspaceManifest, WorkspaceSettings,
} from "../types/contract";

const client = getEngineClient();

const LEGACY_MANIFEST: WorkspaceManifest = {
  id: "legacy", name: "Workspace (no registry workspace active)", engine_model: "—", log_folders: [],
  schema_version: "", created_at: "", updated_at: "", engine_version_seen: [],
  flight_count: 0, storage_backend: "filesystem",
};

// Mirrors update_fleet's own default (Spec 01 §8.4) — used for "Reset to
// shipped" and for the empty-workspace fixture-fallback state.
const DEFAULT_BASELINE_CONFIG: BaselineConfig = {
  membership: "leave_one_out", band_kind_by_metric: {}, outlier_z_threshold: 2.0,
  recent_window_hours: 10, recent_window_min_flights: 5, recent_window_max_flights: 15, om_margin_fraction: 0.25,
};

function clone<T>(x: T): T {
  return typeof structuredClone === "function" ? structuredClone(x) : JSON.parse(JSON.stringify(x));
}

const TAB_IDS = ["engine", "reference", "app"] as const;
type TabId = (typeof TAB_IDS)[number];
const TAB_LABELS: Record<TabId, string> = { engine: "Engine", reference: "Reference & Models", app: "App" };

function numberInput(value: number, onChange: (v: number) => void, opts?: { step?: number; min?: number; max?: number }) {
  return (
    <input
      type="number"
      className="mono"
      value={value}
      step={opts?.step ?? 1}
      min={opts?.min}
      max={opts?.max}
      onChange={(e) => onChange(Number(e.target.value))}
      style={{ width: 90, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 8px", color: "var(--text-primary)", fontSize: 13 }}
    />
  );
}

const PANEL_STYLE: React.CSSProperties = { background: "var(--panel)", borderRadius: 12, padding: "16px 18px" };
const PANEL_TITLE_STYLE: React.CSSProperties = { fontSize: 13, fontWeight: 600, marginBottom: 12 };
const ROW_STYLE: React.CSSProperties = { display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12, marginBottom: 10, gap: 12 };

// Spec 03 v0.6 §5.7, restructured by Spec 14 §5 — Settings is now a
// tabbed section. Engine (read-only profile + limits, overrides out of
// scope per §10 Q1), Reference & Models (what used to be most of
// Baselines.tsx's sidebar — Spec 14 §7.2 "what moves where"), and App
// (this view's pre-Spec-14 content, minus the bits that moved to Engine).
export function Settings() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab: TabId = (TAB_IDS as readonly string[]).includes(params.get("tab") ?? "") ? (params.get("tab") as TabId) : "app";
  function setTab(next: TabId) {
    setParams((p) => {
      const copy = new URLSearchParams(p);
      copy.set("tab", next);
      return copy;
    });
  }

  const [appSettings, setAppSettings] = useState<AppSettings>(fixtureAppSettings);
  const [workspaceSettings, setWorkspaceSettings] = useState<WorkspaceSettings>(fixtureWorkspaceSettings);
  const [manifest, setManifest] = useState<WorkspaceManifest>(fixtureManifest);
  const [usingFixture, setUsingFixture] = useState(true);
  const [loading, setLoading] = useState(true);
  const [exportScope, setExportScope] = useState<"full_workspace" | "single_flight">("full_workspace");
  const [exportAnonymize, setExportAnonymize] = useState(false);
  const [nudgeDismissed, setNudgeDismissed] = useState(false);

  // Spec 07 §6.6 — managing user chart presets lives here, not on the
  // Flight view; shipped presets come along read-only so "Duplicate"
  // has something to duplicate from.
  const [shippedPresets, setShippedPresets] = useState<ChartPreset[]>([]);
  const [userPresets, setUserPresets] = useState<ChartPreset[]>([]);
  const [editingPresetId, setEditingPresetId] = useState<string | null>(null);
  const [presetDraft, setPresetDraft] = useState("");
  const [presetError, setPresetError] = useState<string | null>(null);

  // Reference & Models (Spec 14 §5.1).
  const [fleet, setFleet] = useState<FleetAnalysis>(fixtureFleet);
  const [draftBaselineConfig, setDraftBaselineConfig] = useState<BaselineConfig>(() => clone(fixtureFleet.provenance.baseline_config));
  const [savingReference, setSavingReference] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [unpinTarget, setUnpinTarget] = useState<string | null>(null);
  const [unpinPreview, setUnpinPreview] = useState<UnpinPreview | null>(null);

  // Engine (Spec 14 §5).
  const [engineLimits, setEngineLimits] = useState<EngineLimitsResult>(fixtureEngineLimits);

  // Spec 14 §5.1 (v0.3) — n_min is shown here per trigger, read-only; it
  // lives in rules/active.json and is edited on the topic card (§7.3).
  const [rules, setRules] = useState<RuleSet | null>(null);
  // Spec 14 §5.1 (v0.6): topics with a card, enabled or not — the n_min
  // list shows a disabled one marked disabled, and never the ones the
  // engine doesn't surface.
  const [cardTopicIds, setCardTopicIds] = useState<Set<string>>(new Set());

  // Shared changelog (Spec 14 §5, acceptance 2).
  const [changelog, setChangelog] = useState<SettingsChangelogEntry[]>([]);

  async function refreshChangelog() {
    if (usingFixture) return;
    try {
      const res = await client.getSettingsChangelog();
      setChangelog(res.entries);
    } catch {
      // leave whatever was already loaded
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [app, active, chartPresets, liveFleet, limits, workspaceRules] = await Promise.all([
          client.getAppSettings(), client.getActiveWorkspace(), client.getChartPresets(),
          client.getFleet(), client.getEngineLimits(), client.getWorkspaceRules(),
        ]);
        if (cancelled) return;
        setAppSettings(app);
        if (active.active && active.manifest && active.settings) {
          setManifest(active.manifest);
          setWorkspaceSettings(active.settings);
        } else {
          setManifest(LEGACY_MANIFEST);
        }
        const userIds = new Set(app.chart_presets.map((p) => p.id));
        setShippedPresets(chartPresets.presets.filter((p) => !userIds.has(p.id)));
        setUserPresets(chartPresets.presets.filter((p) => userIds.has(p.id)));
        setFleet(liveFleet);
        setDraftBaselineConfig(clone(liveFleet.provenance.baseline_config));
        setEngineLimits(limits);
        setRules(workspaceRules.rules);
        setCardTopicIds(new Set(workspaceRules.card_topic_ids));
        setUsingFixture(false);
        try {
          const changelogRes = await client.getSettingsChangelog();
          if (!cancelled) setChangelog(changelogRes.entries);
        } catch {
          // non-fatal — changelog just stays empty
        }
      } catch {
        if (!cancelled) {
          setAppSettings(fixtureAppSettings);
          setWorkspaceSettings(fixtureWorkspaceSettings);
          setManifest(fixtureManifest);
          setShippedPresets([]);
          setUserPresets([]);
          setFleet(fixtureFleet);
          setDraftBaselineConfig(clone(fixtureFleet.provenance.baseline_config));
          setEngineLimits(fixtureEngineLimits);
          setRules(null);
          setUsingFixture(true);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function refreshPresets() {
    if (usingFixture) return;
    try {
      const [app, chartPresets] = await Promise.all([client.getAppSettings(), client.getChartPresets()]);
      setAppSettings(app);
      const userIds = new Set(app.chart_presets.map((p) => p.id));
      setShippedPresets(chartPresets.presets.filter((p) => !userIds.has(p.id)));
      setUserPresets(chartPresets.presets.filter((p) => userIds.has(p.id)));
    } catch {
      // leave whatever was already loaded
    }
  }

  function startRename(preset: ChartPreset) {
    setEditingPresetId(preset.id);
    setPresetDraft(preset.label);
    setPresetError(null);
  }

  async function confirmRename(preset: ChartPreset) {
    if (!presetDraft.trim()) return;
    try {
      await client.saveUserPreset({ id: preset.id, label: presetDraft.trim(), channels: preset.channels, description: preset.description });
      setEditingPresetId(null);
      await refreshPresets();
    } catch (e) {
      setPresetError(e instanceof Error ? e.message : "Couldn't save that name");
    }
  }

  async function deletePreset(id: string) {
    try {
      await client.deleteUserPreset(id);
      await refreshPresets();
    } catch {
      // leave the list as-is — the delete just didn't reach the server
    }
  }

  async function duplicatePreset(preset: ChartPreset) {
    try {
      await client.saveUserPreset({ label: `${preset.label} copy`, channels: preset.channels, description: preset.description });
      await refreshPresets();
    } catch {
      // leave the list as-is
    }
  }

  async function movePreset(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= userPresets.length) return;
    const reordered = [...userPresets];
    [reordered[index], reordered[target]] = [reordered[target], reordered[index]];
    setUserPresets(reordered); // optimistic — reorder feels instant, not round-trip-gated
    try {
      await client.reorderUserPresets(reordered.map((p) => p.id));
    } catch {
      await refreshPresets(); // couldn't persist — fall back to whatever the server actually has
    }
  }

  async function updateAppSettings(patch: Partial<AppSettings>) {
    const next = { ...appSettings, ...patch };
    setAppSettings(next);
    if (usingFixture) return;
    try {
      await client.saveAppSettings(next);
      await refreshChangelog();
    } catch {
      // server unreachable — local state already updated, nothing more to do
    }
  }

  async function updateWorkspaceSettings(patch: Partial<WorkspaceSettings>) {
    const next = { ...workspaceSettings, ...patch };
    setWorkspaceSettings(next);
    if (usingFixture || manifest.id === "legacy") return;
    try {
      await client.saveWorkspaceSettings(next);
      await refreshChangelog();
    } catch {
      // server unreachable — local state already updated, nothing more to do
    }
  }

  const referenceDirty = JSON.stringify(draftBaselineConfig) !== JSON.stringify(fleet.provenance.baseline_config);

  async function saveReference() {
    setSavingReference(true);
    try {
      const newFleet = await client.saveBaselineConfig(draftBaselineConfig);
      setFleet(newFleet);
      setDraftBaselineConfig(clone(newFleet.provenance.baseline_config));
      await refreshChangelog();
    } catch {
      // server unreachable — draft stays, nothing applied
    } finally {
      setSavingReference(false);
    }
  }

  async function resetReferenceToShipped() {
    setSavingReference(true);
    try {
      const newFleet = await client.saveBaselineConfig(DEFAULT_BASELINE_CONFIG);
      setFleet(newFleet);
      setDraftBaselineConfig(clone(newFleet.provenance.baseline_config));
      await refreshChangelog();
    } catch {
      // server unreachable
    } finally {
      setSavingReference(false);
    }
  }

  function removeOverride(metricId: string) {
    setDraftBaselineConfig((prev) => {
      const next = clone(prev);
      if (next.outlier_z_threshold_overrides) delete next.outlier_z_threshold_overrides[metricId];
      return next;
    });
  }

  async function handleRebuildReference() {
    if (usingFixture) return;
    setRebuilding(true);
    try {
      const newFleet = await client.rebuildFleet();
      setFleet(newFleet);
      setDraftBaselineConfig(clone(newFleet.provenance.baseline_config));
    } catch {
      // server unreachable
    } finally {
      setRebuilding(false);
    }
  }

  const totalFlights = fleet.flight_ids.length + fleet.excluded.length;
  const takeoffMapModel = fleet.models.find((m) => m.id === "takeoff_map");
  const modelInsufficientNote = fleet.quality.find(
    (d) => (d as { code?: string }).code === "MODEL_INSUFFICIENT_DATA",
  ) as { message?: string } | undefined;

  const stratifiedMetrics = useMemo(
    () => Object.entries(draftBaselineConfig.band_kind_by_metric ?? {}).filter(([, kind]) => kind != null),
    [draftBaselineConfig.band_kind_by_metric],
  );

  return (
    <NavShell>
      <div style={{ flexGrow: 1, overflowY: "auto", padding: "24px 28px", display: "flex", flexDirection: "column", gap: 20 }}>
        <div>
          <h1 style={{ margin: "0 0 12px", fontSize: 19, fontWeight: 700 }}>
            Settings {usingFixture && <span style={{ fontSize: 12, fontWeight: 400, color: "var(--text-tertiary)" }}>(sample)</span>}
            {loading && <span style={{ fontSize: 12, fontWeight: 400, color: "var(--text-tertiary)" }}> · loading…</span>}
          </h1>
          <div style={{ display: "flex", gap: 8 }}>
            {TAB_IDS.map((id) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                style={{
                  padding: "6px 14px", borderRadius: 20, fontSize: 12, fontWeight: 600, cursor: "pointer",
                  border: tab === id ? "1px solid var(--accent)" : "1px solid var(--border)",
                  background: tab === id ? "var(--accent-15)" : "transparent",
                  color: tab === id ? "var(--accent)" : "var(--text-secondary)",
                }}
              >
                {TAB_LABELS[id]}
              </button>
            ))}
          </div>
        </div>

        {tab === "engine" && (
          <>
            <div style={PANEL_STYLE}>
              <div style={PANEL_TITLE_STYLE}>Engine profile</div>
              <div style={ROW_STYLE}>
                <span style={{ color: "var(--text-secondary)" }}>Model</span>
                <span className="mono" style={{ color: "var(--text-primary)" }}>{engineLimits.engine.engine}</span>
              </div>
              {engineLimits.engine.variant && (
                <div style={ROW_STYLE}>
                  <span style={{ color: "var(--text-secondary)" }}>Variant</span>
                  <span className="mono" style={{ color: "var(--text-primary)" }}>{engineLimits.engine.variant}</span>
                </div>
              )}
              {engineLimits.engine.om_reference && (
                <div style={ROW_STYLE}>
                  <span style={{ color: "var(--text-secondary)" }}>OM reference</span>
                  <span style={{ color: "var(--text-primary)", textAlign: "right" }}>{engineLimits.engine.om_reference}</span>
                </div>
              )}
              <div style={ROW_STYLE}>
                <span style={{ color: "var(--text-secondary)" }}>Source status</span>
                <span
                  className="mono"
                  style={{ color: engineLimits.engine.source_status === "VERIFIED" ? "var(--accent)" : "var(--severity-warning)" }}
                  title={engineLimits.engine.source_status === "VERIFIED" ? "Values sourced directly from the Operators Manual" : "Not yet verified against the Operators Manual — do not rely on these limits for operational decisions"}
                >
                  {engineLimits.engine.source_status}
                </span>
              </div>
              <div style={{ ...ROW_STYLE, marginBottom: 0 }}>
                <span style={{ color: "var(--text-secondary)" }}>Engine overrides</span>
                <span style={{ color: "var(--text-tertiary)" }}>
                  None<InlineHelp id="engine.overrides" />
                </span>
              </div>
            </div>

            <div style={PANEL_STYLE}>
              <div style={PANEL_TITLE_STYLE}>
                OM limits {engineLimits.limits.length > 0 && <span style={{ color: "var(--text-tertiary)", fontWeight: 400 }}>({engineLimits.limits.length})</span>}
              </div>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr style={{ textAlign: "left", color: "var(--text-tertiary)" }}>
                      <th style={{ fontWeight: 500, padding: "4px 8px 4px 0" }}>Limit</th>
                      <th style={{ fontWeight: 500, padding: "4px 8px" }}>Value</th>
                      <th style={{ fontWeight: 500, padding: "4px 8px" }}>Severity</th>
                      <th style={{ fontWeight: 500, padding: "4px 8px" }}>Suppression<InlineHelp id="engine.suppression" /></th>
                    </tr>
                  </thead>
                  <tbody>
                    {engineLimits.limits.map((lim) => {
                      const suppression: string[] = [];
                      if (lim.phases && lim.phases.length > 0) suppression.push(`checked only during ${lim.phases.join(", ")}`);
                      if (lim.min_duration_s) suppression.push(`must persist ${lim.min_duration_s}s`);
                      if (lim.min_duration_by_phase) {
                        const byPhase = Object.entries(lim.min_duration_by_phase).filter(([, s]) => s != null);
                        if (byPhase.length > 0) suppression.push(byPhase.map(([ph, s]) => `${ph}: ${s}s`).join(", "));
                      }
                      if (lim.min_rpm) suppression.push(`rpm ≥ ${lim.min_rpm}`);
                      if (lim.requires_reached_since_start) suppression.push("after first reached this flight");
                      return (
                        <tr key={`${lim.id}-${lim.limit_type}`} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                          <td style={{ padding: "6px 8px 6px 0", color: "var(--text-primary)" }}>{lim.label}</td>
                          <td className="mono" style={{ padding: "6px 8px", color: "var(--text-secondary)" }}>
                            {lim.limit_type === "MIN" ? "≥" : "≤"} {lim.limit_value} {lim.unit}
                          </td>
                          <td style={{ padding: "6px 8px", color: "var(--text-tertiary)" }}>{lim.severity}</td>
                          <td style={{ padding: "6px 8px", color: "var(--text-tertiary)" }}>{suppression.join(" · ") || "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {tab === "reference" && (
          <>
            <div style={PANEL_STYLE}>
              <div style={PANEL_TITLE_STYLE}>Contributing flights<InlineHelp id="reference.contributing_flights" /></div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 10 }}>
                {fleet.flight_ids.length} of {totalFlights} flights contribute
                {fleet.excluded.length > 0 && ` · ${fleet.excluded.length} excluded`}
              </div>
              <div style={{ display: "flex", gap: 10 }}>
                <a href="#" onClick={(e) => { e.preventDefault(); navigate("/flights?filter=excluded"); }} style={{ fontSize: 12 }}>
                  View excluded in Flights →
                </a>
                <button
                  onClick={handleRebuildReference}
                  disabled={rebuilding || usingFixture}
                  style={{ padding: "4px 12px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", fontSize: 11, cursor: usingFixture ? "default" : "pointer", marginLeft: "auto" }}
                >
                  {rebuilding ? "Rebuilding…" : "Rebuild reference"}
                </button>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div style={PANEL_STYLE}>
                <div style={PANEL_TITLE_STYLE}>Comparison</div>
                <label style={ROW_STYLE}>
                  <span style={{ color: "var(--text-secondary)" }}>Outlier z-threshold<InlineHelp id="reference.outlier_z_threshold" /></span>
                  {numberInput(draftBaselineConfig.outlier_z_threshold, (v) => setDraftBaselineConfig((p) => ({ ...p, outlier_z_threshold: v })), { step: 0.1, min: 0 })}
                </label>
                <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 10 }}>
                  default: 2.0
                </div>
                <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 4 }}>n_min (sample-size gate), per trigger — read-only here, edited on each topic's card:</div>
                {rules ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 2, marginBottom: 10 }}>
                    {Object.entries(rules.rules)
                      .filter(([topicId]) => cardTopicIds.has(topicId))
                      .flatMap(([topicId, topic]) =>
                        (topic.triggers ?? [])
                          .filter((t) => t.n_min != null)
                          .map((t) => ({ topicId, type: t.type, n_min: t.n_min as number, enabled: topic.enabled }))
                      )
                      .map(({ topicId, type, n_min, enabled }) => (
                        <div key={`${topicId}-${type}`} className="mono" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 11, color: enabled ? "var(--text-secondary)" : "var(--text-tertiary)" }}>
                          <span>{topicId.replace(/_/g, " ")} &middot; {type}{enabled ? "" : " · disabled"}</span>
                          <span>{n_min}</span>
                        </div>
                      ))}
                  </div>
                ) : (
                  <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 10 }}>not connected to a live workspace</div>
                )}
                {Object.keys(draftBaselineConfig.outlier_z_threshold_overrides ?? {}).length > 0 && (
                  <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                    <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>Per-metric overrides</div>
                    {Object.entries(draftBaselineConfig.outlier_z_threshold_overrides ?? {}).map(([metric, z]) => (
                      <div key={metric} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12 }}>
                        <span className="mono" style={{ color: "var(--text-secondary)" }}>{metric}: {z}</span>
                        <a href="#" onClick={(e) => { e.preventDefault(); removeOverride(metric); }} style={{ fontSize: 11, color: "var(--text-tertiary)" }}>remove</a>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div style={PANEL_STYLE}>
                <div style={PANEL_TITLE_STYLE}>Window</div>
                <label style={ROW_STYLE}>
                  <span style={{ color: "var(--text-secondary)" }}>Recent window (hours)<InlineHelp id="reference.recent_window" /></span>
                  {numberInput(draftBaselineConfig.recent_window_hours, (v) => setDraftBaselineConfig((p) => ({ ...p, recent_window_hours: v })), { min: 1 })}
                </label>
                <label style={ROW_STYLE}>
                  <span style={{ color: "var(--text-secondary)" }}>Min flights in window</span>
                  {numberInput(draftBaselineConfig.recent_window_min_flights, (v) => setDraftBaselineConfig((p) => ({ ...p, recent_window_min_flights: v })), { min: 1 })}
                </label>
                <label style={ROW_STYLE}>
                  <span style={{ color: "var(--text-secondary)" }}>Max flights in window</span>
                  {numberInput(draftBaselineConfig.recent_window_max_flights, (v) => setDraftBaselineConfig((p) => ({ ...p, recent_window_max_flights: v })), { min: 1 })}
                </label>
                <label style={{ ...ROW_STYLE, marginBottom: 0 }}>
                  <span style={{ color: "var(--text-secondary)" }}>OM margin fraction</span>
                  {numberInput(draftBaselineConfig.om_margin_fraction, (v) => setDraftBaselineConfig((p) => ({ ...p, om_margin_fraction: v })), { step: 0.05, min: 0, max: 1 })}
                </label>
                <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 8 }}>
                  Defaults: 10h &middot; 5 &middot; 15 &middot; 0.25
                </div>
              </div>
            </div>

            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <ScopeCaption scope="reference_settings" />
              <button
                onClick={resetReferenceToShipped}
                disabled={savingReference || usingFixture}
                style={{ padding: "7px 14px", borderRadius: 8, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", fontSize: 12, cursor: usingFixture ? "default" : "pointer" }}
              >
                Reset to shipped defaults
              </button>
              <button
                onClick={saveReference}
                disabled={savingReference || !referenceDirty || usingFixture}
                title={usingFixture ? "not connected to a live workspace" : undefined}
                style={{ padding: "7px 14px", borderRadius: 8, background: referenceDirty ? "var(--accent)" : "var(--panel)", border: "1px solid var(--border)", color: referenceDirty ? "var(--bg)" : "var(--text-tertiary)", fontSize: 12, fontWeight: 600, cursor: referenceDirty && !usingFixture ? "pointer" : "default" }}
              >
                {savingReference ? "Saving…" : APPLY_LABEL.reference_settings}
              </button>
            </div>

            <div style={PANEL_STYLE}>
              <div style={PANEL_TITLE_STYLE}>Reference per metric<InlineHelp id="reference.pinning" /></div>
              {Object.keys(draftBaselineConfig.pinned_references ?? {}).length === 0 ? (
                <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
                  None — every metric's reference is rolling. Pin one from its panel on Trends.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {Object.entries(draftBaselineConfig.pinned_references ?? {}).map(([metricId, ref]) => (
                    <div key={metricId} style={{ fontSize: 12, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                      <span style={{ color: "var(--text-secondary)" }}>
                        {metricId}
                        {ref.label ? ` (${ref.label})` : ""}
                        <span style={{ color: "var(--text-tertiary)" }}> &middot; n={ref.flight_ids.length}, set {ref.set_at.slice(0, 10)}</span>
                      </span>
                      <a
                        href="#"
                        onClick={(e) => {
                          e.preventDefault();
                          if (usingFixture) return;
                          setUnpinTarget(metricId);
                          setUnpinPreview(null);
                          client.previewClearReference(metricId).then(setUnpinPreview);
                        }}
                        style={{ fontSize: 11 }}
                      >
                        unpin reference
                      </a>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div style={PANEL_STYLE}>
              <div style={PANEL_TITLE_STYLE}>Stratification<InlineHelp id="reference.stratification" /></div>
              <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 10 }}>
                Read-only in v1 — the band edges are research-paper §9 constants.
              </div>
              {stratifiedMetrics.length === 0 ? (
                <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginBottom: 12 }}>No metric is stratified in this workspace.</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 3, marginBottom: 12 }}>
                  {stratifiedMetrics.map(([metric, kind]) => (
                    <div key={metric} className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                      {metric} &middot; {kind}
                    </div>
                  ))}
                </div>
              )}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, color: "var(--text-tertiary)", marginBottom: 6 }}>DA BAND (ft)</div>
                  {engineLimits.band_edges.da_band.map((b) => (
                    <div key={b.name} className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                      {bandLabel(b.name)}: {b.min}–{b.max}
                    </div>
                  ))}
                </div>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, color: "var(--text-tertiary)", marginBottom: 6 }}>OAT BAND (°C)</div>
                  {engineLimits.band_edges.oat_band.map((b) => (
                    <div key={b.name} className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                      {bandLabel(b.name)}: {b.min}–{b.max}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div style={PANEL_STYLE}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>Models</div>
                <button
                  onClick={handleRebuildReference}
                  disabled={rebuilding || usingFixture}
                  style={{ padding: "4px 12px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", fontSize: 11, cursor: usingFixture ? "default" : "pointer" }}
                >
                  {rebuilding ? "Refitting…" : "Refit"}
                </button>
              </div>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Takeoff MAP vs PA/OAT</div>
              {takeoffMapModel ? (
                <>
                  <div style={{ display: "flex", gap: 20, fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>
                    <span>R&sup2; {typeof takeoffMapModel.r_squared === "number" ? takeoffMapModel.r_squared.toFixed(2) : "—"}</span>
                    <span>n = {takeoffMapModel.n}</span>
                    {takeoffMapModel.residual_se != null && <span>residual SD {takeoffMapModel.residual_se.toFixed(2)} inHg</span>}
                  </div>
                  <a href="#" onClick={(e) => { e.preventDefault(); navigate("/trends?panel=boost_power"); }} style={{ fontSize: 12 }}>
                    See the residual panel on Trends →
                  </a>
                </>
              ) : (
                <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
                  {modelInsufficientNote?.message ?? "Still collecting data for a model fit."}
                </div>
              )}
            </div>
          </>
        )}

        {tab === "app" && (
          <>
            {!nudgeDismissed && (
              <div style={{ display: "flex", alignItems: "center", gap: 10, background: "rgba(79,195,176,0.08)", border: "1px solid rgba(79,195,176,0.3)", borderRadius: 10, padding: "11px 14px" }}>
                <span style={{ fontSize: 12, color: "var(--text-primary)", flexGrow: 1 }}>
                  Browser storage can be evicted, especially in Safari. Allow persistent storage for this site, and export a backup bundle now and then.
                </span>
                <button
                  style={{ padding: "5px 12px", borderRadius: 6, background: "var(--accent)", border: "none", color: "var(--bg)", fontSize: 11, fontWeight: 600, cursor: "pointer" }}
                  onClick={() => setNudgeDismissed(true)}
                >
                  Allow
                </button>
                <button
                  style={{ padding: "5px 12px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", fontSize: 11, cursor: "pointer" }}
                  onClick={() => setNudgeDismissed(true)}
                >
                  Dismiss
                </button>
              </div>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div style={PANEL_STYLE}>
                <div style={PANEL_TITLE_STYLE}>App</div>
                <div style={ROW_STYLE}>
                  <span style={{ color: "var(--text-secondary)" }}>Units</span>
                  <select
                    value={appSettings.units}
                    onChange={(e) => updateAppSettings({ units: e.target.value as AppSettings["units"] })}
                    style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "5px 8px", color: "var(--text-primary)", fontSize: 12 }}
                  >
                    <option value="imperial">Imperial</option>
                    <option value="metric">Metric</option>
                  </select>
                </div>
                <div style={{ ...ROW_STYLE, marginBottom: 0 }}>
                  <span style={{ color: "var(--text-secondary)" }}>Workspace that reopens on launch</span>
                  <span className="mono" style={{ color: "var(--text-primary)" }}>{manifest.name}</span>
                </div>
              </div>

              <div style={PANEL_STYLE}>
                <div style={PANEL_TITLE_STYLE}>Workspace — {manifest.name}</div>
                <div style={{ ...ROW_STYLE, marginBottom: 0 }}>
                  <span style={{ color: "var(--text-secondary)" }}>Anonymize by default</span>
                  <input
                    type="checkbox"
                    checked={workspaceSettings.anonymize_by_default}
                    disabled={manifest.id === "legacy"}
                    onChange={(e) => updateWorkspaceSettings({ anonymize_by_default: e.target.checked })}
                  />
                </div>
              </div>
            </div>

            {/* Spec 14 v0.12 §5.2 — local server only; renders nothing otherwise. */}
            <DataLocationPanel panelStyle={PANEL_STYLE} titleStyle={PANEL_TITLE_STYLE} />

            <div style={PANEL_STYLE}>
              <div style={{ ...PANEL_TITLE_STYLE, marginBottom: 4 }}>Chart presets</div>
              <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 14 }}>
                One set for the whole app, shared across workspaces (Spec 07 §6.1). Create a new preset from the Flight view's "Save as preset…" — this is where you rename, reorder, delete, or duplicate a shipped one afterward.
              </div>

              <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, color: "var(--text-tertiary)", marginBottom: 8 }}>
                SHIPPED
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 16 }}>
                {shippedPresets.map((p) => (
                  <div key={p.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12, padding: "6px 0", borderBottom: "1px solid var(--border-subtle)" }}>
                    <div>
                      <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{p.label}</span>
                      <span style={{ color: "var(--text-tertiary)", marginLeft: 8 }}>{p.channels.length} channel{p.channels.length === 1 ? "" : "s"}</span>
                    </div>
                    <button
                      onClick={() => duplicatePreset(p)}
                      disabled={usingFixture}
                      style={{ padding: "3px 10px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", fontSize: 11, cursor: usingFixture ? "default" : "pointer", opacity: usingFixture ? 0.5 : 1 }}
                    >
                      Duplicate
                    </button>
                  </div>
                ))}
              </div>

              <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, color: "var(--text-tertiary)", marginBottom: 8 }}>
                YOURS
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {userPresets.map((p, i) => (
                  <div key={p.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12, padding: "6px 0", borderBottom: "1px solid var(--border-subtle)" }}>
                    {editingPresetId === p.id ? (
                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexGrow: 1 }}>
                        <input
                          autoFocus
                          type="text"
                          value={presetDraft}
                          onChange={(e) => setPresetDraft(e.target.value)}
                          onKeyDown={(e) => e.key === "Enter" && confirmRename(p)}
                          style={{ flexGrow: 1, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "4px 8px", color: "var(--text-primary)", fontSize: 12 }}
                        />
                        <button
                          onClick={() => confirmRename(p)}
                          disabled={!presetDraft.trim()}
                          style={{ padding: "3px 10px", borderRadius: 6, background: "var(--accent)", border: "none", color: "var(--bg)", fontSize: 11, fontWeight: 600, cursor: presetDraft.trim() ? "pointer" : "default" }}
                        >
                          Save
                        </button>
                        <button
                          onClick={() => { setEditingPresetId(null); setPresetError(null); }}
                          style={{ padding: "3px 10px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", fontSize: 11, cursor: "pointer" }}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <>
                        <div>
                          <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{p.label}</span>
                          <span style={{ color: "var(--text-tertiary)", marginLeft: 8 }}>{p.channels.length} channel{p.channels.length === 1 ? "" : "s"}</span>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <button onClick={() => movePreset(i, -1)} disabled={i === 0} style={{ background: "none", border: "none", color: i === 0 ? "var(--text-tertiary)" : "var(--text-secondary)", cursor: i === 0 ? "default" : "pointer", fontSize: 12, opacity: i === 0 ? 0.4 : 1 }} title="Move up">↑</button>
                          <button onClick={() => movePreset(i, 1)} disabled={i === userPresets.length - 1} style={{ background: "none", border: "none", color: i === userPresets.length - 1 ? "var(--text-tertiary)" : "var(--text-secondary)", cursor: i === userPresets.length - 1 ? "default" : "pointer", fontSize: 12, opacity: i === userPresets.length - 1 ? 0.4 : 1 }} title="Move down">↓</button>
                          <a href="#" onClick={(e) => { e.preventDefault(); startRename(p); }} style={{ fontSize: 11, color: "var(--text-tertiary)" }}>Rename</a>
                          <a href="#" onClick={(e) => { e.preventDefault(); deletePreset(p.id); }} style={{ fontSize: 11, color: "var(--text-tertiary)" }}>Delete</a>
                        </div>
                      </>
                    )}
                  </div>
                ))}
                {userPresets.length === 0 && (
                  <div style={{ fontSize: 12, color: "var(--text-tertiary)", padding: "6px 0" }}>
                    No presets of your own yet — save one from the Flight view, or duplicate a shipped preset above.
                  </div>
                )}
              </div>
              {presetError && (
                <div style={{ fontSize: 11, color: "var(--severity-limit)", marginTop: 8 }}>{presetError}</div>
              )}
            </div>

            <div style={PANEL_STYLE}>
              <div style={PANEL_TITLE_STYLE}>Export &amp; import</div>
              <div style={{ display: "flex", gap: 24 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8 }}>
                    Export this workspace as a portable bundle — for backup, or to open on another device.
                  </div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <select
                      value={exportScope}
                      onChange={(e) => setExportScope(e.target.value as typeof exportScope)}
                      style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px", color: "var(--text-secondary)", fontSize: 12 }}
                    >
                      <option value="full_workspace">Full workspace</option>
                      <option value="single_flight">Single flight</option>
                    </select>
                    <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--text-secondary)" }}>
                      <input type="checkbox" checked={exportAnonymize} onChange={(e) => setExportAnonymize(e.target.checked)} /> Anonymize
                    </label>
                    <button
                      title="export_bundle isn't implemented yet (Spec 02 §7) — the CLI's export-bundle subcommand is the same stub"
                      style={{ padding: "6px 14px", borderRadius: 6, background: "var(--accent)", border: "none", color: "var(--bg)", fontSize: 12, fontWeight: 600, cursor: "pointer", opacity: 0.6 }}
                      disabled
                    >
                      Export
                    </button>
                  </div>
                </div>
                <div style={{ width: 1, background: "var(--border)" }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8 }}>
                    Import a bundle — opens as a preview first; nothing merges until you confirm (Spec 03 §5.8).
                  </div>
                  <button
                    title="bundle preview isn't implemented yet"
                    style={{ padding: "6px 14px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-primary)", fontSize: 12, cursor: "pointer", opacity: 0.6 }}
                    disabled
                  >
                    Choose bundle file…
                  </button>
                </div>
              </div>
            </div>
          </>
        )}

        <div style={PANEL_STYLE}>
          <div style={PANEL_TITLE_STYLE}>
            Changelog {changelog.length > 0 && <span style={{ color: "var(--text-tertiary)", fontWeight: 400 }}>({changelog.length})</span>}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 10 }}>
            Every change made in any Settings tab, newest first.
          </div>
          {changelog.length === 0 ? (
            <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>No changes yet.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {changelog.map((e) => (
                <div key={e.id} className="mono" style={{ fontSize: 11, color: "var(--text-secondary)", display: "flex", gap: 10 }}>
                  <span style={{ color: "var(--text-tertiary)", flexShrink: 0 }}>{e.at.slice(0, 10)}</span>
                  <span style={{ flexShrink: 0, color: "var(--text-tertiary)" }}>[{TAB_LABELS[e.tab as TabId] ?? e.tab}]</span>
                  <span>
                    {e.setting}: {JSON.stringify(e.before)} &rarr; {JSON.stringify(e.after)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {unpinTarget && (
        <UnpinConfirmDialog
          metricLabel={unpinTarget}
          preview={unpinPreview}
          onCancel={() => setUnpinTarget(null)}
          onConfirm={async () => {
            const metricId = unpinTarget;
            setUnpinTarget(null);
            const updated = await client.clearReference(metricId);
            setDraftBaselineConfig((prev) => ({ ...prev, pinned_references: updated.pinned_references }));
            setFleet((f) => ({ ...f, provenance: { ...f.provenance, baseline_config: { ...f.provenance.baseline_config, pinned_references: updated.pinned_references } } }));
          }}
        />
      )}
    </NavShell>
  );
}
