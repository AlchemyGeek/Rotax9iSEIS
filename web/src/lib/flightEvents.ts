import type {
  CasEvent, ExceedanceEvent, FilterTarget, FlightAnalysis, FlightEvent, Insight, InsightSet, InsightSeverity, Phase,
} from "../types/contract";
import { phaseAtTime } from "./phases";
import { notLaneCheckText } from "./casEvent";

// Spec 03 v0.16 §5.2 / Spec 09 v0.19 §12.1: the Flight view's Events
// section — one chronological table of every event on the flight, limit
// and CAS (`exceedances[]`, both `source` values). Filter state and the
// severity label come from the limit_exceedances insight that carries the
// event (matched by event_id); the event list itself is the data.

export type EventSource = "limit" | "cas";

// Two glyphs, shared by the table and the chart markers.
export const EVENT_GLYPH: Record<EventSource, string> = { limit: "▲", cas: "◆" };

export interface EventRow {
  key: string; // event_id, or a positional fallback for pre-Spec-09 analyses
  n: number; // 1-based chronological position — same number on the chart marker
  source: EventSource;
  event: FlightEvent;
  elapsed_s: number | null;
  phase: string | null;
  target: FilterTarget | null;
  targetLabel: string; // "Fuel pressure maximum (max 46 psi)" / "ENGINE ECU"
  duration_s: number;
  excessText: string | null; // limits only
  reason: string | null; // CAS not_lane_check_reason in words, with the band
  severity: InsightSeverity | null;
  // "suppressed": inside a filter (collapsed); "breach": a filtered
  // target's event the filter doesn't tolerate.
  filterState: "none" | "suppressed" | "breach";
  // Which condition hides it (Spec 09 §11.3), and the phases its rows lie
  // in (v0.20, from the limit insight's event).
  suppressedBy: "phase" | "duration" | "magnitude" | null;
  phases: string[] | null;
  insight: Insight | null;
  eventIndex: number; // index into insight.events / insight.evidence
}

export interface FilteredGroup {
  kind: "filtered";
  key: string;
  targetLabel: string;
  filterId: string | null;
  rows: EventRow[];
}

export type EventItem = { kind: "row"; row: EventRow } | FilteredGroup;

function isCas(e: FlightEvent): e is CasEvent {
  return (e as CasEvent).source === "cas";
}

function fmtNum(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

function limitTargetLabel(e: ExceedanceEvent): string {
  return `${e.label} (${e.limit_type === "MIN" ? "min" : "max"} ${fmtNum(e.limit_value)} ${e.unit})`;
}

export function buildEventRows(fa: FlightAnalysis, insightSet: InsightSet): EventRow[] {
  const limitTopic = insightSet.topics.find((t) => t.topic_id === "limit_exceedances");
  const byEventId = new Map<string, { insight: Insight; index: number }>();
  for (const ins of limitTopic?.insights ?? []) {
    (ins.events ?? []).forEach((ev, index) => byEventId.set(ev.event_id, { insight: ins, index }));
  }
  const phases: Phase[] = fa.phases;

  const rows = fa.exceedances.map((e, i): Omit<EventRow, "n"> => {
    const key = e.event_id ?? `event-${i}`;
    const hit = e.event_id ? byEventId.get(e.event_id) : undefined;
    const insEvent = hit?.insight.events?.[hit.index];
    const suppressed = Boolean(insEvent && insEvent.suppressed_by);
    const filterState: EventRow["filterState"] = suppressed
      ? "suppressed"
      : hit?.insight.filter?.outcome === "breach" ? "breach" : "none";
    if (isCas(e)) {
      return {
        key, source: "cas", event: e, elapsed_s: e.elapsed_s, phase: e.phase,
        target: { kind: "cas", cas_id: e.cas_id }, targetLabel: e.cas_id, duration_s: e.duration_s,
        excessText: null, reason: notLaneCheckText(e),
        severity: hit?.insight.severity ?? null, filterState, insight: hit?.insight ?? null, eventIndex: hit?.index ?? 0,
        suppressedBy: insEvent?.suppressed_by ?? null, phases: null,
      };
    }
    const lim = e as ExceedanceEvent;
    const limEvent = insEvent && !("classification" in insEvent) ? insEvent : undefined;
    const excess = lim.excess ?? null;
    return {
      key, source: "limit", event: e, elapsed_s: lim.elapsed_s,
      phase: phaseAtTime(phases, lim.elapsed_s) ?? null,
      target: lim.limit_id ? { kind: "limit", limit_id: lim.limit_id } : null,
      targetLabel: limitTargetLabel(lim), duration_s: lim.duration_s,
      excessText: excess === null ? null : `${lim.limit_type === "MIN" ? "−" : "+"}${fmtNum(Math.abs(excess))} ${lim.unit}`,
      reason: limEvent?.suppressed_by === "phase" ? `suppressed (phase: ${(limEvent.phases ?? []).join(", ")})` : null,
      severity: hit?.insight.severity ?? null, filterState, insight: hit?.insight ?? null, eventIndex: hit?.index ?? 0,
      suppressedBy: limEvent?.suppressed_by ?? null, phases: limEvent?.phases ?? null,
    };
  });

  return rows
    .map((r, i) => ({ r, i }))
    .sort((a, b) => (a.r.elapsed_s ?? Infinity) - (b.r.elapsed_s ?? Infinity) || a.i - b.i)
    .map(({ r }, idx) => ({ ...r, n: idx + 1 }));
}

// Suppressed events collapse to one line per target, placed where that
// target's first suppressed event falls; everything else is a row.
export function groupEventRows(rows: EventRow[]): EventItem[] {
  const items: EventItem[] = [];
  const groups = new Map<string, FilteredGroup>();
  for (const row of rows) {
    if (row.filterState !== "suppressed") {
      items.push({ kind: "row", row });
      continue;
    }
    const gkey = row.target ? (row.target.kind === "cas" ? `cas:${row.target.cas_id}` : row.target.limit_id) : row.targetLabel;
    let g = groups.get(gkey);
    if (!g) {
      const label = row.event.source === "cas" ? (row.event as CasEvent).cas_id : (row.event as ExceedanceEvent).label;
      g = { kind: "filtered", key: `filtered:${gkey}`, targetLabel: label, filterId: row.insight?.filter?.filter_id ?? null, rows: [] };
      groups.set(gkey, g);
      items.push(g);
    }
    g.rows.push(row);
  }
  return items;
}

// The event a clicked insight points at, for highlighting its Events row
// and chart marker: its own event at evidenceIndex, else the first
// exceedance / cas_event evidence ref.
export function insightEventId(insight: Insight, evidenceIndex = 0): string | null {
  const own = insight.events?.[evidenceIndex]?.event_id;
  if (own) return own;
  const ref = insight.evidence.find((ev) => ev.kind === "exceedance" || ev.kind === "cas_event");
  return ref && "ref" in ref ? ref.ref : null;
}
