import { useMemo } from "react";
import type { FleetAnalysis, TrendsPanel } from "../types/contract";
import { metricLabel, panelLabel, unitFor } from "../lib/trendsUnits";

// Spec 12 §7/§7.1 — the change summary: one row per metric/coupled panel
// that qualifies (§5.6), ranked by the engine (fleet.change_summary),
// level crossings first. Row click opens that panel (handled by the
// caller, which also shades the recent/reference regions — Trends.tsx).

function formatDelta(value: number, unit: string): string {
  const v = Math.abs(value);
  const text = v >= 10 ? v.toFixed(0) : v.toFixed(1);
  return unit ? (unit === "%" || unit.startsWith("°") ? `${text}${unit}` : `${text} ${unit}`) : text;
}

interface Props {
  fleet: FleetAnalysis;
  panels: TrendsPanel[];
  onOpenPanel: (panel: string, flightIds: string[]) => void;
  onOpenFlights: (flightIds: string[]) => void;
}

export function ChangeSummaryList({ fleet, panels, onOpenPanel, onOpenFlights }: Props) {
  const declByMetric = useMemo(() => {
    const out: Record<string, { panel: string; phrasing: { higher: string; lower: string } | null; role: string }> = {};
    for (const p of panels) for (const m of p.metrics) out[m.metric_id] = { panel: p.panel, phrasing: m.phrasing, role: m.role };
    return out;
  }, [panels]);

  const checkedCount = useMemo(() => Object.values(fleet.metrics).filter((m) => m.shift).length, [fleet]);
  const consideredInRows = fleet.change_summary.reduce((n, r) => n + (r.members?.length ?? 1), 0);
  const otherCount = Math.max(0, checkedCount - consideredInRows);

  if (fleet.change_summary.length === 0) {
    const hours = fleet.provenance.baseline_config.recent_window_hours;
    return (
      <div style={{ background: "var(--panel)", borderRadius: 12, padding: "16px 18px", fontSize: 13, color: "var(--text-secondary)" }}>
        No change detected across {checkedCount} metric{checkedCount === 1 ? "" : "s"} over the last {hours} hours.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {fleet.change_summary.map((row) => {
        const metric = fleet.metrics[row.metric_id];
        const shift = metric?.shift;
        if (!shift) return null;
        const decl = declByMetric[row.metric_id];
        const panelId = row.panel ?? decl?.panel ?? "";
        const unit = unitFor(row.metric_id);
        const delta = shift.recent.mean != null && shift.reference.mean != null ? formatDelta(shift.recent.mean - shift.reference.mean, unit) : "";
        const phrase = decl?.phrasing ? decl.phrasing[shift.direction === "lower" ? "lower" : "higher"] : `${shift.direction} than it used to`;
        const label = row.panel ? `${panelLabel(row.panel)} · ${metricLabel(row.metric_id)}` : `${panelLabel(panelId)} · ${metricLabel(row.metric_id)}`;
        const level = shift.level;
        const qualifiers: string[] = [];
        if (shift.bend?.fires) qualifiers.push("and the rate of change has shifted");
        if (level.om_margin) qualifiers.push("within the OM margin");
        if (level.filter_edge) qualifiers.push("at the edge of your filter band");
        if (shift.reference.kind === "pinned") qualifiers.push(`since ${shift.reference.label ?? "pinned reference"}`);
        const allFlightIds = row.members
          ? row.members.flatMap((m) => fleet.metrics[m]?.shift?.recent.flight_ids ?? [])
          : shift.recent.flight_ids;

        return (
          <div
            key={row.metric_id}
            onClick={() => onOpenPanel(panelId, shift.recent.flight_ids)}
            style={{ background: "var(--panel)", borderRadius: 12, padding: "14px 16px", cursor: "pointer" }}
          >
            <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 2 }}>{label}</div>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              {metricLabel(row.metric_id)} is {delta ? `about ${delta} ` : ""}{phrase}
              {row.members && row.members.length > 1 && (
                <span style={{ fontWeight: 400, color: "var(--text-tertiary)" }}> (relative to the other cylinders)</span>
              )}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: qualifiers.length ? 4 : 0 }}>
              last{" "}
              <a href="#" onClick={(e) => { e.stopPropagation(); e.preventDefault(); onOpenFlights(shift.recent.flight_ids); }}>
                {shift.recent.n} flight{shift.recent.n === 1 ? "" : "s"}
              </a>{" "}
              ({(shift.recent.hours_to - shift.recent.hours_from).toFixed(1)} h) vs.{" "}
              <a href="#" onClick={(e) => { e.stopPropagation(); e.preventDefault(); onOpenFlights(allFlightIds); }}>
                {shift.reference.n} earlier flight{shift.reference.n === 1 ? "" : "s"}
              </a>
              {shift.comparison.scope === "band" ? ", compared within band" : ""}
            </div>
            {qualifiers.length > 0 && (
              <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{qualifiers.join(" · ")}</div>
            )}
          </div>
        );
      })}
      {otherCount > 0 && (
        <div style={{ fontSize: 12, color: "var(--text-tertiary)", padding: "4px 4px" }}>
          {otherCount} other metric{otherCount === 1 ? "" : "s"} checked, no change.
        </div>
      )}
    </div>
  );
}
