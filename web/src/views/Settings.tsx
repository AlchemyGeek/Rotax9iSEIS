import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { NavShell } from "../components/NavShell";
import { getEngineClient } from "../lib/engineClient";
import {
  appSettings as fixtureAppSettings,
  workspaceManifest as fixtureManifest,
  workspaceSettings as fixtureWorkspaceSettings,
} from "../lib/fixtures";
import type { AppSettings, ChartPreset, WorkspaceManifest, WorkspaceSettings } from "../types/contract";

const client = getEngineClient();

const LEGACY_MANIFEST: WorkspaceManifest = {
  id: "legacy", name: "Workspace (no registry workspace active)", engine_model: "—", log_folders: [],
  schema_version: "", created_at: "", updated_at: "", engine_version_seen: [],
  flight_count: 0, storage_backend: "filesystem",
};

// Spec 03 v0.6 §5.7 — deliberately narrower than the wireframe this was
// drawn from (design/wireframes/Settings.dc.html predates the nav
// correction): the workspace switcher now lives permanently in the nav
// (§4), and the log-folder/rescan/missing-log table is Flights (§5.1).
// Settings doesn't duplicate either — this view is only what's left:
// app-level settings, workspace-level settings, bundle export/import, and
// the storage persistence nudge.
export function Settings() {
  const navigate = useNavigate();
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

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [app, active, chartPresets] = await Promise.all([
          client.getAppSettings(), client.getActiveWorkspace(), client.getChartPresets(),
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
        setUsingFixture(false);
      } catch {
        if (!cancelled) {
          setAppSettings(fixtureAppSettings);
          setWorkspaceSettings(fixtureWorkspaceSettings);
          setManifest(fixtureManifest);
          setShippedPresets([]);
          setUserPresets([]);
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

  async function updateWorkspaceSettings(patch: Partial<WorkspaceSettings>) {
    const next = { ...workspaceSettings, ...patch };
    setWorkspaceSettings(next);
    if (usingFixture || manifest.id === "legacy") return;
    try {
      await client.saveWorkspaceSettings(next);
    } catch {
      // server unreachable — local state already updated, nothing more to do
    }
  }

  return (
    <NavShell>
      <div style={{ flexGrow: 1, overflowY: "auto", padding: "24px 28px", display: "flex", flexDirection: "column", gap: 20 }}>
        <h1 style={{ margin: 0, fontSize: 19, fontWeight: 700 }}>
          Settings {usingFixture && <span style={{ fontSize: 12, fontWeight: 400, color: "var(--text-tertiary)" }}>(sample)</span>}
          {loading && <span style={{ fontSize: 12, fontWeight: 400, color: "var(--text-tertiary)" }}> · loading…</span>}
        </h1>

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
          <div style={{ background: "var(--panel)", borderRadius: 12, padding: "16px 18px" }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>App</div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12, marginBottom: 10 }}>
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
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12 }}>
              <span style={{ color: "var(--text-secondary)" }}>Workspace that reopens on launch</span>
              <span className="mono" style={{ color: "var(--text-primary)" }}>{manifest.name}</span>
            </div>
          </div>

          <div style={{ background: "var(--panel)", borderRadius: 12, padding: "16px 18px" }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Workspace — {manifest.name}</div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12, marginBottom: 10 }}>
              <span style={{ color: "var(--text-secondary)" }}>Engine model</span>
              <span className="mono" style={{ color: "var(--text-primary)" }} title="Locked at creation — changing it isn't an edit, it's a reason to make a new workspace (Spec 02 §5.6)">
                {manifest.engine_model} <span style={{ color: "var(--text-tertiary)" }}>(locked)</span>
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12, marginBottom: 10 }}>
              <span style={{ color: "var(--text-secondary)" }}>Engine overrides</span>
              <a href="#" onClick={(e) => { e.preventDefault(); navigate("/baselines"); }} style={{ fontSize: 12 }}>
                None active — edit in Baselines →
              </a>
            </div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12 }}>
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

        <div style={{ background: "var(--panel)", borderRadius: 12, padding: "18px 20px" }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Chart presets</div>
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

        <div style={{ background: "var(--panel)", borderRadius: 12, padding: "18px 20px" }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Export &amp; import</div>
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
      </div>
    </NavShell>
  );
}
