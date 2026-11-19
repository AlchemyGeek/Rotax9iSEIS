import { useEffect, useState } from "react";
import { getEngineClient } from "../../lib/engineClient";
import { useCapabilities } from "../../lib/capabilities";
import type { AircraftRecord, AircraftView, AircraftWorkspaceRef } from "../../types/contract";

const client = getEngineClient();

const PANEL: React.CSSProperties = { background: "var(--panel)", borderRadius: 12, padding: "16px 18px" };
const TITLE: React.CSSProperties = { fontSize: 13, fontWeight: 600, marginBottom: 10 };
const INPUT: React.CSSProperties = { background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 8px", color: "var(--text-primary)", fontSize: 12 };
const BUTTON: React.CSSProperties = { padding: "5px 12px", borderRadius: 6, fontSize: 12, cursor: "pointer", border: "1px solid var(--border)", background: "transparent", color: "var(--text-primary)" };
const MUTED: React.CSSProperties = { fontSize: 11, color: "var(--text-tertiary)" };

/** "916iS" → "Rotax 916 iS" (aircraft.engine_label). */
export function engineLabel(model: string | null | undefined): string {
  const m = (model ?? "").trim();
  if (/^\d{3}/.test(m)) return `Rotax ${m.slice(0, 3)} ${m.slice(3)}`.trim();
  return m ? `Rotax ${m}` : "—";
}

// Settings → Aircraft (Spec 16 §4.4, D10/D11; Session F): the record the
// workspaces of one aircraft share — its fields, the owner's notes (what
// was changed and when; Claude reads them), the documents folders (read in
// place by EIS on this computer, so server host only: greyed in the
// browser), and the aircraft's workspaces with a workspace whose engine
// differs from the record's flagged, movable to another aircraft or a new one.
export function AircraftSettings() {
  const caps = useCapabilities();
  const docsHere = caps?.features.documents === true;
  const [view, setView] = useState<AircraftView | null>(null);
  const [all, setAll] = useState<(AircraftRecord & { workspaces: AircraftWorkspaceRef[] })[]>([]);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState("");
  const [dirs, setDirs] = useState<string[]>([]);
  const [newDir, setNewDir] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [moving, setMoving] = useState<{ ws: string; target: string; name: string } | null>(null);

  function take(v: AircraftView) {
    setView(v);
    const f: Record<string, string> = { name: v.aircraft.name };
    for (const { key } of v.fields) f[key] = String(v.aircraft[key] ?? "");
    setFields(f);
    setNotes(v.notes);
    setDirs(v.aircraft.documents_dirs ?? []);
  }
  async function load(aircraftId?: string) {
    try {
      const [v, list] = await Promise.all([client.aircraftGet(aircraftId), client.listAircraft()]);
      take(v);
      setAll(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  useEffect(() => { void load(); }, []);

  async function run(what: string, fn: () => Promise<AircraftView>) {
    setError(null);
    setSaved(null);
    try {
      take(await fn());
      setAll(await client.listAircraft());
      setSaved(what);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (!view) return <div style={PANEL}>{error ? <span style={{ color: "var(--severity-warning)", fontSize: 12 }}>{error}</span> : <span style={MUTED}>Loading…</span>}</div>;
  const ac = view.aircraft;
  const fieldsDirty = fields.name !== ac.name || view.fields.some(({ key }) => (fields[key] ?? "") !== String(ac[key] ?? ""));
  const others = all.filter((a) => a.id !== ac.id);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }} data-testid="aircraft-settings">
      {error && <div style={{ fontSize: 12, color: "var(--severity-warning)" }}>{error}</div>}
      {saved && <div style={MUTED} data-testid="aircraft-saved">{saved}</div>}

      <div style={PANEL}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <div style={TITLE}>Aircraft</div>
          <span style={MUTED}>{engineLabel(ac.engine_model)}</span>
          {others.length > 0 && (
            <select aria-label="Show aircraft" value={ac.id} onChange={(e) => void load(e.target.value)} style={{ ...INPUT, marginLeft: "auto" }}>
              {all.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          )}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "180px 1fr", gap: "8px 12px", alignItems: "center", maxWidth: 720 }}>
          <label htmlFor="ac-name" style={{ fontSize: 12, color: "var(--text-secondary)" }}>Name</label>
          <input id="ac-name" style={INPUT} value={fields.name ?? ""} maxLength={80} onChange={(e) => setFields({ ...fields, name: e.target.value })} />
          {view.fields.map(({ key, label, hint }) => (
            <FieldRow key={key} id={`ac-${key}`} label={label} hint={hint} value={fields[key] ?? ""} onChange={(v) => setFields({ ...fields, [key]: v })} />
          ))}
        </div>
        <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
          <button type="button" style={BUTTON} disabled={!fieldsDirty} data-testid="aircraft-save"
            onClick={() => void run("Aircraft saved.", () => client.aircraftSet({ aircraft_id: ac.id, aircraft: fields }))}>Save</button>
          {fieldsDirty && <button type="button" style={BUTTON} onClick={() => take(view)}>Revert</button>}
        </div>
      </div>

      <div style={PANEL}>
        <div style={TITLE}>Notes</div>
        <div style={{ ...MUTED, marginBottom: 8, maxWidth: 720 }}>
          What was changed and when — a new propeller, a governor adjustment, a service bulletin done. Claude reads these before an investigation.
        </div>
        <textarea aria-label="Aircraft notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={8} data-testid="aircraft-notes"
          style={{ ...INPUT, width: "100%", maxWidth: 720, fontFamily: "ui-monospace, Menlo, monospace", lineHeight: 1.5 }} />
        <div style={{ marginTop: 8 }}>
          <button type="button" style={BUTTON} disabled={notes === view.notes} data-testid="aircraft-notes-save"
            onClick={() => void run("Notes saved.", () => client.aircraftSet({ aircraft_id: ac.id, notes }))}>Save notes</button>
        </div>
      </div>

      <div style={{ ...PANEL, opacity: docsHere ? 1 : 0.6 }} data-testid="aircraft-documents">
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <div style={TITLE}>Documents folders</div>
          {!docsHere && caps && <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-tertiary)", letterSpacing: 0.3 }} data-testid="documents-extension-only">EXTENSION ONLY</span>}
        </div>
        <div style={{ ...MUTED, marginBottom: 8, maxWidth: 720 }}>
          {docsHere
            ? "Folders of manuals and bulletins (PDF, Markdown, text) that investigations may read in place. Nothing is copied into EIS."
            : "Investigations read manuals in place from folders on your computer, through EIS running there (the Claude Desktop extension or a pip install). This browser can't."}
        </div>
        {dirs.length === 0 && <div style={MUTED}>No folder yet.</div>}
        {dirs.map((d) => (
          <div key={d} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, marginBottom: 4 }}>
            <span className="mono">{d}</span>
            {docsHere && <button type="button" style={{ ...BUTTON, fontSize: 11, padding: "2px 8px" }} onClick={() => setDirs(dirs.filter((x) => x !== d))}>Remove</button>}
          </div>
        ))}
        {docsHere && (
          <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
            <input aria-label="Add a documents folder" placeholder="/Users/you/Aircraft/Manuals" value={newDir} onChange={(e) => setNewDir(e.target.value)}
              style={{ ...INPUT, width: 420 }} />
            <button type="button" style={BUTTON} disabled={!newDir.trim()} onClick={() => { setDirs([...dirs, newDir.trim()]); setNewDir(""); }}>Add</button>
            <button type="button" style={BUTTON} data-testid="documents-save" disabled={JSON.stringify(dirs) === JSON.stringify(ac.documents_dirs ?? [])}
              onClick={() => void run("Documents folders saved.", () => client.aircraftSet({ aircraft_id: ac.id, aircraft: { documents_dirs: dirs } }))}>Save folders</button>
          </div>
        )}
      </div>

      <div style={PANEL}>
        <div style={TITLE}>This aircraft's workspaces</div>
        {view.workspaces.length === 0 && <div style={MUTED}>None.</div>}
        {view.workspaces.map((w) => {
          const mismatch = w.engine_model && ac.engine_model && w.engine_model !== ac.engine_model;
          return (
            <div key={w.id} style={{ borderTop: "1px solid var(--border-subtle)", padding: "8px 0", fontSize: 12 }} data-testid="aircraft-workspace">
              <div style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap" }}>
                <span style={{ fontWeight: 600 }}>{w.name}</span>
                <span style={MUTED}>{engineLabel(w.engine_model)} · {w.flight_count} flight{w.flight_count === 1 ? "" : "s"}</span>
                <span style={{ flexGrow: 1 }} />
                {moving?.ws !== w.id && <button type="button" style={{ ...BUTTON, fontSize: 11 }} onClick={() => setMoving({ ws: w.id, target: others[0]?.id ?? "new", name: "" })} data-testid="workspace-move">Move to another aircraft…</button>}
              </div>
              {mismatch && (
                <div style={{ fontSize: 11, color: "var(--severity-watch)", marginTop: 4 }} data-testid="engine-mismatch">
                  This workspace's profile is {engineLabel(w.engine_model)}; the aircraft record says {engineLabel(ac.engine_model)}.
                  If it is another aircraft, move it to its own.
                </div>
              )}
              {moving?.ws === w.id && (
                <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 6, flexWrap: "wrap" }}>
                  <select aria-label="Move to" value={moving.target} onChange={(e) => setMoving({ ...moving, target: e.target.value })} style={INPUT}>
                    {others.map((a) => <option key={a.id} value={a.id}>{a.name} ({engineLabel(a.engine_model)})</option>)}
                    <option value="new">A new aircraft…</option>
                  </select>
                  {moving.target === "new" && (
                    <input aria-label="New aircraft name" placeholder={`e.g. ${engineLabel(w.engine_model)} test cell`} value={moving.name}
                      onChange={(e) => setMoving({ ...moving, name: e.target.value })} style={{ ...INPUT, width: 240 }} />
                  )}
                  <button type="button" style={BUTTON} data-testid="workspace-move-confirm"
                    onClick={() => { const m = moving; setMoving(null); void run(`${w.name} moved.`, () => client.aircraftAssign(m.target === "new"
                      ? { workspace_id: w.id, new_aircraft: { name: m.name.trim() } } : { workspace_id: w.id, aircraft_id: m.target })).then(() => load(ac.id)); }}>
                    Move
                  </button>
                  <button type="button" style={BUTTON} onClick={() => setMoving(null)}>Cancel</button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function FieldRow({ id, label, hint, value, onChange }: { id: string; label: string; hint: string; value: string; onChange: (v: string) => void }) {
  return (
    <>
      <label htmlFor={id} style={{ fontSize: 12, color: "var(--text-secondary)" }}>{label}</label>
      <input id={id} style={INPUT} value={value} placeholder={hint} onChange={(e) => onChange(e.target.value)} />
    </>
  );
}
