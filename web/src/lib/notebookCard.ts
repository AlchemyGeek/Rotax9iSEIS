// Spec 03 v0.34 §5.10 / Spec 16 §5.5 — what a notebook says about itself,
// as marks and words. Every value comes from the engine's card
// (list_studies); this file only names and draws it. The one-line form
// (`cardLine`) is the HTML export's, ported string for string in
// slingology_eis/investigations/nbhtml.py (card_line) and checked against
// the same golden.

import type { NotebookCard, NotebookOrigin, NotebookTest } from "../types/contract";
import { channelLabel } from "./research";
import { escapeHtml } from "./notebook";

export const ORIGIN: Record<NotebookOrigin, { glyph: string; label: string }> = {
  marks: { glyph: "✎", label: "From your marks" },
  candidate: { glyph: "◉", label: "From something EIS raised" },
  asked: { glyph: "?", label: "From a question asked in Claude Desktop" },
  imported: { glyph: "↓", label: "Imported" },
};

export const TEST: Record<NotebookTest, { glyph: string; label: string }> = {
  cycling: { glyph: "↻", label: "cycling" },
  coupling: { glyph: "⇄", label: "coupling" },
  groups: { glyph: "⊟", label: "groups" },
  unusual: { glyph: "◇", label: "unusual" },
};

export const EVIDENCE: { key: keyof NotebookCard["evidence"]; glyph: string; one: string; many: string }[] = [
  { key: "log_views", glyph: "∿", one: "log view", many: "log views" },
  { key: "figures", glyph: "◫", one: "figure", many: "figures" },
  { key: "tables", glyph: "▦", one: "table", many: "tables" },
];

export const OUTPUTS: Record<NotebookCard["outputs"], { label: string; color: string }> = {
  current: { label: "Outputs current for this workspace", color: "var(--success)" },
  pending: { label: "New outputs from a re-run are waiting to be accepted", color: "var(--severity-watch)" },
  elsewhere: { label: "Some outputs ran elsewhere (another computer or JupyterLab)", color: "var(--severity-info-text)" },
};

/** The short channel names the cards and marks carry; the full name on hover. */
const SHORT: Record<string, string> = {
  rpm: "RPM", map_inhg: "MAP", fuel_flow_gph: "FF", fuel_press_psi: "FP", oil_temp_f: "OIL T", oil_press_psi: "OIL P",
  coolant_temp_f: "CT", egt_spread_f: "EGT Δ", egt_mean_f: "EGT", ias_kt: "IAS", vs_fpm: "VS", power_pct: "PWR",
  main_volts: "V", batt_amps: "A", throttle_pct: "THR", press_alt_ft: "ALT", oat_c: "OAT", oat_f: "OAT",
};

export function channelShort(id: string): string {
  const egt = /^egt([1-4])_f$/.exec(id);
  if (egt) return `EGT ${egt[1]}`;
  return SHORT[id] ?? id;
}

export function channelTitle(id: string): string {
  return channelLabel(id) === id ? id : `${channelLabel(id)} (${id})`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function ymd(d: string): [number, number, number] | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d);
  return m ? [+m[1], +m[2], +m[3]] : null;
}

/** "Oct 24", "Oct 2–24", "Apr–Nov", "Nov 2025–Feb 2026". */
export function spanText(span: [string, string] | null | undefined): string {
  if (!span) return "";
  const a = ymd(span[0]), b = ymd(span[1]);
  if (!a || !b) return "";
  const mon = (x: [number, number, number]) => MONTHS[x[1] - 1];
  if (a[0] !== b[0]) return `${mon(a)} ${a[0]}–${mon(b)} ${b[0]}`;
  if (a[1] !== b[1]) return `${mon(a)}–${mon(b)}`;
  if (a[2] !== b[2]) return `${mon(a)} ${a[2]}–${b[2]}`;
  return `${mon(a)} ${a[2]}`;
}

/** "3 flights · Oct 2–24", "62 flights · Apr–Nov", "no flights read". */
export function scopeText(card: Pick<NotebookCard, "flights" | "date_span">): string {
  if (!card.flights) return "no flights read";
  const n = `${card.flights} flight${card.flights === 1 ? "" : "s"}`;
  const s = spanText(card.date_span);
  return s ? `${n} · ${s}` : n;
}

export function evidenceText(e: NotebookCard["evidence"]): string {
  return EVIDENCE.filter((x) => e[x.key]).map((x) => `${e[x.key]} ${e[x.key] === 1 ? x.one : x.many}`).join(", ");
}

/** D19: "n actions" ("no actions" when the Answer proposes none) — nbhtml.actions_text. */
export function actionsText(n: number): string {
  return !n ? "no actions" : `${n} action${n === 1 ? "" : "s"}`;
}

/** The card as one line of the HTML export's header (nbhtml.card_line). */
export function cardLine(card: NotebookCard | null | undefined): string {
  if (!card) return "";
  const parts: string[] = [`${ORIGIN[card.origin]?.glyph ?? "?"} ${ORIGIN[card.origin]?.label ?? card.origin}`];
  if (card.channels.length) parts.push(card.channels.map(channelShort).join(" "));
  parts.push(scopeText(card));
  const ev = EVIDENCE.filter((x) => card.evidence[x.key]).map((x) => `${x.glyph} ${card.evidence[x.key]} ${card.evidence[x.key] === 1 ? x.one : x.many}`);
  if (ev.length) parts.push(ev.join(" "));
  if (card.tests.length) parts.push(card.tests.map((t) => `${TEST[t]?.glyph ?? ""} ${t}`).join(" "));
  if (card.actions !== undefined && card.actions !== null) parts.push(actionsText(card.actions));
  if (card.tags.length) parts.push("tags: " + card.tags.join(", "));
  return '<p class="meta card">' + parts.map((p) => escapeHtml(p)).join(" · ") + "</p>";
}
