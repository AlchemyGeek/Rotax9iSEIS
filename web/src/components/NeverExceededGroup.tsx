import { useState } from "react";
import { EventStrip } from "./EventStrip";
import { panelLabel } from "../lib/trendsUnits";
import type { FleetAnalysis, TrendsPanel } from "../types/contract";

// Spec 12 §9.1 (Session F) — tier 3: one collapsed group at the
// bottom for every limit whose only badge is *never exceeded*, so the
// page doesn't scroll through a dozen empty panels. Rows are one line
// each (name, tick count, "never exceeded on N flights") and expand to
// just the event strip — not a full TrendsPanelStrip — since there's
// no magnitude/shift to show for a limit with zero events.

interface Props {
  panels: TrendsPanel[]; // tier 3 only
  fleet: FleetAnalysis;
  highlightFlight: string | null;
  onOpenFlight: (flightId: string) => void;
}

function representativeMetricId(panel: TrendsPanel): string | undefined {
  return panel.metrics.find((m) => m.metric_id.endsWith("_peak_excess") || m.metric_id.endsWith("_block_s"))?.metric_id
    ?? panel.metrics[0]?.metric_id;
}

// A CAS alert panel (Spec 12 v0.10 G3) joins this group on the same
// rule; it was never *seen*, not never exceeded.
function groupSummary(panels: TrendsPanel[]): string {
  const alerts = panels.filter((p) => p.cas_id).length;
  const limits = panels.length - alerts;
  const parts = [];
  if (limits) parts.push(`${limits} limit${limits === 1 ? "" : "s"} never exceeded`);
  if (alerts) parts.push(`${alerts} alert${alerts === 1 ? "" : "s"} never seen`);
  return parts.join(", ");
}

export function NeverExceededGroup({ panels, fleet, highlightFlight, onOpenFlight }: Props) {
  const [open, setOpen] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  if (panels.length === 0) return null;

  return (
    <div style={{ background: "var(--panel)", borderRadius: 14, overflow: "hidden", marginTop: 10 }}>
      <div
        onClick={() => setOpen((o) => !o)}
        style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", cursor: "pointer" }}
      >
        <span style={{ fontSize: 14, fontWeight: 700 }}>
          Never exceeded ({panels.length})
        </span>
        <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}>{open ? "▾" : "▸"}</span>
      </div>
      {open && (
        <div style={{ padding: "0 16px 16px", display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 4 }}>
            {groupSummary(panels)} on {fleet.flight_ids.length} flight{fleet.flight_ids.length === 1 ? "" : "s"}.
          </div>
          {panels.map((panel) => {
            const metricId = representativeMetricId(panel);
            const metric = metricId ? fleet.metrics[metricId] : undefined;
            const events = metric?.events ?? [];
            const rowOpen = expandedRows.has(panel.panel);
            return (
              <div key={panel.panel}>
                <div
                  onClick={() => setExpandedRows((prev) => {
                    const next = new Set(prev);
                    if (next.has(panel.panel)) next.delete(panel.panel); else next.add(panel.panel);
                    return next;
                  })}
                  style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 4px", cursor: "pointer", fontSize: 12 }}
                >
                  <span>{panelLabel(panel.panel)}</span>
                  <span style={{ color: "var(--text-tertiary)" }}>
                    {events.length} tick{events.length === 1 ? "" : "s"} &middot; {panel.cas_id ? "never seen" : "never exceeded"} on {events.length} flight{events.length === 1 ? "" : "s"}
                    <span style={{ marginLeft: 8 }}>{rowOpen ? "▾" : "▸"}</span>
                  </span>
                </div>
                {rowOpen && metric?.events && metric.frequency && (
                  <EventStrip
                    events={metric.events}
                    frequency={metric.frequency}
                    verb={panel.cas_id ? "occurred" : "exceeded"}
                    highlightFlight={highlightFlight}
                    onOpenFlight={onOpenFlight}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
