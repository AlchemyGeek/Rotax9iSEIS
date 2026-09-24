import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { NavShell } from "../components/NavShell";
import { annotationStore as fixtureAnnotations } from "../lib/fixtures";
import type { Annotation } from "../types/contract";

type TypeFilter = "all" | "insight" | "event";

function typeFilterOf(a: Annotation): TypeFilter {
  return a.ref.kind === "insight" ? "insight" : "event";
}

function refBadge(a: Annotation): { label: string; color: string; bg: string } {
  if (a.ref.kind === "ecu_run") return { label: "ECU EVENT", color: "var(--severity-limit)", bg: "rgba(229,72,77,0.12)" };
  if (a.ref.kind === "insight") return { label: "INSIGHT", color: "var(--severity-info-text)", bg: "rgba(100,116,139,0.15)" };
  return { label: a.ref.kind.toUpperCase(), color: "var(--text-secondary)", bg: "var(--panel-control)" };
}

function refLinkLabel(a: Annotation): string {
  if (a.ref.kind === "insight") return `${a.ref.insight_id} →`;
  if (a.ref.kind === "ecu_run") return `${a.ref.ref} →`;
  return `${a.ref.ref} →`;
}

function refTarget(a: Annotation): string {
  return a.ref.kind === "ecu_run" ? "/ecu" : `/flights/${a.flight_id}`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" });
}

// Browse/manage every note across the fleet (Spec 03 §5.6) — findable
// later without hunting through individual flights (BACKLOG B4's original
// motivation). Edit/delete are real local-state mutations, not stubs —
// there's just no workspace-write endpoint yet for them to persist
// through (Spec 02 annotations.json isn't wired to the local server),
// which matches how the rest of this fixture round is scoped.
export function Annotations() {
  const navigate = useNavigate();
  const [annotations, setAnnotations] = useState<Annotation[]>(fixtureAnnotations.annotations);
  const [search, setSearch] = useState("");
  const [flightFilter, setFlightFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const flightDates = useMemo(() => {
    const map = new Map<string, string>();
    for (const a of annotations) if (!map.has(a.flight_id)) map.set(a.flight_id, formatDate(a.created_at));
    return map;
  }, [annotations]);

  const filtered = useMemo(() => {
    return annotations
      .filter((a) => (search ? a.note.toLowerCase().includes(search.toLowerCase()) : true))
      .filter((a) => (flightFilter === "all" ? true : a.flight_id === flightFilter))
      .filter((a) => (typeFilter === "all" ? true : typeFilterOf(a) === typeFilter))
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
  }, [annotations, search, flightFilter, typeFilter]);

  const flightCount = new Set(annotations.map((a) => a.flight_id)).size;

  function startEdit(a: Annotation) {
    setEditingId(a.id);
    setDraft(a.note);
  }
  function saveEdit(id: string) {
    setAnnotations((prev) => prev.map((a) => (a.id === id ? { ...a, note: draft, updated_at: new Date().toISOString() } : a)));
    setEditingId(null);
  }
  function deleteAnnotation(id: string) {
    setAnnotations((prev) => prev.filter((a) => a.id !== id));
  }

  return (
    <NavShell>
      <div style={{ flexGrow: 1, overflowY: "auto", padding: "24px 28px", display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <h1 style={{ margin: "0 0 4px", fontSize: 19, fontWeight: 700 }}>Annotations</h1>
          <span className="mono" style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
            {annotations.length} notes across {flightCount} flights
          </span>
        </div>

        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <input
            type="text"
            placeholder="Search notes…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ flexGrow: 1, maxWidth: 360, background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, padding: "9px 12px", color: "var(--text-primary)", fontSize: 13 }}
          />
          <select
            value={flightFilter}
            onChange={(e) => setFlightFilter(e.target.value)}
            style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, padding: "9px 12px", color: "var(--text-secondary)", fontSize: 13 }}
          >
            <option value="all">All flights</option>
            {Array.from(flightDates.entries()).map(([fid, date]) => (
              <option key={fid} value={fid}>{date}</option>
            ))}
          </select>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value as TypeFilter)}
            style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, padding: "9px 12px", color: "var(--text-secondary)", fontSize: 13 }}
          >
            <option value="all">All types</option>
            <option value="insight">Insights</option>
            <option value="event">ECU events</option>
          </select>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {filtered.map((a) => {
            const badge = refBadge(a);
            return (
              <div key={a.id} style={{ background: "var(--panel)", borderRadius: 12, padding: "16px 18px" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <a href="#" onClick={(e) => { e.preventDefault(); navigate(`/flights/${a.flight_id}`); }} style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
                      {formatDate(a.created_at)}
                    </a>
                    <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: 0.4, color: badge.color, background: badge.bg, padding: "3px 8px", borderRadius: 10 }}>
                      {badge.label}
                    </span>
                    <a href="#" onClick={(e) => { e.preventDefault(); navigate(refTarget(a)); }} style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                      {refLinkLabel(a)}
                    </a>
                  </div>
                  <div style={{ display: "flex", gap: 10 }}>
                    <button onClick={() => startEdit(a)} style={{ background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer", fontSize: 11 }}>
                      Edit
                    </button>
                    <button onClick={() => deleteAnnotation(a.id)} style={{ background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer", fontSize: 11 }}>
                      Delete
                    </button>
                  </div>
                </div>
                {editingId === a.id ? (
                  <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                    <textarea
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      rows={2}
                      style={{ flexGrow: 1, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: 8, color: "var(--text-primary)", fontSize: 13, fontFamily: "inherit" }}
                    />
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      <button onClick={() => saveEdit(a.id)} style={{ padding: "5px 10px", borderRadius: 6, background: "var(--accent)", border: "none", color: "var(--bg)", fontSize: 11, fontWeight: 600, cursor: "pointer" }}>
                        Save
                      </button>
                      <button onClick={() => setEditingId(null)} style={{ padding: "5px 10px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", fontSize: 11, cursor: "pointer" }}>
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div style={{ fontSize: 13, color: "var(--text-primary)", lineHeight: 1.5, marginBottom: 8 }}>{a.note}</div>
                )}
                <span className="mono" style={{ fontSize: 10, color: "var(--text-tertiary)" }}>
                  added {formatDate(a.created_at)}
                  {a.updated_at && ` · edited ${formatDate(a.updated_at)}`}
                </span>
              </div>
            );
          })}
          {filtered.length === 0 && (
            <div style={{ padding: 24, textAlign: "center", color: "var(--text-tertiary)", fontSize: 13 }}>No annotations match this filter.</div>
          )}
        </div>
      </div>
    </NavShell>
  );
}
