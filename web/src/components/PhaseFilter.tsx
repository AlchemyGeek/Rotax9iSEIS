import { useState } from "react";
import { PHASE_ORDER, phaseColor, phaseLabel } from "../lib/phases";

interface Props {
  // null = every phase included (the default, and the canonical "all"
  // state persisted to AppSettings.flight_chart.phase_filter) — never
  // represented as "all PHASE_ORDER entries explicitly selected," so a
  // newly-added phase in a future PHASE_ORDER change is included by
  // default rather than silently excluded from an old saved selection.
  selected: string[] | null;
  onChange: (next: string[] | null) => void;
}

// Insights panel's phase filter (not the chart's — Spec 07's picker is a
// separate, channel-scoped concept). Lives next to the "Insights (N)"
// header, not the Timeline, since it only ever affects which insights
// render in the list below it.
export function PhaseFilter({ selected, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const allSelected = selected === null;
  const activeCount = allSelected ? PHASE_ORDER.length : selected.length;

  function toggle(phase: string) {
    const current = selected ?? [...PHASE_ORDER];
    const next = current.includes(phase) ? current.filter((p) => p !== phase) : [...current, phase];
    onChange(next.length === PHASE_ORDER.length ? null : next);
  }

  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        title="filter the Insights list by flight phase"
        style={{
          display: "flex", alignItems: "center", gap: 5, padding: "3px 9px", borderRadius: 6,
          background: allSelected ? "transparent" : "var(--panel-control)",
          border: `1px solid ${allSelected ? "var(--border)" : "var(--accent)"}`,
          color: allSelected ? "var(--text-secondary)" : "var(--text-primary)",
          fontSize: 11, cursor: "pointer",
        }}
      >
        Phases{!allSelected && ` (${activeCount})`}
      </button>

      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 20 }} />
          <div
            style={{
              position: "absolute", top: "calc(100% + 6px)", right: 0, zIndex: 21,
              width: 190, background: "var(--panel-control)", border: "1px solid var(--border)",
              borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,0.4)", padding: 8,
            }}
          >
            <button
              onClick={() => onChange(null)}
              disabled={allSelected}
              style={{
                width: "100%", textAlign: "left", padding: "5px 8px", borderRadius: 6, marginBottom: 4,
                background: "transparent", border: "none", color: allSelected ? "var(--text-tertiary)" : "var(--accent)",
                fontSize: 11, fontWeight: 600, cursor: allSelected ? "default" : "pointer",
              }}
            >
              All phases
            </button>
            {PHASE_ORDER.map((phase) => {
              const checked = allSelected || (selected?.includes(phase) ?? false);
              return (
                <label
                  key={phase}
                  style={{ display: "flex", alignItems: "center", gap: 7, padding: "4px 8px", borderRadius: 6, cursor: "pointer", fontSize: 12 }}
                >
                  <input type="checkbox" checked={checked} onChange={() => toggle(phase)} style={{ margin: 0 }} />
                  <span style={{ width: 7, height: 7, borderRadius: "50%", background: phaseColor(phase), flexShrink: 0 }} />
                  <span style={{ color: "var(--text-primary)" }}>{phaseLabel(phase)}</span>
                </label>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
