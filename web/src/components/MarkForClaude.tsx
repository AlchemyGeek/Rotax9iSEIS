import { useState } from "react";
import { getEngineClient } from "../lib/engineClient";
import { channelLabel } from "../lib/research";
import { windowTime } from "../lib/timeLabel";
import type { OwnerQuestionWithPins, PinQuestionTarget } from "../types/contract";

const client = getEngineClient();

// Spec 16 D16 — *Mark for Claude*. With a window selected (the chart
// zoomed), the owner marks it with a note under a question: a new one
// with a title, one of the open ones, or none (unassigned). A pin stores
// flight, window, the channels shown and the note — nothing else; the
// confirmation says where it went (Research → Inbox) and how to hand it
// to Claude. Both hosts mark; on the website the question waits there.

const BTN: React.CSSProperties = {
  fontSize: 11, padding: "2px 10px", borderRadius: 6, cursor: "pointer",
  background: "var(--panel-control)", color: "var(--text-secondary)", border: "1px solid var(--border)",
};
const INPUT: React.CSSProperties = {
  fontSize: 12, padding: "5px 8px", borderRadius: 6, border: "1px solid var(--border)",
  background: "var(--bg)", color: "var(--text-primary)", width: "100%", boxSizing: "border-box",
};

type Choice = "new" | "existing" | "none";

export function MarkForClaude({ flightId, window: win, channels, zoomed, startLocal = null, tz = null }: {
  flightId: string;
  window: [number, number];
  channels: string[];
  zoomed: boolean;
  /** The flight's local start and zone (get_flight's ident), for the window's time (Spec 03 v0.34). */
  startLocal?: string | null;
  tz?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [questions, setQuestions] = useState<OwnerQuestionWithPins[] | null>(null);
  const [choice, setChoice] = useState<Choice>("new");
  const [title, setTitle] = useState("");
  const [existing, setExisting] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [a, b] = [Math.floor(win[0]), Math.ceil(win[1])];
  const when = windowTime(startLocal, tz, a, b);

  async function begin() {
    setOpen(true);
    setDone(null);
    setError(null);
    setNote("");
    setTitle("");
    try {
      const l = await client.pinsList({ status: ["new", "investigating"] });
      setQuestions(l.questions);
      const newest = l.newest_open ?? l.questions[0]?.id ?? "";
      setExisting(newest);
      setChoice(l.questions.length ? "existing" : "new");
    } catch (e) {
      setQuestions([]);
      setChoice("new");
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const target: PinQuestionTarget | undefined =
    choice === "none" ? null : choice === "new" ? (title.trim() ? { title: title.trim() } : undefined) : existing || undefined;

  async function save() {
    if (target === undefined) return;
    setBusy(true);
    setError(null);
    try {
      const r = await client.flightPin({ flight_id: flightId, start_s: a, end_s: b, channels, note: note.trim() || null, question: target });
      setOpen(false);
      setDone(`Marked ${when.short} ${r.where}. In Claude Desktop, choose Investigate${r.question ? ` — with no text it takes your newest open question` : ""}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <span style={{ display: "inline-flex", flexDirection: "column", gap: 6 }} data-testid="mark-for-claude">
      <span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
        <button type="button" style={{ ...BTN, opacity: zoomed ? 1 : 0.6, cursor: zoomed ? "pointer" : "default" }} disabled={!zoomed}
          onClick={() => (open ? setOpen(false) : void begin())} data-testid="mark-open"
          title={zoomed ? "Mark this window, with a note, for Claude to look at" : "Zoom the chart to the window you want to mark"}>
          Mark for Claude…
        </button>
        {done && <span style={{ fontSize: 11, color: "var(--text-secondary)" }} data-testid="mark-done" role="status">{done}</span>}
      </span>
      {open && (
        <div role="dialog" aria-label="Mark for Claude" data-testid="mark-dialog"
          style={{ border: "1px solid var(--border)", borderRadius: 10, padding: "12px 14px", background: "var(--panel)", maxWidth: 560, display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ fontSize: 12, color: "var(--text-secondary)" }} data-testid="mark-window" title={when.full}>
            {when.short} · {channels.length ? channels.map(channelLabel).join(", ") : "no channels shown"}
          </div>
          <label style={{ fontSize: 12, display: "flex", flexDirection: "column", gap: 4 }}>
            What do you see here?
            <textarea aria-label="Note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} style={INPUT}
              placeholder="e.g. rpm wanders by about 100 in the climb, MAP steady" />
          </label>
          <fieldset style={{ border: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 6, fontSize: 12 }}>
            <legend style={{ fontSize: 12, marginBottom: 4 }}>Which question is it part of?</legend>
            {questions && questions.length > 0 && (
              <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input type="radio" name="q" checked={choice === "existing"} onChange={() => setChoice("existing")} />
                An open question
                <select aria-label="Open question" value={existing} onChange={(e) => { setExisting(e.target.value); setChoice("existing"); }} style={{ ...INPUT, width: "auto" }}>
                  {questions.map((q) => <option key={q.id} value={q.id}>{q.title} ({q.pin_count} mark{q.pin_count === 1 ? "" : "s"})</option>)}
                </select>
              </label>
            )}
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input type="radio" name="q" checked={choice === "new"} onChange={() => setChoice("new")} />
              A new question
              <input aria-label="New question title" value={title} onChange={(e) => { setTitle(e.target.value); setChoice("new"); }}
                placeholder="e.g. rough climbs" style={{ ...INPUT, width: 260 }} />
            </label>
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input type="radio" name="q" checked={choice === "none"} onChange={() => setChoice("none")} />
              None for now (unassigned)
            </label>
          </fieldset>
          {error && <div style={{ fontSize: 12, color: "var(--severity-warning)" }}>{error}</div>}
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" onClick={() => void save()} disabled={busy || target === undefined} data-testid="mark-save"
              style={{ ...BTN, background: "var(--brand)", color: "var(--on-brand)", border: "1px solid var(--brand)", fontWeight: 600, opacity: target === undefined ? 0.6 : 1 }}>
              {busy ? "Marking…" : "Mark"}
            </button>
            <button type="button" onClick={() => setOpen(false)} style={BTN}>Cancel</button>
          </div>
          <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
            EIS keeps where to look and your note — no measurement. Claude reads it when you ask it to investigate.
          </div>
        </div>
      )}
    </span>
  );
}
