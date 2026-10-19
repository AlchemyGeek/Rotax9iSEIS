import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getEngineClient } from "../lib/engineClient";
import type { FilterHealth, FilterListEntry, FilterStatus, LimitFilter, WorkspaceRegistryEntry } from "../types/contract";
import { targetLabel } from "../types/contract";
import { FilterEditor } from "./FilterEditor";
import { FilterHealthCharts } from "./FilterHealthCharts";
import { notifyFiltersChanged } from "../lib/filterAttention";
import { ScopeCaption } from "./ScopeCaption";
import { APPLY_LABEL, filterScope } from "../lib/scope";

const STATUS_STYLE: Record<FilterStatus, { label: string; color: string }> = {
  breached: { label: "BREACHED", color: "var(--severity-limit)" },
  drifting: { label: "DRIFTING", color: "var(--severity-warning)" },
  review_due: { label: "REVIEW DUE", color: "var(--severity-watch)" },
  quiet: { label: "QUIET", color: "var(--severity-info-text)" },
  collecting: { label: "COLLECTING", color: "var(--severity-info-text)" },
  stable: { label: "STABLE", color: "var(--ok)" },
};

function StatusBadge({ status }: { status: FilterStatus }) {
  const s = STATUS_STYLE[status];
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 10, fontWeight: 700, letterSpacing: 0.5, color: s.color }}>
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: s.color }} />
      {s.label}
    </span>
  );
}

// The statistics behind a Drifting reason, for those who want them.
function driftDetailText(details: NonNullable<FilterHealth["drift_details"]>): string {
  return details
    .map((d) => {
      if (d.metric === "share_with_events") {
        return `Event frequency: ${Math.round((d.values[0] ?? 0) * 100)}% of the last ${d.window} flights vs ${Math.round((d.typical ?? 0) * 100)}% of the reference; drifting at +${Math.round((d.threshold_delta ?? 0) * 100)} points or more.`;
      }
      const cmp = d.comparison?.scope === "band" ? `reference flights in the "${d.comparison.band}" band` : "all reference flights";
      const above = d.z?.some((z) => z === null)
        ? "Last flights above a reference that never varied (any increase counts)"
        : `Last flights ${d.z?.map((z) => (z ?? 0).toFixed(1)).join(" and ")} std devs above typical`;
      return (
        `${d.metric.replace(/_/g, " ")}: compared with ${cmp} (n=${d.comparison?.n}), typical ${d.typical?.toFixed(2)} ± ${(d.std ?? 0).toFixed(2)}. ` +
        `${above}; drifting above ${d.z_threshold} ` +
        `on 2 flights in a row (set per metric in Settings → Reference & Models).`
      );
    })
    .join("\n\n");
}

// Spec 09 v0.20 §12.2: events hidden because they lay wholly in an
// excluded phase, over the monitored history.
function phaseSuppressedText(series: FilterHealth["series"]): string {
  const total = series.reduce((n, s) => n + (s.suppressed_by_phase ?? 0), 0);
  const flights = series.filter((s) => (s.suppressed_by_phase ?? 0) > 0).length;
  return total === 0
    ? "nothing suppressed by phase yet"
    : `${total} event${total === 1 ? "" : "s"} suppressed by phase on ${flights} flight${flights === 1 ? "" : "s"}`;
}

function History({ history }: { history: LimitFilter["history"] }) {
  return (
    <div className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)", display: "flex", flexDirection: "column", gap: 2 }}>
      {[...history].reverse().map((h, i) => (
        <div key={i}>
          {formatDate(h.at)} · {h.action}
          {h.after && h.action !== "reviewed" && h.action !== "rebaselined" && ` → ${JSON.stringify(h.after)}`}
        </div>
      ))}
    </div>
  );
}

const client = getEngineClient();

function formatDate(iso: string | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

// Spec 09 §2, for pilots: shown behind "How filters differ from your reference".
function FiltersExplainer() {
  return (
    <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.55, background: "var(--bg)", borderRadius: 8, padding: "10px 12px" }}>
      <p style={{ margin: "0 0 6px" }}>
        <strong>Your reference</strong> is the tool's memory of what is normal for your engine. It learns from every flight and tells you
        when a flight is unusual <em>for your aircraft</em>, even if nothing went past an OM limit.
      </p>
      <p style={{ margin: "0 0 6px" }}>
        <strong>A filter</strong> is your own statement about one OM limit: “on my aircraft, this limit is exceeded in a way I understand and
        accept.” You set it, you say why, and exceedances within it collapse into one quiet line. Anything beyond it is still reported at the
        limit's normal severity, marked “beyond your filter”.
      </p>
      <p style={{ margin: "0 0 6px" }}>
        A filter never switches the reference off: a flight that is unusually hot for your engine still gets a “watch” insight. And unlike the
        reference, a filter doesn't keep learning — one that did would slowly accept a problem that is getting worse.
      </p>
      <p style={{ margin: 0 }}>
        For temperature-sensitive limits (such as oil, coolant and EGT temperatures, and fuel pressure), each new flight is
        compared with your reference flights in similar outside temperature once there are at least 10 of them, so a cold-day
        reading isn't mistaken for a change. Manifold pressure and overboost are compared by density altitude the same way.
      </p>
    </div>
  );
}

// Spec 09 §9: copy another workspace's filters here — offered only for
// workspaces with the same engine model; the server enforces it too.
function CopyFilters({ onCopied }: { onCopied: () => void }) {
  const [sources, setSources] = useState<WorkspaceRegistryEntry[] | null>(null);
  const [selected, setSelected] = useState("");
  const [result, setResult] = useState<string | null>(null);

  async function open() {
    try {
      const [active, all] = await Promise.all([client.getActiveWorkspace(), client.listWorkspaces()]);
      const model = active.manifest?.engine_model;
      const activeId = active.manifest?.id;
      const same = all.filter((w) => w.engine_model === model && w.id !== activeId);
      setSources(same);
      setSelected(same[0]?.id ?? "");
    } catch {
      setSources([]);
    }
  }

  async function copy() {
    try {
      const r = await client.copyFilters(selected);
      const invalid = r.copied.filter((c) => !c.valid).length;
      setResult(
        `Copied ${r.copied.length} filter${r.copied.length === 1 ? "" : "s"}` +
          (invalid ? ` (${invalid} not applied here — see below)` : "") +
          (r.skipped.length ? `; skipped ${r.skipped.map((s) => `${targetLabel(s.target)} (${s.reason})`).join(", ")}` : "") +
          ".",
      );
      onCopied();
    } catch (e) {
      setResult(e instanceof Error ? e.message : String(e));
    }
  }

  if (sources === null) {
    return (
      <span onClick={open} style={{ fontSize: 12, color: "var(--text-secondary)", cursor: "pointer", marginLeft: "auto" }}>
        Copy filters from…
      </span>
    );
  }
  return (
    <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
      {sources.length === 0 ? (
        <span style={{ color: "var(--text-tertiary)" }}>No other workspace with this engine model.</span>
      ) : (
        <>
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "4px 8px", color: "var(--text-primary)", fontSize: 12 }}
          >
            {sources.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
          <ScopeCaption scope="all_limits" />
          <span onClick={copy} style={{ color: "var(--link)", textDecoration: "underline", textDecorationColor: "var(--link-underline)", textUnderlineOffset: 2, cursor: "pointer" }}>{APPLY_LABEL.all_limits}</span>
        </>
      )}
      <span onClick={() => { setSources(null); setResult(null); }} style={{ color: "var(--text-tertiary)", cursor: "pointer" }}>
        Close
      </span>
      {result && <span style={{ color: "var(--text-secondary)" }}>{result}</span>}
    </span>
  );
}

// Spec 09 §12.2: the Notes page's "Limit filters" section.
interface Props {
  // Lets a tab-style host (the Notes page) show "Limit filters (N)" on
  // its own tab button without duplicating this component's fetch —
  // called whenever entries actually loads, never while still null.
  onCount?: (n: number) => void;
}

export function LimitFiltersSection({ onCount }: Props = {}) {
  const navigate = useNavigate();
  const [entries, setEntries] = useState<FilterListEntry[] | null>(null);
  const [health, setHealth] = useState<Record<string, FilterHealth>>({});
  const [editing, setEditing] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState<string | null>(null);
  const [explain, setExplain] = useState(false);

  const load = useCallback(async () => {
    const [list, h] = await Promise.all([client.listFilters(), client.filterHealth()]);
    return { list: list.filters, health: Object.fromEntries(h.health.map((x) => [x.filter_id, x])) };
  }, []);

  const refresh = useCallback(async () => {
    try {
      const r = await load();
      setEntries(r.list);
      setHealth(r.health);
    } catch {
      setEntries(null); // server unreachable: no section in the sample view
    }
    notifyFiltersChanged();
  }, [load]);

  useEffect(() => {
    if (entries !== null) onCount?.(entries.length);
  }, [entries, onCount]);

  useEffect(() => {
    let cancelled = false;
    load()
      .then((r) => {
        if (cancelled) return;
        setEntries(r.list);
        setHealth(r.health);
      })
      .catch(() => !cancelled && setEntries(null));
    return () => {
      cancelled = true;
    };
  }, [load]);

  async function act(fn: () => Promise<unknown>) {
    try {
      await fn();
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
        <span onClick={() => setExplain((v) => !v)} style={{ fontSize: 12, color: "var(--link)", textDecoration: "underline", textDecorationColor: "var(--link-underline)", textUnderlineOffset: 2, cursor: "pointer" }}>
          How filters differ from your reference {explain ? "▾" : "▸"}
        </span>
        <CopyFilters onCopied={() => void refresh()} />
      </div>
      {explain && <FiltersExplainer />}
      {entries.length === 0 && (
        <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
          No filters. To accept a known, consistent exceedance, open a flight and use “Filter this limit…” on its limit card.
        </div>
      )}
      {entries.map(({ filter, limit, valid, diagnostics, summary, target_label }) => {
        const h = health[filter.id];
        return (
          <div key={filter.id} style={{ background: "var(--panel)", borderRadius: 10, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              {h && <StatusBadge status={h.status} />}
              <span style={{ fontSize: 13, fontWeight: 600 }}>{target_label ?? targetLabel(filter.target, limit?.label)}</span>
              {limit && filter.target.kind !== "cas" && (
                <span className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                  OM {limit.limit_type === "MIN" ? "min" : "max"} {limit.limit_value} {limit.unit} · {limit.severity}
                </span>
              )}
              {!valid && <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.5, color: "var(--severity-limit)" }}>NOT APPLIED</span>}
              <a
                href="#"
                onClick={(e) => { e.preventDefault(); navigate(`/trends?panel=${encodeURIComponent(filter.target.kind === "cas" ? `cas:${filter.target.cas_id}` : `limit:${filter.target.limit_id}`)}`); }}
                style={{ marginLeft: "auto", fontSize: 11 }}
                title="See this limit's panel on Trends — the filter band and its reference shift"
              >
                View on Trends →
              </a>
            </div>
            {h && h.reasons.length > 0 && (
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5 }}>
                {h.reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
                {h.drift_details && h.drift_details.length > 0 && (
                  <li style={{ listStyle: "none", marginLeft: -18, color: "var(--text-tertiary)" }}>
                    The shaded area on the charts below marks the {h.reference?.flight_ids.length ?? filter.reference.flight_ids.length} reference
                    flights (grey): what was normal when you set this filter, last changed its limits or reset its reference. Drift
                    compares your recent flights with them. If the new behaviour is expected, Reset reference makes your latest flights the reference.
                  </li>
                )}
                {h.drift_details && h.drift_details.length > 0 && (
                  <li style={{ listStyle: "none", marginLeft: -18 }}>
                    <span title={driftDetailText(h.drift_details)} style={{ fontSize: 11, color: "var(--text-tertiary)", cursor: "help", textDecoration: "underline dotted" }}>
                      How was this decided?
                    </span>
                  </li>
                )}
              </ul>
            )}
            <div className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>Tolerates {summary || "—"}</div>
            {filter.phases && filter.phases.length > 0 && (
              // Spec 09 v0.20 §12.2: the excluded phases, and what they hide.
              <div data-testid="filter-phases" style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                Excluded phases: {filter.phases.join(", ")}
                {h && ` · ${phaseSuppressedText(h.series)}`}
              </div>
            )}
            {filter.note && <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.45 }}>“{filter.note}”</div>}
            {!valid && (
              <div style={{ fontSize: 12, color: "var(--severity-limit)" }}>
                {diagnostics.map((d) => d.message).join(" ")} The limit reports unfiltered until this is fixed.
              </div>
            )}
            {h && limit && filter.target.kind !== "cas" && h.series.length > 0 && (
              <FilterHealthCharts health={h} unit={limit.unit} limitValue={limit.limit_value} stratifyKind={limit.stratify_by} />
            )}
            <div style={{ display: "flex", gap: 14, fontSize: 11, color: "var(--text-tertiary)", alignItems: "center", flexWrap: "wrap" }}>
              <span>
                Set {formatDate(filter.created_at)}
                {filter.updated_at ? ` · edited ${formatDate(filter.updated_at)}` : ""}
                {filter.reviewed_at ? ` · reviewed ${formatDate(filter.reviewed_at)}` : ""}
              </span>
              {h?.hours_since_review !== null && h?.hours_since_review !== undefined && (
                <span>{h.hours_since_review} h since {filter.reviewed_at ? "review" : "set"}</span>
              )}
              <span>{h?.reference?.flight_ids.length ?? filter.reference.flight_ids.length} reference flights</span>
              {h?.last_breach && (
                <span onClick={() => navigate(`/flights/${h.last_breach!.flight_id}`)} style={{ cursor: "pointer", color: "var(--severity-limit)" }}>
                  last breach →
                </span>
              )}
              <span style={{ marginLeft: "auto", display: "flex", gap: 12, alignItems: "center" }}>
                <ScopeCaption scope={filterScope(filter.target)} />
                {[
                  ["Edit", () => setEditing(editing === filter.id ? null : filter.id)],
                  ["Reset reference", () => act(() => client.rebaselineFilter(filter.id))],
                  ["Mark reviewed", () => act(() => client.reviewFilter(filter.id))],
                  ["History", () => setHistoryOpen(historyOpen === filter.id ? null : filter.id)],
                  ["Remove", () => act(() => client.deleteFilter(filter.id))],
                ].map(([label, onClick]) => (
                  <span
                    key={label as string}
                    onClick={onClick as () => void}
                    title={
                      label === "Reset reference"
                        ? "Accept how the engine behaves now: the filter's reference becomes the most recent flights"
                        : label === "Mark reviewed"
                          ? "Clears Breached and Review due; Drifting clears only when it stops or you reset the reference"
                          : undefined
                    }
                    style={{ cursor: "pointer", color: "var(--text-secondary)" }}
                  >
                    {label as string}
                  </span>
                ))}
              </span>
            </div>
            {historyOpen === filter.id && <History history={filter.history} />}
            {editing === filter.id && (
              <FilterEditor
                target={filter.target}
                onSaved={() => {
                  setEditing(null);
                  void refresh();
                }}
                onCancel={() => setEditing(null)}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
