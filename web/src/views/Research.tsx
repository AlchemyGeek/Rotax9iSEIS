import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { NavShell, DOCS_URL } from "../components/NavShell";
import { EngineRpcError, getEngineClient } from "../lib/engineClient";
import type { StudySummary } from "../types/contract";
import { Inbox } from "../components/research/Inbox";
import { MoveWorkspaceBanner } from "../components/MoveWorkspace";
import { BODY, BUTTON, LINK, MUTED, NOTICE, PANEL, PANEL_TITLE } from "../components/research/ui";

const client = getEngineClient();

// Spec 16 D15 — Research home is the notebooks and the inbox: Claude
// investigates, EIS measures. The user looks and marks in EIS (the Flight
// view), asks in Claude Desktop, and reads the notebook here. The hand
// studies, presets-to-study and the question forms are retired (Spec 06
// v1.0); nothing here changes Flights, Trends or Journal.

const KIND: React.CSSProperties = { fontSize: 10, fontWeight: 700, letterSpacing: 0.3, color: "var(--text-tertiary)", textTransform: "uppercase" };

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function Research() {
  const navigate = useNavigate();
  const [studies, setStudies] = useState<StudySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [noWorkspace, setNoWorkspace] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importNote, setImportNote] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    try {
      const s = await client.listStudies();
      setStudies(s.studies);
      setNoWorkspace(false);
    } catch (e) {
      if (e instanceof EngineRpcError && e.code === "NO_ACTIVE_WORKSPACE") setNoWorkspace(true);
      else setError(e instanceof Error ? e.message : String(e));
      setStudies([]);
    }
  }
  useEffect(() => { void load(); }, []);

  async function onImportFile(file: File) {
    setImporting(true);
    setImportNote(null);
    try {
      // Spec 16 §5.1: a notebook — cells whose flights are absent are read-only.
      const res = await client.importStudy(file);
      const ro = res.notebook.cells.filter((c) => c.metadata?.slingology?.read_only).length;
      setImportNote(ro ? `Imported the notebook: ${ro} cell${ro === 1 ? "" : "s"} name flights not in this workspace and show the sender's outputs.` : "Imported the notebook.");
      await load();
      navigate(`/research/${res.study_id}`);
    } catch (e) {
      setImportNote(e instanceof Error ? e.message : String(e));
    } finally {
      setImporting(false);
    }
  }

  return (
    <NavShell>
      <div style={{ width: "100%", overflowY: "auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>Research</h1>
          <span style={BODY} data-testid="research-model">
            Claude investigates; EIS measures. Look at a flight and mark what looks odd, ask in Claude Desktop, and read the notebook here.{" "}
            <a href={`${DOCS_URL}concepts/research/`} target="_blank" rel="noopener noreferrer" style={LINK}>How it works</a>
          </span>
          <span style={{ flexGrow: 1 }} />
          <input ref={fileRef} type="file" accept=".zip,.ipynb" style={{ display: "none" }} data-testid="import-study-input"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void onImportFile(f); e.target.value = ""; }} />
          <button type="button" onClick={() => fileRef.current?.click()} style={BUTTON} disabled={importing || noWorkspace} title="A notebook's .zip or an .ipynb">{importing ? "Importing…" : "Import a notebook…"}</button>
        </div>

        {noWorkspace && <div style={NOTICE}>Open or create a workspace first — Research works on the flights of the active workspace.</div>}
        {error && <div style={{ ...NOTICE, color: "var(--severity-warning)" }}>{error}</div>}
        {importNote && <div style={NOTICE}>{importNote}</div>}

        {!noWorkspace && <MoveWorkspaceBanner />}
        {!noWorkspace && <Inbox />}

        <section style={PANEL}>
          <div style={PANEL_TITLE}>Notebooks {studies && <span style={MUTED}>({studies.length})</span>}</div>
          {studies === null && <div style={MUTED}>Loading…</div>}
          {studies && studies.length === 0 && (
            <div style={BODY}>
              No notebooks yet. Mark a window on a flight for Claude, then ask in Claude Desktop — the investigation is written here as a notebook.
            </div>
          )}
          {studies && studies.length > 0 && (
            <table style={{ width: "100%", borderCollapse: "collapse" }} data-testid="studies-table">
              <tbody>
                {studies.map((s) => (
                  <tr key={s.study_id} style={{ borderBottom: "1px solid var(--border)", cursor: "pointer" }} onClick={() => navigate(`/research/${s.study_id}`)} data-testid="study-row">
                    <td style={{ padding: "9px 8px", fontSize: 13, fontWeight: 600, whiteSpace: "nowrap", verticalAlign: "top" }}>{s.name}</td>
                    <td style={{ padding: "9px 8px", whiteSpace: "nowrap", verticalAlign: "top" }} data-testid="study-kind">
                      <span style={KIND} title="A notebook (Jupyter .ipynb)">{s.author === "claude" ? "Claude" : "you"}{s.status === "finished" ? " · finished" : ""}</span>
                    </td>
                    <td style={{ padding: "9px 8px", fontSize: 12, color: "var(--text-secondary)" }}>
                      {s.finding ?? <span style={MUTED}>{s.question ?? "open"}{s.pending ? ` · ${s.pending} cell${s.pending === 1 ? "" : "s"} pending` : ""}</span>}
                    </td>
                    <td className="mono" style={{ ...MUTED, padding: "9px 8px", whiteSpace: "nowrap", textAlign: "right" }}>{formatWhen(s.updated)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </NavShell>
  );
}
