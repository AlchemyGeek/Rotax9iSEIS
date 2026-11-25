import type React from "react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getEngineClient } from "../../lib/engineClient";
import { useCapabilities } from "../../lib/capabilities";
import { labelTime, windowTime } from "../../lib/timeLabel";
import { DOCS_URL } from "../NavShell";
import type { InboxCandidate, InboxListing, InboxStatus, OwnerQuestionWithPins, Pin, PinQuestionTarget, PinsListing } from "../../types/contract";
import { ActionMenu, ChannelTags, StatusMark, type MenuItem } from "./bits";
import { BODY, BUTTON, LINK, MUTED, NOTICE, PANEL, PRIMARY } from "./ui";

const client = getEngineClient();

// Spec 03 v0.34 §5.10 item 3, Spec 16 §6 (D5, D8, D16) — the inbox as a
// digest: one line per item — a status dot and word, the title, a summary
// on the right — the owner's questions first, then what EIS raised;
// resolved items under *Show resolved*; loose marks one collapsed line.
// A line expands in place: a question's marks (each a link to its flight
// at the window, with its channels and the note), a candidate's
// explanation and evidence. The one standing button is *Open the
// investigation*; everything else — Nothing here / Watch / Acted with a
// note, Rename, Delete, a mark's Edit note / Move / Delete — is in the
// item's or the mark's ⋯ menu, with the confirmations they always had.
// EIS never says what a candidate means.

const OPEN: InboxStatus[] = ["new", "investigating", "watch"];
const KIND_LABEL: Record<string, string> = { recurring: "recurring pattern", shift: "shift", group: "group apart" };
const RESOLVE: { status: InboxStatus; label: string; hint: string }[] = [
  { status: "nothing-here", label: "Nothing here…", hint: "Looked at, nothing to follow (a candidate comes back only once the recent window has moved on)" },
  { status: "watch", label: "Watch…", hint: "Keep it in view; it stays listed" },
  { status: "acted", label: "Acted…", hint: "Something was done about it (say what)" },
];
const WORD: Record<InboxStatus, string> = { new: "new", investigating: "investigating", "nothing-here": "nothing here", watch: "watch", acted: "acted" };
const NEW_QUESTION = "__new__";
const UNASSIGNED = "__none__";
const INPUT: React.CSSProperties = {
  fontSize: 12, padding: "4px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text-primary)",
};
const SUBHEAD: React.CSSProperties = { fontSize: 11, color: "var(--text-tertiary)", margin: "10px 0 2px" };

export function pinHref(p: Pin): string {
  const w = `${Math.floor(p.start_s)}-${Math.ceil(p.end_s)}`;
  return `/flights/${p.flight}?window=${w}${p.channels.length ? `&channels=${p.channels.join(",")}` : ""}`;
}

function marks(n: number): string {
  return `${n} mark${n === 1 ? "" : "s"}`;
}

function candidateSummary(c: InboxCandidate): string {
  const kind = KIND_LABEL[c.kind] ?? c.kind;
  return c.fired.hits != null && c.fired.of != null ? `${kind} · ${c.fired.hits} of ${c.fired.of}` : kind;
}

function sliceWindow(sliceId: string): string | null {
  const m = /^([0-9a-f]{16}):.*:(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$/.exec(sliceId);
  return m ? `${Math.floor(Number(m[2]))}-${Math.ceil(Number(m[3]))}` : null;
}

export function Inbox() {
  const caps = useCapabilities();
  const bench = caps?.features.bench === true;
  const [listing, setListing] = useState<InboxListing | null>(null);
  const [pins, setPins] = useState<PinsListing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showResolved, setShowResolved] = useState(false);
  const navigate = useNavigate();

  async function loadInbox() {
    try { setListing(await client.inboxList()); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }
  async function loadPins() {
    try { setPins(await client.pinsList()); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }
  useEffect(() => { void loadPins(); void loadInbox(); }, []);

  async function act(fn: () => Promise<unknown>, reload: "pins" | "inbox") {
    setError(null);
    try {
      await fn();
      await (reload === "pins" ? loadPins() : loadInbox());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const questions = pins?.questions ?? [];
  const cands = listing?.candidates ?? [];
  const openQ = questions.filter((q) => OPEN.includes(q.status));
  const openC = cands.filter((c) => OPEN.includes(c.status));
  const resolvedQ = questions.filter((q) => !openQ.includes(q));
  const resolvedC = cands.filter((c) => !openC.includes(c));
  const unassigned = pins?.unassigned ?? [];
  const nOpen = openQ.length + openC.length;
  const loaded = !!pins && !!listing;
  const nothing = loaded && nOpen === 0 && unassigned.length === 0 && resolvedQ.length + resolvedC.length === 0;
  const newestOpen = questions.find((q) => q.id === pins?.newest_open) ?? null;

  const question = (q: OwnerQuestionWithPins) => (
    <QuestionLine key={q.id} q={q} all={questions} onOpenStudy={(id) => navigate(`/research/${id}`)} act={(fn) => act(fn, "pins")} />
  );
  const candidate = (c: InboxCandidate) => (
    <CandidateLine key={c.id} c={c} onOpenStudy={(id) => navigate(`/research/${id}`)}
      onMark={(status, note) => act(() => client.inboxResolve({ candidate_id: c.id, status, note: note ?? c.note, study_id: c.study_id }), "inbox")} />
  );

  return (
    <section style={PANEL} data-testid="inbox">
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 6 }}>
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }} data-testid="inbox-title">Inbox{loaded ? ` (${nOpen} open)` : ""}</h2>
        <span style={{ flexGrow: 1 }} />
        {listing?.last_scan && (
          <span style={{ ...MUTED, fontWeight: 400 }} data-testid="inbox-scan">
            EIS looked at {listing.last_scan.flights} flights on {new Date(listing.last_scan.at).toLocaleDateString(undefined, { month: "short", day: "numeric" })} · {listing.last_scan.sensitivity}
            {" "}· <button type="button" style={{ ...LINK, fontSize: 11 }} onClick={() => navigate("/settings?tab=research")}>change</button>
          </span>
        )}
      </div>
      {error && <div style={{ ...NOTICE, color: "var(--severity-warning)", marginBottom: 6 }}>{error}</div>}
      {!loaded && !error && <div style={MUTED}>Looking across the recent flights…</div>}
      {nothing && (
        <div style={BODY} data-testid="inbox-empty">
          Nothing here yet: zoom a flight's chart to something odd and use <em>Mark for Claude</em>, and EIS adds what it finds after each Sync.
        </div>
      )}

      {openQ.length > 0 && <div style={SUBHEAD}>Your questions</div>}
      {openQ.map(question)}
      {unassigned.length > 0 && <UnassignedLine pins={unassigned} all={questions} act={(fn) => act(fn, "pins")} />}

      {openC.length > 0 && <div style={SUBHEAD}>Raised by EIS</div>}
      {openC.map(candidate)}
      {loaded && openC.length === 0 && !nothing && <div style={{ ...MUTED, padding: "6px 0" }} data-testid="inbox-nothing-raised">EIS has raised nothing new over the recent flights.</div>}

      {resolvedQ.length + resolvedC.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <button type="button" style={{ ...LINK, fontSize: 11 }} onClick={() => setShowResolved((v) => !v)} data-testid="inbox-show-resolved" aria-expanded={showResolved}>
            {showResolved ? "Hide" : "Show"} resolved ({resolvedQ.length + resolvedC.length})
          </button>
          {showResolved && <div data-testid="inbox-resolved">{resolvedQ.map(question)}{resolvedC.map(candidate)}</div>}
        </div>
      )}

      {caps && !bench && loaded && (
        <div style={{ ...MUTED, marginTop: 10, fontSize: 12 }} data-testid="inbox-install">
          {newestOpen ? <>“{newestOpen.title}” is waiting for Claude: </> : null}
          install EIS for Claude Desktop on your computer and choose <em>Investigate</em> in a new chat.{" "}
          <a href={`${DOCS_URL}walkthroughs/install-extension/`} target="_blank" rel="noopener noreferrer" style={LINK}>How to install</a>
        </div>
      )}
    </section>
  );
}

// ── One line, expandable ──────────────────────────────────────────────────

function Line({ status, title, summary, expanded, onToggle, menu, testid, data, children }: {
  status: React.ReactNode; title: React.ReactNode; summary: string; expanded: boolean; onToggle: () => void;
  menu?: MenuItem[]; testid: string; data?: Record<string, string>; children?: React.ReactNode;
}) {
  return (
    <div style={{ borderTop: "1px solid var(--border)" }} data-testid={testid} {...Object.fromEntries(Object.entries(data ?? {}).map(([k, v]) => [`data-${k}`, v]))}>
      <div className="inbox-line" style={{ display: "flex", alignItems: "center", gap: 6, borderRadius: 6 }}>
        <button type="button" onClick={onToggle} aria-expanded={expanded} data-testid="inbox-line"
          style={{ flexGrow: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 10, background: "none", border: "none",
            padding: "7px 4px", cursor: "pointer", color: "var(--text-primary)", textAlign: "left" }}>
          <span aria-hidden style={{ width: 12, fontSize: 12, color: "var(--text-secondary)" }}>{expanded ? "▾" : "▸"}</span>
          <span style={{ width: 96, flexShrink: 0 }}>{status}</span>
          <span style={{ fontSize: 13, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }} data-testid="inbox-line-title">{title}</span>
          <span style={{ flexGrow: 1 }} />
          <span style={{ ...MUTED, whiteSpace: "nowrap" }} data-testid="inbox-line-summary">{summary}</span>
        </button>
        {menu && menu.length > 0 ? <ActionMenu items={menu} testid="inbox-item-menu" /> : <span style={{ width: 26 }} />}
      </div>
      {expanded && <div style={{ padding: "2px 30px 12px 20px", display: "flex", flexDirection: "column", gap: 8 }} data-testid="inbox-expanded">{children}</div>}
    </div>
  );
}

function ResolveForm({ status, initial, onConfirm, onCancel }: {
  status: InboxStatus; initial: string; onConfirm: (note: string | null) => void; onCancel: () => void;
}) {
  const [note, setNote] = useState(initial);
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }} data-testid="inbox-resolve-form">
      <input aria-label="Note" autoFocus value={note} onChange={(e) => setNote(e.target.value)}
        placeholder={status === "acted" ? "What was done — e.g. governor re-adjusted" : "A note (optional)"}
        style={{ ...INPUT, flexGrow: 1, maxWidth: 520 }} />
      <button type="button" style={PRIMARY} onClick={() => onConfirm(note.trim() || null)} data-testid="inbox-resolve-confirm">Mark {WORD[status]}</button>
      <button type="button" style={BUTTON} onClick={onCancel}>Cancel</button>
    </div>
  );
}

// ── The owner's question ──────────────────────────────────────────────────

function QuestionLine({ q, all, onOpenStudy, act }: {
  q: OwnerQuestionWithPins; all: OwnerQuestionWithPins[]; onOpenStudy: (id: string) => void;
  act: (fn: () => Promise<unknown>) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [resolving, setResolving] = useState<InboxStatus | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState(q.title);
  const [deleting, setDeleting] = useState(false);
  const open = (f: () => void) => () => { setExpanded(true); f(); };
  const menu: MenuItem[] = [
    ...RESOLVE.map((r) => ({ label: r.label, hint: r.hint, testid: `question-mark-${r.status}`, onSelect: open(() => setResolving(r.status)) })),
    { label: "Rename…", testid: "question-rename", onSelect: open(() => setRenaming(true)) },
    { label: "Delete…", testid: "question-delete", danger: true, onSelect: open(() => setDeleting(true)) },
  ];
  return (
    <Line testid="question" data={{ status: q.status, question: q.id }} expanded={expanded} onToggle={() => setExpanded((v) => !v)} menu={menu}
      status={<StatusMark status={q.status} />} title={q.title} summary={marks(q.pin_count)}>
      {renaming && (
        <span style={{ display: "inline-flex", gap: 6 }}>
          <input aria-label="Question title" autoFocus value={title} onChange={(e) => setTitle(e.target.value)} style={{ ...INPUT, width: 300 }} />
          <button type="button" style={PRIMARY} disabled={!title.trim()} data-testid="question-rename-save"
            onClick={() => void act(() => client.questionEdit({ question_id: q.id, title: title.trim() })).then(() => setRenaming(false))}>Save</button>
          <button type="button" style={BUTTON} onClick={() => { setTitle(q.title); setRenaming(false); }}>Cancel</button>
        </span>
      )}
      {deleting && (
        <span style={{ fontSize: 12, display: "inline-flex", gap: 6, alignItems: "center" }}>
          Delete the question? Its marks stay, unassigned.
          <button type="button" style={BUTTON} onClick={() => void act(() => client.questionDelete(q.id))} data-testid="question-delete-confirm">Delete</button>
          <button type="button" style={BUTTON} onClick={() => setDeleting(false)}>Keep</button>
        </span>
      )}
      {resolving && (
        <ResolveForm status={resolving} initial={q.note ?? ""} onCancel={() => setResolving(null)}
          onConfirm={(note) => { const s = resolving; setResolving(null); void act(() => client.questionResolve({ question_id: q.id, status: s, note, study_id: q.study_id })); }} />
      )}
      {q.note && <div style={{ ...BODY, fontStyle: "italic" }} data-testid="question-note">“{q.note}”</div>}
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {q.pins.map((p) => <MarkRow key={p.id} p={p} all={all} act={act} />)}
        {q.pins.length === 0 && <div style={MUTED}>No marks under this question.</div>}
      </div>
      {q.study_id && (
        <div><button type="button" style={PRIMARY} onClick={() => onOpenStudy(q.study_id!)} data-testid="question-open-study">Open the investigation</button></div>
      )}
    </Line>
  );
}

function UnassignedLine({ pins, all, act }: { pins: Pin[]; all: OwnerQuestionWithPins[]; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <Line testid="questions-unassigned" expanded={expanded} onToggle={() => setExpanded((v) => !v)}
      status={<span style={{ ...MUTED, display: "inline-flex", alignItems: "center", gap: 5 }}><span style={{ width: 7, height: 7, borderRadius: "50%", border: "1px solid var(--text-tertiary)" }} />loose</span>}
      title="Unassigned" summary={marks(pins.length)}>
      {pins.map((p) => <MarkRow key={p.id} p={p} all={all} act={act} />)}
    </Line>
  );
}

// ── A mark ────────────────────────────────────────────────────────────────

function MarkRow({ p, all, act }: { p: Pin; all: OwnerQuestionWithPins[]; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState(p.note ?? "");
  const [moving, setMoving] = useState(false);
  const [dest, setDest] = useState(p.question_id ?? UNASSIGNED);
  const [newTitle, setNewTitle] = useState("");
  const here = p.flight_here !== false;
  const t = p.when ? labelTime(p.when) : windowTime(null, null, p.start_s, p.end_s);
  const flight = `${p.date ?? "a flight not here yet"}${p.flight_name ? ` “${p.flight_name}”` : ""}`;

  function move() {
    const target: PinQuestionTarget = dest === UNASSIGNED ? null : dest === NEW_QUESTION ? { title: newTitle.trim() } : dest;
    setMoving(false);
    void act(() => client.pinEdit({ pin_id: p.id, question: target }));
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, padding: "5px 0 5px 10px", borderLeft: "2px solid var(--border)" }} data-testid="pin" data-pin={p.id}>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        {here
          ? <Link to={pinHref(p)} className="mono" style={{ fontSize: 12, color: "var(--link)" }} data-testid="pin-open" title={`Open the flight at this window — ${t.full}`}>{flight}</Link>
          : <span className="mono" style={{ fontSize: 12, opacity: 0.6 }} data-testid="pin-open" title="This flight's log isn't in this workspace yet">{flight}</span>}
        <span style={MUTED} title={t.full} data-testid="pin-when">{t.short}</span>
        <ChannelTags channels={p.channels} />
        <span style={{ flexGrow: 1 }} />
        <ActionMenu testid="pin-menu" title="Mark actions" items={[
          { label: "Edit note…", testid: "pin-edit", onSelect: () => setEditing(true) },
          { label: "Move…", testid: "pin-move", onSelect: () => setMoving(true) },
          { label: "Delete", testid: "pin-delete", danger: true, onSelect: () => void act(() => client.pinDelete(p.id)) },
        ]} />
      </div>
      {editing ? (
        <span style={{ display: "flex", gap: 6 }}>
          <input aria-label="Mark note" autoFocus value={note} onChange={(e) => setNote(e.target.value)} style={{ ...INPUT, flexGrow: 1, maxWidth: 520 }} />
          <button type="button" style={PRIMARY} onClick={() => { setEditing(false); void act(() => client.pinEdit({ pin_id: p.id, note: note.trim() || null })); }} data-testid="pin-note-save">Save</button>
          <button type="button" style={BUTTON} onClick={() => { setNote(p.note ?? ""); setEditing(false); }}>Cancel</button>
        </span>
      ) : p.note ? <div style={{ ...BODY, fontStyle: "italic" }} data-testid="pin-note">“{p.note}”</div> : null}
      {moving && (
        <span style={{ display: "inline-flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          <select aria-label="Move to" value={dest} onChange={(e) => setDest(e.target.value)} style={INPUT}>
            {all.map((q) => <option key={q.id} value={q.id}>{q.title}</option>)}
            <option value={UNASSIGNED}>Unassigned</option>
            <option value={NEW_QUESTION}>A new question…</option>
          </select>
          {dest === NEW_QUESTION && <input aria-label="New question title" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="Title" style={{ ...INPUT, width: 200 }} />}
          <button type="button" style={PRIMARY} disabled={dest === NEW_QUESTION && !newTitle.trim()} onClick={move} data-testid="pin-move-confirm">Move</button>
          <button type="button" style={BUTTON} onClick={() => setMoving(false)}>Cancel</button>
        </span>
      )}
    </div>
  );
}

// ── What EIS raised ───────────────────────────────────────────────────────

function CandidateLine({ c, onMark, onOpenStudy }: {
  c: InboxCandidate; onMark: (s: InboxStatus, note: string | null) => Promise<void>; onOpenStudy: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [resolving, setResolving] = useState<InboxStatus | null>(null);
  const [evidence, setEvidence] = useState(false);
  const navigate = useNavigate();
  const cols = c.evidence?.columns ?? [];
  const flightCol = cols.indexOf("flight"), sliceCol = cols.indexOf("slice_id"), dateCol = cols.indexOf("date");
  const shown = cols.map((col, i) => [col, i] as const).filter(([col]) => !["slice_id", "flight", "date"].includes(col));
  const p = c.parameters;
  return (
    <Line testid="inbox-candidate" data={{ status: c.status }} expanded={expanded} onToggle={() => setExpanded((v) => !v)}
      menu={RESOLVE.map((r) => ({ label: r.label, hint: r.hint, testid: `inbox-mark-${r.status}`, onSelect: () => { setExpanded(true); setResolving(r.status); } }))}
      status={<StatusMark status={c.status} />} title={c.preset_name} summary={candidateSummary(c)}>
      {resolving && <ResolveForm status={resolving} initial={c.note ?? ""} onCancel={() => setResolving(null)}
        onConfirm={(note) => { const s = resolving; setResolving(null); void onMark(s, note); }} />}
      <div style={BODY}>{c.summary}</div>
      <div style={MUTED} data-testid="inbox-sensitivity">
        {c.descriptors.join(", ")} · {c.fired.rule}{c.fired.hits != null && c.fired.of != null ? ` — ${c.fired.hits} of ${c.fired.of}` : ""}
        {" "}· {c.sensitivity} sensitivity: a pattern in {p.n} of {p.m} recent slices, a shift beyond {p.shift_z}
        {!c.holds && <em> · not seen in the last scan</em>}
      </div>
      {c.note && <div style={{ ...BODY, fontStyle: "italic" }} data-testid="inbox-note">“{c.note}”</div>}
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        {c.study_id && <button type="button" style={PRIMARY} onClick={() => onOpenStudy(c.study_id!)} data-testid="inbox-open-study">Open the investigation</button>}
        <button type="button" style={{ ...LINK, fontSize: 11 }} onClick={() => setEvidence((v) => !v)} data-testid="inbox-evidence-toggle" aria-expanded={evidence}>
          {evidence ? "Hide" : "Show"} the evidence ({c.evidence?.rows.length ?? 0} slices)
        </button>
      </div>
      {evidence && c.evidence && (
        <table style={{ borderCollapse: "collapse", fontSize: 11 }} data-testid="inbox-evidence">
          <thead><tr>{["flight", ...shown.map(([col]) => col)].map((h) => <th key={h} style={{ textAlign: "left", padding: "2px 8px", color: "var(--text-tertiary)", fontWeight: 600 }}>{h}</th>)}</tr></thead>
          <tbody>
            {c.evidence.rows.map((r, i) => {
              const w = sliceCol >= 0 ? sliceWindow(String(r[sliceCol])) : null;
              const flight = flightCol >= 0 ? String(r[flightCol]) : "";
              return (
                <tr key={i} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                  <td style={{ padding: "2px 8px" }}>
                    <button type="button" className="mono" style={{ ...LINK, fontSize: 11 }} onClick={() => navigate(`/flights/${flight}${w ? `?window=${w}` : ""}`)}>
                      {dateCol >= 0 ? String(r[dateCol]) : flight}
                    </button>
                  </td>
                  {shown.map(([col, j]) => <td key={col} className="mono" style={{ padding: "2px 8px", textAlign: "right" }}>{r[j] === null ? "—" : String(r[j])}</td>)}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Line>
  );
}
