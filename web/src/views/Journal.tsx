import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { NavShell } from "../components/NavShell";
import { LimitFiltersSection } from "../components/LimitFiltersSection";
import { FilterEditor } from "../components/FilterEditor";
import { ExcludeConfirmDialog } from "../components/ExcludeDialog";
import { notifyFiltersChanged } from "../lib/filterAttention";
import { notifyShiftHistoryChanged } from "../lib/shiftHistoryAttention";
import { EngineRpcError, getEngineClient, type FlightSummary } from "../lib/engineClient";
import type { Annotation, FilterTarget, JournalEntry, JournalEntryKind } from "../types/contract";
import { InlineHelp } from "../components/InlineHelp";
import { ScopeCaption } from "../components/ScopeCaption";
import { APPLY_LABEL, filterScope, type Scope } from "../lib/scope";

const client = getEngineClient();

// Spec 14 v0.10 §6 — Journal is the register of decisions in force. Each
// decision has exactly one entry while it stands: reversing it removes the
// entry, editing it updates the entry. The counted effect is live — the
// server recomputes it every time this page opens — and a decision that
// currently does nothing says so. Journal creates nothing itself except a
// free-text annotation; every other decision is made where its result is.

// §7.5 — the scope of the decision each entry stands for.
const ENTRY_SCOPE: Partial<Record<JournalEntryKind, Scope>> = {
  exclusion: "flight",
  reference_pin: "metric",
  limit_filter: "limit",
  rule_edit: "topic",
  disabled_topic: "topic",
  changed_setting: "reference_settings",
};

// The full §6.1 taxonomy, in table order. acknowledged_insight has no
// entries yet (Spec 11 silencing is not built); its chip still shows so
// the taxonomy reads as complete.
const KIND_ORDER: JournalEntryKind[] = [
  "acknowledged_insight", "limit_filter", "disabled_topic", "rule_edit", "changed_setting",
  "exclusion", "reference_pin", "annotation",
];
const KIND_LABELS: Record<JournalEntryKind, string> = {
  acknowledged_insight: "Acknowledged insight",
  limit_filter: "Filter",
  disabled_topic: "Disabled topic",
  rule_edit: "Rule edit",
  changed_setting: "Changed setting",
  exclusion: "Excluded from reference",
  reference_pin: "Reference pinned",
  annotation: "Annotation",
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
};

function formatDate(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" });
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
    default:
      return "";
  }
}

type GroupBy = "date" | "flight";

export function Journal() {
  const navigate = useNavigate();
  // Spec 14 v0.13 §5: Settings links a changed setting to its entry here.
  const [params] = useSearchParams();
  const focusEntry = params.get("entry");
  const [activeTab, setActiveTab] = useState<"journal" | "filters">("journal");
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [flights, setFlights] = useState<FlightSummary[]>([]);
  const [usingFixture, setUsingFixture] = useState(true);
  const [loading, setLoading] = useState(true);
  const [kindFilter, setKindFilter] = useState<JournalEntryKind | "all">("all");
  const [groupBy, setGroupBy] = useState<GroupBy>("date");
  // One entry at a time is being edited or removed.
  const [editing, setEditing] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [filterCount, setFilterCount] = useState<number | null>(null);
  // The server answered but couldn't read the Journal — say so, rather
  // than showing an empty sample page as if there were no decisions.
  const [loadError, setLoadError] = useState<string | null>(null);

  async function load() {
    const [j, a, f] = await Promise.all([
      client.getJournal(),
      client.listAnnotations(),
      client.listFlights().catch(() => [] as FlightSummary[]),
    ]);
    setEntries(j.entries);
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

  // Opened from a Settings mark: bring that entry into view.
  useEffect(() => {
    if (focusEntry) document.getElementById(`journal-entry-${focusEntry}`)?.scrollIntoView?.({ block: "center" });
  }, [entries, focusEntry]);

  const annotationById = useMemo(() => new Map(annotations.map((a) => [a.id, a])), [annotations]);
  const flightById = useMemo(() => new Map(flights.map((f) => [f.flight_id, f])), [flights]);

  const kindCounts = useMemo(() => {
    const m = new Map<JournalEntryKind, number>();
    for (const e of entries) m.set(e.kind, (m.get(e.kind) ?? 0) + 1);
    return m;
  }, [entries]);

  // Most recently changed first; entries with an open change notice float
  // to the top (§6.2).
  const visible = useMemo(() => {
    const base = kindFilter === "all" ? entries : entries.filter((e) => e.kind === kindFilter);
    return [...base].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  }, [entries, kindFilter]);
  const attention = visible.filter((e) => (e.notices ?? []).length > 0);
  const rest = visible.filter((e) => (e.notices ?? []).length === 0);

  function flightIdOf(e: JournalEntry): string | null {
    const fid = (e.where as { flight_id?: string } | null | undefined)?.flight_id;
    return typeof fid === "string" ? fid : null;
  }

  function flightLabel(fid: string): string {
    const f = flightById.get(fid);
    return f ? `${f.header.date} · ${f.source_filename ?? fid}` : fid;
  }

  const groups = useMemo(() => {
    const out: { key: string; label: string; entries: JournalEntry[] }[] = [];
    const index = new Map<string, number>();
    for (const e of rest) {
      let key: string;
      let label: string;
      if (groupBy === "date") {
        key = e.updated_at.slice(0, 10);
        label = formatDate(e.updated_at);
      } else {
        const fid = flightIdOf(e);
        key = fid ?? "_workspace";
        label = fid ? flightLabel(fid) : "Whole workspace";
      }
      if (!index.has(key)) {
        index.set(key, out.length);
        out.push({ key, label, entries: [] });
      }
      out[index.get(key)!].entries.push(e);
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rest, groupBy, flightById]);

  function openWhere(e: JournalEntry) {
    const fid = flightIdOf(e);
    if (fid) navigate(`/flights/${fid}`);
    else if (e.kind === "limit_filter") setActiveTab("filters");
    else if (e.kind === "reference_pin") navigate(`/trends?metric=${encodeURIComponent(e.ref_id)}`);
    else if (e.kind === "changed_setting") navigate("/settings?tab=reference");
  }

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
    if (e.kind === "changed_setting") return navigate("/settings?tab=reference");
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

  const canEdit = (k: JournalEntryKind) => k !== "disabled_topic" && k !== "acknowledged_insight";
  const scopeOf = (e: JournalEntry): Scope | undefined =>
    e.kind === "limit_filter" ? filterScope((e.where as { target?: FilterTarget } | null)?.target) : ENTRY_SCOPE[e.kind];

  const LINK: React.CSSProperties = { background: "none", border: "none", padding: 0, color: "var(--text-tertiary)", cursor: "pointer", fontSize: 11 };
  const BUTTON = (primary: boolean): React.CSSProperties => ({
    padding: "5px 11px", borderRadius: 6, fontSize: 11, cursor: "pointer", fontWeight: primary ? 600 : 400,
    background: primary ? "var(--accent)" : "transparent", color: primary ? "var(--bg)" : "var(--text-secondary)",
    border: primary ? "none" : "1px solid var(--border)",
  });

  function renderEntry(e: JournalEntry) {
    const scope = scopeOf(e);
    const live = e.kind === "annotation" ? annotationById.get(e.ref_id) : null;
    const isEditing = editing === e.id;
    const isRemoving = removing === e.id;
    return (
      <div
        key={e.id}
        id={`journal-entry-${e.id}`}
        data-testid={`journal-entry-${e.id}`}
        data-focused={focusEntry === e.id || undefined}
        style={{ background: "var(--panel)", borderRadius: 12, padding: "14px 18px", display: "flex", flexDirection: "column", gap: 6, outline: focusEntry === e.id ? "2px solid var(--accent)" : "none" }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
            <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: 0.4, color: "var(--text-secondary)", background: "var(--panel-control)", padding: "3px 8px", borderRadius: 10, flexShrink: 0 }}>
              {KIND_LABELS[e.kind]}
            </span>
            <a href="#" onClick={(ev) => { ev.preventDefault(); openWhere(e); }} style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
              {live ? live.note.slice(0, 80) : e.what}
            </a>
          </div>
          {!usingFixture && (
            <div style={{ display: "flex", gap: 12, alignItems: "center", flexShrink: 0 }}>
              {scope && <ScopeCaption scope={scope} />}
              {canEdit(e.kind) && <button type="button" style={LINK} onClick={() => startEdit(e)}>Edit</button>}
              <button type="button" style={LINK} onClick={() => { setEditing(null); setRemoving(e.id); }}>{REMOVE_LABEL[e.kind]}</button>
            </div>
          )}
        </div>

        {e.current && <div className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>{e.current}</div>}
        {e.effect && (
          <div data-testid="live-effect" style={{ fontSize: 13, color: e.effect.zero ? "var(--text-tertiary)" : "var(--text-primary)" }}>
            {e.effect.text.charAt(0).toUpperCase() + e.effect.text.slice(1)}
          </div>
        )}
        {(e.notices ?? []).map((n) => (
          <div key={n.kind} data-testid="change-notice" style={{ background: "rgba(245,165,36,0.08)", border: "1px solid rgba(245,165,36,0.3)", borderRadius: 8, padding: "8px 12px", fontSize: 12, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
            <span>
              <strong style={{ color: "var(--severity-warning)" }}>{n.kind === "no_effect" ? "No effect" : n.kind === "breached" ? "Breached" : "Drifting"}</strong>
              {n.text ? ` — ${n.text}` : ""}
            </span>
            {!usingFixture && (n.kind === "no_effect" ? (
              <button type="button" style={{ ...LINK, color: "var(--accent)" }} onClick={() => void act(() => client.confirmJournalNotice(e.id, "no_effect"))}>
                Keep it
              </button>
            ) : (
              <button type="button" style={{ ...LINK, color: "var(--accent)" }} onClick={() => setActiveTab("filters")}>
                Review in Limit filters →
              </button>
            ))}
          </div>
        ))}

        {isEditing && (e.kind === "annotation" || e.kind === "exclusion") && (
          <div style={{ display: "flex", gap: 8 }}>
            <textarea
              aria-label={e.kind === "exclusion" ? "Reason" : "Note"}
              value={draft}
              onChange={(ev) => setDraft(ev.target.value)}
              rows={2}
              style={{ flexGrow: 1, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: 8, color: "var(--text-primary)", fontSize: 13, fontFamily: "inherit" }}
            />
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <button type="button" disabled={busy} style={BUTTON(true)} onClick={() => saveEdit(e)}>Save</button>
              <button type="button" style={BUTTON(false)} onClick={() => setEditing(null)}>Cancel</button>
            </div>
          </div>
        )}
        {isEditing && e.kind === "limit_filter" && (
          <FilterEditor
            target={(e.where as { target: FilterTarget }).target}
            onSaved={() => { notifyFiltersChanged(); void act(async () => {}); }}
            onCancel={() => setEditing(null)}
          />
        )}
        {isRemoving && e.kind !== "exclusion" && (
          <div role="dialog" aria-label={REMOVE_LABEL[e.kind]} style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 8 }}>
            {scope && <ScopeCaption scope={scope} />}
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{removalPreview(e)}</div>
            <div style={{ display: "flex", gap: 8 }}>
              <button type="button" disabled={busy} style={BUTTON(true)} onClick={() => remove(e)}>
                {scope ? APPLY_LABEL[scope] : REMOVE_LABEL[e.kind]}
              </button>
              <button type="button" style={BUTTON(false)} onClick={() => setRemoving(null)}>Cancel</button>
            </div>
          </div>
        )}

        {e.reason && <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>Reason: {e.reason}</div>}
        {e.note && e.kind !== "annotation" && <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{e.note}</div>}
        <span className="mono" style={{ fontSize: 10, color: "var(--text-tertiary)" }}>
          {`made ${formatDate(e.created_at)}` +
            (formatDate(e.updated_at) !== formatDate(e.created_at) ? ` · changed ${formatDate(e.updated_at)}` : "")}
        </span>
        {isRemoving && e.kind === "exclusion" && (
          <ExcludeConfirmDialog
            mode="include"
            flightId={e.ref_id}
            flightLabel={e.what}
            busy={busy}
            onCancel={() => setRemoving(null)}
            onConfirm={() => void act(() => client.includeFlight(e.ref_id))}
          />
        )}
      </div>
    );
  }

  const chip = (active: boolean, enabled = true): React.CSSProperties => ({
    padding: "4px 10px", borderRadius: 20, fontSize: 11, cursor: enabled ? "pointer" : "default",
    border: active ? "1px solid var(--accent)" : "1px solid var(--border)",
    background: active ? "var(--accent-15)" : "transparent",
    color: active ? "var(--accent)" : enabled ? "var(--text-secondary)" : "var(--text-tertiary)",
    opacity: enabled ? 1 : 0.5,
  });
  const tab = (active: boolean): React.CSSProperties => ({
    padding: "5px 12px", borderRadius: 20, fontSize: 11, fontWeight: 600, cursor: "pointer",
    border: active ? "1px solid var(--text-secondary)" : "1px solid var(--border)",
    background: active ? "var(--panel-control)" : "transparent", color: "var(--text-secondary)",
  });

  return (
    <NavShell>
      <div style={{ flexGrow: 1, overflowY: "auto", padding: "24px 28px", display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <h1 style={{ margin: "0 0 4px", fontSize: 19, fontWeight: 700 }}>
            Journal {usingFixture && <span style={{ fontSize: 12, fontWeight: 400, color: "var(--text-tertiary)" }}>(sample)</span>}
            {loading && <span style={{ fontSize: 12, fontWeight: 400, color: "var(--text-tertiary)" }}> · loading…</span>}
          </h1>
          <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
            Decisions in force, each with what it is doing now<InlineHelp id="journal.live_effect" />
          </span>
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" onClick={() => setActiveTab("journal")} style={tab(activeTab === "journal")}>Journal ({entries.length})</button>
          {!usingFixture && (
            <button type="button" onClick={() => setActiveTab("filters")} style={tab(activeTab === "filters")}>
              Limit filters{filterCount !== null ? ` (${filterCount})` : ""}
            </button>
          )}
        </div>

        {activeTab === "filters" && !usingFixture && <LimitFiltersSection onCount={setFilterCount} />}

        {activeTab === "journal" && loadError && (
          <div role="alert" style={{ fontSize: 13, color: "var(--severity-warning)", lineHeight: 1.5 }}>
            Couldn't load the Journal — your decisions are still saved. If the local server was started
            before the app was updated, restart it (<span className="mono">slingology-eis serve</span>) and reload.
            <div className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 4 }}>{loadError}</div>
          </div>
        )}

        {activeTab === "journal" && !loadError && (
          <>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
              <button type="button" onClick={() => setKindFilter("all")} style={chip(kindFilter === "all")}>All ({entries.length})</button>
              {KIND_ORDER.map((k) => {
                const n = kindCounts.get(k) ?? 0;
                return (
                  <button key={k} type="button" onClick={() => setKindFilter(k)} disabled={n === 0 && kindFilter !== k} style={chip(kindFilter === k, n > 0)}>
                    {KIND_LABELS[k]} ({n})
                  </button>
                );
              })}
              <span style={{ flexGrow: 1 }} />
              <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>Group by</span>
              {(["date", "flight"] as GroupBy[]).map((g) => (
                <button key={g} type="button" onClick={() => setGroupBy(g)} style={chip(groupBy === g)}>{g === "date" ? "Date" : "Flight"}</button>
              ))}
            </div>

            {visible.length === 0 ? (
              <div style={{ fontSize: 13, color: "var(--text-tertiary)" }}>
                {kindFilter === "all" ? "No decisions in force." : `No ${KIND_LABELS[kindFilter].toLowerCase()} decisions in force.`}
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                {attention.length > 0 && (
                  <section style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <h2 style={{ fontSize: 12, fontWeight: 600, color: "var(--severity-warning)", margin: 0 }}>
                      Needs a look<InlineHelp id="journal.change_notices" />
                    </h2>
                    {attention.map(renderEntry)}
                  </section>
                )}
                {groups.map((g) => (
                  <section key={g.key} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <h2 style={{ fontSize: 12, fontWeight: 600, color: "var(--text-tertiary)", margin: 0 }}>{g.label}</h2>
                    {g.entries.map(renderEntry)}
                  </section>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </NavShell>
  );
}
