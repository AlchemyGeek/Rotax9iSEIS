// Spec 16 §5.3 — the investigation notebook (.ipynb) as the Research page
// shows it. The markup of markdown cells and outputs is a port of the
// engine's HTML export (slingology_eis/investigations/nbhtml.py), string for
// string, so the page and the exported page show one thing; both are
// checked against one golden (web/src/fixtures/research-notebook.render.json,
// tests/unit/test_nbhtml_parity.py and notebook.test.ts).
//
// Safety: a notebook may have been sent to the user, so nothing in it runs.
// Text and markdown are escaped; links to javascript:/data:/vbscript: are
// dropped; SVG is shown through <img> (a data: URL, where scripts don't
// run); `text/html` is used only for the tables EIS writes (output metadata
// `slingology.table`), and even then only table tags survive.

import { shortWindow } from "./timeLabel";

export const LOGVIEW_MIME = "application/vnd.slingology.logview+json";

export type NbText = string | string[] | undefined | null;

export interface NbOutput {
  output_type: "stream" | "execute_result" | "display_data" | "error" | string;
  name?: string;
  text?: NbText;
  data?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  ename?: string;
  evalue?: string;
  traceback?: string[] | string;
}

export interface NbCellMeta {
  role?: string;
  ran?: { engine?: string; flights?: string[]; at?: string; ms?: number; status?: string; source?: string; digest?: string };
  pending?: { outputs: NbOutput[]; ran?: unknown } | null;
  ran_elsewhere?: boolean | string;
  read_only?: boolean;
  [k: string]: unknown;
}

export interface NbCell {
  id: string;
  cell_type: "markdown" | "code" | "raw";
  source: NbText;
  outputs?: NbOutput[];
  metadata?: { slingology?: NbCellMeta; [k: string]: unknown };
}

export interface NbMeta {
  id: string;
  name?: string;
  kind?: string;
  author?: string;
  question?: string;
  status?: string;
  summary?: string;
  summaries?: { summary?: string; finished?: string | null }[];
  reopened?: string;
  engine?: string;
  updated?: string;
  created?: string;
  inbox_candidate?: string | null;
  workspace_id?: string;
  imported?: unknown;
  [k: string]: unknown;
}

export interface Notebook {
  nbformat: number;
  nbformat_minor: number;
  metadata: { slingology?: NbMeta; [k: string]: unknown };
  cells: NbCell[];
}

export interface LogViewRef {
  flight: string;
  flight_date_local?: string;
  start_s: number;
  end_s: number;
  channels: string[];
  marks?: LogViewMark[];
  title?: string | null;
  window_label?: string;
  rule?: unknown;
}

/** The engine writes `{t_s, label}`; `[t_s, label]` (the cell_append form) is read too. */
export type LogViewMark = { t_s: number; label: string } | [number, string];

export function logviewMarks(ref: LogViewRef): { t_s: number; label: string }[] {
  return (ref.marks ?? []).map((m) => (Array.isArray(m) ? { t_s: Number(m[0]), label: String(m[1] ?? "") } : { t_s: Number(m.t_s), label: String(m.label ?? "") }));
}

export const text = (t: NbText): string => (Array.isArray(t) ? t.join("") : t ?? "");
export const nbMeta = (nb: Notebook): NbMeta => (nb.metadata?.slingology ?? { id: "" }) as NbMeta;
export const cellMeta = (c: NbCell): NbCellMeta => (c.metadata?.slingology ?? {}) as NbCellMeta;

// ── Escaping, as Python's html.escape / html.unescape on what escape makes ──

export function escapeHtml(s: string, quote = true): string {
  s = s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return quote ? s.replace(/"/g, "&quot;").replace(/'/g, "&#x27;") : s;
}

function unescapeHtml(s: string): string {
  return s.replace(/&(amp|lt|gt|quot|#x27|#39);/g, (_m, e: string) =>
    ({ amp: "&", lt: "<", gt: ">", quot: '"', "#x27": "'", "#39": "'" })[e] ?? _m);
}

function b64(s: string): string {
  const bytes = new TextEncoder().encode(s);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

// ── Markdown (the subset notebooks use) ─────────────────────────────────────

/** `files/…` images a markdown cell shows, as data: URLs (load_study's `files`). */
export type FileImages = Record<string, string> | undefined;

const IMG_EXT = new Set([".svg", ".png", ".jpg", ".jpeg"]);

function safeUrl(u: string): string {
  u = unescapeHtml(u);
  if (/^\s*(javascript|data|vbscript):/i.test(u)) return "#";
  return escapeHtml(u, true);
}

function image(alt: string, url: string, files: FileImages): string {
  const u = unescapeHtml(url);
  const ext = u.includes(".") ? "." + u.split(".").pop()!.toLowerCase() : "";
  if (files && u.startsWith("files/") && IMG_EXT.has(ext) && files[u]) {
    return `<img class="figure" alt="${alt}" src="${files[u]}">`;
  }
  return `<img alt="${alt}" src="${safeUrl(url)}">`;
}

function inline(s: string, files?: FileImages): string {
  s = escapeHtml(s, false);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (_m, alt: string, url: string) => image(alt, url, files));
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_m, label: string, url: string) => `<a href="${safeUrl(url)}">${label}</a>`);
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(?<![*\p{L}\p{N}_])\*([^*\n]+)\*(?![*\p{L}\p{N}_])/gu, "<em>$1</em>");
  return s;
}

const LIST_ITEM = /^\s*([-*•]|\d+\.)\s+/;

export function markdown(src: string, files?: FileImages): string {
  const out: string[] = [];
  const lines = src.split(/\r\n|\r|\n/);
  if (lines.length && lines[lines.length - 1] === "") lines.pop();
  const para: string[] = [];
  const flush = () => {
    if (para.length) {
      out.push("<p>" + inline(para.join(" "), files) + "</p>");
      para.length = 0;
    }
  };
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("```")) {
      flush();
      let j = i + 1;
      while (j < lines.length && !lines[j].startsWith("```")) j++;
      out.push("<pre><code>" + escapeHtml(lines.slice(i + 1, j).join("\n")) + "</code></pre>");
      i = j + 1;
      continue;
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) {
      flush();
      const n = h[1].length;
      out.push(`<h${n}>${inline(h[2])}</h${n}>`);
    } else if (LIST_ITEM.test(line)) {
      flush();
      const tag = /^\s*\d+\./.test(line) ? "ol" : "ul";
      const items: string[] = [];
      while (i < lines.length && LIST_ITEM.test(lines[i])) {
        items.push("<li>" + inline(lines[i].replace(LIST_ITEM, "")) + "</li>");
        i++;
      }
      out.push(`<${tag}>` + items.join("") + `</${tag}>`);
      continue;
    } else if (line.startsWith("|") && i + 1 < lines.length && /^\|?\s*:?-{3,}/.test(lines[i + 1])) {
      flush();
      const row = (s: string) => s.trim().replace(/^\|+|\|+$/g, "").split("|").map((c) => c.trim());
      const head = row(line);
      const body: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].startsWith("|")) body.push(row(lines[i++]));
      out.push('<table class="eis-table"><thead><tr>' + head.map((c) => `<th>${inline(c)}</th>`).join("")
        + "</tr></thead><tbody>" + body.map((r) => "<tr>" + r.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>").join("")
        + "</tbody></table>");
      continue;
    } else if (line.startsWith(">")) {
      flush();
      out.push("<blockquote>" + inline(line.replace(/^[> ]+/, "")) + "</blockquote>");
    } else if (!line.trim()) {
      flush();
    } else {
      para.push(line.trim());
    }
    i++;
  }
  flush();
  return out.join("\n");
}

// ── Outputs ─────────────────────────────────────────────────────────────────

const TABLE_TAGS = new Set(["table", "caption", "thead", "tbody", "tr", "th", "td", "p"]);

/** EIS's table HTML with every tag but the table's own dropped and every
 *  attribute dropped (the table keeps class="eis-table"). Identity on what
 *  the bench writes. */
export function sanitizeTable(html: string): string {
  return html.split(/(<[^>]*>)/).map((tok) => {
    if (tok.startsWith("<")) {
      const m = /^<(\/?)([a-zA-Z]+)\b/.exec(tok);
      if (!m || !TABLE_TAGS.has(m[2].toLowerCase())) return "";
      const tag = m[2].toLowerCase();
      return m[1] ? `</${tag}>` : tag === "table" ? '<table class="eis-table">' : `<${tag}>`;
    }
    return tok.replace(/>/g, "&gt;");
  }).join("");
}

function img(svg: string, cls = "figure", alt = "figure"): string {
  return `<img class="${cls}" alt="${escapeHtml(alt)}" src="data:image/svg+xml;base64,${b64(svg)}">`;
}

export function isTable(o: NbOutput): boolean {
  const sm = (o.metadata?.slingology ?? {}) as { table?: unknown };
  return !!(o.data && "text/html" in o.data && sm.table);
}

export function logviewRef(o: NbOutput): LogViewRef | null {
  const d = o.data;
  if (!d || !(LOGVIEW_MIME in d) || !("image/svg+xml" in d)) return null;
  return (d[LOGVIEW_MIME] ?? {}) as LogViewRef;
}

/** The title and the short window (Spec 03 v0.34) — nbhtml.logview_caption. */
export function logviewCaption(ref: LogViewRef): string {
  const title = String(ref.title ?? "").trim();
  const when = ref.window_label ? shortWindow(ref.window_label) : "";
  return [title, when].filter(Boolean).join(" · ") || "log view";
}

export function outputHtml(o: NbOutput): string {
  const t = o.output_type;
  if (t === "stream") {
    return `<pre class="${o.name === "stderr" ? "stderr" : "stdout"}">` + escapeHtml(text(o.text)) + "</pre>";
  }
  if (t === "error") {
    const tb = o.traceback ?? [];
    const body = Array.isArray(tb) ? tb.join("\n") : String(tb);
    // eslint-disable-next-line no-control-regex
    return '<pre class="error">' + escapeHtml(body.replace(/\x1b\[[0-9;]*m/g, "")) + "</pre>";
  }
  const data = (o.data ?? {}) as Record<string, NbText>;
  const ref = logviewRef(o);
  if (ref) {
    const cap = escapeHtml(logviewCaption(ref));
    const full = escapeHtml(String(ref.window_label ?? ""));
    return `<figure class="logview">${img(text(data["image/svg+xml"]), "figure", cap)}<figcaption title="${full}">${cap}</figcaption></figure>`;
  }
  if ("image/svg+xml" in data) return img(text(data["image/svg+xml"]), "figure", text(data["text/plain"]) || "figure");
  if ("image/png" in data) return `<img class="figure" alt="figure" src="data:image/png;base64,${text(data["image/png"]).trim()}">`;
  if (isTable(o)) return sanitizeTable(text(data["text/html"]));
  if ("text/plain" in data) return "<pre>" + escapeHtml(text(data["text/plain"])) + "</pre>";
  return "";
}

// ── The header's state line ─────────────────────────────────────────────────

/** Spec 16 F17: open, finished, or *reopened* — finished before, a follow-up under way. */
export function notebookStatus(m: NbMeta): string {
  return m.status === "open" && m.reopened ? "reopened" : m.status || "open";
}

/** F17: the summaries a follow-up replaced, newest first, each with its
 * date — the markup nbhtml.summary_history writes in the export. */
export function summaryHistory(summaries: { summary?: string; finished?: string | null }[]): string {
  const items = [...summaries].reverse().map((e) =>
    `<div class="earlier"><p class="meta">Summary of ${escapeHtml((e.finished ?? "").slice(0, 10) || "undated")}</p>${markdown(e.summary ?? "")}</div>`);
  return `<details class="summary-history"><summary>Earlier summaries (${summaries.length})</summary>${items.join("")}</details>`;
}

/** The summary, open, with the earlier ones inside it — nbhtml.summary_block. */
export function summaryBlock(summary: string, summaries: { summary?: string; finished?: string | null }[]): string {
  return '<details class="summary" open><summary>Summary</summary>' + markdown(summary)
    + (summaries.length ? summaryHistory(summaries) : "") + "</details>";
}

/** The setup cell (D14) — bound eis to the workspace; not shown (Spec 03 v0.34). */
export function isSetupCell(c: NbCell): boolean {
  return c.cell_type === "code" && (c.id === "setup" || cellMeta(c).role === "setup");
}

/** "by claude · finished · engine 1.0.2 · 2026-11-15" — the export's line. */
export function metaLine(m: NbMeta): string {
  return [`by ${m.author || "user"}`, notebookStatus(m), `engine ${m.engine ?? ""}`, (m.updated ?? "").slice(0, 10)]
    .filter(Boolean).map((x) => escapeHtml(String(x))).join(" · ");
}

export interface OutputsState {
  pending: number;
  ranElsewhere: number;
  readOnly: number;
}

export function outputsState(nb: Notebook): OutputsState {
  const s: OutputsState = { pending: 0, ranElsewhere: 0, readOnly: 0 };
  for (const c of nb.cells) {
    if (c.cell_type !== "code") continue;
    const sm = cellMeta(c);
    if (sm.pending) s.pending++;
    if (sm.ran_elsewhere) s.ranElsewhere++;
    if (sm.read_only) s.readOnly++;
  }
  return s;
}

/** "outputs current for this workspace", or what is not: the export says the same. */
export function outputsLine(s: OutputsState): string {
  const parts: string[] = [];
  const n = (k: number, what: string) => `${k} cell${k === 1 ? "" : "s"} ${what}`;
  if (s.pending) parts.push(n(s.pending, "with new outputs pending"));
  if (s.ranElsewhere) parts.push(n(s.ranElsewhere, "ran elsewhere"));
  if (s.readOnly) parts.push(n(s.readOnly, "read-only (flights not here)"));
  return parts.length ? "outputs: " + parts.join(" · ") : "outputs current for this workspace";
}

/** The flags a code cell carries, as the export prints them. */
export function cellFlags(c: NbCell): string[] {
  const sm = cellMeta(c);
  return [["ran elsewhere", sm.ran_elsewhere], ["read-only", sm.read_only]].filter(([, on]) => on).map(([f]) => f as string);
}

// ── Spec 16 D19 §5.6: the shaped notebook's reading order (nbhtml.layout, value for value) ──

export const EVIDENCE_LABEL: Record<string, string> = { table: "Table", figure: "Figure", logview: "Log view" };

export function isShaped(nb: Notebook): boolean {
  return nbMeta(nb).shape === 1;
}

/** A cell's role; a code cell with none is support, a markdown cell narrative. */
export function cellRole(c: NbCell): string {
  return cellMeta(c).role || (c.cell_type === "code" ? "support" : "narrative");
}

function evidenceMark(o: NbOutput): [string, string] | null {
  const ev = ((o.metadata?.slingology ?? {}) as { evidence?: { kind?: string; caption?: string } }).evidence;
  if (ev) return [ev.kind || "table", String(ev.caption ?? "")];
  const ref = o.data?.[LOGVIEW_MIME] as { caption?: string; title?: string } | undefined;
  if (ref && typeof ref === "object") return ["logview", String(ref.caption || ref.title || "")];
  return null;
}

/** Section 1's markdown without the notebook's title (the header has it). */
export function topSource(src: string): string {
  return src.replace(/^# [^\n]*\n+/, "");
}

export interface EvidenceLabel { output: number; label: string; caption: string }
export type LayoutBlock =
  | { kind: "section"; n: number; id: string }
  | { kind: "working"; ids: string[] }
  | { kind: "markdown" | "support" | "code"; id: string }
  | { kind: "evidence"; id: string; labels: EvidenceLabel[] };

/** Sections 1–3's markdown (`top`) and the blocks in reading order: headings,
 *  markdown, evidence (each evidence output numbered with its caption),
 *  support (folded), other code, and *Working* — section 7's cells as one. */
export function layout(nb: Notebook): { top: string[]; blocks: LayoutBlock[] } {
  const top: string[] = [];
  const blocks: LayoutBlock[] = [];
  let n = 0;
  let section: number | null = null;
  const working: string[] = [];
  for (const c of nb.cells) {
    const sm = cellMeta(c);
    if (isSetupCell(c)) continue;
    if (sm.role === "section") {
      section = Number(sm.section);
      if (sm.generated) {
        const src = text(c.source);
        top.push(section === 1 ? topSource(src) : src);
        continue;
      }
      blocks.push({ kind: "section", n: section, id: c.id });
      if (section === 7) blocks.push({ kind: "working", ids: working });
      continue;
    }
    if (section === 7) { working.push(c.id); continue; }
    if (c.cell_type === "markdown") { blocks.push({ kind: "markdown", id: c.id }); continue; }
    if (c.cell_type !== "code") continue;
    const r = cellRole(c);
    if (r === "evidence") {
      const labels: EvidenceLabel[] = [];
      (c.outputs ?? []).forEach((o, i) => {
        const mark = evidenceMark(o);
        if (mark) { n++; labels.push({ output: i, label: `${EVIDENCE_LABEL[mark[0]] ?? "Table"} ${n}`, caption: mark[1] }); }
      });
      blocks.push({ kind: "evidence", id: c.id, labels });
    } else blocks.push({ kind: r === "support" ? "support" : "code", id: c.id });
  }
  return { top, blocks };
}

export function evidenceCaption(label: string, caption: string): string {
  return caption ? `<figcaption><strong>${escapeHtml(label)}.</strong> ${inline(caption)}</figcaption>`
    : `<figcaption><strong>${escapeHtml(label)}.</strong></figcaption>`;
}

/** An evidence output without the table's own <caption> (the numbered caption replaces it). */
export function evidenceOutput(o: NbOutput): string {
  return outputHtml(o).replace(/<caption>[\s\S]*?<\/caption>/, "");
}

export function workingSummary(k: number): string {
  return `Working (${k} cell${k === 1 ? "" : "s"})`;
}

export interface EarlierAnswer { shows?: string[]; means?: string | null; finished?: string | null }

/** The Answers a re-finish replaced, newest first, each with its date — nbhtml.answer_history. */
export function answerHistory(history: EarlierAnswer[]): string {
  const items = [...history].reverse().map((e) => {
    const body = (e.shows ?? []).map((x) => `<li>${inline(x)}</li>`).join("");
    return `<div class="earlier"><p class="meta">Answer of ${escapeHtml((e.finished ?? "").slice(0, 10) || "undated")}</p>`
      + (body ? `<ul>${body}</ul>` : "") + (e.means ? markdown(e.means) : "") + "</div>";
  });
  return `<details class="answer-history"><summary>Earlier answers (${history.length})</summary>${items.join("")}</details>`;
}

/** Sections 1–3 in one block with the earlier Answers (or summaries) inside — nbhtml.answer_block. */
export function answerBlock(top: string[], history: EarlierAnswer[], summaries: { summary?: string; finished?: string | null }[]): string {
  const earlier = history.length ? answerHistory(history) : summaries.length ? summaryHistory(summaries) : "";
  return '<section class="answer">' + top.map((t) => markdown(t)).join("") + earlier + "</section>";
}
