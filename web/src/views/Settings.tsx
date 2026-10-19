import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { NavShell } from "../components/NavShell";
import { InlineHelp } from "../components/InlineHelp";
import { DataLocationPanel } from "../components/DataLocation";
import { StoragePanel } from "../components/StoragePanel";
import { useCapabilities } from "../lib/capabilities";
import { ImportWorkspaceDialog } from "../components/ImportWorkspaceDialog";
import { UnpinConfirmDialog } from "../components/PinDialogs";
import { bandLabel } from "../lib/bands";
import { EngineRpcError, getEngineClient } from "../lib/engineClient";
import { ScopeCaption } from "../components/ScopeCaption";
import { APPLY_LABEL } from "../lib/scope";
import {
  appSettings as fixtureAppSettings,
  engineLimits as fixtureEngineLimits,
  fleetAnalysis as fixtureFleet,
  workspaceManifest as fixtureManifest,
} from "../lib/fixtures";
import type {
  AppSettings, BaselineConfig, ChartPreset, EngineLimitsResult, FleetAnalysis,
  ChangedSetting, LogChannelRow, RuleSet, UnpinPreview, WorkspaceManifest,
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
// Observed range of a raw channel: whole numbers as they are, others to 0.1.
function fmtRange(v: number) {
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

export function Settings() {
  const caps = useCapabilities();
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
  const [manifest, setManifest] = useState<WorkspaceManifest>(fixtureManifest);
  const [usingFixture, setUsingFixture] = useState(true);
  const [loading, setLoading] = useState(true);
  // Spec 02 v0.11 §7.2: Include logs (default on), Anonymise logs (off).
  const [exportIncludeLogs, setExportIncludeLogs] = useState(true);
  const [exportAnonymise, setExportAnonymise] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [identityMentions, setIdentityMentions] = useState<{ where: string; value: string }[]>([]);
  // Importing needs only a reachable server — not an active workspace,
  // which a fresh install (the usual importer) doesn't have yet.
  const [serverReachable, setServerReachable] = useState(false);
  useEffect(() => {
    client.listWorkspaces().then(() => setServerReachable(true), () => setServerReachable(false));
  }, []);

  // Spec 02 v0.12: anonymising doesn't rewrite your own words, so say where
  // the tail number or system ID appears in them before exporting.
  async function chooseAnonymise(on: boolean) {
    setExportAnonymise(on);
    if (!on) {
      setIdentityMentions([]);
      return;
    }
    try {
      setIdentityMentions((await client.previewWorkspaceExport()).identity_mentions);
    } catch {
      setIdentityMentions([]);
    }
  }
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
  // Spec 14 v0.14 §5.3 — raw general-purpose channels and their assignments.
  const [logChannels, setLogChannels] = useState<LogChannelRow[] | null>(null);
  const [assigning, setAssigning] = useState(false);

  async function refreshLogChannels() {
    try {
      setLogChannels((await client.getLogChannels()).channels);
    } catch {
      setLogChannels(null);
    }
  }

  async function assignChannel(raw: string, target: string | null) {
    setAssigning(true);
    try {
      setLogChannels((await client.setChannelAssignment(raw, target)).channels);
      await refreshChangedSettings();
    } catch {
      // server unreachable
    } finally {
      setAssigning(false);
    }
  }

  // Spec 14 §5.1 (v0.3) — n_min is shown here per trigger, read-only; it
  // lives in rules/active.json and is edited on the topic card (§7.3).
  const [rules, setRules] = useState<RuleSet | null>(null);
  // Spec 14 §5.1 (v0.6): topics with a card, enabled or not — the n_min
  // list shows a disabled one marked disabled, and never the ones the
  // engine doesn't surface.
  const [cardTopicIds, setCardTopicIds] = useState<Set<string>>(new Set());

  // Spec 14 v0.13 §5 — no changelog; settings that differ from shipped
  // are marked with the shipped value and a link to their Journal entry.
  const [changedSettings, setChangedSettings] = useState<ChangedSetting[]>([]);

  async function refreshChangedSettings() {
    try {
      const res = await client.listChangedSettings();
      setChangedSettings(res.settings);
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
          client.getFleet(), client.getEngineLimits(),
          // No workspace yet (a first run): no rules to list — not a
          // reason to show the sample settings instead.
          client.getWorkspaceRules().catch((err) => {
            if (err instanceof EngineRpcError && err.code === "NO_ACTIVE_WORKSPACE") return { rules: null, card_topic_ids: [] as string[] };
            throw err;
          }),
        ]);
        if (cancelled) return;
        setAppSettings(app);
        if (active.active && active.manifest && active.settings) {
          setManifest(active.manifest);
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
          const changed = await client.listChangedSettings();
          if (!cancelled) setChangedSettings(changed.settings);
        } catch {
          // non-fatal — values just show unmarked
        }
        try {
          const lc = await client.getLogChannels();
          if (!cancelled) setLogChannels(lc.channels);
        } catch {
          // an older server: the panel stays hidden
        }
      } catch {
        if (!cancelled) {
          setAppSettings(fixtureAppSettings);
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
    } catch {
      // server unreachable — local state already updated, nothing more to do
    }
  }

  async function handleExport() {
    setExporting(true);
    setExportMessage(null);
    try {
      const res = await client.exportWorkspace({ include_logs: exportIncludeLogs, anonymise: exportAnonymise });
      const a = document.createElement("a");
      a.href = client.downloadUrl(res.download_url);
      a.download = res.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setExportMessage(
        `${res.filename}: ${res.flights} flights${res.logs_included ? `, ${res.logs_included} logs` : ""}` +
        (res.logs_included ? ". The recipient unzips it and imports the folder it creates." : ".") +
        (res.notes.length ? ` ${res.notes.join(" ")}` : ""),
      );
    } catch (e) {
      setExportMessage(e instanceof Error ? e.message : "Couldn't export the workspace.");
    } finally {
      setExporting(false);
    }
  }


  const referenceDirty = JSON.stringify(draftBaselineConfig) !== JSON.stringify(fleet.provenance.baseline_config);

  async function saveReference() {
    setSavingReference(true);
    try {
      const newFleet = await client.saveBaselineConfig(draftBaselineConfig);
      setFleet(newFleet);
      setDraftBaselineConfig(clone(newFleet.provenance.baseline_config));
      await refreshChangedSettings();
    } catch {
      // server unreachable — draft stays, nothing applied
    } finally {
      setSavingReference(false);
    }
  }

  async function resetReferenceToShipped() {
    setSavingReference(true);
    try {
      // Every setting back at shipped; the server keeps pinned references
      // (their own Journal decisions, Spec 14 §6.1).
      const newFleet = await client.saveBaselineConfig(DEFAULT_BASELINE_CONFIG);
      setFleet(newFleet);
      setDraftBaselineConfig(clone(newFleet.provenance.baseline_config));
      await refreshChangedSettings();
    } catch {
      // server unreachable
    } finally {
      setSavingReference(false);
    }
  }

  // Spec 14 v0.13: Reset to shipped for one setting, as in Journal.
  async function resetSetting(refId: string) {
    setSavingReference(true);
    try {
      const newFleet = await client.resetSetting(refId);
      setFleet(newFleet);
      setDraftBaselineConfig(clone(newFleet.provenance.baseline_config));
      await refreshChangedSettings();
      if (refId.startsWith("channel_assignment:")) await refreshLogChannels();
    } catch {
      // server unreachable
    } finally {
      setSavingReference(false);
    }
  }

  const changedById = useMemo(() => new Map(changedSettings.map((c) => [c.ref_id, c])), [changedSettings]);

  // The mark beside a changed value: shipped value, its Journal entry,
  // Reset to shipped. Nothing for a value at shipped.
  function changedMark(refId: string) {
    const c = changedById.get(refId);
    if (!c) return null;
    return (
      <div data-testid={`changed-${refId}`} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 11, color: "var(--severity-warning)", marginBottom: 10 }}>
        <span>Changed · shipped: <span className="mono">{c.shipped}</span></span>
        {c.entry_id && (
          <a href="#" onClick={(e) => { e.preventDefault(); navigate(`/journal?entry=${encodeURIComponent(c.entry_id!)}`); }} style={{ fontSize: 11 }}>
            Journal entry →
          </a>
        )}
        <button
          type="button"
          onClick={() => resetSetting(refId)}
          disabled={savingReference}
          style={{ background: "none", border: "none", padding: 0, color: "var(--text-tertiary)", cursor: "pointer", fontSize: 11 }}
        >
          Reset to shipped
        </button>
      </div>
    );
  }

  // Changed settings that have no control of their own on this page
  // (membership, the event-frequency threshold, a weather band set by hand).
  const INLINE_MARKS = new Set(["outlier_z_threshold", "recent_window", "om_margin_fraction"]);
  const otherChanged = changedSettings.filter(
    (c) => !INLINE_MARKS.has(c.ref_id) && !c.ref_id.startsWith("outlier_z_threshold_overrides:") && !c.ref_id.startsWith("channel_assignment:"),
  );

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

  // The sample settings are only for when no server answers; don't flash
  // them before the real ones.
  if (loading) {
    return (
      <NavShell>
        <div style={{ flexGrow: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span style={{ color: "var(--text-tertiary)", fontSize: 13 }}>Loading…</span>
        </div>
      </NavShell>
    );
  }

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
              {caps && (
                // Spec 04 §9.8: the About line names the host.
                <div style={ROW_STYLE} data-testid="engine-host">
                  <span style={{ color: "var(--text-secondary)" }}>Runs</span>
                  <span style={{ color: "var(--text-primary)" }}>{caps.host === "browser" ? "in this browser" : "on the local server"}</span>
                </div>
              )}
              {engineLimits.engine_version && (
                // Spec 14 v0.13 §5: the engine version in effect. Its What's
                // new (Spec 13's generated page) isn't in the app yet.
                <div style={ROW_STYLE}>
                  <span style={{ color: "var(--text-secondary)" }}>Engine version</span>
                  <span className="mono" style={{ color: "var(--text-primary)" }}>{engineLimits.engine_version}</span>
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

            {logChannels && (
              <div style={PANEL_STYLE} data-testid="log-channels">
                <div style={PANEL_TITLE_STYLE}>Log channels<InlineHelp id="engine.log_channels" /></div>
                <div style={{ marginBottom: 10 }}><ScopeCaption scope="workspace" /></div>
                {logChannels.length === 0 ? (
                  <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>No general-purpose channels in this workspace's logs.</div>
                ) : (
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                    <thead>
                      <tr style={{ textAlign: "left", color: "var(--text-tertiary)" }}>
                        <th style={{ fontWeight: 500, padding: "4px 8px 4px 0" }}>Channel</th>
                        <th style={{ fontWeight: 500, padding: "4px 8px" }}>Source</th>
                        <th style={{ fontWeight: 500, padding: "4px 8px" }}>Range seen</th>
                        <th style={{ fontWeight: 500, padding: "4px 8px" }}>Assignment</th>
                      </tr>
                    </thead>
                    <tbody>
                      {logChannels.map((row) => (
                        <tr key={row.raw} data-testid={`log-channel-${row.raw}`} style={{ borderTop: "1px solid var(--border-subtle)", verticalAlign: "top" }}>
                          <td style={{ padding: "6px 8px 6px 0", color: "var(--text-primary)" }}>
                            {row.label} <span className="mono" style={{ fontSize: 10, color: "var(--text-tertiary)" }}>{row.raw}</span>
                          </td>
                          <td style={{ padding: "6px 8px", color: "var(--text-secondary)" }}>
                            {row.sources.join(", ")} · {row.flights} {row.flights === 1 ? "flight" : "flights"}
                          </td>
                          <td className="mono" style={{ padding: "6px 8px", color: "var(--text-secondary)" }}>
                            {row.min == null || row.max == null ? "—" : `${fmtRange(row.min)} – ${fmtRange(row.max)}`}
                          </td>
                          <td style={{ padding: "6px 8px" }}>
                            <select
                              aria-label={`Assignment for ${row.label}`}
                              value={row.assignment?.channel ?? ""}
                              disabled={assigning || usingFixture}
                              onChange={(e) => assignChannel(row.raw, e.target.value || null)}
                              style={{ fontSize: 12 }}
                            >
                              <option value="">Not assigned</option>
                              {row.options.map((o) => (
                                <option key={o.channel} value={o.channel}>{o.name}{o.unit && !o.name.includes(o.unit) ? ` (${o.unit})` : ""}</option>
                              ))}
                            </select>
                            <div style={{ marginTop: 6 }}>{changedMark(`channel_assignment:${row.raw}`)}</div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
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
                {changedMark("outlier_z_threshold") ?? (
                  <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 10 }}>
                    default: 2.0
                  </div>
                )}
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
                      <div key={metric}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12 }}>
                          <span className="mono" style={{ color: "var(--text-secondary)" }}>{metric}: {z}</span>
                          <a href="#" onClick={(e) => { e.preventDefault(); removeOverride(metric); }} style={{ fontSize: 11, color: "var(--text-tertiary)" }}>remove</a>
                        </div>
                        {changedMark(`outlier_z_threshold_overrides:${metric}`)}
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
                {changedMark("recent_window")}
                <label style={{ ...ROW_STYLE, marginBottom: 0 }}>
                  <span style={{ color: "var(--text-secondary)" }}>OM margin fraction</span>
                  {numberInput(draftBaselineConfig.om_margin_fraction, (v) => setDraftBaselineConfig((p) => ({ ...p, om_margin_fraction: v })), { step: 0.05, min: 0, max: 1 })}
                </label>
                <div style={{ marginTop: 8 }}>{changedMark("om_margin_fraction")}</div>
                <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 8 }}>
                  Defaults: 10h &middot; 5 &middot; 15 &middot; 0.25
                </div>
              </div>
            </div>

            {otherChanged.length > 0 && (
              <div style={PANEL_STYLE} data-testid="other-changed-settings">
                <div style={PANEL_TITLE_STYLE}>Other settings changed from shipped</div>
                {otherChanged.map((c) => (
                  <div key={c.ref_id}>
                    <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                      {c.label}: <span className="mono" style={{ color: "var(--text-primary)" }}>{c.current}</span>
                    </div>
                    {changedMark(c.ref_id)}
                  </div>
                ))}
              </div>
            )}

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
                  Browser storage can be evicted, especially in Safari. Allow persistent storage for this site, and export the workspace now and then as a backup.
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

              {/* Spec 02 v0.11 §7.2 / Spec 03 v0.19 §5.7: share the whole
                  workspace; import one as a new workspace. */}
              <div style={PANEL_STYLE} data-testid="workspace-share">
                <div style={PANEL_TITLE_STYLE}>Share a workspace</div>
                <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 10 }}>
                  Export this whole workspace for someone else to open: its settings and decisions, with the logs so they see exactly what you see. To share only some flights, make a workspace with just those logs and export that.
                </div>
                <label style={{ ...ROW_STYLE, justifyContent: "flex-start", gap: 8 }}>
                  <input type="checkbox" checked={exportIncludeLogs} onChange={(e) => { setExportIncludeLogs(e.target.checked); if (!e.target.checked) void chooseAnonymise(false); }} />
                  <span style={{ color: "var(--text-secondary)" }}>Include logs</span>
                </label>
                <label style={{ ...ROW_STYLE, justifyContent: "flex-start", gap: 8, opacity: exportIncludeLogs ? 1 : 0.5 }}>
                  <input type="checkbox" checked={exportAnonymise} disabled={!exportIncludeLogs} onChange={(e) => void chooseAnonymise(e.target.checked)} />
                  <span style={{ color: "var(--text-secondary)" }}>Anonymise logs</span>
                </label>
                <div data-testid="privacy-notice" style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 10 }}>
                  {exportAnonymise
                    ? "The log copies get a pseudonym for the tail number and system ID; GPS position, navigation and radio columns are blanked; file names become neutral. Dates, times and engine hours stay. Your annotation text, filter notes and the workspace name go as written."
                    : "The logs carry your tail number, system ID, dates, times and GPS track unless anonymised. Your annotation text, filter notes and the workspace name go as written."}
                </div>
                {exportAnonymise && identityMentions.length > 0 && (
                  <div data-testid="identity-mentions" role="alert" style={{ fontSize: 11, color: "var(--severity-warning)", marginBottom: 10 }}>
                    Your own text still names the aircraft — anonymising leaves it as written:{" "}
                    {identityMentions.map((m) => `${m.where} (${m.value})`).join(", ")}. Change it first, or export as it is.
                  </div>
                )}
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <button
                    type="button"
                    onClick={handleExport}
                    disabled={exporting || usingFixture || manifest.id === "legacy"}
                    style={{ padding: "6px 14px", borderRadius: 6, background: "var(--accent)", border: "none", color: "var(--bg)", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                  >
                    {exporting ? "Exporting…" : "Export workspace…"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setImporting(true)}
                    disabled={!serverReachable}
                    title={serverReachable ? undefined : "no local server reachable"}
                    style={{ padding: "6px 14px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-primary)", fontSize: 12, cursor: "pointer" }}
                  >
                    Import workspace…
                  </button>
                </div>
                {exportMessage && <div role="status" style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 8 }}>{exportMessage}</div>}
              </div>
            </div>
            {importing && <ImportWorkspaceDialog onClose={() => setImporting(false)} />}

            {/* Spec 14 v0.12 §5.2 — local server only; renders nothing otherwise. */}
            {caps && !caps.features.data_location && caps.features.persistent_storage_status ? (
              // Spec 14 v0.16 §5.2.1: the browser host shows Storage instead.
              <StoragePanel panelStyle={PANEL_STYLE} titleStyle={PANEL_TITLE_STYLE} />
            ) : (
              <DataLocationPanel panelStyle={PANEL_STYLE} titleStyle={PANEL_TITLE_STYLE} />
            )}

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

          </>
        )}

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
