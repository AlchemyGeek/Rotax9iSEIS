import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { NavShell, DOCS_URL } from "../components/NavShell";
import { EngineRpcError, getEngineClient } from "../lib/engineClient";
import type { StudySummary } from "../types/contract";
import { Inbox } from "../components/research/Inbox";
import { NotebookGrid } from "../components/research/Notebooks";
import { PageHelp } from "../components/research/bits";
import { MoveWorkspaceBanner } from "../components/MoveWorkspace";
import { BODY, BUTTON, LINK, MUTED, NOTICE } from "../components/research/ui";

const client = getEngineClient();

// Spec 03 v0.34 §5.10 (Spec 16 D15) — Research home, top to bottom: the
// header (Research, its help, *Import a notebook…*), the *Move my
// workspace* banner until dismissed, the notebooks as cards, the inbox as a
// digest. The notebook is the page's object; the inbox is its to-do list;
// nothing is expanded until asked. The model sentence is in the help.
// Nothing here changes Flights, Trends or Journal.

const H2: React.CSSProperties = { margin: 0, fontSize: 15, fontWeight: 600 };

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
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>Research</h1>
          <PageHelp testid="research-help">
            <p style={{ margin: "0 0 6px" }} data-testid="research-model">
              <strong>Claude investigates; EIS measures.</strong> Look at a flight and mark what looks odd, ask in Claude Desktop, and read the notebook here.
            </p>
            <p style={{ margin: "0 0 6px" }}>
              Notebooks are Claude's investigations, newest first; the inbox holds your questions with their marks and what EIS raised across the recent flights.
            </p>
            <a href={`${DOCS_URL}concepts/research/`} target="_blank" rel="noopener noreferrer" style={{ ...LINK, fontSize: 12 }}>How it works</a>
          </PageHelp>
          <span style={{ flexGrow: 1 }} />
          <input ref={fileRef} type="file" accept=".zip,.ipynb" style={{ display: "none" }} data-testid="import-study-input"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void onImportFile(f); e.target.value = ""; }} />
          <button type="button" onClick={() => fileRef.current?.click()} style={BUTTON} disabled={importing || noWorkspace} title="A notebook's .zip or an .ipynb">{importing ? "Importing…" : "Import a notebook…"}</button>
        </div>

        {noWorkspace && <div style={NOTICE}>Open or create a workspace first — Research works on the flights of the active workspace.</div>}
        {error && <div style={{ ...NOTICE, color: "var(--severity-warning)" }}>{error}</div>}
        {importNote && <div style={NOTICE}>{importNote}</div>}

        {!noWorkspace && <MoveWorkspaceBanner dismissable />}

        {!noWorkspace && (
          <section style={{ display: "flex", flexDirection: "column", gap: 10 }} data-testid="notebooks">
            <h2 style={H2}>Notebooks {studies && studies.length > 0 && <span style={{ ...MUTED, fontSize: 12, fontWeight: 400 }}>({studies.length})</span>}</h2>
            {studies === null && <div style={MUTED}>Loading…</div>}
            {studies && studies.length === 0 && (
              <div style={BODY} data-testid="notebooks-empty">No notebooks yet. Mark a window on a flight, then ask in Claude Desktop.</div>
            )}
            {studies && studies.length > 0 && <NotebookGrid studies={studies} onChanged={() => void load()} />}
          </section>
        )}

        {!noWorkspace && <Inbox />}
      </div>
    </NavShell>
  );
}
