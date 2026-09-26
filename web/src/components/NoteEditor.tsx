import { useState } from "react";

function NoteIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 3v5a1 1 0 001 1h5" />
      <path d="M17 21H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z" />
    </svg>
  );
}

// Shared by Flight view's insight cards and ECU's IN_FLIGHT event cards
// (Spec 02 §6.5) — same pilot-note affordance either way: a persistent
// icon indicator (filled once a note exists), expanding in place to an
// inline textarea rather than a separate dialog/page. `NoteToggle` is the
// small icon alone, for callers (like ECU) that want it in their own
// header row instead of NoteSection's default top-right placement.
export function NoteToggle({ note, expanded, onToggle }: { note?: string; expanded: boolean; onToggle: (e: React.MouseEvent) => void }) {
  return (
    <span
      onClick={onToggle}
      title={note ? (expanded ? "hide note" : "view note") : "add a note"}
      style={{ display: "flex", alignItems: "center", color: note ? "var(--accent)" : "var(--text-tertiary)", cursor: "pointer", flexShrink: 0 }}
    >
      <NoteIcon filled={Boolean(note)} />
    </span>
  );
}

export function NoteSection({
  note,
  expanded,
  onSave,
  onDelete,
  onCollapse,
}: {
  note?: string;
  expanded: boolean;
  onSave: (text: string) => void;
  onDelete?: () => void;
  onCollapse: () => void;
}) {
  const [editing, setEditing] = useState(!note);
  const [draft, setDraft] = useState(note ?? "");

  if (!expanded) return null;

  function startEdit(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDraft(note ?? "");
    setEditing(true);
  }
  function save(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (draft.trim()) onSave(draft.trim());
    setEditing(false);
  }
  function cancel(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setEditing(false);
    if (!note) onCollapse();
  }
  function remove(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    onDelete?.();
    setEditing(false);
    onCollapse();
  }

  return (
    <div
      style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border-subtle)" }}
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}
    >
      {editing ? (
        <>
          <textarea
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={2}
            placeholder="Your note…"
            style={{ width: "100%", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: 8, color: "var(--text-primary)", fontSize: 12, fontFamily: "inherit", resize: "vertical" }}
          />
          <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
            <button onClick={save} disabled={!draft.trim()} style={{ padding: "4px 10px", borderRadius: 6, background: "var(--accent)", border: "none", color: "var(--bg)", fontSize: 11, fontWeight: 600, cursor: draft.trim() ? "pointer" : "default" }}>
              Save
            </button>
            <button onClick={cancel} style={{ padding: "4px 10px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", fontSize: 11, cursor: "pointer" }}>
              Cancel
            </button>
          </div>
        </>
      ) : (
        <>
          <div style={{ fontSize: 12, color: "var(--text-primary)", lineHeight: 1.45, whiteSpace: "pre-wrap" }}>{note}</div>
          <div style={{ display: "flex", gap: 12, marginTop: 6 }}>
            <a href="#" onClick={startEdit} style={{ fontSize: 11, color: "var(--text-tertiary)" }}>Edit</a>
            <a href="#" onClick={remove} style={{ fontSize: 11, color: "var(--text-tertiary)" }}>Delete</a>
          </div>
        </>
      )}
    </div>
  );
}
