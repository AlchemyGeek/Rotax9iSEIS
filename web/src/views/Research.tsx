import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { NavShell, DOCS_URL } from "../components/NavShell";
import { InlineHelp } from "../components/InlineHelp";
import { EngineRpcError, getEngineClient } from "../lib/engineClient";
import type { SlicePresets, StudySummary } from "../types/contract";
import { stashStudySeed } from "../lib/research";
import { BODY, BUTTON, LINK, MUTED, NOTICE, PANEL, PANEL_TITLE, PRIMARY } from "../components/research/ui";

const client = getEngineClient();

// Spec 06 §12 — Research home: the workspace's studies (name, first finding,
// updated), the presets with a one-line question each, New study, and
// import of a .eisstudy. Research is a destination of its own (D7; Spec 03
// principle 6): nothing here changes Flights, Trends or Journal.

// Spec 06 §14.6 — the questions the app's own research left open (Spec 10
// D2, §4.2, D7), named here as a pointer until the v2 example studies exist.
const OPEN_QUESTIONS = [
  "Does the oil temperature rise rate in climb depend on how steeply, how long and how hot the climb is?",
  "Does cruise fuel flow at a given power setting depend on density altitude beyond what the engine's own map explains?",
  "Can the peak oil and coolant temperature of a flight be predicted from its airborne time and outside air temperature?",
];

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function Research() {
  const navigate = useNavigate();
  const [studies, setStudies] = useState<StudySummary[] | null>(null);
  const [presets, setPresets] = useState<SlicePresets | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [noWorkspace, setNoWorkspace] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importNote, setImportNote] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    try {
      const [s, p] = await Promise.all([client.listStudies(), client.listSlicePresets()]);
      setStudies(s.studies);
      setPresets(p);
      setNoWorkspace(false);
    } catch (e) {
      if (e instanceof EngineRpcError && e.code === "NO_ACTIVE_WORKSPACE") setNoWorkspace(true);
      else setError(e instanceof Error ? e.message : String(e));
      setStudies([]);
    }
  }
  useEffect(() => { void load(); }, []);

  function newFromPreset(ruleId: string, name: string) {
    stashStudySeed({ name, from: "flight", selection: { mode: "all", split: null }, slice_rules: [ruleId], hand_slices: [],
      tests: [{ test_id: "cycling", params: {}, channels: ["rpm"] }] });
    navigate("/research/new");
  }

  async function onImportFile(file: File) {
    setImporting(true);
    setImportNote(null);
    try {
      const res = await client.importStudy(file);
      setImportNote(res.read_only
        ? `Imported read-only: none of its ${res.missing.length} flights are in this workspace.`
        : `Imported: ${res.matched.length} of ${res.matched.length + res.missing.length} flights are here.`);
      await load();
      navigate(`/research/${res.study.study_id}`);
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
          <span style={BODY}>Ask a question about pieces of your flights — slices — and read the answer against a reference, never a verdict.</span>
          <span style={{ flexGrow: 1 }} />
          <input ref={fileRef} type="file" accept=".eisstudy,.zip" style={{ display: "none" }} data-testid="import-study-input"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void onImportFile(f); e.target.value = ""; }} />
          <button type="button" onClick={() => fileRef.current?.click()} style={BUTTON} disabled={importing || noWorkspace}>{importing ? "Importing…" : "Import a study…"}</button>
          <button type="button" onClick={() => navigate("/research/new")} style={PRIMARY} disabled={noWorkspace} data-testid="new-study">New study</button>
        </div>

        {noWorkspace && <div style={NOTICE}>Open or create a workspace first — Research works on the flights of the active workspace.</div>}
        {error && <div style={{ ...NOTICE, color: "var(--severity-warning)" }}>{error}</div>}
        {importNote && <div style={NOTICE}>{importNote}</div>}

        <section style={PANEL}>
          <div style={PANEL_TITLE}>Studies {studies && <span style={MUTED}>({studies.length})</span>}</div>
          {studies === null && <div style={MUTED}>Loading…</div>}
          {studies && studies.length === 0 && (
            <div style={BODY}>
              No studies yet. Start from a preset below, press New study, or use <em>Research this</em> on a flight, a Trends card or an event.
            </div>
          )}
          {studies && studies.length > 0 && (
            <table style={{ width: "100%", borderCollapse: "collapse" }} data-testid="studies-table">
              <tbody>
                {studies.map((s) => (
                  <tr key={s.study_id} style={{ borderBottom: "1px solid var(--border)", cursor: "pointer" }} onClick={() => navigate(`/research/${s.study_id}`)} data-testid="study-row">
                    <td style={{ padding: "9px 8px", fontSize: 13, fontWeight: 600, whiteSpace: "nowrap", verticalAlign: "top" }}>
                      {s.name}
                      {s.read_only && <span style={{ marginLeft: 8, fontSize: 10, fontWeight: 700, color: "var(--severity-watch)" }}>SENDER'S RESULTS</span>}
                    </td>
                    <td style={{ padding: "9px 8px", fontSize: 12, color: "var(--text-secondary)" }}>{s.finding ?? <span style={MUTED}>not run yet · {s.tests} question{s.tests === 1 ? "" : "s"}</span>}</td>
                    <td className="mono" style={{ ...MUTED, padding: "9px 8px", whiteSpace: "nowrap", textAlign: "right" }}>{formatWhen(s.updated)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section style={PANEL}>
          <div style={PANEL_TITLE}>Start from a preset <InlineHelp id="research.slice_rule" /></div>
          {presets?.note && <div style={{ ...NOTICE, marginBottom: 10 }}>{presets.note}</div>}
          {!presets && !noWorkspace && <div style={MUTED}>Loading…</div>}
          {presets && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10 }}>
              {presets.presets.map((p) => (
                <button key={p.rule_id} type="button" onClick={() => newFromPreset(p.rule_id, p.name)} data-testid="preset-card"
                  style={{ textAlign: "left", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: "10px 12px", cursor: "pointer", color: "var(--text-primary)" }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{p.name}</div>
                  <div style={{ ...BODY, marginTop: 2 }}>{p.question ?? p.isolates ?? p.description}</div>
                  <div className="mono" style={{ ...MUTED, marginTop: 4 }}>{p.description}</div>
                </button>
              ))}
            </div>
          )}
        </section>

        <section style={{ ...PANEL, background: "transparent", border: "1px dashed var(--border)" }}>
          <div style={PANEL_TITLE}>Questions this app's own research left open</div>
          <ul style={{ margin: 0, paddingLeft: 18, ...BODY, lineHeight: 1.6 }}>
            {OPEN_QUESTIONS.map((q) => <li key={q}>{q}</li>)}
          </ul>
          <div style={{ ...MUTED, marginTop: 8 }}>
            These need a test Research does not have yet (does a measurement depend on conditions?). They will arrive as example studies.{" "}
            <a href={`${DOCS_URL}concepts/research/`} target="_blank" rel="noopener noreferrer" style={LINK}>About Research</a>
          </div>
        </section>
      </div>
    </NavShell>
  );
}
