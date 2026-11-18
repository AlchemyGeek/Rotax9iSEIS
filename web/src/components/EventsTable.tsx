import { useEffect, useRef, useState } from "react";
import type { Annotation, AnnotationRef, CasEvent, EcuRunRecord, ExceedanceEvent } from "../types/contract";
import { EVENT_GLYPH, groupEventRows, type EventRow, type FilteredGroup } from "../lib/flightEvents";
import { filterScope, SCOPE_CAPTION } from "../lib/scope";
import { SeverityBadge } from "./SeverityBadge";
import { FilterEditor } from "./FilterEditor";
import { CasEventDetails } from "./CasEventDetails";
import { NoteSection } from "./NoteEditor";

// Spec 03 v0.16 §5.2 / Spec 09 v0.19 §12.1 — the Flight view's Events
// section: one chronological table of every event on the flight, limit
// and CAS. Row actions are the same for both sources: open on chart, add
// a note, filter. Events inside a filter collapse to one line per target;
// a filtered target's breach is an ordinary row marked *beyond your
// filter*. The table scrolls horizontally rather than wrapping.

function fmtTime(row: EventRow): string {
  const utc = row.event.start_utc;
  if (utc) return utc.slice(11, 19);
  if (row.elapsed_s === null) return "—";
  const t = Math.round(row.elapsed_s);
  return `+${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}

function fmtDuration(s: number): string {
  const t = Math.round(s);
  return t < 60 ? `${t} s` : `${Math.floor(t / 60)} min${t % 60 ? ` ${t % 60} s` : ""}`;
}

function noteRef(row: EventRow): AnnotationRef {
  return { kind: row.source === "cas" ? "cas_event" : "exceedance", ref: row.key };
}

const TH: React.CSSProperties = { textAlign: "left", padding: "6px 10px", fontSize: 11, color: "var(--text-tertiary)", fontWeight: 600, whiteSpace: "nowrap" };
const TD: React.CSSProperties = { padding: "7px 10px", fontSize: 12, whiteSpace: "nowrap", verticalAlign: "top" };
const ACTION: React.CSSProperties = { background: "none", border: "none", padding: 0, color: "var(--link)", textDecoration: "underline", textDecorationColor: "var(--link-underline)", textUnderlineOffset: 2, fontSize: 11, cursor: "pointer", whiteSpace: "nowrap" };

export interface EventsTableProps {
  rows: EventRow[];
  flightId: string;
  activeEventId: string | null;
  // Live features off in sample mode (no server to persist notes/filters).
  interactive: boolean;
  annotations: Annotation[];
  filterSummaryById: Record<string, string>;
  ecuRuns: EcuRunRecord[];
  casEvents: CasEvent[];
  onOpen: (row: EventRow) => void;
  onSaveNote: (ref: AnnotationRef, text: string) => void;
  onDeleteNote: (annotationId: string) => void;
  onFilterSaved: () => void;
}

export function EventsTable(props: EventsTableProps) {
  const { rows } = props;
  const items = groupEventRows(rows);
  const [openGroups, setOpenGroups] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<string | null>(null);

  // A clicked insight's event: show its row (expanding a collapsed group
  // that holds it) and scroll it into view.
  const tbodyRef = useRef<HTMLTableSectionElement>(null);
  useEffect(() => {
    if (!props.activeEventId) return;
    const group = items.find((it): it is FilteredGroup => it.kind === "filtered" && it.rows.some((r) => r.key === props.activeEventId));
    if (group) setOpenGroups((prev) => new Set(prev).add(group.key));
    const el = [...(tbodyRef.current?.querySelectorAll("[data-event-id]") ?? [])]
      .find((n) => n.getAttribute("data-event-id") === props.activeEventId);
    el?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.activeEventId]);

  if (rows.length === 0) {
    return <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>No events on this flight</div>;
  }

  return (
    <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }} data-testid="events-scroll">
      <table style={{ borderCollapse: "collapse", minWidth: "100%" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border)" }}>
            <th style={TH}>#</th>
            <th style={TH}>Time</th>
            <th style={TH}>Phase</th>
            <th style={TH}>Limit / alert</th>
            <th style={TH}>Duration</th>
            <th style={TH}>Excess</th>
            <th style={TH}>Reason</th>
            <th style={TH}>Severity</th>
            <th style={TH} />
          </tr>
        </thead>
        <tbody ref={tbodyRef}>
          {items.map((item) => {
            if (item.kind === "row") return <Row key={item.row.key} row={item.row} {...props} expanded={expanded === item.row.key} onToggle={() => setExpanded(expanded === item.row.key ? null : item.row.key)} />;
            const open = openGroups.has(item.key);
            const summary = item.filterId ? props.filterSummaryById[item.filterId] : undefined;
            return [
              <tr key={item.key} data-testid="filtered-group" style={{ borderBottom: "1px solid var(--border)" }}>
                <td colSpan={9} style={{ ...TD, color: "var(--text-tertiary)" }}>
                  <span
                    role="button"
                    tabIndex={0}
                    aria-expanded={open}
                    onClick={() => setOpenGroups((prev) => { const n = new Set(prev); if (n.has(item.key)) n.delete(item.key); else n.add(item.key); return n; })}
                    onKeyDown={(e) => { if (e.key === "Enter") (e.currentTarget as HTMLElement).click(); }}
                    style={{ cursor: "pointer" }}
                  >
                    {open ? "▾" : "▸"} {item.rows.length} {item.targetLabel} event{item.rows.length === 1 ? "" : "s"} within your filter{summary ? `: ${summary}` : ""}
                  </span>
                </td>
              </tr>,
              ...(open
                ? item.rows.map((r) => <Row key={r.key} row={r} {...props} muted expanded={expanded === r.key} onToggle={() => setExpanded(expanded === r.key ? null : r.key)} />)
                : []),
            ];
          })}
        </tbody>
      </table>
    </div>
  );
}

function Row({ row, muted, expanded, onToggle, ...props }: EventsTableProps & { row: EventRow; muted?: boolean; expanded: boolean; onToggle: () => void }) {
  const [filterOpen, setFilterOpen] = useState(false);
  const [noteOpen, setNoteOpen] = useState(false);
  const active = props.activeEventId === row.key;
  const ref = noteRef(row);
  const note = props.annotations.find((a) => a.ref.kind === ref.kind && a.ref.kind !== "insight" && a.ref.ref === row.key);
  const scope = filterScope(row.target);
  const filterLabel = row.insight?.filter
    ? "Edit filter…"
    : row.insight?.filterable === false
      ? "Why can't I filter this?"
      : row.source === "cas" ? "Filter this alert…" : "Filter this limit…";
  const canFilter = props.interactive && row.target !== null;
  const lim = row.source === "limit" ? (row.event as ExceedanceEvent) : null;

  return (
    <>
      <tr
        data-event-id={row.key}
        data-testid="event-row"
        onClick={onToggle}
        style={{
          borderBottom: expanded || filterOpen || noteOpen ? "none" : "1px solid var(--border)",
          cursor: "pointer",
          background: active ? "var(--brand-fill)" : undefined,
          color: muted ? "var(--text-tertiary)" : "var(--text-secondary)",
        }}
      >
        <td style={TD} className="mono" title={row.source === "cas" ? "alert" : "limit"}>{EVENT_GLYPH[row.source]}{row.n}</td>
        <td style={TD} className="mono">{fmtTime(row)}</td>
        <td style={TD}>{row.phase ?? "—"}</td>
        <td style={{ ...TD, color: muted ? undefined : "var(--text-primary)" }}>
          {row.targetLabel}
          {row.filterState === "breach" && <span style={{ marginLeft: 8, fontSize: 10, fontWeight: 700, color: "var(--severity-limit)" }}>beyond your filter</span>}
        </td>
        <td style={TD} className="mono">{fmtDuration(row.duration_s)}</td>
        <td style={TD} className="mono">{row.excessText ?? "—"}</td>
        <td style={TD}>{row.reason ?? "—"}</td>
        <td style={TD}>{row.severity ? <SeverityBadge severity={row.severity} size="sm" /> : "—"}</td>
        <td style={TD} onClick={(e) => e.stopPropagation()}>
          <span style={{ display: "flex", gap: 12 }}>
            <button type="button" style={ACTION} onClick={() => props.onOpen(row)}>Chart</button>
            {props.interactive && (
              <button type="button" style={ACTION} onClick={() => setNoteOpen((v) => !v)}>{note ? "Note" : "Add a note"}</button>
            )}
            {canFilter && (
              <button type="button" style={ACTION} title={SCOPE_CAPTION[scope]} onClick={() => setFilterOpen((v) => !v)}>{filterLabel}</button>
            )}
          </span>
        </td>
      </tr>
      {expanded && (
        <tr style={{ borderBottom: filterOpen || noteOpen ? "none" : "1px solid var(--border)" }}>
          <td colSpan={9} style={{ padding: "4px 10px 10px 34px", fontSize: 12, color: "var(--text-secondary)" }}>
            {lim ? (
              <span className="mono">
                {lim.observed_value.toFixed(1)} {lim.unit} against the OM {lim.limit_type === "MIN" ? "min" : "max"} {lim.limit_value} {lim.unit}
                {" · "}{fmtDuration(lim.duration_s)} · {row.phase ?? "phase unknown"}
                {lim.start_utc ? ` · from ${lim.start_utc.slice(11, 19)} UTC` : ""}
              </span>
            ) : (
              <CasEventDetails
                defaultOpen
                events={props.casEvents.filter((e) => e.event_id === row.key)}
                ecuRuns={props.ecuRuns}
              />
            )}
          </td>
        </tr>
      )}
      {noteOpen && (
        <tr style={{ borderBottom: filterOpen ? "none" : "1px solid var(--border)" }}>
          <td colSpan={9} style={{ padding: "4px 10px 10px 34px" }}>
            <NoteSection
              note={note?.note}
              expanded
              onSave={(text) => { props.onSaveNote(ref, text); setNoteOpen(false); }}
              onDelete={note ? () => props.onDeleteNote(note.id) : undefined}
              onCollapse={() => setNoteOpen(false)}
            />
          </td>
        </tr>
      )}
      {filterOpen && row.target && (
        <tr style={{ borderBottom: "1px solid var(--border)" }}>
          <td colSpan={9} style={{ padding: "4px 10px 10px 34px", whiteSpace: "normal" }}>
            <FilterEditor
              target={row.target}
              flightPeak={lim?.excess ?? null}
              eventDurationS={row.source === "cas" ? row.duration_s : null}
              eventPhases={row.source === "limit" ? row.phases : null}
              createdFrom={row.insight ? { flight_id: props.flightId, insight_id: row.insight.id } : undefined}
              onSaved={() => { setFilterOpen(false); props.onFilterSaved(); }}
              onCancel={() => setFilterOpen(false)}
            />
          </td>
        </tr>
      )}
    </>
  );
}
