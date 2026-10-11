import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { NavShell } from "../components/NavShell";
import { LimitFiltersSection } from "../components/LimitFiltersSection";
import { notifyFiltersChanged } from "../lib/filterAttention";
import { notifyShiftHistoryChanged } from "../lib/shiftHistoryAttention";
import { annotationStore as fixtureAnnotations } from "../lib/fixtures";
import { getEngineClient } from "../lib/engineClient";
import type { Annotation, FilterHealth, JournalEntry, JournalEntryKind } from "../types/contract";

const client = getEngineClient();

// Spec 14 §6.1 — the full kind taxonomy, in table order. Four of these
// (acknowledged_insight, disabled_topic, rule_edit, exclusion) have no
// entries yet: acknowledging/disabling a topic needs Spec 11's silencing
// levels (paused — not built anywhere in this codebase today); rule_edit
// and exclusion land with Spec 14 steps 5 and 4. The chips still show
// all seven so the taxonomy reads as complete, not as if three kinds
// were forgotten.
const KIND_ORDER: JournalEntryKind[] = [
  "acknowledged_insight", "limit_filter", "disabled_topic", "rule_edit",
  "exclusion", "reference_pin", "annotation",
];
const KIND_LABELS: Record<JournalEntryKind, string> = {
  acknowledged_insight: "Acknowledged insight",
  limit_filter: "Limit filter",
  disabled_topic: "Disabled topic",
  rule_edit: "Rule edit",
  exclusion: "Excluded from reference",
  reference_pin: "Reference pinned",
  annotation: "Annotation",
};

function formatDate(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" });
}

// Spec 03 §5.6's old Annotations page, renamed and redefined by Spec 14
// §6: every decision (§3) made elsewhere in the flow lands here for
// review, editing and reversal. Journal creates nothing itself except a
// free-text annotation — everything else is a read/manage surface over
// a decision whose real engine effect was already applied where it was
// made (an insight card, Flights, Trends, Reference & Models).
export function Journal() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<"journal" | "filters">("journal");
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [annotations, setAnnotations] = useState<Annotation[]>(fixtureAnnotations.annotations);
  const [filterHealth, setFilterHealth] = useState<FilterHealth[]>([]);
  const [usingFixture, setUsingFixture] = useState(true);
  const [loading, setLoading] = useState(true);
  const [kindFilter, setKindFilter] = useState<JournalEntryKind | "all">("all");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [filterCount, setFilterCount] = useState<number | null>(null);

  async function refresh() {
    if (usingFixture) return;
    try {
      const [j, a, fh] = await Promise.all([client.getJournal(), client.listAnnotations(), client.filterHealth()]);
      setEntries(j.entries);
      setAnnotations(a.annotations);
      setFilterHealth(fh.health);
    } catch {
      // leave whatever was already loaded
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [j, a, fh] = await Promise.all([client.getJournal(), client.listAnnotations(), client.filterHealth()]);
        if (cancelled) return;
        setEntries(j.entries);
        setAnnotations(a.annotations);
        setFilterHealth(fh.health);
        setUsingFixture(false);
      } catch {
        if (!cancelled) {
          setEntries([]);
          setAnnotations(fixtureAnnotations.annotations);
          setFilterHealth([]);
          setUsingFixture(true);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const annotationById = useMemo(() => new Map(annotations.map((a) => [a.id, a])), [annotations]);
  const filterHealthById = useMemo(() => new Map(filterHealth.map((h) => [h.filter_id, h])), [filterHealth]);

  // Spec 14 §6.2 — the one real "something changed" signal available
  // today: a filter whose reference has drifted (Spec 09 §12). Pinned
  // to the top while unresolved (Breached/Drifting); clears itself once
  // filter_health reports Stable/Quiet/Review due or the filter closes.
  const changeNotices = useMemo(
    () =>
      entries
        .filter((e) => e.kind === "limit_filter" && e.status === "open" && e.ref_id)
        .map((e) => ({ entry: e, health: filterHealthById.get(e.ref_id!) }))
        .filter((x): x is { entry: JournalEntry; health: FilterHealth } =>
          !!x.health && (x.health.status === "breached" || x.health.status === "drifting")),
    [entries, filterHealthById],
  );

  const kindCounts = useMemo(() => {
    const m = new Map<JournalEntryKind, number>();
    for (const e of entries) m.set(e.kind, (m.get(e.kind) ?? 0) + 1);
    return m;
  }, [entries]);

  const filtered = useMemo(() => {
    const base = kindFilter === "all" ? entries : entries.filter((e) => e.kind === kindFilter);
    return [...base].sort((a, b) => b.at.localeCompare(a.at));
  }, [entries, kindFilter]);

  function startEdit(a: Annotation) {
    setEditingId(a.id);
    setDraft(a.note);
  }
  async function saveEdit(id: string) {
    const existing = annotationById.get(id);
    if (!existing) return;
    try {
      await client.saveAnnotation({ id, flightId: existing.flight_id, ref: existing.ref, note: draft });
      await refresh();
    } catch {
      // server unreachable
    }
    setEditingId(null);
  }

  async function reverseEntry(entry: JournalEntry) {
    if (entry.status === "closed" || !entry.ref_id || usingFixture) return;
    try {
      if (entry.kind === "annotation") {
        await client.deleteAnnotation(entry.ref_id);
      } else if (entry.kind === "limit_filter") {
        await client.deleteFilter(entry.ref_id);
        notifyFiltersChanged();
      } else if (entry.kind === "reference_pin") {
        await client.clearReference(entry.ref_id);
        notifyShiftHistoryChanged();
      } else if (entry.kind === "exclusion") {
        await client.includeFlight(entry.ref_id);
      }
      await refresh();
    } catch {
      // server unreachable — leave as-is
    }
  }

  function openWhere(entry: JournalEntry) {
    const where = entry.where as Record<string, unknown> | null | undefined;
    if ((entry.kind === "annotation" || entry.kind === "exclusion") && where?.flight_id) navigate(`/flights/${where.flight_id}`);
    else if (entry.kind === "limit_filter") setActiveTab("filters");
    else if (entry.kind === "reference_pin") navigate("/settings?tab=reference");
  }

  function entryBody(entry: JournalEntry): { title: string; detail: string | null } {
    if (entry.kind === "annotation" && entry.ref_id) {
      const live = annotationById.get(entry.ref_id);
      if (live) return { title: formatDate(live.created_at), detail: live.note };
    }
    if (entry.kind === "limit_filter" && entry.ref_id) {
      const health = filterHealthById.get(entry.ref_id);
      if (health && entry.status === "open") return { title: entry.what, detail: health.summary ?? null };
    }
    return { title: entry.what, detail: entry.note ?? null };
  }

  return (
    <NavShell>
      <div style={{ flexGrow: 1, overflowY: "auto", padding: "24px 28px", display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <h1 style={{ margin: "0 0 4px", fontSize: 19, fontWeight: 700 }}>
            Journal {usingFixture && <span style={{ fontSize: 12, fontWeight: 400, color: "var(--text-tertiary)" }}>(sample)</span>}
            {loading && <span style={{ fontSize: 12, fontWeight: 400, color: "var(--text-tertiary)" }}> · loading…</span>}
          </h1>
          <span className="mono" style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
            {entries.length} entries
          </span>
          {" · "}
          <a href="#" onClick={(e) => { e.preventDefault(); navigate("/settings"); }} style={{ fontSize: 12 }}>
            Settings changelog →
          </a>
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={() => setActiveTab("journal")}
            style={{
              padding: "5px 12px", borderRadius: 20, fontSize: 11, fontWeight: 600, cursor: "pointer",
              border: activeTab === "journal" ? "1px solid var(--text-secondary)" : "1px solid var(--border)",
              background: activeTab === "journal" ? "var(--panel-control)" : "transparent",
              color: "var(--text-secondary)",
            }}
          >
            Journal ({entries.length})
          </button>
          {!usingFixture && (
            <button
              onClick={() => setActiveTab("filters")}
              style={{
                padding: "5px 12px", borderRadius: 20, fontSize: 11, fontWeight: 600, cursor: "pointer",
                border: activeTab === "filters" ? "1px solid var(--text-secondary)" : "1px solid var(--border)",
                background: activeTab === "filters" ? "var(--panel-control)" : "transparent",
                color: "var(--text-secondary)",
              }}
            >
              Limit filters{filterCount !== null ? ` (${filterCount})` : ""}
            </button>
          )}
        </div>

        {activeTab === "filters" && !usingFixture && <LimitFiltersSection onCount={setFilterCount} />}

        {activeTab === "journal" && (
          <>
            {changeNotices.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {changeNotices.map(({ entry, health }) => (
                  <div
                    key={entry.id}
                    style={{
                      background: "rgba(245,165,36,0.08)", border: "1px solid rgba(245,165,36,0.3)",
                      borderRadius: 10, padding: "10px 14px", fontSize: 12, display: "flex",
                      alignItems: "center", justifyContent: "space-between", gap: 10,
                    }}
                  >
                    <span>
                      <strong style={{ color: "var(--severity-warning)" }}>{health.status === "breached" ? "Breached" : "Drifting"}</strong>
                      {" — "}{entry.what}{health.reasons[0] ? `: ${health.reasons[0]}` : ""}
                    </span>
                    <a href="#" onClick={(e) => { e.preventDefault(); setActiveTab("filters"); }} style={{ fontSize: 11, flexShrink: 0 }}>
                      Review in Limit filters →
                    </a>
                  </div>
                ))}
              </div>
            )}

            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <button
                onClick={() => setKindFilter("all")}
                style={{
                  padding: "4px 10px", borderRadius: 20, fontSize: 11, cursor: "pointer",
                  border: kindFilter === "all" ? "1px solid var(--accent)" : "1px solid var(--border)",
                  background: kindFilter === "all" ? "var(--accent-15)" : "transparent",
                  color: kindFilter === "all" ? "var(--accent)" : "var(--text-tertiary)",
                }}
              >
                All ({entries.length})
              </button>
              {KIND_ORDER.map((k) => (
                <button
                  key={k}
                  onClick={() => setKindFilter(k)}
                  disabled={(kindCounts.get(k) ?? 0) === 0 && kindFilter !== k}
                  style={{
                    padding: "4px 10px", borderRadius: 20, fontSize: 11,
                    cursor: (kindCounts.get(k) ?? 0) === 0 ? "default" : "pointer",
                    border: kindFilter === k ? "1px solid var(--accent)" : "1px solid var(--border)",
                    background: kindFilter === k ? "var(--accent-15)" : "transparent",
                    color: kindFilter === k ? "var(--accent)" : (kindCounts.get(k) ?? 0) === 0 ? "var(--text-tertiary)" : "var(--text-secondary)",
                    opacity: (kindCounts.get(k) ?? 0) === 0 ? 0.5 : 1,
                  }}
                >
                  {KIND_LABELS[k]} ({kindCounts.get(k) ?? 0})
                </button>
              ))}
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {filtered.map((entry) => {
                const { title, detail } = entryBody(entry);
                const isAnnotation = entry.kind === "annotation";
                const liveAnnotation = isAnnotation && entry.ref_id ? annotationById.get(entry.ref_id) : null;
                return (
                  <div
                    key={entry.id}
                    data-testid={`journal-entry-${entry.id}`}
                    style={{
                      background: "var(--panel)", borderRadius: 12, padding: "16px 18px",
                      opacity: entry.status === "closed" ? 0.6 : 1,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8, gap: 10 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: 0.4, color: "var(--text-secondary)", background: "var(--panel-control)", padding: "3px 8px", borderRadius: 10 }}>
                          {KIND_LABELS[entry.kind]}
                        </span>
                        <a href="#" onClick={(e) => { e.preventDefault(); openWhere(entry); }} style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", textDecoration: entry.status === "closed" ? "line-through" : "none" }}>
                          {title}
                        </a>
                        {entry.status === "closed" && (
                          <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>closed {entry.closed_at ? formatDate(entry.closed_at) : ""}</span>
                        )}
                      </div>
                      <div style={{ display: "flex", gap: 10, flexShrink: 0 }}>
                        {isAnnotation && entry.status === "open" && liveAnnotation && (
                          <button onClick={() => startEdit(liveAnnotation)} style={{ background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer", fontSize: 11 }}>
                            Edit
                          </button>
                        )}
                        {entry.status === "open" && !usingFixture && (
                          <button onClick={() => reverseEntry(entry)} style={{ background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer", fontSize: 11 }}>
                            {entry.kind === "reference_pin" ? "Unpin" : entry.kind === "annotation" ? "Delete" : entry.kind === "exclusion" ? "Include again" : "Remove"}
                          </button>
                        )}
                      </div>
                    </div>
                    {isAnnotation && editingId === entry.ref_id ? (
                      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                        <textarea
                          value={draft}
                          onChange={(e) => setDraft(e.target.value)}
                          rows={2}
                          style={{ flexGrow: 1, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: 8, color: "var(--text-primary)", fontSize: 13, fontFamily: "inherit" }}
                        />
                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                          <button onClick={() => saveEdit(entry.ref_id!)} style={{ padding: "5px 10px", borderRadius: 6, background: "var(--accent)", border: "none", color: "var(--bg)", fontSize: 11, fontWeight: 600, cursor: "pointer" }}>
                            Save
                          </button>
                          <button onClick={() => setEditingId(null)} style={{ padding: "5px 10px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", fontSize: 11, cursor: "pointer" }}>
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      detail && <div style={{ fontSize: 13, color: "var(--text-primary)", lineHeight: 1.5, marginBottom: 8 }}>{detail}</div>
                    )}
                    <span className="mono" style={{ fontSize: 10, color: "var(--text-tertiary)" }}>
                      {formatDate(entry.at)}
                      {entry.reason && ` · ${entry.reason}`}
                      {entry.effect && ` · ${entry.effect}`}
                    </span>
                  </div>
                );
              })}
              {filtered.length === 0 && (
                <div style={{ padding: 24, textAlign: "center", color: "var(--text-tertiary)", fontSize: 13 }}>
                  No entries{kindFilter !== "all" ? ` of kind "${KIND_LABELS[kindFilter]}"` : ""} yet.
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </NavShell>
  );
}
