import { useEffect, useState } from "react";
import { getEngineClient } from "../lib/engineClient";
import type { FolderPicking } from "../lib/browserClient";
import { resetApp } from "../lib/appReset";
import type { StorageUsage } from "../types/contract";

// Spec 14 v0.16 §5.2.1 — Settings → App → Storage (browser host): how much
// the workspaces take, whether the browser has agreed to keep them, a way
// to keep a copy, and a way to remove everything from this device.

const client = getEngineClient();
const BUTTON: React.CSSProperties = { padding: "6px 12px", borderRadius: 6, background: "var(--panel-control)", border: "1px solid var(--border)", color: "var(--text-primary)", fontSize: 12, cursor: "pointer" };

function size(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

export function StoragePanel({ panelStyle, titleStyle }: { panelStyle: React.CSSProperties; titleStyle: React.CSSProperties }) {
  const [usage, setUsage] = useState<StorageUsage | null>(null);
  const [persisted, setPersisted] = useState<boolean | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    client.getStorageUsage().then(setUsage, () => setUsage(null));
    navigator.storage?.persisted?.().then(setPersisted, () => setPersisted(null));
  }, []);

  async function exportAll() {
    setBusy("export");
    setMessage(null);
    try {
      const active = await client.getActiveWorkspace();
      const workspaces = await client.listWorkspaces();
      for (const w of workspaces) {
        await client.switchWorkspace(w.id);
        const res = await client.exportWorkspace({ include_logs: true, anonymise: false });
        const a = document.createElement("a");
        a.href = client.downloadUrl(res.download_url);
        a.download = res.filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
      }
      if (active.active && active.manifest) await client.switchWorkspace(active.manifest.id);
      setMessage(`${workspaces.length} workspace${workspaces.length === 1 ? "" : "s"} exported, one file each.`);
    } catch (e) {
      setMessage(`Export stopped: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(null);
    }
  }

  async function deleteAll() {
    setBusy("delete");
    try {
      await (client as unknown as FolderPicking).deleteAllData();
      setBusy(null);
      setConfirming(false);
      // The first-run state, without a reload (Spec 14 v0.17 §5.2.1).
      window.location.hash = "#/flights";
      resetApp();
    } catch (e) {
      setMessage(`Couldn't delete: ${e instanceof Error ? e.message : String(e)}`);
      setBusy(null);
    }
  }

  const count = usage?.workspace_count ?? 0;
  return (
    <div style={panelStyle} data-testid="storage-panel">
      <div style={titleStyle}>Storage</div>
      <div style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: 8 }}>
        <div>
          <span style={{ color: "var(--text-tertiary)" }}>Space used: </span>
          <span className="mono">{usage ? size(usage.total_bytes) : "—"}</span>
          {usage && usage.workspaces.length > 0 && <span aria-hidden> · </span>}
          {usage && usage.workspaces.length > 0 && (
            <button type="button" onClick={() => setExpanded((v) => !v)} style={{ marginLeft: 8, background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer", fontSize: 11 }}>
              {expanded ? "hide" : "per workspace"}
            </button>
          )}
        </div>
        {expanded && usage && (
          <div style={{ display: "flex", flexDirection: "column", gap: 2, paddingLeft: 10 }}>
            {usage.workspaces.map((w) => (
              <div key={w.id} className="mono" style={{ fontSize: 11 }}>{w.name}: {size(w.bytes)}</div>
            ))}
          </div>
        )}
        <div data-testid="storage-persistent">
          {persisted
            ? "The browser has agreed to keep this data."
            : "The browser may clear this data if space runs low — export a copy to be safe."}
        </div>
        <div style={{ color: "var(--text-tertiary)", fontSize: 11 }}>
          Your logs stay in your own folders and are never stored here.
        </div>
        <span style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button type="button" style={BUTTON} disabled={busy != null || count === 0} onClick={exportAll}>
            {busy === "export" ? "Exporting…" : "Export all workspaces…"}
          </button>
          {!confirming ? (
            <button type="button" style={{ ...BUTTON, color: "var(--severity-limit)" }} disabled={busy != null} onClick={() => setConfirming(true)}>
              Delete all data on this device
            </button>
          ) : (
            <span role="dialog" aria-label="Delete all data" style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <span>Delete {count} workspace{count === 1 ? "" : "s"} from this device? Your log folders aren't touched.</span>
              <button type="button" style={{ ...BUTTON, color: "var(--severity-limit)" }} disabled={busy != null} onClick={deleteAll}>
                {busy === "delete" ? "Deleting…" : "Delete"}
              </button>
              <button type="button" style={BUTTON} disabled={busy != null} onClick={() => setConfirming(false)}>Cancel</button>
            </span>
          )}
        </span>
        {message && <div role="status">{message}</div>}
      </div>
    </div>
  );
}
