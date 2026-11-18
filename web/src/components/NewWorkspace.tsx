import { useRef, useState } from "react";
import { resetApp } from "../lib/appReset";
import type { FolderPicking } from "../lib/browserClient";
import { useCapabilities } from "../lib/capabilities";
import { getEngineClient } from "../lib/engineClient";
import { canKeepFolders } from "../lib/pageFolders";

// Spec 16 D18 — three ways to start a workspace, side by side: Create from
// logs, Import a workspace, Load from a folder. The first-workspace page
// (Flights with no workspace) and + New workspace both show this.

// Mirrors slingology_eis/workspace.py's ENGINE_MODELS.
export const ENGINE_MODELS = ["912iS", "915iS", "916iS"];
export const WEBSITE_APP_URL = "https://alchemygeek.github.io/Rotax9iSEIS/app/";

const FIELD: React.CSSProperties = { background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 8px", color: "var(--text-primary)", fontSize: 12 };
const CARD: React.CSSProperties = { flex: "1 1 220px", minWidth: 220, background: "var(--panel-control)", border: "1px solid var(--border)", borderRadius: 10, padding: "14px 16px", display: "flex", flexDirection: "column", gap: 8 };
const TITLE: React.CSSProperties = { fontSize: 14, fontWeight: 700 };
const TEXT: React.CSSProperties = { fontSize: 12, color: "var(--text-secondary)", flexGrow: 1 };
const PRIMARY: React.CSSProperties = { alignSelf: "flex-start", padding: "6px 14px", borderRadius: 6, background: "var(--brand)", border: "none", color: "var(--on-brand)", fontSize: 12, fontWeight: 600, cursor: "pointer" };
const SECONDARY: React.CSSProperties = { ...PRIMARY, background: "transparent", border: "1px solid var(--border)", color: "var(--text-primary)" };

/** Can this browser open a folder at all (kept, or for this visit)? */
function folderInputSupported(): boolean {
  return typeof document !== "undefined" && "webkitdirectory" in document.createElement("input");
}

const baseName = (path: string) => path.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || path;

export function NewWorkspaceChoices({ first, onImport }: { first?: boolean; onImport: () => void }) {
  const caps = useCapabilities();
  const client = getEngineClient();
  const byPath = caps ? caps.features.add_folder_by_path : true;
  const onWebsite = caps?.features.move_workspace === true;
  const pageFolders = caps?.features.choose_folder ? (client as unknown as FolderPicking) : null;
  const keeps = canKeepFolders();
  const folderInput = folderInputSupported();

  const [name, setName] = useState("");
  const [engine, setEngine] = useState("916iS");
  const [tail, setTail] = useState("");
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dirInput = useRef<HTMLInputElement>(null);

  async function create(fallbackName?: string) {
    const n = name.trim() || fallbackName || "";
    if (!n) throw new Error("Give the workspace a name — the aircraft's, say.");
    await client.createWorkspace(n, engine, tail.trim() || undefined);
  }

  async function run(label: string, work: () => Promise<void>) {
    setError(null);
    setBusy(label);
    try {
      await work();
    } catch (e) {
      if ((e as Error)?.name === "AbortError") { setBusy(null); return; }
      setError(e instanceof Error ? e.message : String(e));
      setBusy(null);
    }
  }

  // Flights then shows the folder and the Analyze button (or the drop zone).
  // A reload is the blunt guarantee every view rereads the new workspace;
  // a folder picked in this page lives in its memory, so it remounts instead.
  const open = (keepPage: boolean) => {
    window.location.hash = "#/flights";
    if (keepPage) resetApp();
    else window.location.reload();
  };

  const fromLogs = () => run("logs", async () => { await create(); open(false); });

  const fromPath = () => run("folder", async () => {
    if (!path.trim()) throw new Error("Type the folder's path — where you keep the logs.");
    await create(baseName(path.trim()));
    await client.addLogFolder(path.trim());
    open(false);
  });

  const fromPicker = () => run("folder", async () => {
    // Picked first: the click is the gesture the browser asks for.
    const picked = await pageFolders!.pickFolder();
    await create(picked.name);
    await pageFolders!.registerPickedFolder(picked);
    open(true);
  });

  async function fromFolderInput(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (!files.length || !pageFolders) return;
    const top = (files[0] as File & { webkitRelativePath?: string }).webkitRelativePath?.split("/")[0];
    await run("folder", async () => {
      await create(top);
      await pageFolders.addFolderFiles(files);
      open(true);
    });
  }

  let folderBody: React.ReactNode;
  if (byPath) {
    folderBody = (
      <>
        <input aria-label="Folder path" placeholder="/path/to/logs" className="mono" value={path} onChange={(e) => setPath(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void fromPath()} style={{ ...FIELD, fontSize: 11 }} data-testid="new-ws-folder-path" />
        <button type="button" style={PRIMARY} disabled={busy !== null} onClick={() => void fromPath()} data-testid="new-ws-folder">
          {busy === "folder" ? "Loading…" : "Load folder"}
        </button>
      </>
    );
  } else if (pageFolders && (keeps || folderInput)) {
    folderBody = (
      <>
        {!keeps && <span style={{ ...TEXT, flexGrow: 0, fontSize: 11 }}>This browser opens the folder for this visit; you choose it again to sync new logs.</span>}
        <input ref={dirInput} type="file" multiple hidden onChange={(e) => void fromFolderInput(e)}
          {...({ webkitdirectory: "", directory: "" } as Record<string, string>)} data-testid="new-ws-folder-input" />
        <button type="button" style={PRIMARY} disabled={busy !== null} data-testid="new-ws-folder"
          onClick={() => (keeps ? void fromPicker() : dirInput.current?.click())}>
          {busy === "folder" ? "Loading…" : "Choose folder…"}
        </button>
      </>
    );
  } else {
    folderBody = (
      <>
        <span style={{ ...TEXT, flexGrow: 0 }} data-testid="new-ws-no-folder">
          This browser can't open a folder. Choose the log files instead — or use Chrome, Edge or Safari on a computer, which can.
        </span>
        <button type="button" style={SECONDARY} disabled={busy !== null} onClick={() => void fromLogs()} data-testid="new-ws-folder-files">
          Choose files instead
        </button>
      </>
    );
  }

  return (
    <div data-testid="new-workspace" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {first && (
        <div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>Your first workspace</div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>A workspace is one aircraft's logs, its analyses and your decisions about them. Start it one of three ways.</div>
        </div>
      )}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <input autoFocus={!first} placeholder="Workspace name" aria-label="Workspace name" value={name} onChange={(e) => setName(e.target.value)} style={{ ...FIELD, width: 220 }} />
        <select aria-label="Engine model" value={engine} onChange={(e) => setEngine(e.target.value)} style={FIELD}>
          {ENGINE_MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <input placeholder="Tail number (optional)" aria-label="Tail number" value={tail} onChange={(e) => setTail(e.target.value)} style={{ ...FIELD, width: 170 }} />
        <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>The engine decides which Operators Manual limits apply; it can't be changed later.</span>
      </div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <div style={CARD} data-testid="new-ws-logs-card">
          <div style={TITLE}>Create from logs</div>
          <div style={TEXT}>
            Pick or drop your log files{byPath ? ", or add the folder you keep them in" : ""}. Garmin G3X, Garmin AXIS SD card, or the aircraft log from flyGarmin.
          </div>
          <button type="button" style={PRIMARY} disabled={busy !== null} onClick={() => void fromLogs()} data-testid="new-ws-create">
            {busy === "logs" ? "Creating…" : "Create"}
          </button>
        </div>
        <div style={CARD} data-testid="new-ws-import-card">
          <div style={TITLE}>Import a workspace</div>
          <div style={TEXT}>
            A workspace export — a <span className="mono">.zip</span> or <span className="mono">.eisworkspace</span> — from another computer, or from someone sharing theirs. Its name comes with it.
          </div>
          {!onWebsite && (
            // Spec 16 D17: the first run on this computer points back to the website's button.
            <div style={{ fontSize: 11, color: "var(--text-tertiary)" }} data-testid="move-mirror">
              Been using the website? Open it and press <em>Move my workspace</em>.{" "}
              <a href={WEBSITE_APP_URL} target="_blank" rel="noreferrer">Open the website</a>
            </div>
          )}
          <button type="button" style={SECONDARY} disabled={busy !== null} onClick={onImport} data-testid="new-ws-import">Import workspace…</button>
        </div>
        <div style={CARD} data-testid="new-ws-folder-card">
          <div style={TITLE}>Load from a folder</div>
          <div style={TEXT}>
            Point at the folder you keep your logs in: EIS reads every log in it, subfolders included, and keeps reading it as you add more. The folder holds logs — not another EIS workspace.
          </div>
          {folderBody}
        </div>
      </div>
      {error && <div role="alert" style={{ fontSize: 12, color: "var(--severity-warning)" }} data-testid="new-ws-error">{error}</div>}
    </div>
  );
}

/** + New workspace, with a workspace already open: the same three, in a dialog. */
export function NewWorkspaceDialog({ onClose, onImport }: { onClose: () => void; onImport: () => void }) {
  return (
    <div role="dialog" aria-label="New workspace" data-testid="new-workspace-dialog"
      style={{ position: "fixed", inset: 0, zIndex: 50, background: "rgba(0,0,0,0.55)", display: "flex", alignItems: "flex-start", justifyContent: "center", paddingTop: 80 }}
      onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 14, padding: "18px 20px", width: "min(920px, 94vw)", boxShadow: "0 12px 40px rgba(0,0,0,0.5)" }}>
        <div style={{ display: "flex", alignItems: "center", marginBottom: 12 }}>
          <div style={{ fontSize: 16, fontWeight: 700, flexGrow: 1 }}>New workspace</div>
          <button type="button" aria-label="Close" onClick={onClose} style={{ background: "none", border: "none", color: "var(--text-secondary)", fontSize: 18, cursor: "pointer" }}>×</button>
        </div>
        <NewWorkspaceChoices onImport={onImport} />
      </div>
    </div>
  );
}
