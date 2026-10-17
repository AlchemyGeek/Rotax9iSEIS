import { useState } from "react";
import type { CasEvent, EcuClassification, EcuRunRecord } from "../types/contract";
import { ECU_CLASS_LABEL, casEventRowText } from "../lib/casEvent";

const CLASS_ORDER: EcuClassification[] = ["GROUND_START", "LANE_CHECK", "GROUND", "IN_FLIGHT", "GROUND_SHUTDOWN"];

function clock(utc: string | null): string {
  return utc ? utc.slice(11, 19) : "—";
}

// Spec 03 §5.4 (v0.14): a CAS event's expanded view — what was going on
// when it fired, and every ENGINE ECU run on this flight by class, so the
// ground-context runs (start, lane check, shutdown) stay visible here and
// nowhere else.
export function CasEventDetails({ events, ecuRuns, defaultOpen = false }: { events: CasEvent[]; ecuRuns: EcuRunRecord[]; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  if (events.length === 0 && ecuRuns.length === 0) return null;
  const byClass = CLASS_ORDER.map((c) => ({ cls: c, runs: ecuRuns.filter((r) => r.classification === c) })).filter((g) => g.runs.length > 0);
  return (
    <div style={{ fontSize: 11, color: "var(--text-tertiary)", paddingLeft: 4 }}>
      <span onClick={() => setOpen((v) => !v)} style={{ cursor: "pointer" }} data-testid="cas-details-toggle">
        {open ? "▾ Hide alert context" : "▸ Alert context and this flight's ENGINE ECU runs"}
      </span>
      {open && (
        <div style={{ marginTop: 6, background: "var(--panel)", borderRadius: 8, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 8, color: "var(--text-secondary)" }}>
          {events.map((e) => (
            <div key={e.event_id} style={{ lineHeight: 1.5 }}>
              <div style={{ color: "var(--text-primary)" }}>{casEventRowText(e)}</div>
              <div className="mono">
                {clock(e.start_utc)}
                {e.context.ias_kt !== null && ` · IAS ${Math.round(e.context.ias_kt)} kt`}
                {e.context.oil_nan_frac !== null && e.context.oil_nan_frac > 0 && ` · oil pressure missing ${Math.round(e.context.oil_nan_frac * 100)}% of rows`}
                {e.context.co_alerts.length > 0 && ` · with ${e.context.co_alerts.join(", ")}`}
              </div>
            </div>
          ))}
          {byClass.length > 0 && (
            <div>
              <div style={{ fontWeight: 600, color: "var(--text-tertiary)", marginBottom: 3 }}>ENGINE ECU runs this flight</div>
              {byClass.map(({ cls, runs }) => (
                <div key={cls} className="mono" style={{ lineHeight: 1.5 }}>
                  {ECU_CLASS_LABEL[cls]} ({runs.length}): {runs.map((r) => `${clock(r.start_utc)} ${Math.round(r.duration_s)} s`).join(", ")}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
