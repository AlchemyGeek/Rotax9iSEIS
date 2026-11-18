import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getEngineClient } from "../../lib/engineClient";
import { channelLabel } from "../../lib/research";
import type { InboxStatus, OwnerQuestionWithPins, Pin, PinQuestionTarget, PinsListing } from "../../types/contract";
import { BODY, BUTTON, LINK, MUTED, PRIMARY } from "./ui";

const client = getEngineClient();

// Spec 16 D16 — the owner's questions in the inbox, beside the scan's
// candidates and with the same statuses: each with its marks across
// flights (a mark opens its flight at the window, with its channels), the
// notebook that took it up, and edit / move / delete. Loose marks sit
// under *Unassigned*. Nothing here measures: a mark is where to look and
// the owner's sentence.

export const QUESTION_STATUS: Record<InboxStatus, string> = {
  new: "new", investigating: "investigating", "nothing-here": "nothing here", watch: "watching", acted: "acted on",
};
const RESOLVE: { status: InboxStatus; label: string }[] = [
  { status: "nothing-here", label: "Nothing here" }, { status: "watch", label: "Watch" }, { status: "acted", label: "Acted" },
];
const INPUT: React.CSSProperties = {
  fontSize: 12, padding: "4px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text-primary)",
};
const NEW_QUESTION = "__new__";
const UNASSIGNED = "__none__";

export function pinHref(p: Pin): string {
  const w = `${Math.floor(p.start_s)}-${Math.ceil(p.end_s)}`;
  return `/flights/${p.flight}?window=${w}${p.channels.length ? `&channels=${p.channels.join(",")}` : ""}`;
}

export function Questions({ listing, onChanged, onError }: {
  listing: PinsListing;
  onChanged: () => Promise<void> | void;
  onError: (msg: string | null) => void;
}) {
  const [showResolved, setShowResolved] = useState(false);
  const open = listing.questions.filter((q) => q.status === "new" || q.status === "investigating" || q.status === "watch");
  const resolved = listing.questions.filter((q) => !open.includes(q));

  async function act(fn: () => Promise<unknown>) {
    onError(null);
    try {
      await fn();
      await onChanged();
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    }
  }

  if (!listing.questions.length && !listing.unassigned.length) {
    return (
      <div style={{ ...BODY, padding: "6px 0 10px" }} data-testid="questions-empty">
        Seen something on a flight? Zoom the chart to it and use <em>Mark for Claude</em> — your marks gather here under your questions.
      </div>
    );
  }
  const all = listing.questions;
  const card = (q: OwnerQuestionWithPins) => <QuestionCard key={q.id} q={q} all={all} act={act} />;
  return (
    <div data-testid="questions">
      {open.map(card)}
      {listing.unassigned.length > 0 && (
        <div style={{ borderTop: "1px solid var(--border)", padding: "10px 0" }} data-testid="questions-unassigned">
          <div style={{ fontSize: 13, fontWeight: 600 }}>Unassigned <span style={MUTED}>({listing.unassigned.length})</span></div>
          {listing.unassigned.map((p) => <PinRow key={p.id} p={p} all={all} act={act} />)}
        </div>
      )}
      {resolved.length > 0 && (
        <div style={{ marginTop: 4 }}>
          <button type="button" style={{ ...LINK, fontSize: 11 }} onClick={() => setShowResolved((v) => !v)} data-testid="questions-show-resolved">
            {showResolved ? "Hide" : "Show"} resolved questions ({resolved.length})
          </button>
          {showResolved && resolved.map(card)}
        </div>
      )}
    </div>
  );
}

function QuestionCard({ q, all, act }: { q: OwnerQuestionWithPins; all: OwnerQuestionWithPins[]; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(q.title);
  const [marking, setMarking] = useState<InboxStatus | null>(null);
  const [note, setNote] = useState(q.note ?? "");
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <div style={{ borderTop: "1px solid var(--border)", padding: "10px 0" }} data-testid="question" data-status={q.status} data-question={q.id}>
      <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.3, textTransform: "uppercase", color: q.status === "new" ? "var(--brand-tint)" : "var(--text-tertiary)" }}>
          {QUESTION_STATUS[q.status]}
        </span>
        <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>your question</span>
        {editing ? (
          <span style={{ display: "inline-flex", gap: 6 }}>
            <input aria-label="Question title" value={title} onChange={(e) => setTitle(e.target.value)} style={{ ...INPUT, width: 280 }} />
            <button type="button" style={PRIMARY} disabled={!title.trim()} onClick={() => void act(() => client.questionEdit({ question_id: q.id, title: title.trim() })).then(() => setEditing(false))}>Save</button>
            <button type="button" style={BUTTON} onClick={() => { setTitle(q.title); setEditing(false); }}>Cancel</button>
          </span>
        ) : (
          <span style={{ fontSize: 13, fontWeight: 600 }} data-testid="question-title">{q.title}</span>
        )}
        <span style={MUTED}>{q.pin_count} mark{q.pin_count === 1 ? "" : "s"}</span>
      </div>
      {q.note && <div style={{ ...BODY, marginTop: 4, fontStyle: "italic" }}>“{q.note}”</div>}
      <div style={{ marginTop: 6 }}>
        {q.pins.map((p) => <PinRow key={p.id} p={p} all={all} act={act} />)}
      </div>
      <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap", alignItems: "center" }}>
        {q.study_id && <button type="button" style={PRIMARY} onClick={() => navigate(`/research/${q.study_id}`)} data-testid="question-open-study">Open the investigation</button>}
        {RESOLVE.map((m) => (
          <button key={m.status} type="button" style={{ ...BUTTON, ...(q.status === m.status ? { borderColor: "var(--brand-tint)" } : {}) }}
            onClick={() => setMarking(m.status)} data-testid={`question-mark-${m.status}`}>{m.label}…</button>
        ))}
        {!editing && <button type="button" style={{ ...LINK, fontSize: 11 }} onClick={() => setEditing(true)} data-testid="question-rename">Rename</button>}
        {!confirmDelete
          ? <button type="button" style={{ ...LINK, fontSize: 11 }} onClick={() => setConfirmDelete(true)} data-testid="question-delete">Delete</button>
          : (
            <span style={{ fontSize: 11, display: "inline-flex", gap: 6, alignItems: "center" }}>
              Delete the question? Its marks stay, unassigned.
              <button type="button" style={BUTTON} onClick={() => void act(() => client.questionDelete(q.id))} data-testid="question-delete-confirm">Delete</button>
              <button type="button" style={BUTTON} onClick={() => setConfirmDelete(false)}>Keep</button>
            </span>
          )}
      </div>
      {marking && (
        <div style={{ display: "flex", gap: 6, marginTop: 8, alignItems: "center" }}>
          <input aria-label="Note" value={note} onChange={(e) => setNote(e.target.value)} placeholder={marking === "acted" ? "What was done" : "A note (optional)"}
            style={{ ...INPUT, flexGrow: 1, maxWidth: 520 }} />
          <button type="button" style={PRIMARY} data-testid="question-mark-confirm"
            onClick={() => { const s = marking; setMarking(null); void act(() => client.questionResolve({ question_id: q.id, status: s, note: note.trim() || null, study_id: q.study_id })); }}>
            Mark {QUESTION_STATUS[marking]}
          </button>
          <button type="button" style={BUTTON} onClick={() => setMarking(null)}>Cancel</button>
        </div>
      )}
    </div>
  );
}

function PinRow({ p, all, act }: { p: Pin; all: OwnerQuestionWithPins[]; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState(p.note ?? "");
  const [moving, setMoving] = useState(false);
  const [dest, setDest] = useState(p.question_id ?? UNASSIGNED);
  const [newTitle, setNewTitle] = useState("");
  const here = p.flight_here !== false;
  const label = `${p.date ?? "a flight not here yet"}${p.flight_name ? ` “${p.flight_name}”` : ""}`;

  function move() {
    const target: PinQuestionTarget = dest === UNASSIGNED ? null : dest === NEW_QUESTION ? { title: newTitle.trim() } : dest;
    setMoving(false);
    void act(() => client.pinEdit({ pin_id: p.id, question: target }));
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, padding: "5px 0 5px 12px", borderLeft: "2px solid var(--border)", marginTop: 4 }} data-testid="pin" data-pin={p.id}>
      <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
        <button type="button" className="mono" style={{ ...LINK, fontSize: 12, opacity: here ? 1 : 0.6 }} disabled={!here}
          onClick={() => navigate(pinHref(p))} data-testid="pin-open" title={here ? "Open the flight at this window" : "This flight's log isn't in this workspace yet"}>
          {label}
        </button>
        <span style={MUTED}>{p.when ?? `${Math.round(p.start_s)}–${Math.round(p.end_s)} s into the flight`}</span>
        {p.channels.length > 0 && <span style={MUTED}>· {p.channels.map(channelLabel).join(", ")}</span>}
      </div>
      {editing ? (
        <span style={{ display: "flex", gap: 6 }}>
          <input aria-label="Mark note" value={note} onChange={(e) => setNote(e.target.value)} style={{ ...INPUT, flexGrow: 1, maxWidth: 520 }} />
          <button type="button" style={PRIMARY} onClick={() => { setEditing(false); void act(() => client.pinEdit({ pin_id: p.id, note: note.trim() || null })); }} data-testid="pin-note-save">Save</button>
          <button type="button" style={BUTTON} onClick={() => { setNote(p.note ?? ""); setEditing(false); }}>Cancel</button>
        </span>
      ) : (
        <div style={{ ...BODY, fontStyle: p.note ? "italic" : "normal" }} data-testid="pin-note">{p.note ? `“${p.note}”` : <span style={MUTED}>no note</span>}</div>
      )}
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        {!editing && <button type="button" style={{ ...LINK, fontSize: 11 }} onClick={() => setEditing(true)} data-testid="pin-edit">Edit note</button>}
        <button type="button" style={{ ...LINK, fontSize: 11 }} onClick={() => setMoving((v) => !v)} data-testid="pin-move">Move…</button>
        <button type="button" style={{ ...LINK, fontSize: 11 }} onClick={() => void act(() => client.pinDelete(p.id))} data-testid="pin-delete">Delete</button>
        {moving && (
          <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
            <select aria-label="Move to" value={dest} onChange={(e) => setDest(e.target.value)} style={INPUT}>
              {all.map((q) => <option key={q.id} value={q.id}>{q.title}</option>)}
              <option value={UNASSIGNED}>Unassigned</option>
              <option value={NEW_QUESTION}>A new question…</option>
            </select>
            {dest === NEW_QUESTION && <input aria-label="New question title" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="Title" style={{ ...INPUT, width: 200 }} />}
            <button type="button" style={PRIMARY} disabled={dest === NEW_QUESTION && !newTitle.trim()} onClick={move} data-testid="pin-move-confirm">Move</button>
          </span>
        )}
      </div>
    </div>
  );
}
