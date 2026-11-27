import type React from "react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { NotebookCard as Card, StudySummary } from "../../types/contract";
import { EVIDENCE, ORIGIN, OUTPUTS, TEST, actionsText, evidenceText, scopeText } from "../../lib/notebookCard";
import { TagEditor, ChannelTags, StatusMark, shortDate, statusColor } from "./bits";

// Spec 03 v0.34 §5.10 item 2 — the workspace's notebooks as cards, newest
// first, two or three to a row (one on a narrow window). Each card is what
// list_studies says the notebook is (Spec 16 §5.5): origin, title and status
// coloured by its resolution, the question, channels, scope, evidence and
// tests, the outputs' state, Claude's tags (a click filters), author and
// date. Nothing is typed here; nothing is computed. Above six notebooks a
// filter row appears: All · Open · Finished, and the tags present.

export const FILTER_ROW_ABOVE = 6;

type StatusFilter = "all" | "open" | "finished";

const EMPTY_CARD: Card = {
  v: 0, origin: "asked", channels: [], flights: 0, date_span: null, evidence: { log_views: 0, figures: 0, tables: 0 },
  tests: [], outputs: "current", resolution: null, tags: [],
};

const GRID: React.CSSProperties = {
  display: "grid", gap: 12,
  // two or three a row: a column is at least 300 px and at least a third of the row (one on a narrow window)
  gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, max(300px, calc((100% - 24px) / 3))), 1fr))",
};

const CARD: React.CSSProperties = {
  position: "relative", background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 10,
  padding: "12px 14px", display: "flex", flexDirection: "column", gap: 7, minWidth: 0,
};

const ROW: React.CSSProperties = { display: "flex", alignItems: "center", gap: 8, minWidth: 0 };
const GLYPH: React.CSSProperties = { fontSize: 11, color: "var(--text-tertiary)", whiteSpace: "nowrap" };
const FILTER: React.CSSProperties = {
  background: "none", border: "1px solid var(--border)", borderRadius: 999, padding: "2px 10px", fontSize: 11,
  color: "var(--text-secondary)", cursor: "pointer",
};

function status(s: StudySummary): string {
  return s.status === "reopened" ? "reopened" : s.status === "finished" ? "finished" : "open";
}

function sorted(studies: StudySummary[]): StudySummary[] {
  return [...studies].sort((a, b) => String(b.updated ?? b.created ?? "").localeCompare(String(a.updated ?? a.created ?? "")));
}

export function NotebookGrid({ studies, onChanged }: { studies: StudySummary[]; onChanged?: () => void }) {
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [tag, setTag] = useState<string | null>(null);
  const tags = useMemo(() => [...new Set(studies.flatMap((s) => s.card?.tags ?? []))].sort((a, b) => a.localeCompare(b)), [studies]);
  const showRow = studies.length > FILTER_ROW_ABOVE;
  const shown = sorted(studies).filter((s) =>
    (filter === "all" || (filter === "finished" ? status(s) === "finished" : status(s) !== "finished"))
    && (!tag || (s.card?.tags ?? []).includes(tag)));

  const on = (active: boolean): React.CSSProperties => active
    ? { ...FILTER, background: "var(--brand-fill)", borderColor: "var(--brand-tint)", color: "var(--text-primary)" } : FILTER;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {(showRow || tag) && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }} data-testid="notebook-filters">
          {showRow && (["all", "open", "finished"] as StatusFilter[]).map((f) => (
            <button key={f} type="button" style={on(filter === f)} aria-pressed={filter === f} onClick={() => setFilter(f)} data-testid={`notebook-filter-${f}`}>
              {f[0].toUpperCase() + f.slice(1)}
            </button>
          ))}
          {showRow && tags.length > 0 && <span style={{ width: 1, height: 16, background: "var(--border)", margin: "0 4px" }} />}
          {(showRow ? tags : tag ? [tag] : []).map((t) => (
            <button key={t} type="button" style={on(tag === t)} aria-pressed={tag === t} onClick={() => setTag(tag === t ? null : t)} data-testid="notebook-filter-tag">
              {t}{tag === t ? " ×" : ""}
            </button>
          ))}
        </div>
      )}
      <div style={GRID} data-testid="notebook-grid">
        {shown.map((s) => <NotebookCard key={s.study_id} s={s} onTag={(t) => setTag(tag === t ? null : t)} activeTag={tag} onChanged={onChanged} />)}
      </div>
      {shown.length === 0 && <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>No notebook matches.</div>}
    </div>
  );
}

export function NotebookCard({ s, onTag, activeTag, onChanged }: {
  s: StudySummary; onTag?: (t: string) => void; activeTag?: string | null; onChanged?: () => void;
}) {
  const c = s.card ?? EMPTY_CARD;
  const st = status(s);
  const resolved = st === "finished" && c.resolution;
  const origin = ORIGIN[c.origin] ?? ORIGIN.asked;
  const out = OUTPUTS[c.outputs] ?? OUTPUTS.current;
  const ev = EVIDENCE.filter((e) => c.evidence[e.key]);
  return (
    <article className="nb-card" style={CARD} data-testid="notebook-card" data-study={s.study_id} data-status={st}>
      <div style={ROW}>
        <span title={origin.label} aria-label={origin.label} data-testid="card-origin" data-origin={c.origin}
          style={{ width: 18, textAlign: "center", fontSize: 13, color: "var(--text-secondary)", flexShrink: 0 }}>{origin.glyph}</span>
        {/* The title is the card's link; its ::after covers the card, so a click anywhere opens the notebook. */}
        <Link to={`/research/${s.study_id}`} className="card-link" data-testid="card-link"
          style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", textDecoration: "none", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0, flexGrow: 1 }}
          title={s.name}>
          {s.name}
        </Link>
        <StatusMark status={st} testid="card-status"
          color={resolved ? statusColor(c.resolution) : undefined}
          title={resolved ? `Finished: ${c.resolution === "nothing-here" ? "nothing here" : c.resolution}` : undefined} />
      </div>
      {s.question && (
        <div style={{ fontSize: 12, color: "var(--text-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
          title={s.question} data-testid="card-question">{s.question}</div>
      )}
      <ChannelTags channels={c.channels} />
      <div style={{ ...ROW, flexWrap: "wrap", rowGap: 4 }}>
        <span style={GLYPH} data-testid="card-scope" title={c.date_span ? `${c.date_span[0]} to ${c.date_span[1]}` : undefined}>{scopeText(c)}</span>
        {ev.length > 0 && (
          <span style={{ ...GLYPH, display: "inline-flex", gap: 8 }} title={evidenceText(c.evidence)} data-testid="card-evidence">
            {ev.map((e) => <span key={e.key} data-evidence={e.key}>{e.glyph} {c.evidence[e.key]}</span>)}
          </span>
        )}
        {c.tests.map((t) => (
          <span key={t} style={{ ...GLYPH, color: "var(--text-secondary)" }} title={`Test: ${TEST[t]?.label ?? t}`} data-testid="card-test">
            {TEST[t]?.glyph} {t}
          </span>
        ))}
        {c.actions !== undefined && c.actions !== null && (
          <span style={{ ...GLYPH, color: c.actions ? "var(--text-secondary)" : undefined }} data-testid="card-actions"
            title={c.actions ? "Proposed actions in the notebook's Answer" : "The Answer proposes no action"}>
            → {actionsText(c.actions)}
          </span>
        )}
      </div>
      <div style={{ ...ROW, marginTop: "auto" }}>
        <span aria-label={out.label} title={out.label} data-testid="card-outputs" data-outputs={c.outputs}
          style={{ width: 7, height: 7, borderRadius: "50%", background: out.color, flexShrink: 0 }} />
        <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 4, minWidth: 0 }}>
          {c.tags.map((t) => (
            <button key={t} type="button" onClick={() => onTag?.(t)} data-testid="card-tag" title={`Show the notebooks tagged “${t}”`}
              style={{ position: "relative", zIndex: 1, background: activeTag === t ? "var(--brand-fill)" : "var(--panel-control)", border: "none",
                borderRadius: 4, padding: "0 6px", fontSize: 10, lineHeight: "16px", color: "var(--text-secondary)", cursor: "pointer" }}>
              {t}
            </button>
          ))}
          {onChanged && <TagEditor studyId={s.study_id} tags={c.tags} onSaved={onChanged} testid="card-tag-add" />}
        </span>
        <span style={{ flexGrow: 1 }} />
        <span style={{ ...GLYPH, display: "inline-flex", gap: 6, alignItems: "center" }} data-testid="card-author">
          <span title={s.author === "claude" ? "Written by Claude" : "Written by you"}>{s.author === "claude" ? "✳ Claude" : "you"}</span>
          <span className="mono" title={s.updated ?? undefined}>{shortDate(s.updated ?? s.created)}</span>
        </span>
      </div>
    </article>
  );
}
