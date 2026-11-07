import type { HandSlice, ResearchTestId, ResearchTestResult, SliceRule, StudySelection, StudyTest, UserReference } from "../types/contract";

// Spec 06 — the web's Research helpers. Nothing here computes a result:
// every number comes from the host (§11, API-first). This file holds the
// questions as the pilot reads them, the pre-seed that "Research this"
// hands to a new study (§12), and small formatting helpers.

// The four v1 tests (§7.1–§7.4), in the order the "add a question" menu
// shows them. Labels mirror the engine's QUESTIONS; a second line says what
// the test needs so a pilot picks the right channels.
export const RESEARCH_TESTS: { id: ResearchTestId; question: string; needs: string }[] = [
  { id: "cycling", question: "Is this signal steady, or is it cycling?", needs: "one channel" },
  { id: "coupling", question: "Do these two move together, and who leads?", needs: "a reference channel and one or more others" },
  { id: "groups", question: "Are these two groups different?", needs: "a split of the selection and one descriptor" },
  { id: "unusual", question: "Which of these slices is unusual?", needs: "the channels to look across" },
];

export const TEST_QUESTION: Record<ResearchTestId, string> = Object.fromEntries(RESEARCH_TESTS.map((t) => [t.id, t.question])) as Record<ResearchTestId, string>;

// Channels a pilot is likely to ask about, in menu order. Anything the
// registry knows is accepted by the host; this is the short list.
export const RESEARCH_CHANNELS = [
  "rpm", "map_inhg", "fuel_flow_gph", "egt1_f", "egt2_f", "egt3_f", "egt4_f", "oil_press_psi", "oil_temp_f",
  "coolant_temp_f", "fuel_press_psi", "main_volts", "ias_kt", "vs_fpm", "power_pct",
];

export const CHANNEL_LABELS: Record<string, string> = {
  rpm: "RPM", map_inhg: "MAP", fuel_flow_gph: "Fuel flow", egt1_f: "EGT 1", egt2_f: "EGT 2", egt3_f: "EGT 3", egt4_f: "EGT 4",
  oil_press_psi: "Oil pressure", oil_temp_f: "Oil temperature", coolant_temp_f: "Coolant temperature",
  fuel_press_psi: "Fuel pressure", main_volts: "Main volts", ias_kt: "IAS", vs_fpm: "Vertical speed", power_pct: "Power",
  egt_spread_f: "EGT spread", egt_mean_f: "EGT mean", batt_amps: "Battery amps", throttle_pct: "Throttle",
};

export function channelLabel(id: string): string {
  return CHANNEL_LABELS[id] ?? id;
}

// Descriptors a groups test can compare (§6). The key is "<channel>.<name>".
export const DESCRIPTOR_NAMES: { key: string; label: string }[] = [
  { key: "median", label: "level (median)" }, { key: "mean", label: "mean" }, { key: "max", label: "maximum" },
  { key: "min", label: "minimum" }, { key: "swing", label: "swing (peak-to-peak)" }, { key: "sd", label: "standard deviation" },
  { key: "period_s", label: "period" }, { key: "slope_per_min", label: "slope per minute" },
  { key: "max_rate_per_s", label: "max rate per second" }, { key: "corr0", label: "zero-lag correlation with the reference" },
];

// A Trends metric's channel, for the "Research this" entry from a card
// (§12). Per-limit metrics name their limit; the limit's channel follows
// the Spec 09 catalogue's naming. Unknown metrics fall back to rpm.
export function channelForMetric(metricId: string): string {
  const m = metricId.replace(/^limit_/, "").replace(/_(peak_excess|time_above_pct|block_s)$/, "");
  const cyl = /^egt([1-4])/.exec(m);
  if (cyl) return `egt${cyl[1]}_f`;
  if (m.startsWith("egt_spread") || m.startsWith("egt_split")) return "egt_spread_f";
  if (m.startsWith("oil_temp")) return "oil_temp_f";
  if (m.startsWith("oil_press")) return "oil_press_psi";
  if (m.startsWith("coolant")) return "coolant_temp_f";
  if (m.startsWith("fuel_press")) return "fuel_press_psi";
  if (m.includes("fuel_flow") || m === "cruise_efficiency") return "fuel_flow_gph";
  if (m.includes("map") || m.startsWith("overboost")) return "map_inhg";
  if (m.startsWith("volts")) return "main_volts";
  if (m.includes("thermal")) return "oil_temp_f";
  return "rpm";
}

// The slice rule a Trends metric is best read in: takeoff metrics in the
// full-power preset, everything else in stable cruise.
export function presetForMetric(metricId: string): string {
  return /takeoff|overboost|rpm_takeoff|map_max/.test(metricId) ? "full_power" : "stable_cruise";
}

// ── "Research this" pre-seed (§12 entry points) ─────────────────────────────
// The entry points hand a draft study to /research/new through session
// storage: it survives the route change, never a reload, and is consumed
// once. No engine call is involved until the study page builds slices.

export interface StudySeed {
  name: string;
  from: "flight" | "trends" | "event";
  selection: StudySelection;
  slice_rules: (SliceRule | string)[];
  hand_slices: HandSlice[];
  tests: StudyTest[];
  references?: UserReference[];
  notes?: string;
  view?: { anchor?: string; channels?: string[] };
  // A preset the entry point suggests but does not add (Flight view: the
  // zoom covers a takeoff). The study page offers it as one click.
  suggested_preset?: string;
}

const SEED_KEY = "slingology-eis.research.seed";

export function stashStudySeed(seed: StudySeed) {
  try { sessionStorage.setItem(SEED_KEY, JSON.stringify(seed)); } catch { /* storage unavailable: the page opens empty */ }
}

export function takeStudySeed(): StudySeed | null {
  try {
    const raw = sessionStorage.getItem(SEED_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(SEED_KEY);
    return JSON.parse(raw) as StudySeed;
  } catch {
    return null;
  }
}

// Flight view: the chart's current zoom becomes a hand slice (§5.4, Q4).
// `coversTakeoff` — the zoom holds the TAKEOFF_ROLL phase — makes the
// full-power preset the suggested comparison set.
export function seedFromFlight(args: { flightId: string; date: string; start_s: number; end_s: number; coversTakeoff: boolean; channels: string[] }): StudySeed {
  const start = Math.max(0, Math.floor(args.start_s));
  const end = Math.max(start + 1, Math.ceil(args.end_s));
  return {
    name: `${args.date} — ${fmtClock(start)}–${fmtClock(end)}`,
    from: "flight",
    selection: { mode: "all", split: null },
    slice_rules: [],
    hand_slices: [{ flight: args.flightId, start_s: start, end_s: end, label: `${args.date} ${fmtClock(start)}`, offset_s: 0 }],
    tests: [{ test_id: "cycling", params: {}, channels: [args.channels[0] ?? "rpm"] }],
    view: { anchor: "start", channels: args.channels.length ? args.channels.slice(0, 3) : ["rpm", "map_inhg", "fuel_flow_gph"] },
    suggested_preset: args.coversTakeoff ? "full_power" : undefined,
  };
}

// Trends card: the metric's recent flights against every other flight,
// on the metric's channel, in the slice rule the metric is read in.
export function seedFromTrend(args: { metricId: string; label: string; recentFlightIds: string[]; allFlightIds: string[] }): StudySeed {
  const ch = channelForMetric(args.metricId);
  const recent = new Set(args.recentFlightIds);
  const reference = args.allFlightIds.filter((f) => !recent.has(f));
  return {
    name: `${args.label}: recent flights vs reference`,
    from: "trends",
    selection: {
      mode: "all",
      split: { by: "flights", groups: [{ label: "reference flights", flights: reference }, { label: "recent flights", flights: args.recentFlightIds }] },
    },
    slice_rules: [presetForMetric(args.metricId)],
    hand_slices: [],
    tests: [{ test_id: "groups", params: { descriptor: `${ch}.median` }, channels: [ch] }],
    view: { anchor: "crossing", channels: [ch, "rpm"] },
    notes: `Started from the Trends card for ${args.label}.`,
  };
}

// Events table: this event's window on this flight, and the same limit's
// condition across every flight — the rule is the limit's channel past the
// limit value, so the slices are the moments any flight did the same thing.
export function seedFromEvent(args: {
  flightId: string; date: string; label: string; channel: string; limitType: "MIN" | "MAX"; limitValue: number;
  start_s: number; duration_s: number;
}): StudySeed {
  const start = Math.max(0, Math.floor(args.start_s) - 10);
  const end = Math.ceil(args.start_s + Math.max(args.duration_s, 1)) + 10;
  const rule: SliceRule = {
    rule_id: `event-${args.channel}`,
    name: `${args.label} — moments past the limit`,
    conditions: [{ channel: args.channel, op: args.limitType === "MAX" ? ">=" : "<=", value: args.limitValue }],
    min_duration_s: 1, merge_gap_s: 3, pad_s: 10, phase: null,
  };
  return {
    name: `${args.label} — ${args.date}`,
    from: "event",
    selection: { mode: "all", split: null },
    slice_rules: [rule],
    hand_slices: [{ flight: args.flightId, start_s: start, end_s: end, label: `${args.date} event`, offset_s: 0 }],
    tests: [{ test_id: "unusual", params: {}, channels: [args.channel, "rpm", "map_inhg"] }],
    view: { anchor: "crossing", channels: [args.channel, "rpm"] },
    notes: `Started from an event on ${args.date}.`,
  };
}

// ── Formatting ──────────────────────────────────────────────────────────────

export function fmtClock(s: number): string {
  const m = Math.floor(s / 60), r = Math.round(s % 60);
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

export function fmtNum(v: unknown, nd = 1): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v !== "number" || !isFinite(v)) return String(v);
  if (Math.abs(v) >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return v.toLocaleString(undefined, { maximumFractionDigits: nd });
}

export function fmtRef(r: { value: number | [number, number] | null; unit?: string }): string {
  if (r.value === null || r.value === undefined) return "—";
  const u = r.unit ? ` ${r.unit}` : "";
  if (Array.isArray(r.value)) return `${fmtNum(r.value[0])}–${fmtNum(r.value[1])}${u}`;
  return `${fmtNum(r.value)}${u}`;
}

// The per-slice table as CSV (§8 Evidence, one click away).
export function tableToCsv(result: ResearchTestResult): string {
  const cols = result.evidence.table.columns;
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const head = cols.map((c) => esc(c.unit ? `${c.label} (${c.unit})` : c.label)).join(",");
  const body = result.evidence.table.rows.map((row) => cols.map((c) => esc(row[c.key])).join(","));
  return [head, ...body].join("\n");
}

export function downloadText(filename: string, text: string, type = "text/plain") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function describeSelection(sel: StudySelection, flightCount?: number): string {
  const base = sel.mode === "all" ? "all flights" : `${sel.flights?.length ?? 0} chosen flight${(sel.flights?.length ?? 0) === 1 ? "" : "s"}`;
  const n = sel.mode === "all" && flightCount !== undefined ? ` (${flightCount})` : "";
  const split = sel.split ? `, split by ${splitLabel(sel.split)}` : "";
  return base + n + split;
}

export function splitLabel(split: NonNullable<StudySelection["split"]>): string {
  switch (split.by) {
    case "da_band": return "density-altitude band";
    case "oat_band": return "OAT band";
    case "engine_hours": return "engine hours";
    case "source": return "log source";
    case "rule": return "slice rule";
    case "date": return `date (${split.date})`;
    case "flights": return split.groups.map((g) => g.label).join(" vs ");
  }
}

// Spec 06 D5 / acceptance 9: no verdict words in text we write ourselves.
// The result sentences come from the engine (checked there); this guards
// the page's own labels in a test.
export const FORBIDDEN_UI_WORDS = ["abnormal", "fault", "defect", "cycling detected", "failure"];
