import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getEngineClient } from "../lib/engineClient";
import type { FilterListEntry } from "../types/contract";
import { FilterEditor } from "./FilterEditor";

const client = getEngineClient();

function formatDate(iso: string | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

// Spec 09 §2, for pilots: shown behind "How filters differ from baselines".
function FiltersExplainer() {
  return (
    <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.55, background: "var(--bg)", borderRadius: 8, padding: "10px 12px" }}>
      <p style={{ margin: "0 0 6px" }}>
        <strong>Your baseline</strong> is the tool's memory of what is normal for your engine. It learns from every flight and tells you
        when a flight is unusual <em>for your aircraft</em>, even if nothing went past an OM limit.
      </p>
      <p style={{ margin: "0 0 6px" }}>
        <strong>A filter</strong> is your own statement about one OM limit: “on my aircraft, this limit is exceeded in a way I understand and
        accept.” You set it, you say why, and exceedances within it collapse into one quiet line. Anything beyond it is still reported at the
        limit's normal severity, marked “beyond your filter”.
      </p>
      <p style={{ margin: 0 }}>
        A filter never switches the baseline off: a flight that is unusually hot for your engine still gets a “watch” insight. And unlike the
        baseline, a filter doesn't keep learning — one that did would slowly accept a problem that is getting worse.
      </p>
    </div>
  );
}

// Spec 09 §12.2: the Notes page's "Limit filters" section.
export function LimitFiltersSection() {
  const navigate = useNavigate();
  const [entries, setEntries] = useState<FilterListEntry[] | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [explain, setExplain] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setEntries((await client.listFilters()).filters);
    } catch {
      setEntries(null); // server unreachable: no section in the sample view
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    client
      .listFilters()
      .then((r) => !cancelled && setEntries(r.filters))
      .catch(() => !cancelled && setEntries(null));
    return () => {
      cancelled = true;
    };
  }, []);

  async function remove(id: string) {
    try {
      await client.deleteFilter(id);
    } finally {
      await refresh();
    }
  }

  if (entries === null) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>Limit filters</h2>
        <span className="mono" style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
          {entries.length} filter{entries.length === 1 ? "" : "s"}
        </span>
        <span onClick={() => setExplain((v) => !v)} style={{ fontSize: 12, color: "var(--accent)", cursor: "pointer" }}>
          How filters differ from baselines {explain ? "▾" : "▸"}
        </span>
      </div>
      {explain && <FiltersExplainer />}
      {entries.length === 0 && (
        <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
          No filters. To accept a known, consistent exceedance, open a flight and use “Filter this limit…” on its limit card.
        </div>
      )}
      {entries.map(({ filter, limit, valid, diagnostics, summary }) => (
        <div key={filter.id} style={{ background: "var(--panel)", borderRadius: 10, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>{limit?.label ?? filter.limit_id}</span>
            {limit && (
              <span className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                OM {limit.limit_type === "MIN" ? "min" : "max"} {limit.limit_value} {limit.unit} · {limit.severity}
              </span>
            )}
            {!valid && (
              <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.5, color: "var(--severity-limit)" }}>NOT APPLIED</span>
            )}
          </div>
          <div className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>Tolerates {summary || "—"}</div>
          {filter.note && <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.45 }}>“{filter.note}”</div>}
          {!valid && (
            <div style={{ fontSize: 12, color: "var(--severity-limit)" }}>
              {diagnostics.map((d) => d.message).join(" ")} The limit reports unfiltered until this is fixed.
            </div>
          )}
          <div style={{ display: "flex", gap: 14, fontSize: 11, color: "var(--text-tertiary)", alignItems: "center" }}>
            <span>Set {formatDate(filter.created_at)}{filter.updated_at ? ` · edited ${formatDate(filter.updated_at)}` : ""}</span>
            <span>{filter.reference.flight_ids.length} reference flights</span>
            {filter.created_from && (
              <span onClick={() => navigate(`/flights/${filter.created_from!.flight_id}`)} style={{ cursor: "pointer", color: "var(--accent)" }}>
                from flight →
              </span>
            )}
            <span style={{ marginLeft: "auto", display: "flex", gap: 12 }}>
              <span onClick={() => setEditing(editing === filter.id ? null : filter.id)} style={{ cursor: "pointer", color: "var(--text-secondary)" }}>
                Edit
              </span>
              <span onClick={() => remove(filter.id)} style={{ cursor: "pointer", color: "var(--text-secondary)" }}>
                Remove
              </span>
            </span>
          </div>
          {editing === filter.id && (
            <FilterEditor
              limitId={filter.limit_id}
              onSaved={() => {
                setEditing(null);
                void refresh();
              }}
              onCancel={() => setEditing(null)}
            />
          )}
        </div>
      ))}
    </div>
  );
}
