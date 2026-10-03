import { useState } from "react";
import type { Insight, InsightEvent } from "../types/contract";
import { SeverityBadge } from "./SeverityBadge";
import { NoteSection, NoteToggle } from "./NoteEditor";

// Insights are the entry point, charts are the evidence (Spec 03
// principle 2) — clicking a card with evidence jumps/zooms the chart to
// the window that justifies it; cards with none render as plain info.
// Notes (Spec 02 §6.5) are the other thing a card can carry: a pilot's
// own explanation attached to this specific insight, editable in place.
function fmtClock(s: number | null): string {
  if (s === null) return "—";
  const t = Math.max(0, Math.round(s));
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const sec = t % 60;
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
}

function fmtDuration(s: number): string {
  const t = Math.round(s);
  if (t < 60) return `${t} s`;
  if (t < 3600) return `${Math.floor(t / 60)} min${t % 60 ? ` ${t % 60} s` : ""}`;
  return `${Math.floor(t / 3600)} h ${Math.floor((t % 3600) / 60)} min`;
}

// Spec 09 §12.1: a limit card's expanded rows — one per (merged) event,
// each zooming the chart to its own window (evidence[i]). `index` is the
// event's position in insight.events/evidence, not its position in this
// (possibly phase-filtered) list — onEventClick keys off the former.
function EventRows({
  items, unit, limitType, onEventClick,
}: {
  items: { event: InsightEvent; index: number }[];
  unit?: string;
  limitType?: "MIN" | "MAX";
  onEventClick?: (index: number) => void;
}) {
  return (
    <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 2 }}>
      {items.map(({ event: ev, index }) => (
        <div
          key={ev.event_id}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onEventClick?.(index);
          }}
          className="mono"
          title="Show this event on the chart"
          style={{
            display: "grid",
            gridTemplateColumns: "58px 1fr auto",
            gap: 8,
            fontSize: 11,
            padding: "4px 6px",
            borderRadius: 5,
            background: "var(--bg)",
            color: ev.suppressed_by ? "var(--text-tertiary)" : "var(--text-secondary)",
            cursor: onEventClick ? "pointer" : "default",
          }}
        >
          <span>{fmtClock(ev.elapsed_s)}</span>
          <span>
            {ev.observed_value.toFixed(1)}
            {unit ? ` ${unit}` : ""}
            {ev.excess !== null && ` (${ev.excess.toFixed(1)} ${limitType === "MIN" ? "under" : "over"})`}
          </span>
          <span>{fmtDuration(ev.duration_s)}</span>
        </div>
      ))}
    </div>
  );
}

export function InsightCard({
  insight,
  topicId,
  onClick,
  onEventClick,
  visibleEventIndices,
  unit,
  limitType,
  filterAction,
  note,
  onSaveNote,
  onDeleteNote,
  notesEnabled = true,
}: {
  insight: Insight;
  topicId: string;
  onClick?: () => void;
  onEventClick?: (index: number) => void;
  // The Insights panel's phase filter (FlightView) — original indices
  // into insight.events that match it, or null when no filter is active
  // (every event counts). Computed by the caller, not here: it needs
  // flightAnalysis.phases and the current filter selection, neither of
  // which this component otherwise knows about.
  visibleEventIndices?: number[] | null;
  unit?: string;
  limitType?: "MIN" | "MAX";
  // Spec 09 §12.1: "Filter this limit…" / "Edit filter…" on limit cards.
  filterAction?: { label: string; onClick: () => void };
  note?: string;
  onSaveNote?: (text: string) => void;
  onDeleteNote?: () => void;
  notesEnabled?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [eventsOpen, setEventsOpen] = useState(false);
  const allEvents = insight.events ?? [];
  const visibleIdx = visibleEventIndices ?? allEvents.map((_, i) => i);
  const visibleItems = visibleIdx.map((i) => ({ event: allEvents[i], index: i }));
  const hiddenCount = allEvents.length - visibleItems.length;

  // A card with several events has no single "the evidence" to jump to —
  // insight.evidence[0] is just whichever event happened to sort first,
  // not necessarily the one worth seeing. Clicking the card used to jump
  // there anyway under the same "View evidence →" label a single-event
  // card shows, so it read as broken/arbitrary for anyone who clicked
  // expecting the same one-destination behavior. Multi-event cards
  // expand the list on click instead (same as the "Show N events" line
  // below) — a specific event row (already correct) is the only way to
  // jump to a particular moment. Phase-filtered down to exactly one
  // visible event, a card goes back to being directly jumpable — to
  // that event specifically (via onEventClick, its real index), not
  // index 0 of the unfiltered list.
  const singleFilteredEvent = allEvents.length > 0 && visibleItems.length === 1 ? visibleItems[0] : null;
  const multiEvent = visibleItems.length > 1;
  const jumpable = Boolean(
    onClick && ((allEvents.length === 0 && insight.evidence.length > 0) || singleFilteredEvent !== null)
  );
  const clickable = jumpable || multiEvent;
  const Wrapper = clickable ? "a" : "div";

  function toggleEvents(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setEventsOpen((v) => !v);
  }

  function toggleExpanded(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setExpanded((v) => !v);
  }

  return (
    <Wrapper
      href={clickable ? "#timeline" : undefined}
      onClick={
        jumpable
          ? (e: React.MouseEvent) => {
              e.preventDefault();
              if (singleFilteredEvent) onEventClick?.(singleFilteredEvent.index);
              else onClick?.();
            }
          : multiEvent
            ? (e: React.MouseEvent) => toggleEvents(e)
            : undefined
      }
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
      {(jumpable || filterAction) && (
        <div style={{ display: "flex", gap: 14, fontSize: 11, marginTop: 6 }}>
          {jumpable && <span>View evidence →</span>}
          {filterAction && (
            <span
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                filterAction.onClick();
              }}
              style={{ color: "var(--text-tertiary)", cursor: "pointer", textDecoration: "underline dotted" }}
            >
              {filterAction.label}
            </span>
          )}
        </div>
      )}
      {multiEvent && (
        <div onClick={toggleEvents} style={{ fontSize: 11, marginTop: 6, color: "var(--text-tertiary)", cursor: "pointer" }}>
          {eventsOpen
            ? "▾ Hide events"
            : `▸ Show ${visibleItems.length}${hiddenCount > 0 ? ` of ${allEvents.length}` : ""} events — click one to view on the chart →`}
        </div>
      )}
      {multiEvent && eventsOpen && <EventRows items={visibleItems} unit={unit} limitType={limitType} onEventClick={onEventClick} />}
      {allEvents.length > 0 && visibleItems.length === 0 && (
        <div style={{ fontSize: 11, marginTop: 6, color: "var(--text-tertiary)" }}>No events in the selected phase(s).</div>
      )}

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
