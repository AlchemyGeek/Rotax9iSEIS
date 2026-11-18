import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getEngineClient } from "../../lib/engineClient";
import { useCapabilities } from "../../lib/capabilities";
import { DOCS_URL } from "../NavShell";
import type { InboxCandidate, InboxListing, InboxStatus } from "../../types/contract";
import { BODY, BUTTON, LINK, MUTED, NOTICE, PANEL, PANEL_TITLE, PRIMARY } from "./ui";

const client = getEngineClient();

const OPEN: InboxStatus[] = ["new", "investigating"];
const STATUS_LABEL: Record<InboxStatus, string> = {
  new: "new", investigating: "investigating", "nothing-here": "nothing here", watch: "watching", acted: "acted on",
};
const KIND_LABEL: Record<string, string> = { recurring: "recurring pattern", shift: "shift", group: "group apart" };
const MARKS: { status: InboxStatus; label: string; hint: string }[] = [
  { status: "nothing-here", label: "Nothing here", hint: "It comes back only once the recent window has moved on" },
  { status: "watch", label: "Watch", hint: "Keep it in view; it stays listed" },
  { status: "acted", label: "Acted", hint: "Something was done about it (say what)" },
];

/** "a pattern in 6 of 10 recent slices; a shift beyond 3.0" — the parameters it fired with. */
function sensitivityLine(c: InboxCandidate): string {
  const p = c.parameters;
  return `${c.sensitivity} sensitivity: a pattern in ${p.n} of ${p.m} recent slices, a shift beyond ${p.shift_z}`;
}

function sliceWindow(sliceId: string): { flight: string; window: string } | null {
  const m = /^([0-9a-f]{16}):.*:(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$/.exec(sliceId);
  return m ? { flight: m[1], window: `${Math.floor(Number(m[2]))}-${Math.ceil(Number(m[3]))}` } : null;
}

// Spec 16 §6 (D5, D8) — the inbox on Research home, both tiers: what the
// detectors raised over the recent flights (candidates, their evidence, the
// sensitivity they fired at, their status). The pilot can mark it (nothing
// here / watch / acted, with a note) and open the notebook an investigation
// linked; following one up is an ask in Claude Desktop (D15). Where no
// bench exists (the website) it invites installing EIS for Claude Desktop.
// EIS never says what a candidate means.
export function Inbox() {
  const navigate = useNavigate();
  const caps = useCapabilities();
  const bench = caps?.features.bench === true;
  const [listing, setListing] = useState<InboxListing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showResolved, setShowResolved] = useState(false);

  async function load() {
    try {
      setListing(await client.inboxList());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  useEffect(() => { void load(); }, []);

  async function mark(c: InboxCandidate, status: InboxStatus, note: string | null) {
    setError(null);
    try {
      await client.inboxResolve({ candidate_id: c.id, status, note: note ?? c.note, study_id: c.study_id });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const cands = listing?.candidates ?? [];
  const open = cands.filter((c) => OPEN.includes(c.status) || c.status === "watch");
  const resolved = cands.filter((c) => !open.includes(c));

  return (
    <section style={PANEL} data-testid="inbox">
      <div style={{ ...PANEL_TITLE, display: "flex", alignItems: "baseline", gap: 10 }}>
        <span>Inbox {listing && <span style={MUTED}>({open.length})</span>}</span>
        {listing?.last_scan && (
          <span style={{ ...MUTED, fontWeight: 400 }} data-testid="inbox-scan">
            looked at {listing.last_scan.flights} flights on {new Date(listing.last_scan.at).toLocaleDateString(undefined, { month: "short", day: "numeric" })} · {listing.last_scan.sensitivity} sensitivity
            {" "}· <button type="button" style={{ ...LINK, fontSize: 11 }} onClick={() => navigate("/settings?tab=research")}>change</button>
          </span>
        )}
      </div>
      {!listing && !error && <div style={MUTED}>Looking across the recent flights…</div>}
      {error && <div style={{ ...NOTICE, color: "var(--severity-warning)" }}>{error}</div>}
      {listing && open.length === 0 && (
        <div style={BODY}>Nothing new. After each Sync EIS looks across the recent flights for a pattern that keeps coming back, a measurement that has moved, or slices that group apart.</div>
      )}
      {open.map((c) => <Candidate key={c.id} c={c} onMark={(s, n) => void mark(c, s, n)} onOpenStudy={() => navigate(`/research/${c.study_id}`)} />)}
      {resolved.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <button type="button" style={{ ...LINK, fontSize: 11 }} onClick={() => setShowResolved((v) => !v)} data-testid="inbox-show-resolved">
            {showResolved ? "Hide" : "Show"} resolved ({resolved.length})
          </button>
          {showResolved && resolved.map((c) => <Candidate key={c.id} c={c} onMark={(s, n) => void mark(c, s, n)} onOpenStudy={() => navigate(`/research/${c.study_id}`)} />)}
        </div>
      )}
      {caps && !bench && listing && (
        <div style={{ ...NOTICE, marginTop: 10 }} data-testid="inbox-install">
          To have Claude investigate a candidate — look at the flights, measure across them and write it up as a notebook — install
          EIS for Claude Desktop on your computer. <a href={`${DOCS_URL}walkthroughs/install-extension/`} target="_blank" rel="noopener noreferrer" style={LINK}>How to install</a>
        </div>
      )}
    </section>
  );
}

function Candidate({ c, onMark, onOpenStudy }: {
  c: InboxCandidate; onMark: (s: InboxStatus, note: string | null) => void; onOpenStudy: () => void;
}) {
  const [marking, setMarking] = useState<InboxStatus | null>(null);
  const [note, setNote] = useState(c.note ?? "");
  const [evidence, setEvidence] = useState(false);
  const flightCol = c.evidence?.columns.indexOf("flight") ?? -1;
  const sliceCol = c.evidence?.columns.indexOf("slice_id") ?? -1;
  const navigate = useNavigate();
  const shown = (c.evidence?.columns ?? []).map((col, i) => [col, i] as const).filter(([col]) => !["slice_id", "flight", "date"].includes(col));

  return (
    <div style={{ borderTop: "1px solid var(--border)", padding: "10px 0" }} data-testid="inbox-candidate" data-status={c.status}>
      <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.3, textTransform: "uppercase", color: c.status === "new" ? "var(--brand-tint)" : "var(--text-tertiary)" }}>{STATUS_LABEL[c.status]}</span>
        <span style={{ fontSize: 13, fontWeight: 600 }}>{c.preset_name}</span>
        <span style={MUTED}>{KIND_LABEL[c.kind] ?? c.kind} · {c.descriptors.join(", ")}</span>
        {!c.holds && <span style={{ ...MUTED, fontStyle: "italic" }}>not seen in the last scan</span>}
      </div>
      <div style={{ ...BODY, marginTop: 4 }}>{c.summary}</div>
      <div style={{ ...MUTED, marginTop: 2 }} data-testid="inbox-sensitivity">
        {c.fired.rule}{c.fired.hits != null && c.fired.of != null ? ` — ${c.fired.hits} of ${c.fired.of}` : ""} · {sensitivityLine(c)}
      </div>
      {c.note && <div style={{ ...BODY, marginTop: 4, fontStyle: "italic" }} data-testid="inbox-note">“{c.note}”</div>}
      <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap", alignItems: "center" }}>
        {c.study_id && <button type="button" style={PRIMARY} onClick={onOpenStudy} data-testid="inbox-open-study">Open the investigation</button>}
        {MARKS.map((m) => (
          <button key={m.status} type="button" title={m.hint} style={{ ...BUTTON, ...(c.status === m.status ? { borderColor: "var(--brand-tint)" } : {}) }}
            onClick={() => setMarking(m.status)} data-testid={`inbox-mark-${m.status}`}>{m.label}…</button>
        ))}
        <button type="button" style={{ ...LINK, fontSize: 11 }} onClick={() => setEvidence((v) => !v)} data-testid="inbox-evidence-toggle">
          {evidence ? "Hide" : "Show"} the evidence ({c.evidence?.rows.length ?? 0} slices)
        </button>
      </div>
      {marking && (
        <div style={{ display: "flex", gap: 6, marginTop: 8, alignItems: "center" }}>
          <input aria-label="Note" value={note} onChange={(e) => setNote(e.target.value)} placeholder={marking === "acted" ? "What was done — e.g. governor re-adjusted" : "A note (optional)"}
            style={{ flexGrow: 1, maxWidth: 520, fontSize: 12, padding: "5px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text-primary)" }} />
          <button type="button" style={PRIMARY} onClick={() => { onMark(marking, note.trim() || null); setMarking(null); }} data-testid="inbox-mark-confirm">
            Mark {STATUS_LABEL[marking]}
          </button>
          <button type="button" style={BUTTON} onClick={() => setMarking(null)}>Cancel</button>
        </div>
      )}
      {evidence && c.evidence && (
        <table style={{ marginTop: 8, borderCollapse: "collapse", fontSize: 11 }} data-testid="inbox-evidence">
          <thead><tr>{["flight", ...shown.map(([col]) => col)].map((h) => <th key={h} style={{ textAlign: "left", padding: "2px 8px", color: "var(--text-tertiary)", fontWeight: 600 }}>{h}</th>)}</tr></thead>
          <tbody>
            {c.evidence.rows.map((r, i) => {
              const w = sliceCol >= 0 ? sliceWindow(String(r[sliceCol])) : null;
              const flight = flightCol >= 0 ? String(r[flightCol]) : "";
              const date = c.evidence.columns.indexOf("date") >= 0 ? String(r[c.evidence.columns.indexOf("date")]) : flight;
              return (
                <tr key={i} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                  <td style={{ padding: "2px 8px" }}><button type="button" className="mono" style={{ ...LINK, fontSize: 11 }} onClick={() => navigate(`/flights/${flight}${w ? `?window=${w.window}` : ""}`)}>{date}</button></td>
                  {shown.map(([col, j]) => <td key={col} className="mono" style={{ padding: "2px 8px", textAlign: "right" }}>{r[j] === null ? "—" : String(r[j])}</td>)}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
