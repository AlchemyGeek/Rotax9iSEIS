import { useState } from "react";
import type { Insight } from "../types/contract";
import { SeverityBadge } from "./SeverityBadge";
import { NoteSection, NoteToggle } from "./NoteEditor";

// Insights are the entry point, charts are the evidence (Spec 03
// principle 2) — clicking a card with evidence jumps/zooms the chart to
// the window that justifies it; cards with none render as plain info.
// Notes (Spec 02 §6.5) are the other thing a card can carry: a pilot's
// own explanation attached to this specific insight, editable in place.
export function InsightCard({
  insight,
  topicId,
  onClick,
  note,
  onSaveNote,
  onDeleteNote,
  notesEnabled = true,
}: {
  insight: Insight;
  topicId: string;
  onClick?: () => void;
  note?: string;
  onSaveNote?: (text: string) => void;
  onDeleteNote?: () => void;
  notesEnabled?: boolean;
}) {
  const clickable = Boolean(onClick && insight.evidence.length > 0);
  const Wrapper = clickable ? "a" : "div";
  const [expanded, setExpanded] = useState(false);

  function toggleExpanded(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setExpanded((v) => !v);
  }

  return (
    <Wrapper
      href={clickable ? "#timeline" : undefined}
      onClick={clickable ? (e: React.MouseEvent) => { e.preventDefault(); onClick?.(); } : undefined}
      style={{
        display: "block",
        background: "var(--panel)",
        borderRadius: 10,
        padding: "13px 14px",
        cursor: clickable ? "pointer" : "default",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <SeverityBadge severity={insight.severity} />
        {notesEnabled && <NoteToggle note={note} expanded={expanded} onToggle={toggleExpanded} />}
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 3 }}>
        {topicId.replace(/_/g, " ")}
      </div>
      <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.4 }}>{insight.message.text}</div>
      {clickable && <div style={{ fontSize: 11, marginTop: 6 }}>View evidence →</div>}

      {notesEnabled && (
        <NoteSection
          note={note}
          expanded={expanded}
          onSave={(text) => onSaveNote?.(text)}
          onDelete={onDeleteNote}
          onCollapse={() => setExpanded(false)}
        />
      )}
    </Wrapper>
  );
}
