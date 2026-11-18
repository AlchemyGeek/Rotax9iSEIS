import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getEngineClient } from "../../lib/engineClient";
import { useCapabilities } from "../../lib/capabilities";
import {
  cellFlags, cellMeta, logviewRef, markdown, metaLine, nbMeta, outputHtml, outputsLine, outputsState, text,
  type FileImages, type NbCell, type NbOutput, type Notebook,
  summaryHistory,
} from "../../lib/notebook";
import { LogViewCell } from "./LogViewCell";
import { BODY, BUTTON, MUTED, NOTICE, PANEL, PRIMARY } from "./ui";

const client = getEngineClient();

/** load_study's answer for an investigation notebook (Spec 16 §5.1). */
export interface NotebookStudyView {
  study_id: string;
  name: string | null;
  format: "ipynb";
  author?: string | null;
  question?: string | null;
  status?: string | null;
  summary?: string | null;
  engine?: string | null;
  inbox_candidate?: string | null;
  pending?: number;
  notebook: Notebook;
  files?: FileImages;
}

export function isNotebookView(doc: unknown): doc is NotebookStudyView {
  return !!doc && typeof doc === "object" && "notebook" in doc && !!(doc as { notebook?: unknown }).notebook;
}

function Html({ html, className, testid }: { html: string; className?: string; testid?: string }) {
  return <div className={className} data-testid={testid} dangerouslySetInnerHTML={{ __html: html }} />;
}

function Output({ o }: { o: NbOutput }) {
  const ref = logviewRef(o);
  if (ref) return <LogViewCell view={ref} svgHtml={outputHtml(o)} />;
  return <Html html={outputHtml(o)} />;
}

// Spec 16 §5.3 — one renderer for both tiers: markdown, code collapsed
// under *show code* with its outputs, tables, figures and log views (§5.2);
// the header says who wrote it, the question, its status, the engine and
// whether the outputs are current for this workspace. Re-run, Accept and
// Discard need a bench (features.bench); Export and *Run this on my flights*
// work on both tiers. The markup is the HTML export's (lib/notebook.ts).
export function NotebookView({ view, onChanged, onDeleted }: {
  view: NotebookStudyView;
  onChanged: (v: NotebookStudyView) => void;
  onDeleted: () => void;
}) {
  const navigate = useNavigate();
  const caps = useCapabilities();
  const bench = caps?.features.bench === true;
  const nb = view.notebook;
  const m = nbMeta(nb);
  const state = outputsState(nb);
  const imported = !!m.imported || state.readOnly > 0;
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const id = view.study_id;

  async function act(label: string, fn: () => Promise<unknown>, after?: (r: unknown) => string | null) {
    setBusy(label);
    setError(null);
    setNotice(null);
    try {
      const r = await fn();
      const v = await client.loadStudy(id) as unknown as NotebookStudyView;
      onChanged(v);
      if (after) setNotice(after(r));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const rerun = () => act("rerun", () => client.rerunStudyCells(id), (r) => {
    const cells = (r as { cells: { ran: boolean; identical?: boolean }[] }).cells.filter((c) => c.ran);
    const changed = cells.filter((c) => !c.identical).length;
    return changed ? `Re-ran ${cells.length} code cells: ${changed} with different outputs, waiting below for Accept or Discard.`
      : `Re-ran ${cells.length} code cells: every output is identical.`;
  });
  const accept = (cellIds?: string[]) => act("accept", () => client.acceptStudyCells(id, cellIds ? { cell_ids: cellIds } : {}));
  const discard = (cellIds?: string[]) => act("discard", () => client.discardStudyCells(id, cellIds));
  const keepExternal = (cellIds?: string[]) => act("external", () => client.acceptStudyCells(id, { source: "external", ...(cellIds ? { cell_ids: cellIds } : {}) }));

  async function exportAs(format: "zip" | "html") {
    setError(null);
    try {
      const res = await client.exportStudy(id, format);
      const a = document.createElement("a");
      a.href = client.downloadUrl(res.download_url);
      a.download = res.filename;
      a.click();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function runOnMine() {
    setBusy("mine");
    setError(null);
    try {
      const v = await client.runStudyOnMyFlights(id) as unknown as NotebookStudyView;
      navigate(`/research/${v.study_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    try {
      await client.deleteStudy(id);
      onDeleted();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="nb" data-testid="notebook" style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 980 }}>
      <header style={{ ...PANEL, display: "flex", flexDirection: "column", gap: 6 }} data-testid="notebook-header">
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700 }}>{m.name || "Notebook"}</h1>
          <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.4, color: "var(--text-tertiary)" }}>NOTEBOOK</span>
          <span style={{ flexGrow: 1 }} />
          {bench && <button type="button" style={BUTTON} disabled={!!busy} onClick={() => void rerun()} data-testid="nb-rerun">{busy === "rerun" ? "Re-running…" : "Re-run"}</button>}
          <button type="button" style={BUTTON} onClick={() => void exportAs("zip")} data-testid="nb-export-zip">Export notebook (.zip)</button>
          <button type="button" style={BUTTON} onClick={() => void exportAs("html")} data-testid="nb-export-html">Export as a page (.html)</button>
          {imported && <button type="button" style={PRIMARY} disabled={!!busy} onClick={() => void runOnMine()} data-testid="nb-run-mine">{busy === "mine" ? "Running…" : "Run this on my flights"}</button>}
          {!confirmDelete
            ? <button type="button" style={BUTTON} onClick={() => setConfirmDelete(true)}>Delete…</button>
            : <span style={BODY}>Delete this notebook and its files? <button type="button" style={BUTTON} onClick={() => void remove()} data-testid="nb-delete">Delete</button> <button type="button" style={BUTTON} onClick={() => setConfirmDelete(false)}>Keep</button></span>}
        </div>
        <div className="meta" style={{ ...MUTED, fontSize: 13 }} data-testid="nb-meta" dangerouslySetInnerHTML={{ __html: metaLine(m) }} />
        {m.question && <div style={{ ...BODY, fontSize: 15, color: "var(--text-primary)" }}><strong>Question:</strong> {m.question}</div>}
        <div style={{ ...MUTED, color: state.pending || state.ranElsewhere || state.readOnly ? "var(--severity-watch)" : "var(--text-tertiary)" }} data-testid="nb-outputs">{outputsLine(state)}</div>
        {bench && (state.pending > 0 || state.ranElsewhere > 0) && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {state.pending > 0 && <button type="button" style={PRIMARY} disabled={!!busy} onClick={() => void accept()} data-testid="nb-accept-all">Accept all new outputs</button>}
            {state.pending > 0 && <button type="button" style={BUTTON} disabled={!!busy} onClick={() => void discard()} data-testid="nb-discard-all">Discard all</button>}
            {state.ranElsewhere > 0 && <button type="button" style={BUTTON} disabled={!!busy} onClick={() => void keepExternal()} data-testid="nb-keep-external">Keep outputs that ran elsewhere</button>}
          </div>
        )}
        {!bench && caps && (state.ranElsewhere > 0 || state.readOnly > 0) && (
          <div style={MUTED}>This page shows the outputs as they were saved; re-running a notebook needs EIS on your computer (the Claude Desktop extension or a pip install).</div>
        )}
        {m.summary && <section className="summary"><Html html={"<h2>Summary</h2>" + markdown(m.summary)} /></section>}
        {m.reopened && m.status === "open" && (
          <div style={NOTICE} data-testid="nb-reopened">
            Reopened {String(m.reopened).slice(0, 10)}: a follow-up is adding to this notebook. The summary above is from before it; Claude finishes again with a new one.
          </div>
        )}
        {(m.summaries?.length ?? 0) > 0 && <Html className="summary-history" testid="nb-summary-history" html={summaryHistory(m.summaries!)} />}
      </header>
      {error && <div style={{ ...NOTICE, color: "var(--severity-warning)" }}>{error}</div>}
      {notice && <div style={NOTICE} data-testid="nb-notice">{notice}</div>}
      <main style={{ ...PANEL, display: "flex", flexDirection: "column" }}>
        {nb.cells.map((c) => <Cell key={c.id} c={c} files={view.files} bench={bench} busy={!!busy}
          onAccept={() => void accept([c.id])} onDiscard={() => void discard([c.id])} onKeep={() => void keepExternal([c.id])} />)}
      </main>
    </div>
  );
}

function Cell({ c, files, bench, busy, onAccept, onDiscard, onKeep }: {
  c: NbCell; files: FileImages; bench: boolean; busy: boolean; onAccept: () => void; onDiscard: () => void; onKeep: () => void;
}) {
  if (c.cell_type === "markdown") return <Html className="cell markdown" testid="nb-cell-markdown" html={markdown(text(c.source), files)} />;
  if (c.cell_type !== "code") return null;
  const sm = cellMeta(c);
  const flags = cellFlags(c);
  const setup = sm.role === "setup";
  return (
    <div className="cell code" data-testid="nb-cell-code" data-cell={c.id}>
      <details className="code">
        <summary>{setup ? "show code (setup: binds eis to this workspace)" : "show code"}</summary>
        <pre><code>{text(c.source)}</code></pre>
      </details>
      {flags.length > 0 && (
        <p className="flag" data-testid="nb-flag">
          {flags.join(" · ")}
          {bench && sm.ran_elsewhere && !sm.pending && <button type="button" style={{ ...BUTTON, marginLeft: 8, fontSize: 11 }} disabled={busy} onClick={onKeep}>Keep as it is</button>}
        </p>
      )}
      {(c.outputs ?? []).map((o, i) => <Output key={i} o={o} />)}
      {sm.pending && (
        <div className="pending" data-testid="nb-pending">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--severity-watch)" }}>NEW OUTPUTS FROM THE RE-RUN</span>
            {bench && <button type="button" style={{ ...PRIMARY, fontSize: 11 }} disabled={busy} onClick={onAccept}>Accept</button>}
            {bench && <button type="button" style={{ ...BUTTON, fontSize: 11 }} disabled={busy} onClick={onDiscard}>Discard</button>}
          </div>
          {(sm.pending.outputs ?? []).map((o, i) => <Output key={i} o={o} />)}
        </div>
      )}
    </div>
  );
}
