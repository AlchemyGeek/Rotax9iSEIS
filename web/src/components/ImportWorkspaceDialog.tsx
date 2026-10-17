import { useState } from "react";
import { getEngineClient } from "../lib/engineClient";
import { carriesText, finishImport, matchText, plural } from "../lib/importWorkspace";
import type { ImportMatchResult, WorkspaceExportSource, WorkspaceExportSummary } from "../types/contract";

// Spec 03 v0.20 §5.8 — Import workspace, a modal flow (behaviour: Spec 02
// v0.13 §7.4–7.7). Choose → summary (engine check) → name → then either
// the match result (an unzipped export folder's logs/ is linked
// automatically) and the ordinary Sync confirmation on Flights, or — no
// logs/ — an empty workspace. There is no step for linking other folders.
// An import always creates a new workspace; nothing is created before Name.

const client = getEngineClient();

type Step = "choose" | "name" | "match" | "empty";

async function fileToBase64(f: File): Promise<string> {
  const bytes = new Uint8Array(await f.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

const INPUT: React.CSSProperties = { fontSize: 12, padding: "6px 8px", borderRadius: 6, background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text-primary)", flexGrow: 1 };
const BUTTON_BASE: React.CSSProperties = { padding: "6px 12px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", fontSize: 12, cursor: "pointer" };
const PRIMARY_BASE: React.CSSProperties = { ...BUTTON_BASE, background: "var(--accent)", border: "none", color: "var(--bg)", fontWeight: 600 };
// A disabled button has to look it, or a click that does nothing reads as a fault.
const BUTTON = (disabled = false): React.CSSProperties => ({ ...BUTTON_BASE, ...(disabled ? { opacity: 0.45, cursor: "default" } : {}) });
const PRIMARY = (disabled = false): React.CSSProperties => ({ ...PRIMARY_BASE, ...(disabled ? { opacity: 0.45, cursor: "default" } : {}) });

export function ImportWorkspaceDialog({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState<Step>("choose");
  const [path, setPath] = useState("");
  const [source, setSource] = useState<WorkspaceExportSource | null>(null);
  const [summary, setSummary] = useState<WorkspaceExportSummary | null>(null);
  const [name, setName] = useState("");
  const [linked, setLinked] = useState<string | null>(null);
  const [match, setMatch] = useState<ImportMatchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  }

  async function inspect(src: WorkspaceExportSource) {
    const s = await run(() => client.inspectWorkspaceExport(src));
    if (!s) return;
    setSource(src);
    setSummary(s);
    setName(`${s.workspace_name} (imported)`);
  }

  async function create() {
    if (!source) return;
    const res = await run(() => client.importWorkspace(source, name.trim() || undefined));
    if (!res) return;
    if (res.logs_linked) {
      setLinked(summary?.logs_folder ?? "logs/");
      await rematch();
    } else {
      setStep("empty");
    }
  }

  async function rematch() {
    const m = await run(() => client.matchImport());
    if (m) {
      setMatch(m);
      setStep("match");
    }
  }

  return (
    <div role="dialog" aria-label="Import workspace" style={{ position: "fixed", inset: 0, zIndex: 900, background: "rgba(0,0,0,0.55)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div style={{ background: "var(--panel)", borderRadius: 12, padding: "18px 22px", width: 560, maxWidth: "100%", maxHeight: "90vh", overflowY: "auto", display: "flex", flexDirection: "column", gap: 12, color: "var(--text-primary)" }}>
        <div style={{ fontSize: 15, fontWeight: 600 }}>Import workspace</div>

        {step === "choose" && (
          <>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              Enter the folder you unzipped from an export: its logs are linked automatically. Or choose an <span className="mono">.eisworkspace</span> file — without a logs folder the new workspace starts empty. Nothing you already have changes.
            </div>
            <label style={{ fontSize: 12, display: "flex", flexDirection: "column", gap: 4 }}>
              Export file
              <input
                type="file"
                accept=".eisworkspace"
                aria-label="Export file"
                disabled={busy}
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  if (f) await inspect({ content_base64: await fileToBase64(f), filename: f.name });
                }}
              />
            </label>
            <div style={{ display: "flex", gap: 6 }}>
              <input
                aria-label="Export folder or file path"
                placeholder="/Users/you/Downloads/N117ZS"
                className="mono"
                value={path}
                onChange={(e) => setPath(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && path.trim() && !busy && void inspect({ path: path.trim() })}
                style={INPUT}
              />
              <button type="button" style={BUTTON(busy || !path.trim())} disabled={busy || !path.trim()} onClick={() => inspect({ path: path.trim() })}>Open</button>
            </div>
            {summary && (
              <div data-testid="import-summary" style={{ background: "var(--bg)", borderRadius: 8, padding: "10px 12px", fontSize: 12, display: "flex", flexDirection: "column", gap: 4 }}>
                <div style={{ fontWeight: 600 }}>{summary.workspace_name}</div>
                <div>{summary.engine_model} · engine {summary.engine_version}</div>
                <div>
                  {plural(summary.flight_count, "flight")}
                  {summary.date_range && `, ${summary.date_range[0]} to ${summary.date_range[1]}`}
                </div>
                <div>Carries {carriesText(summary.carries)}.</div>
                <div>
                  {summary.logs_folder
                    ? `Logs included${summary.anonymised ? ", anonymised" : ""} — linked from this folder.`
                    : "No logs folder here — the workspace will start empty."}
                </div>
                {summary.engine_check.message && (
                  <div role={summary.engine_check.ok ? "status" : "alert"} style={{ color: summary.engine_check.ok ? "var(--severity-watch)" : "var(--severity-limit)", marginTop: 4 }}>
                    {summary.engine_check.message}
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {step === "name" && (
          <label style={{ fontSize: 12, display: "flex", flexDirection: "column", gap: 4 }}>
            Name for the new workspace
            <input aria-label="Workspace name" value={name} onChange={(e) => setName(e.target.value)} style={INPUT} />
          </label>
        )}

        {step === "match" && linked && (
          <div data-testid="linked-folders" className="mono" style={{ fontSize: 11, color: "var(--text-primary)" }}>
            <span style={{ color: "var(--accent)" }}>✓</span> Linked {linked}
          </div>
        )}

        {step === "empty" && (
          <div data-testid="import-empty" style={{ fontSize: 12, color: "var(--text-secondary)" }}>
            The workspace is created, empty: this export has no logs folder. It lists the sender's flights, and its
            analysis appears once their logs are added (Flights → Add logs…).
          </div>
        )}

        {step === "match" && match && (
          <div data-testid="match-result" style={{ fontSize: 12, display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ fontWeight: 600 }}>{matchText(match)}</div>
            {match.missing.length > 0 && (
              <details>
                <summary>{plural(match.missing.length, "missing flight")} — ask the sender for these logs</summary>
                {match.missing.map((m) => (
                  <div key={m.flight_id} className="mono" style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                    {m.date ?? "—"} {m.airport_hint ?? ""} {m.sender_filename ?? ""}
                  </div>
                ))}
              </details>
            )}
            {match.extra.length > 0 && (
              <details>
                <summary>{plural(match.extra.length, "other log")} held out — not in the sender's workspace (you can include them from Skipped)</summary>
                {match.extra.map((x) => (
                  <div key={x.filename} className="mono" style={{ fontSize: 11, color: "var(--text-secondary)" }}>{x.filename}</div>
                ))}
              </details>
            )}
          </div>
        )}

        {error && <div role="alert" style={{ fontSize: 12, color: "var(--severity-limit)" }}>{error}</div>}

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          {step === "choose" && <button type="button" style={BUTTON()} onClick={onClose}>Cancel</button>}
          {step === "choose" && summary?.engine_check.ok && (
            <button type="button" style={PRIMARY(busy)} disabled={busy} onClick={() => setStep("name")}>Continue</button>
          )}
          {step === "name" && (
            <button type="button" style={PRIMARY(busy || !name.trim())} disabled={busy || !name.trim()} onClick={create}>Create workspace</button>
          )}
          {step === "match" && (
            <button type="button" style={PRIMARY(busy)} disabled={busy} onClick={() => finishImport(true)}>Continue</button>
          )}
          {step === "empty" && (
            <button type="button" style={PRIMARY()} onClick={() => finishImport(false)}>Open workspace</button>
          )}
        </div>
      </div>
    </div>
  );
}
