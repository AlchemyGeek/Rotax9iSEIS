import { useState } from "react";
import type { ShiftEvent } from "../types/contract";
import { metricLabel, panelLabel } from "../lib/trendsUnits";

// Spec 12 §7.1 — a collapsed "Past changes" section beneath the change
// summary: closed shift events, newest first, each linking to its panel
// with the event's window shaded; deletable (the one exception to the
// history's append-only rule).

interface Props {
  events: ShiftEvent[];
  onOpenPanel: (panel: string, flightIds: string[]) => void;
  onDelete: (eventId: string) => void;
  busyId?: string | null;
}

export function PastChanges({ events, onOpenPanel, onDelete, busyId }: Props) {
  const [open, setOpen] = useState(false);
  const closed = events
    .filter((e) => e.cleared_at)
    .sort((a, b) => (b.cleared_at! > a.cleared_at! ? 1 : -1));

  if (closed.length === 0) return null;

  return (
    <div style={{ marginTop: 10 }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{ fontSize: 12, color: "var(--text-tertiary)", background: "none", border: "none", cursor: "pointer", padding: "4px 2px" }}
      >
        {open ? "▾" : "▸"} Past changes ({closed.length})
      </button>
      {open && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 6 }}>
          {closed.map((ev) => {
            const panel = ev.panel ?? "";
            const label = ev.panel ? `${panelLabel(ev.panel)} · ${metricLabel(ev.metric_id)}` : panelLabel(panel) || metricLabel(ev.metric_id);
            return (
              <div
                key={ev.id}
                style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "var(--panel)", borderRadius: 10, padding: "10px 14px", fontSize: 12 }}
              >
                <div
                  onClick={() => onOpenPanel(panel, ev.window.flight_ids)}
                  style={{ cursor: "pointer", color: "var(--text-secondary)" }}
                >
                  <span style={{ fontWeight: 600 }}>{label}</span>{" "}
                  <span style={{ color: "var(--text-tertiary)" }}>
                    {ev.direction} · detected {ev.detected_at.slice(0, 10)}, cleared {ev.cleared_at!.slice(0, 10)}
                    {ev.shift_z != null ? ` (shift_z ${ev.shift_z.toFixed(2)})` : ""}
                  </span>
                </div>
                <button
                  onClick={() => onDelete(ev.id)}
                  disabled={busyId === ev.id}
                  title="Delete this event"
                  style={{ fontSize: 11, color: "var(--text-tertiary)", background: "none", border: "1px solid var(--border)", borderRadius: 6, padding: "3px 8px", cursor: "pointer" }}
                >
                  delete
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
