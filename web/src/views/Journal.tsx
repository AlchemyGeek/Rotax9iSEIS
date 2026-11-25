import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { NavShell } from "../components/NavShell";
import { LimitFiltersSection } from "../components/LimitFiltersSection";
import { FilterEditor } from "../components/FilterEditor";
import { ExcludeConfirmDialog } from "../components/ExcludeDialog";
import { notifyFiltersChanged } from "../lib/filterAttention";
import { notifyShiftHistoryChanged } from "../lib/shiftHistoryAttention";
import { EngineRpcError, getEngineClient, type FlightSummary } from "../lib/engineClient";
import { useCapabilities } from "../lib/capabilities";
import type { Annotation, FilterTarget, JournalEntry, JournalEntryKind, JournalSection } from "../types/contract";
import { InlineHelp } from "../components/InlineHelp";
import { ScopeCaption } from "../components/ScopeCaption";
import { ActionMenu, type MenuItem } from "../components/research/bits";
import { APPLY_LABEL, filterScope, type Scope } from "../lib/scope";

const client = getEngineClient();

// Spec 14 §6 — Journal is the register of decisions in force: one entry per
// decision while it stands; reversing it removes the entry, editing it
// updates it. The effect is live — the engine recomputes it each time the
// page opens — and a decision that currently does nothing says so.
//
// §6.4 (v0.20) — the page answers one glance: what is in force, and does
// anything need me? Change notices first (the page's one accent), then the
// entries one line each, grouped by kind in order of consequence with each
// section's count and total effect (sections, titles and phrases come from
// get_journal: the page computes nothing). A line opens in place to its
// value, scope, reason, note, dates and a ⋯ menu with the actions.

// §7.5 — the scope of the decision each entry stands for.
const ENTRY_SCOPE: Partial<Record<JournalEntryKind, Scope>> = {
  exclusion: "flight",
  reference_pin: "metric",
  limit_filter: "limit",
  rule_edit: "topic",
  disabled_topic: "topic",
  changed_setting: "reference_settings",
};

// The Settings tab a changed setting lives on (Log channels are on Engine).
function settingsTab(e: JournalEntry): string {
  return (e.where as { tab?: string } | null)?.tab ?? "reference";
}

const KIND_LABELS: Record<JournalEntryKind, string> = {
  acknowledged_insight: "Acknowledged insight",
  limit_filter: "Limit filter",
  disabled_topic: "Disabled topic",
  rule_edit: "Rule edit",
  changed_setting: "Changed setting",
  exclusion: "Excluded from reference",
  reference_pin: "Reference pinned",
  annotation: "Annotation",
  study_finding: "Research finding",
};

// The kind glyph at the head of a line; its name is the hover text.
const KIND_GLYPH: Record<JournalEntryKind, string> = {
  limit_filter: "⊖",
  exclusion: "⊘",
  changed_setting: "≠",
  rule_edit: "≠",
  disabled_topic: "○",
  reference_pin: "⌖",
  study_finding: "▤",
  annotation: "❝",
  acknowledged_insight: "✓",
};

// §6.1 "Removed by" — the action that ends each decision.
const REMOVE_LABEL: Record<JournalEntryKind, string> = {
  acknowledged_insight: "Un-acknowledge",
  limit_filter: "Remove filter",
  disabled_topic: "Enable",
  rule_edit: "Reset to shipped",
  changed_setting: "Reset to shipped",
  exclusion: "Include again",
  reference_pin: "Unpin",
  annotation: "Delete",
  study_finding: "Remove from Journal",
};

function longDate(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" });
}

function shortDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return d.toLocaleDateString(undefined, sameYear ? { month: "short", day: "numeric" } : { month: "short", day: "numeric", year: "numeric" });
}

// What removing the decision will do — the original decision's preview,
// in reverse, from its live effect.
function removalPreview(e: JournalEntry): string {
  const effect = e.effect?.text;
  switch (e.kind) {
    case "limit_filter":
      return e.effect?.zero ? "Nothing is hidden by this filter now, so removing it changes no flight." : `Its events show again — it is ${effect}.`;
    case "disabled_topic":
      return e.effect?.zero ? "The topic comes back on; it would raise nothing on your flights now." : `The topic comes back on — it is ${effect}.`;
    case "rule_edit":
      return `The rule goes back to its shipped values${e.current ? ` (${e.current})` : ""}; it ${effect ?? "changes nothing"}.`;
    case "changed_setting":
      return `The setting goes back to its shipped value${e.current ? ` (${e.current})` : ""}; it ${effect ?? "changes nothing"}.`;
    case "reference_pin":
      return "The metric goes back to its automatic reference.";
    case "annotation":
      return "The note is deleted.";
    case "study_finding":
      return "The finding leaves the Journal; the notebook keeps it.";
    default:
      return "";
  }
}

type GroupBy = "kind" | "date" | "flight";

// §6.4 item 4: titles at body size, secondary one step down and one grey, nothing under 13 px.
const TITLE: React.CSSProperties = { fontSize: 14, fontWeight: 400, color: "var(--text-primary)" };
const SECONDARY: React.CSSProperties = { fontSize: 13, color: "var(--text-secondary)" };
const QUIET: React.CSSProperties = { fontSize: 13, color: "var(--text-tertiary)" };
const LINK: React.CSSProperties = {
  background: "none", border: "none", padding: 0, cursor: "pointer", fontSize: 13,
  color: "var(--link)", textDecoration: "underline", textDecorationColor: "var(--link-underline)", textUnderlineOffset: 2,
};
const BUTTON = (primary: boolean): React.CSSProperties => ({
  padding: "5px 11px", borderRadius: 6, fontSize: 13, cursor: "pointer", fontWeight: primary ? 600 : 400,
  background: primary ? "var(--brand)" : "transparent", color: primary ? "var(--on-brand)" : "var(--text-secondary)",
  border: primary ? "none" : "1px solid var(--border)",
});
const SEGMENT = (active: boolean): React.CSSProperties => ({
  padding: "3px 10px", fontSize: 13, cursor: "pointer", border: "1px solid var(--border)",
  background: active ? "var(--panel-control)" : "transparent", color: active ? "var(--text-primary)" : "var(--text-secondary)",
});

export function Journal() {
  const navigate = useNavigate();
  // Spec 14 v0.13 §5: Settings links a changed setting to its entry here.
  const [params, setParams] = useSearchParams();
  const focusEntry = params.get("entry");
  // The filter manager is the URL's ?filters=1, so a link to it works with the page already open,
  // and the browser's Back returns to the Journal.
  const managing = params.get("filters") === "1";
  const setManaging = (on: boolean) => setParams((prev) => {
    const next = new URLSearchParams(prev);
    if (on) next.set("filters", "1"); else next.delete("filters");
    return next;
  });
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [sections, setSections] = useState<JournalSection[] | null>(null);
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [flights, setFlights] = useState<FlightSummary[]>([]);
  const [usingFixture, setUsingFixture] = useState(true);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [groupBy, setGroupBy] = useState<GroupBy>("kind");
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(focusEntry ? [focusEntry] : []));
  const [toggled, setToggled] = useState<Record<string, boolean>>({});
  // One entry at a time is being edited or removed.
  const [editing, setEditing] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  // The server answered but couldn't read the Journal — say so, rather
  // than showing an empty sample page as if there were no decisions.
  const [loadError, setLoadError] = useState<string | null>(null);
  // No workspace yet (a first run): an empty Journal, not an error.
  const [noWorkspace, setNoWorkspace] = useState(false);
  const caps = useCapabilities();

  async function load() {
    const [j, a, f] = await Promise.all([
      client.getJournal().catch((err) => {
        if (err instanceof EngineRpcError && err.code === "NO_ACTIVE_WORKSPACE") {
          setNoWorkspace(true);
          return { entries: [] as JournalEntry[], sections: [] as JournalSection[] };
        }
        throw err;
      }),
      client.listAnnotations(),
      client.listFlights().catch(() => [] as FlightSummary[]),
    ]);
    setEntries(j.entries);
    setSections(j.sections ?? null);
    setAnnotations(a.annotations);
    setFlights(f);
  }

  useEffect(() => {
    let cancelled = false;
    load()
      .then(() => {
        if (!cancelled) {
          setUsingFixture(false);
          setLoadError(null);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setEntries([]);
        if (err instanceof EngineRpcError) {
          setUsingFixture(false);
          setLoadError(err.message);
        } else {
          setUsingFixture(true);
        }
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh() {
    try {
      await load();
    } catch {
      // leave what's loaded
    }
  }

  // Opened from a Settings mark: bring that entry into view, opened.
  useEffect(() => {
    if (focusEntry) document.getElementById(`journal-entry-${focusEntry}`)?.scrollIntoView?.({ block: "center" });
  }, [entries, focusEntry]);

  const annotationById = useMemo(() => new Map(annotations.map((a) => [a.id, a])), [annotations]);
  const flightById = useMemo(() => new Map(flights.map((f) => [f.flight_id, f])), [flights]);

  function flightIdOf(e: JournalEntry): string | null {
    const fid = (e.where as { flight_id?: string } | null | undefined)?.flight_id;
    return typeof fid === "string" ? fid : e.kind === "exclusion" ? e.ref_id : null;
  }
  function flightLabel(fid: string): string {
    const f = flightById.get(fid);
    return f ? `${f.header.date} · ${f.source_filename ?? fid}` : fid;
  }
  const titleOf = (e: JournalEntry) => e.title ?? e.what;

  // Search: title, reason, note, finding and flight (§6.4 item 3).
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return null;
    return new Set(entries.filter((e) => {
      const fid = flightIdOf(e);
      const hay = [titleOf(e), e.what, e.reason, e.note, e.finding, fid ? flightLabel(fid) : null,
        e.kind === "annotation" ? annotationById.get(e.ref_id)?.note : null].filter(Boolean).join(" ").toLowerCase();
      return hay.includes(q);
    }).map((e) => e.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, entries, flightById, annotationById]);
  const shown = (e: JournalEntry) => !matches || matches.has(e.id);
  const byId = useMemo(() => new Map(entries.map((e) => [e.id, e])), [entries]);

  // The groups to draw: the engine's sections by kind; by date or by flight, newest first.
  const groups = useMemo(() => {
    type Group = { key: string; label: string; total?: string; open: boolean; entries: JournalEntry[]; section?: JournalSection };
    if (groupBy === "kind") {
      const secs = sections ?? (entries.length ? [{ key: "all", label: "Decisions", kinds: [], count: entries.length, total: "",
        flights: 0, open: true, entry_ids: entries.map((e) => e.id) } as JournalSection] : []);
      return secs.map((s): Group => ({
        key: s.key, label: s.label, total: s.total, open: s.open, section: s,
        entries: s.entry_ids.map((id) => byId.get(id)).filter((e): e is JournalEntry => !!e),
      }));
    }
    const out: Group[] = [];
    const index = new Map<string, number>();
    for (const e of [...entries].sort((a, b) => b.updated_at.localeCompare(a.updated_at))) {
      let key: string;
      let label: string;
      if (groupBy === "date") {
        key = e.updated_at.slice(0, 10);
        label = longDate(`${key}T12:00:00`);       // the key's own day, whatever the browser's zone
      } else {
        const fid = flightIdOf(e);
        key = fid ?? "_workspace";
        label = fid ? flightLabel(fid) : "Whole workspace";
      }
      if (!index.has(key)) {
        index.set(key, out.length);
        out.push({ key, label, open: true, entries: [] });
      }
      out[index.get(key)!].entries.push(e);
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupBy, sections, entries, byId, flightById]);

  const noticed = entries.filter((e) => (e.notices ?? []).length > 0);

  function openWhere(e: JournalEntry) {
    const fid = flightIdOf(e);
    if (fid) navigate(`/flights/${fid}`);
    else if (e.kind === "limit_filter") setManaging(true);
    else if (e.kind === "reference_pin") navigate(`/trends?metric=${encodeURIComponent(e.ref_id)}`);
    else if (e.kind === "changed_setting") navigate(`/settings?tab=${settingsTab(e)}`);
    else if (e.kind === "study_finding") navigate(`/research/${encodeURIComponent(String((e.where as { study_id?: string } | null)?.study_id ?? ""))}`);
  }
  const WHERE_LABEL: Partial<Record<JournalEntryKind, string>> = {
    limit_filter: "Open in limit filters", reference_pin: "Open in Trends", changed_setting: "Open in Settings", study_finding: "Open the notebook",
  };

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      await refresh();
    } catch {
      // server unreachable — leave as-is
    } finally {
      setBusy(false);
      setEditing(null);
      setRemoving(null);
    }
  }

  function remove(e: JournalEntry) {
    void act(async () => {
      if (e.kind === "annotation") await client.deleteAnnotation(e.ref_id);
      else if (e.kind === "study_finding") await client.forgetStudyFinding(e.ref_id);
      else if (e.kind === "limit_filter") {
        await client.deleteFilter(e.ref_id);
        notifyFiltersChanged();
      } else if (e.kind === "reference_pin") {
        await client.clearReference(e.ref_id);
        notifyShiftHistoryChanged();
      } else if (e.kind === "rule_edit" || e.kind === "disabled_topic") await client.revertRuleEdit(e.id);
      else if (e.kind === "changed_setting") await client.resetSetting(e.ref_id);
    });
  }

  // Rule edits are made in the rule editor panel, which needs a flight
  // to preview against: the most recent one.
  function editRule(e: JournalEntry) {
    const latest = [...flights].sort((a, b) => (b.header.start_utc ?? b.header.date).localeCompare(a.header.start_utc ?? a.header.date))[0];
    if (latest) navigate(`/flights/${latest.flight_id}?edit=${encodeURIComponent(e.ref_id)}`);
  }

  function startEdit(e: JournalEntry) {
    setRemoving(null);
    if (e.kind === "rule_edit") return editRule(e);
    if (e.kind === "reference_pin") return navigate(`/trends?metric=${encodeURIComponent(e.ref_id)}`);
    if (e.kind === "changed_setting") return navigate(`/settings?tab=${settingsTab(e)}`);
    setEditing(e.id);
    if (e.kind === "annotation") setDraft(annotationById.get(e.ref_id)?.note ?? e.what);
    if (e.kind === "exclusion") setDraft(e.reason ?? "");
  }

  function saveEdit(e: JournalEntry) {
    void act(async () => {
      if (e.kind === "annotation") {
        const a = annotationById.get(e.ref_id);
        if (a) await client.saveAnnotation({ id: a.id, flightId: a.flight_id, ref: a.ref, note: draft });
      } else if (e.kind === "exclusion") {
        await client.updateExclusionReason(e.ref_id, draft);
      }
    });
  }

  const canEdit = (k: JournalEntryKind) => k !== "disabled_topic" && k !== "acknowledged_insight" && k !== "study_finding";
  const scopeOf = (e: JournalEntry): Scope | undefined =>
    e.kind === "limit_filter" ? filterScope((e.where as { target?: FilterTarget } | null)?.target)
      // Spec 14 v0.14 §5.3: a log-channel assignment is not a comparison setting.
      : e.kind === "changed_setting" && e.ref_id.startsWith("channel_assignment:") ? "workspace"
      : ENTRY_SCOPE[e.kind];

  function toggleEntry(id: string) {
    setExpanded((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  function noticeAction(e: JournalEntry, kind: string) {
    if (usingFixture) return null;
    return kind === "no_effect"
      ? <button type="button" style={LINK} onClick={() => void act(() => client.confirmJournalNotice(e.id, "no_effect"))}>Keep it</button>
      : <button type="button" style={LINK} onClick={() => setManaging(true)}>Review the filter →</button>;
  }

  function renderEntry(e: JournalEntry) {
    const scope = scopeOf(e);
    const isOpen = expanded.has(e.id);
    const isEditing = editing === e.id;
    const isRemoving = removing === e.id;
    const zero = !!e.effect?.zero;
    const secondary = e.kind === "study_finding" ? e.finding ?? e.what : e.effect?.short ?? e.effect?.text ?? null;
    const note = e.kind === "annotation" ? annotationById.get(e.ref_id)?.note ?? null : e.note;
    const where = flightIdOf(e) ? "Open the flight" : WHERE_LABEL[e.kind];
    const items: MenuItem[] = usingFixture ? [] : [
      ...(canEdit(e.kind) ? [{ label: "Edit", onSelect: () => { toggleOpen(e.id); startEdit(e); }, testid: "journal-edit" }] : []),
      ...(e.kind === "study_finding" ? [{ label: "Open the notebook", onSelect: () => openWhere(e), testid: "journal-open-notebook" }] : []),
      { label: REMOVE_LABEL[e.kind], onSelect: () => { toggleOpen(e.id); setEditing(null); setRemoving(e.id); }, testid: "journal-remove", danger: true },
    ];
    function toggleOpen(id: string) {
      setExpanded((s) => (s.has(id) ? s : new Set([...s, id])));
    }
    return (
      <div key={e.id} id={`journal-entry-${e.id}`} data-testid={`journal-entry-${e.id}`} data-kind={e.kind}
        data-focused={focusEntry === e.id || undefined}
        style={{ borderTop: "1px solid var(--border-subtle)", outline: focusEntry === e.id ? "1px solid var(--text-tertiary)" : "none", borderRadius: focusEntry === e.id ? 6 : 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 2px" }}>
          <button type="button" onClick={() => toggleEntry(e.id)} aria-expanded={isOpen} data-testid="journal-line"
            style={{ display: "flex", alignItems: "baseline", gap: 10, flexGrow: 1, minWidth: 0, background: "none", border: "none", padding: 0, cursor: "pointer", textAlign: "left", color: "inherit", font: "inherit" }}>
            <span aria-hidden title={KIND_LABELS[e.kind]} style={{ ...QUIET, width: 16, textAlign: "center", flexShrink: 0 }} data-testid="journal-glyph">{KIND_GLYPH[e.kind]}</span>
            <span style={{ ...TITLE, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flexShrink: 0, maxWidth: "55%" }} data-testid="journal-title" title={titleOf(e)}>{titleOf(e)}</span>
            {secondary && (
              <span data-testid="live-effect" data-zero={zero || undefined} title={e.effect?.text}
                style={{ ...(zero ? QUIET : SECONDARY), overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: "1 1 0", minWidth: 0, display: "block" }}>
                {zero && <span aria-hidden style={{ display: "inline-block", width: 7, height: 7, borderRadius: 4, border: "1px solid var(--text-tertiary)", marginRight: 5, verticalAlign: "middle" }} />}
                {secondary}
              </span>
            )}
          </button>
          {(e.notices ?? []).length > 0 && <span aria-label="Needs a look" title="Needs a look — see the top of the page" style={{ width: 7, height: 7, borderRadius: 4, background: "var(--severity-warning)", flexShrink: 0 }} />}
          <span style={{ ...QUIET, flexShrink: 0 }} title={longDate(e.updated_at)} data-testid="journal-date">{shortDate(e.updated_at)}</span>
          {items.length > 0 && <ActionMenu items={items} testid="journal-menu" />}
        </div>

        {isOpen && (
          <div data-testid="journal-expanded" style={{ padding: "0 2px 12px 28px", display: "flex", flexDirection: "column", gap: 6 }}>
            {e.current && <div className="mono" style={{ ...SECONDARY, color: "var(--text-primary)" }} data-testid="journal-value">{e.current}</div>}
            {e.effect && !zero && e.kind !== "study_finding" && <div style={SECONDARY}>{e.effect.text.charAt(0).toUpperCase() + e.effect.text.slice(1)}</div>}
            {e.effect && zero && <div style={QUIET}>{e.effect.text.charAt(0).toUpperCase() + e.effect.text.slice(1)}</div>}
            {e.kind === "study_finding" && e.summary && <div style={{ ...SECONDARY, color: "var(--text-primary)", lineHeight: 1.5, whiteSpace: "pre-line" }} data-testid="journal-summary">{e.summary}</div>}
            <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              {scope && <ScopeCaption scope={scope} />}
              {where && <button type="button" style={LINK} onClick={() => openWhere(e)}>{where}</button>}
            </div>
            {e.reason && <div style={SECONDARY} data-testid="journal-reason">“{e.reason}”</div>}
            {note && <div style={{ ...SECONDARY, fontStyle: "italic" }} data-testid="journal-note">“{note}”</div>}
            {(e.notices ?? []).map((n) => <div key={n.kind} style={SECONDARY}>{n.text}</div>)}
            <span style={QUIET}>
              {`made ${longDate(e.created_at)}` + (longDate(e.updated_at) !== longDate(e.created_at) ? ` · changed ${longDate(e.updated_at)}` : "")}
            </span>

            {isEditing && (e.kind === "annotation" || e.kind === "exclusion") && (
              <div style={{ display: "flex", gap: 8 }}>
                <textarea aria-label={e.kind === "exclusion" ? "Reason" : "Note"} value={draft} onChange={(ev) => setDraft(ev.target.value)} rows={2}
                  style={{ flexGrow: 1, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: 8, color: "var(--text-primary)", fontSize: 13, fontFamily: "inherit" }} />
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <button type="button" disabled={busy} style={BUTTON(true)} onClick={() => saveEdit(e)}>Save</button>
                  <button type="button" style={BUTTON(false)} onClick={() => setEditing(null)}>Cancel</button>
                </div>
              </div>
            )}
            {isEditing && e.kind === "limit_filter" && (
              <FilterEditor target={(e.where as { target: FilterTarget }).target}
                onSaved={() => { notifyFiltersChanged(); void act(async () => {}); }} onCancel={() => setEditing(null)} />
            )}
            {isRemoving && e.kind !== "exclusion" && (
              <div role="dialog" aria-label={REMOVE_LABEL[e.kind]} style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 8 }}>
                {scope && <ScopeCaption scope={scope} />}
                <div style={SECONDARY}>{removalPreview(e)}</div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button type="button" disabled={busy} style={BUTTON(true)} onClick={() => remove(e)}>{scope ? APPLY_LABEL[scope] : REMOVE_LABEL[e.kind]}</button>
                  <button type="button" style={BUTTON(false)} onClick={() => setRemoving(null)}>Cancel</button>
                </div>
              </div>
            )}
            {isRemoving && e.kind === "exclusion" && (
              <ExcludeConfirmDialog mode="include" flightId={e.ref_id} flightLabel={titleOf(e)} busy={busy}
                onCancel={() => setRemoving(null)} onConfirm={() => void act(() => client.includeFlight(e.ref_id))} />
            )}
          </div>
        )}
      </div>
    );
  }

  const searching = !!matches;
  const visibleGroups = groups.map((g) => ({ ...g, entries: g.entries.filter(shown) })).filter((g) => g.entries.length > 0);

  return (
    <NavShell>
      <div style={{ flexGrow: 1, overflowY: "auto", padding: "24px 28px", display: "flex", flexDirection: "column", gap: 18, maxWidth: 1100 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>
            Journal {usingFixture && <span style={{ ...QUIET, fontWeight: 400 }}>(sample)</span>}
            {loading && <span style={{ ...QUIET, fontWeight: 400 }}> · loading…</span>}
          </h1>
          <InlineHelp id="journal.live_effect" />
        </div>

        {managing && !usingFixture && (
          <section data-testid="journal-filters-manager" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <button type="button" style={{ ...LINK, alignSelf: "flex-start" }} onClick={() => { setManaging(false); void refresh(); }}>← Back to the Journal</button>
            <LimitFiltersSection />
          </section>
        )}

        {!managing && loadError && (
          <div role="alert" style={{ fontSize: 13, color: "var(--severity-warning)", lineHeight: 1.5 }}>
            Couldn't load the Journal — your decisions are still saved.
            {caps?.host !== "browser" && (
              <> If the local server was started before the app was updated, restart it (<span className="mono">slingology-eis serve</span>) and reload.</>
            )}
            <div className="mono" style={{ fontSize: 13, color: "var(--text-tertiary)", marginTop: 4 }}>{loadError}</div>
          </div>
        )}

        {!managing && !loadError && noWorkspace && (
          <div data-testid="journal-no-workspace" style={SECONDARY}>
            No workspace yet. Create one from the workspace menu at the top; the decisions you make about its flights are listed here.
          </div>
        )}

        {!managing && !loadError && !noWorkspace && (
          <>
            {noticed.length > 0 && (
              // §6.4 item 1: the page's one accent, and only when there is something.
              <section data-testid="journal-notices" style={{ border: "1px solid var(--severity-warning)", borderRadius: 10, padding: "10px 14px", display: "flex", flexDirection: "column", gap: 6 }}>
                <h2 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: "var(--severity-warning)", display: "flex", alignItems: "center" }}>
                  Needs a look<InlineHelp id="journal.change_notices" />
                </h2>
                {noticed.flatMap((e) => (e.notices ?? []).map((n) => (
                  <div key={`${e.id}-${n.kind}`} data-testid="change-notice" data-entry={e.id} style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap" }}>
                    <span style={{ ...TITLE }}>{titleOf(e)}</span>
                    <span style={SECONDARY}>{n.text || (n.kind === "breached" ? "Breached" : n.kind === "drifting" ? "Drifting" : "No effect")}</span>
                    <span style={{ flexGrow: 1 }} />
                    {noticeAction(e, n.kind)}
                  </div>
                )))}
              </section>
            )}

            {entries.length === 0 ? (
              <div style={QUIET}>No decisions in force.</div>
            ) : (
              <>
                <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                  <input type="search" aria-label="Search the Journal" placeholder="Search titles, reasons, notes, flights" value={query}
                    onChange={(ev) => setQuery(ev.target.value)}
                    style={{ fontSize: 13, padding: "5px 10px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text-primary)", width: 300 }} />
                  <span style={{ flexGrow: 1 }} />
                  <span style={QUIET}>Group</span>
                  <span role="group" aria-label="Group the Journal" style={{ display: "inline-flex" }}>
                    {(["kind", "date", "flight"] as GroupBy[]).map((g, i) => (
                      <button key={g} type="button" aria-pressed={groupBy === g} onClick={() => setGroupBy(g)}
                        style={{ ...SEGMENT(groupBy === g), borderRadius: i === 0 ? "6px 0 0 6px" : i === 2 ? "0 6px 6px 0" : 0, marginLeft: i ? -1 : 0 }}>
                        by {g}
                      </button>
                    ))}
                  </span>
                </div>

                {searching && visibleGroups.length === 0 && <div style={QUIET}>Nothing in the Journal matches “{query.trim()}”.</div>}
                <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                  {visibleGroups.map((g) => {
                    const open = searching || (toggled[g.key] ?? g.open);
                    return (
                      <section key={g.key} data-testid={`journal-section-${g.key}`} data-open={open || undefined}>
                        <div style={{ display: "flex", alignItems: "baseline", gap: 10, paddingBottom: 4 }}>
                          <button type="button" aria-expanded={open} onClick={() => setToggled((t) => ({ ...t, [g.key]: !open }))}
                            style={{ background: "none", border: "none", padding: 0, cursor: "pointer", color: "inherit", display: "flex", alignItems: "baseline", gap: 8 }}>
                            <span aria-hidden style={{ ...QUIET, width: 12 }}>{open ? "▾" : "▸"}</span>
                            <h2 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>{g.label}</h2>
                          </button>
                          {g.total
                            ? <span style={SECONDARY} data-testid="journal-section-total">{g.total}</span>
                            : <span style={SECONDARY}>{g.entries.length}</span>}
                          <span style={{ flexGrow: 1 }} />
                          {g.key === "filters" && !usingFixture && (
                            <button type="button" style={LINK} onClick={() => setManaging(true)} data-testid="journal-manage-filters">Manage limit filters →</button>
                          )}
                        </div>
                        {open && g.entries.map(renderEntry)}
                      </section>
                    );
                  })}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </NavShell>
  );
}
